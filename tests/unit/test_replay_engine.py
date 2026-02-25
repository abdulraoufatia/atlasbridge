"""
Tests for the GA Session Replay Engine.

Covers:
- SessionSnapshot creation and hashing
- Replay with same policy produces identical decisions
- Replay with different policy shows diffs
- Deterministic replay (same input → same output)
- ReplayReport serialization (text + JSON)
- Edge cases (empty session, no prompts)
"""

from __future__ import annotations

import json

from atlasbridge.core.policy.model import (
    AutoReplyAction,
    ConfidenceLevel,
    MatchCriteria,
    Policy,
    PolicyDefaults,
    PolicyRule,
    RequireHumanAction,
)
from atlasbridge.core.replay import (
    PromptSnapshot,
    ReplayEngine,
    SessionSnapshot,
)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _make_snapshot(
    prompts: tuple[PromptSnapshot, ...] | None = None,
) -> SessionSnapshot:
    if prompts is None:
        prompts = (
            PromptSnapshot(
                prompt_id="p-001",
                prompt_type="yes_no",
                confidence="high",
                excerpt="Continue? [y/n]",
                status="resolved",
                response_normalized="y",
                channel_identity="user@telegram",
                created_at="2026-01-01T00:00:00Z",
            ),
            PromptSnapshot(
                prompt_id="p-002",
                prompt_type="free_text",
                confidence="medium",
                excerpt="Enter branch name:",
                status="resolved",
                response_normalized="main",
                channel_identity="user@telegram",
                created_at="2026-01-01T00:01:00Z",
            ),
            PromptSnapshot(
                prompt_id="p-003",
                prompt_type="confirm_enter",
                confidence="high",
                excerpt="Press Enter to continue",
                status="expired",
                response_normalized="",
                channel_identity="",
                created_at="2026-01-01T00:02:00Z",
            ),
        )
    return SessionSnapshot(
        session_id="sess-001",
        tool="claude_code",
        command=["claude", "--no-browser"],
        cwd="/home/user/project",
        label="test-session",
        status="completed",
        started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T00:10:00Z",
        prompts=prompts,
    )


def _make_policy_a() -> Policy:
    """Policy that auto-approves yes_no at high confidence."""
    return Policy(
        policy_version="0",
        name="policy-a",
        rules=[
            PolicyRule(
                id="auto-yes",
                description="Auto yes/no at high confidence",
                match=MatchCriteria(
                    prompt_type=["yes_no"],
                    min_confidence=ConfidenceLevel.HIGH,
                ),
                action=AutoReplyAction(value="y"),
            ),
            PolicyRule(
                id="escalate-free",
                description="Escalate free text",
                match=MatchCriteria(prompt_type=["free_text"]),
                action=RequireHumanAction(message="Free text needs review"),
            ),
        ],
        defaults=PolicyDefaults(no_match="require_human"),
    )


def _make_policy_b() -> Policy:
    """Policy that denies yes_no (stricter)."""
    return Policy(
        policy_version="0",
        name="policy-b",
        rules=[
            PolicyRule(
                id="deny-yes-no",
                description="Deny all yes/no",
                match=MatchCriteria(prompt_type=["yes_no"]),
                action=AutoReplyAction(value="n"),
            ),
        ],
        defaults=PolicyDefaults(no_match="deny"),
    )


class FakeDB:
    """Fake database for testing load_session()."""

    def __init__(self, session: dict, prompts: list[dict]) -> None:
        self._session = session
        self._prompts = prompts

    def get_session(self, session_id: str) -> dict | None:
        if self._session.get("id") == session_id:
            return self._session
        return None

    def list_prompts_for_session(self, session_id: str) -> list[dict]:
        return [p for p in self._prompts if p.get("session_id") == session_id]


class DictRow(dict):
    """Dict that supports both dict-key and attribute access (like sqlite3.Row)."""

    def __getitem__(self, key):
        return super().__getitem__(key)


