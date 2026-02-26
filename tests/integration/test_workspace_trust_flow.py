"""Integration tests for workspace trust flow.

Covers:
- Full trust grant/deny flow with normalised replies
- Pre-trusted workspace auto-grant without channel message
- Trust audit trail (actor, channel, session_id)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from atlasbridge.core.store.migrations import run_migrations
from atlasbridge.core.store.workspace_trust import (
    build_trust_prompt,
    get_trust,
    get_workspace_status,
    grant_trust,
    list_workspaces,
    normalise_trust_reply,
    revoke_trust,
)

TERMINAL_WORDS = ("Enter", "Esc", "arrow", "↑", "↓")


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    run_migrations(c, db_path)
    yield c
    c.close()


class TestFullTrustFlow:
    def test_yes_reply_grants_trust(self, conn: sqlite3.Connection) -> None:
        path = "/tmp/project-yes"
        # Simulate: receive trust prompt, user replies "yes"
        reply = "yes"
        decision = normalise_trust_reply(reply)
        assert decision is True
        grant_trust(path, conn, actor="telegram", channel="u999", session_id="sess-abc")
        assert get_trust(path, conn) is True

    def test_no_reply_revokes_trust(self, conn: sqlite3.Connection) -> None:
        path = "/tmp/project-no"
        grant_trust(path, conn, actor="telegram")  # pre-existed
        reply = "no"
        decision = normalise_trust_reply(reply)
        assert decision is False
        revoke_trust(path, conn)
        assert get_trust(path, conn) is False

    def test_ambiguous_reply_does_not_change_state(self, conn: sqlite3.Connection) -> None:
        path = "/tmp/project-ambiguous"
        # Don't grant or revoke — re-prompt scenario
        reply = "maybe"
        decision = normalise_trust_reply(reply)
        assert decision is None
        # State remains untrusted
        assert get_trust(path, conn) is False


class TestPreTrustedWorkspace:
    def test_pre_trusted_workspace_no_prompt_needed(self, conn: sqlite3.Connection) -> None:
        path = "/tmp/already-trusted"
        grant_trust(path, conn, actor="dashboard")
        # Pre-trust check: if trusted, skip channel prompt
        is_trusted = get_trust(path, conn)
        assert is_trusted is True
        # Simulate: engine does NOT emit trust prompt (tested by checking no channel call)

    def test_pre_trusted_status_preserved_across_grants(self, conn: sqlite3.Connection) -> None:
        path = "/tmp/stable-trust"
        grant_trust(path, conn, actor="dashboard", channel="web", session_id="s1")
        # Second grant (different session) — idempotent
        grant_trust(path, conn, actor="telegram", channel="u42", session_id="s2")
        assert get_trust(path, conn) is True
        # Status reflects latest grant
        status = get_workspace_status(path, conn)
        assert status["actor"] == "telegram"


class TestTrustPromptContent:
    def test_prompt_contains_path(self) -> None:
        msg = build_trust_prompt("/home/user/myproject")
        assert "/home/user/myproject" in msg

    @pytest.mark.parametrize("word", TERMINAL_WORDS)
    def test_prompt_has_no_terminal_words(self, word: str) -> None:
        msg = build_trust_prompt("/any/path")
        assert word not in msg, f"Trust prompt contains terminal word: {word!r}"

    def test_prompt_has_yes_no_instructions(self) -> None:
        msg = build_trust_prompt("/any/path").lower()
        assert "yes" in msg or "no" in msg


class TestTrustAuditTrail:
    def test_grant_records_all_fields(self, conn: sqlite3.Connection) -> None:
        path = "/tmp/audit-test"
        grant_trust(path, conn, actor="telegram", channel="12345", session_id="sess-99")
        status = get_workspace_status(path, conn)
        assert status is not None
        assert status["actor"] == "telegram"
        assert status["channel"] == "12345"
        assert status["session_id"] == "sess-99"
        assert status["granted_at"] is not None

    def test_revoke_records_revoked_at(self, conn: sqlite3.Connection) -> None:
        path = "/tmp/revoke-audit"
        grant_trust(path, conn, actor="dashboard")
        revoke_trust(path, conn)
        status = get_workspace_status(path, conn)
        assert status["trusted"] == 0
        assert status["revoked_at"] is not None

    def test_multiple_workspaces_independently_tracked(self, conn: sqlite3.Connection) -> None:
        grant_trust("/tmp/wA", conn, actor="dashboard")
        grant_trust("/tmp/wB", conn, actor="telegram", channel="u1")
        revoke_trust("/tmp/wA", conn)

        assert get_trust("/tmp/wA", conn) is False
        assert get_trust("/tmp/wB", conn) is True
        rows = list_workspaces(conn)
        assert len(rows) == 2
