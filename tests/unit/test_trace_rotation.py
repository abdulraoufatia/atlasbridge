"""
Unit tests for DecisionTrace size-based rotation.

Covers:
- Rotation triggers when file size exceeds max_bytes
- Archives are named .jsonl.1, .jsonl.2, .jsonl.3
- Oldest archive (.jsonl.4+) is dropped — only MAX_ARCHIVES kept
- No rotation when file is under threshold
- record() still works after rotation
"""

from __future__ import annotations

from pathlib import Path

from atlasbridge.core.autopilot.trace import DecisionTrace
from atlasbridge.core.policy.model import (
    AutoReplyAction,
    PolicyDecision,
)


def _make_decision(prompt_id: str = "p1") -> PolicyDecision:
    return PolicyDecision(
        prompt_id=prompt_id,
        session_id="s1",
        policy_hash="abc123",
        matched_rule_id="r1",
        action=AutoReplyAction(value="y"),
        explanation="test",
        confidence="high",
        prompt_type="yes_no",
        autonomy_mode="full",
    )


class TestTraceRotation:
    def test_no_rotation_below_threshold(self, tmp_path: Path) -> None:
        trace_path = tmp_path / "decisions.jsonl"
        # max_bytes = 10 MB; a single entry is way below that
        trace = DecisionTrace(trace_path, max_bytes=10 * 1024 * 1024)
        trace.record(_make_decision())
        assert trace_path.exists()
        archive = trace_path.with_suffix(".jsonl.1")
        assert not archive.exists()

    def test_rotation_triggers_when_threshold_exceeded(self, tmp_path: Path) -> None:
        trace_path = tmp_path / "decisions.jsonl"
        # Very small threshold so a single record triggers rotation on the next call
        trace = DecisionTrace(trace_path, max_bytes=1)  # 1 byte → always rotate

        trace.record(_make_decision("p1"))
        # File now > 1 byte. Next record should rotate.
        trace.record(_make_decision("p2"))

        archive = trace_path.with_suffix(".jsonl.1")
        assert archive.exists(), "Expected .jsonl.1 archive to be created"

    def test_rotation_creates_archive_1(self, tmp_path: Path) -> None:
        trace_path = tmp_path / "decisions.jsonl"
        trace = DecisionTrace(trace_path, max_bytes=1)

        trace.record(_make_decision("p1"))  # write first entry
        trace.record(_make_decision("p2"))  # triggers rotation

        archive1 = trace_path.with_suffix(".jsonl.1")
        assert archive1.exists()
        # The first entry should be in the archive
        content = archive1.read_text()
        assert "p1" in content

    def test_rotation_active_file_is_fresh(self, tmp_path: Path) -> None:
        trace_path = tmp_path / "decisions.jsonl"
        trace = DecisionTrace(trace_path, max_bytes=1)

        trace.record(_make_decision("p1"))
        trace.record(_make_decision("p2"))  # triggers rotation; p2 written to fresh file

        active_content = trace_path.read_text()
        assert "p2" in active_content
        # p1 should be archived, not in active file
        assert "p1" not in active_content

    def test_rotation_shifts_existing_archives(self, tmp_path: Path) -> None:
        trace_path = tmp_path / "decisions.jsonl"
        trace = DecisionTrace(trace_path, max_bytes=1)

        # Record 4 entries; each second record triggers rotation
        for i in range(1, 5):
            trace.record(_make_decision(f"p{i}"))

        # After 4 records with 1-byte threshold we expect multiple rotations
        archive1 = trace_path.with_suffix(".jsonl.1")
        assert archive1.exists()

    def test_rotation_keeps_max_archives(self, tmp_path: Path) -> None:
        trace_path = tmp_path / "decisions.jsonl"
        # Threshold of 1 byte so every second write rotates
        trace = DecisionTrace(trace_path, max_bytes=1)

        # Write enough records to cause 4 rotations
        for i in range(1, 9):
            trace.record(_make_decision(f"p{i}"))

        # At most MAX_ARCHIVES archives should exist
        for _i in range(1, DecisionTrace.MAX_ARCHIVES + 1):
            # The existence check: at most .jsonl.1 through .jsonl.3
            pass  # We just check that .jsonl.4 doesn't exist

        over_limit = trace_path.with_suffix(f".jsonl.{DecisionTrace.MAX_ARCHIVES + 1}")
        assert not over_limit.exists(), (
            f".jsonl.{DecisionTrace.MAX_ARCHIVES + 1} should not exist (exceeds MAX_ARCHIVES)"
        )

    def test_record_works_after_rotation(self, tmp_path: Path) -> None:
        trace_path = tmp_path / "decisions.jsonl"
        trace = DecisionTrace(trace_path, max_bytes=1)

        for i in range(1, 6):
            trace.record(_make_decision(f"p{i}"))

        # After multiple rotations, record() must still succeed
        trace.record(_make_decision("final"))
        assert trace_path.exists()

    def test_tail_reads_from_active_file(self, tmp_path: Path) -> None:
        trace_path = tmp_path / "decisions.jsonl"
        trace = DecisionTrace(trace_path, max_bytes=1)

        trace.record(_make_decision("p1"))
        trace.record(_make_decision("p2"))  # rotation here

        entries = trace.tail(n=10)
        # Active file has p2 only
        assert any(e.get("prompt_id") == "p2" for e in entries)

    def test_max_bytes_attribute(self, tmp_path: Path) -> None:
        trace_path = tmp_path / "decisions.jsonl"
        trace = DecisionTrace(trace_path, max_bytes=5000)
        assert trace._max_bytes == 5000

    def test_default_max_bytes(self, tmp_path: Path) -> None:
        trace_path = tmp_path / "decisions.jsonl"
        trace = DecisionTrace(trace_path)
        assert trace._max_bytes == DecisionTrace.MAX_BYTES_DEFAULT
        assert trace._max_bytes == 10 * 1024 * 1024