# ---------------------------------------------------------------------------
# SessionSnapshot tests
# ---------------------------------------------------------------------------


class TestSessionSnapshot:
    def test_frozen(self):
        snap = _make_snapshot()
        import pytest

        with pytest.raises(AttributeError):
            snap.session_id = "new"  # type: ignore[misc]

    def test_prompt_count(self):
        snap = _make_snapshot()
        assert snap.prompt_count == 3

    def test_content_hash_deterministic(self):
        snap = _make_snapshot()
        assert snap.content_hash() == snap.content_hash()

    def test_content_hash_changes_with_content(self):
        snap1 = _make_snapshot()
        snap2 = _make_snapshot(
            prompts=(
                PromptSnapshot(
                    prompt_id="p-999",
                    prompt_type="yes_no",
                    confidence="low",
                    excerpt="Different",
                    status="expired",
                    response_normalized="",
                    channel_identity="",
                    created_at="2026-01-01T00:00:00Z",
                ),
            )
        )
        assert snap1.content_hash() != snap2.content_hash()

    def test_empty_session(self):
        snap = _make_snapshot(prompts=())
        assert snap.prompt_count == 0
        assert snap.content_hash()  # Should not crash


# ---------------------------------------------------------------------------
# ReplayEngine.replay() tests
# ---------------------------------------------------------------------------


class TestReplay:
    def test_replay_produces_decisions(self):
        snap = _make_snapshot()
        engine = ReplayEngine(db=None)
        report = engine.replay(snap, _make_policy_a())
        assert len(report.decisions) == 3

    def test_replay_first_prompt_auto_approved(self):
        snap = _make_snapshot()
        engine = ReplayEngine(db=None)
        report = engine.replay(snap, _make_policy_a())
        d = report.decisions[0]
        assert d.matched_rule_id == "auto-yes"
        assert d.action_type == "auto_reply"
        assert d.action_value == "y"

    def test_replay_second_prompt_escalated(self):
        snap = _make_snapshot()
        engine = ReplayEngine(db=None)
        report = engine.replay(snap, _make_policy_a())
        d = report.decisions[1]
        assert d.matched_rule_id == "escalate-free"
        assert d.action_type == "require_human"

    def test_replay_third_prompt_default(self):
        snap = _make_snapshot()
        engine = ReplayEngine(db=None)
        report = engine.replay(snap, _make_policy_a())
        d = report.decisions[2]
        assert d.matched_rule_id is None  # no rule matched confirm_enter

    def test_replay_includes_risk(self):
        snap = _make_snapshot()
        engine = ReplayEngine(db=None)
        report = engine.replay(snap, _make_policy_a(), branch="main")
        for d in report.decisions:
            assert d.risk_score is not None

    def test_replay_default_policy(self):
        """Replay with no policy uses default (all require_human)."""
        snap = _make_snapshot()
        engine = ReplayEngine(db=None)
        report = engine.replay(snap)
        for d in report.decisions:
            assert d.action_type == "require_human"

    def test_replay_determinism(self):
        snap = _make_snapshot()
        engine = ReplayEngine(db=None)
        policy = _make_policy_a()
        reports = [engine.replay(snap, policy) for _ in range(50)]
        first = reports[0]
        for r in reports[1:]:
            assert len(r.decisions) == len(first.decisions)
            for d1, d2 in zip(first.decisions, r.decisions, strict=True):
                assert d1.matched_rule_id == d2.matched_rule_id
                assert d1.action_type == d2.action_type
                assert d1.risk_score == d2.risk_score


# ---------------------------------------------------------------------------
# ReplayEngine.replay_diff() tests
# ---------------------------------------------------------------------------


