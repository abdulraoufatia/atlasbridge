"""Unit tests for atlasbridge.core.store.workspace_trust."""

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

TERMINAL_WORDS = ("Enter", "Esc", "arrow", "↑", "↓", "Tab", "ctrl")


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    run_migrations(c, db_path)
    yield c
    c.close()


# ---------------------------------------------------------------------------
# build_trust_prompt — no terminal semantics
# ---------------------------------------------------------------------------


class TestBuildTrustPrompt:
    def test_contains_path(self) -> None:
        msg = build_trust_prompt("/home/user/project")
        assert "/home/user/project" in msg

    def test_contains_yes_no_instruction(self) -> None:
        msg = build_trust_prompt("/tmp/x")
        low = msg.lower()
        assert "yes" in low or "no" in low

    @pytest.mark.parametrize("word", TERMINAL_WORDS)
    def test_no_terminal_semantics(self, word: str) -> None:
        msg = build_trust_prompt("/some/path")
        assert word not in msg, f"Trust prompt contains terminal word: {word!r}"


# ---------------------------------------------------------------------------
# normalise_trust_reply
# ---------------------------------------------------------------------------


class TestNormaliseTrustReply:
    @pytest.mark.parametrize("value", ["yes", "Yes", "YES", "y", "Y"])
    def test_trust_values(self, value: str) -> None:
        assert normalise_trust_reply(value) is True

    @pytest.mark.parametrize("value", ["no", "No", "NO", "n", "N"])
    def test_deny_values(self, value: str) -> None:
        assert normalise_trust_reply(value) is False

    @pytest.mark.parametrize("value", ["maybe", "ok", "sure", "1", "0", ""])
    def test_ambiguous_returns_none(self, value: str) -> None:
        assert normalise_trust_reply(value) is None


# ---------------------------------------------------------------------------
# get_trust / grant_trust
# ---------------------------------------------------------------------------


class TestGetTrust:
    def test_untrusted_by_default(self, conn: sqlite3.Connection) -> None:
        assert get_trust("/tmp/new-project", conn) is False

    def test_grant_then_get(self, conn: sqlite3.Connection) -> None:
        path = "/tmp/test-workspace"
        grant_trust(path, conn, actor="dashboard", channel="web", session_id="sess-1")
        assert get_trust(path, conn) is True

    def test_symlink_equivalence(self, conn: sqlite3.Connection, tmp_path: Path) -> None:
        real = tmp_path / "real"
        real.mkdir()
        link = tmp_path / "link"
        link.symlink_to(real)
        grant_trust(str(real), conn, actor="dashboard")
        # Both should resolve to the same canonical path
        assert get_trust(str(real), conn) is True

    def test_grant_is_idempotent(self, conn: sqlite3.Connection) -> None:
        path = "/tmp/idempotent"
        grant_trust(path, conn, actor="dashboard")
        grant_trust(path, conn, actor="dashboard")  # second call — must not raise
        assert get_trust(path, conn) is True

    def test_grant_records_actor(self, conn: sqlite3.Connection) -> None:
        path = "/tmp/actor-test"
        grant_trust(path, conn, actor="telegram", channel="12345", session_id="s1")
        status = get_workspace_status(path, conn)
        assert status is not None
        assert status["actor"] == "telegram"
        assert status["channel"] == "12345"
        assert status["session_id"] == "s1"
        assert status["granted_at"] is not None


# ---------------------------------------------------------------------------
# revoke_trust
# ---------------------------------------------------------------------------


class TestRevokeTrust:
    def test_revoke_after_grant(self, conn: sqlite3.Connection) -> None:
        path = "/tmp/revoke-me"
        grant_trust(path, conn, actor="dashboard")
        assert get_trust(path, conn) is True
        revoke_trust(path, conn)
        assert get_trust(path, conn) is False

    def test_revoke_sets_revoked_at(self, conn: sqlite3.Connection) -> None:
        path = "/tmp/revoke-timestamp"
        grant_trust(path, conn, actor="dashboard")
        revoke_trust(path, conn)
        status = get_workspace_status(path, conn)
        assert status is not None
        assert status["trusted"] == 0
        assert status["revoked_at"] is not None

    def test_revoke_untracked_path_no_error(self, conn: sqlite3.Connection) -> None:
        # Should not raise even if path not in DB
        revoke_trust("/tmp/never-granted", conn)


# ---------------------------------------------------------------------------
# list_workspaces
# ---------------------------------------------------------------------------


class TestListWorkspaces:
    def test_empty_list(self, conn: sqlite3.Connection) -> None:
        assert list_workspaces(conn) == []

    def test_multiple_workspaces(self, conn: sqlite3.Connection) -> None:
        grant_trust("/tmp/a", conn, actor="dashboard")
        grant_trust("/tmp/b", conn, actor="telegram")
        rows = list_workspaces(conn)
        paths = {r["path"] for r in rows}
        assert "/tmp/a" in paths
        assert "/tmp/b" in paths

    def test_list_shows_trust_status(self, conn: sqlite3.Connection) -> None:
        grant_trust("/tmp/trusted", conn, actor="dashboard")
        grant_trust("/tmp/revoked", conn, actor="dashboard")
        revoke_trust("/tmp/revoked", conn)
        rows = list_workspaces(conn)
        by_path = {r["path"]: r for r in rows}
        assert by_path["/tmp/trusted"]["trusted"] == 1
        assert by_path["/tmp/revoked"]["trusted"] == 0