class TestReplayDiff:
    def test_same_policy_no_diffs(self):
        snap = _make_snapshot()
        engine = ReplayEngine(db=None)
        policy = _make_policy_a()
        report = engine.replay_diff(snap, policy, policy)
        assert report.is_identical
        assert report.diff_count == 0

    def test_different_policy_shows_diffs(self):
        snap = _make_snapshot()
        engine = ReplayEngine(db=None)
        report = engine.replay_diff(snap, _make_policy_a(), _make_policy_b())
        assert not report.is_identical
        assert report.diff_count > 0

    def test_diff_identifies_changed_fields(self):
        snap = _make_snapshot()
        engine = ReplayEngine(db=None)
        report = engine.replay_diff(snap, _make_policy_a(), _make_policy_b())
        # First prompt: policy-a → auto_reply "y", policy-b → auto_reply "n"
        # Should have an action_value diff
        value_diffs = [d for d in report.diffs if d.field == "action_value"]
        assert len(value_diffs) > 0

    def test_diff_report_name(self):
        snap = _make_snapshot()
        engine = ReplayEngine(db=None)
        report = engine.replay_diff(snap, _make_policy_a(), _make_policy_b())
        assert "policy-a" in report.policy_name
        assert "policy-b" in report.policy_name


# ---------------------------------------------------------------------------
# ReplayEngine.load_session() tests
# ---------------------------------------------------------------------------


class TestLoadSession:
    def test_load_session(self):
        session = DictRow(
            {
                "id": "sess-001",
                "tool": "claude_code",
                "command": '["claude", "--no-browser"]',
                "cwd": "/home/user",
                "label": "test",
                "status": "completed",
                "started_at": "2026-01-01T00:00:00Z",
                "ended_at": "2026-01-01T00:10:00Z",
            }
        )
        prompts = [
            DictRow(
                {
                    "id": "p-001",
                    "session_id": "sess-001",
                    "prompt_type": "yes_no",
                    "confidence": "high",
                    "excerpt": "Continue? [y/n]",
                    "status": "resolved",
                    "response_normalized": "y",
                    "channel_identity": "user@telegram",
                    "created_at": "2026-01-01T00:00:00Z",
                }
            ),
        ]
        db = FakeDB(session, prompts)
        engine = ReplayEngine(db)
        snap = engine.load_session("sess-001")
        assert snap.session_id == "sess-001"
        assert snap.prompt_count == 1
        assert snap.prompts[0].prompt_type == "yes_no"

    def test_load_session_not_found(self):
        import pytest

        db = FakeDB({"id": "other"}, [])
        engine = ReplayEngine(db)
        with pytest.raises(ValueError, match="not found"):
            engine.load_session("nonexistent")


# ---------------------------------------------------------------------------
# ReplayReport serialization tests
# ---------------------------------------------------------------------------


class TestReportSerialization:
    def test_to_text(self):
        snap = _make_snapshot()
        engine = ReplayEngine(db=None)
        report = engine.replay(snap, _make_policy_a())
        text = report.to_text()
        assert "SESSION REPLAY REPORT" in text
        assert "sess-001" in text
        assert "policy-a" in text

    def test_to_json(self):
        snap = _make_snapshot()
        engine = ReplayEngine(db=None)
        report = engine.replay(snap, _make_policy_a())
        j = report.to_json()
        parsed = json.loads(j)
        assert "session_id" in parsed
        assert "decisions" in parsed
        assert "is_identical" in parsed

    def test_to_dict_structure(self):
        snap = _make_snapshot()
        engine = ReplayEngine(db=None)
        report = engine.replay(snap, _make_policy_a())
        d = report.to_dict()
        assert d["prompt_count"] == 3
        assert isinstance(d["decisions"], list)
        assert isinstance(d["diffs"], list)

    def test_diff_report_text(self):
        snap = _make_snapshot()
        engine = ReplayEngine(db=None)
        report = engine.replay_diff(snap, _make_policy_a(), _make_policy_b())
        text = report.to_text()
        assert "DIFFERENCES:" in text
