"""Integration tests for dashboard edition gating, badges, and CLI --edition flag."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from starlette.testclient import TestClient


def _make_client(tmp_path, edition_env: str = "core"):
    """Create a test client with the given edition env."""
    import sqlite3

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, tool TEXT, command TEXT, "
        "cwd TEXT, status TEXT, pid INTEGER, started_at TEXT, ended_at TEXT, "
        "exit_code INTEGER, label TEXT, metadata TEXT)"
    )
    conn.execute(
        "CREATE TABLE prompts (id TEXT PRIMARY KEY, session_id TEXT, "
        "prompt_type TEXT, confidence TEXT, excerpt TEXT, status TEXT, "
        "nonce TEXT, nonce_used INTEGER, expires_at TEXT, created_at TEXT, "
        "resolved_at TEXT, response_normalized TEXT, channel_identity TEXT, "
        "channel_message_id TEXT, metadata TEXT)"
    )
    conn.execute(
        "CREATE TABLE audit_events (id TEXT PRIMARY KEY, event_type TEXT, "
        "session_id TEXT, prompt_id TEXT, payload TEXT, timestamp TEXT, "
        "prev_hash TEXT, hash TEXT)"
    )
    conn.commit()
    conn.close()

    trace_path = tmp_path / "decisions.jsonl"
    trace_path.write_text("")

    from atlasbridge.dashboard.app import create_app

    app = create_app(db_path=db_path, trace_path=trace_path)
    return TestClient(app)


@pytest.fixture
def core_client(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLASBRIDGE_EDITION", "core")
    return _make_client(tmp_path, "core")


@pytest.fixture
def enterprise_client(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLASBRIDGE_EDITION", "enterprise")
    return _make_client(tmp_path, "enterprise")


# ---------------------------------------------------------------------------
# Edition badges in banner
# ---------------------------------------------------------------------------


class TestEditionBadges:
    """Banner must show edition badge + invariant badges."""

    def test_core_shows_core_badge(self, core_client):
        resp = core_client.get("/")
        assert "badge-edition-core" in resp.text
        assert ">CORE<" in resp.text

    def test_core_shows_readonly_badge(self, core_client):
        resp = core_client.get("/")
        assert "READ-ONLY" in resp.text

    def test_core_shows_local_only_badge(self, core_client):
        resp = core_client.get("/")
        assert "LOCAL ONLY" in resp.text

    def test_enterprise_shows_enterprise_badge(self, enterprise_client):
        resp = enterprise_client.get("/")
        assert "badge-edition-enterprise" in resp.text
        assert ">ENTERPRISE<" in resp.text

    def test_enterprise_shows_readonly_badge(self, enterprise_client):
        resp = enterprise_client.get("/")
        assert "READ-ONLY" in resp.text

    def test_enterprise_shows_local_only_badge(self, enterprise_client):
        resp = enterprise_client.get("/")
        assert "LOCAL ONLY" in resp.text

    def test_badges_on_all_core_pages(self, core_client):
        """All pages must show edition + invariant badges."""
        for path in ["/", "/traces", "/integrity", "/settings"]:
            resp = core_client.get(path)
            assert "badge-edition" in resp.text, f"No edition badge on {path}"
            assert "READ-ONLY" in resp.text, f"No READ-ONLY badge on {path}"
            assert "LOCAL ONLY" in resp.text, f"No LOCAL ONLY badge on {path}"


# ---------------------------------------------------------------------------
# Conditional enterprise nav links
# ---------------------------------------------------------------------------


class TestConditionalNav:
    """Enterprise-only nav links must not appear in core edition."""

    def test_core_nav_excludes_enterprise_settings(self, core_client):
        resp = core_client.get("/")
        assert "/enterprise/settings" not in resp.text

    def test_enterprise_nav_includes_enterprise_settings(self, enterprise_client):
        resp = enterprise_client.get("/")
        assert "/enterprise/settings" in resp.text

    def test_core_nav_has_settings(self, core_client):
        """Core nav still includes the regular Settings link."""
        resp = core_client.get("/")
        assert '"/settings"' in resp.text or 'href="/settings"' in resp.text


# ---------------------------------------------------------------------------
# Core has zero enterprise language
# ---------------------------------------------------------------------------


class TestCoreNoEnterpriseCopy:
    """Core dashboard must not contain enterprise language."""

    FORBIDDEN = ("RBAC", "Organization", "Tenant", "GBAC")

    def test_home_no_enterprise_language(self, core_client):
        resp = core_client.get("/")
        for word in self.FORBIDDEN:
            assert word not in resp.text, f"Found {word!r} in core home page"

    def test_settings_no_enterprise_language(self, core_client):
        resp = core_client.get("/settings")
        for word in self.FORBIDDEN:
            assert word not in resp.text, f"Found {word!r} in core settings page"

    def test_traces_no_enterprise_language(self, core_client):
        resp = core_client.get("/traces")
        for word in self.FORBIDDEN:
            assert word not in resp.text, f"Found {word!r} in core traces page"


# ---------------------------------------------------------------------------
# Enterprise settings route gating
# ---------------------------------------------------------------------------


class TestEnterpriseRouteGating:
    """Enterprise routes must be gated by edition."""

    def test_enterprise_settings_404_on_core(self, core_client):
        """Enterprise settings returns 404 on core edition."""
        resp = core_client.get("/enterprise/settings")
        assert resp.status_code == 404

    def test_enterprise_settings_404_is_json(self, core_client):
        """404 response is JSON with capability error info."""
        resp = core_client.get("/enterprise/settings")
        data = resp.json()
        assert "error" in data


# ---------------------------------------------------------------------------
# Edition resolution (CLI flag)
# ---------------------------------------------------------------------------


class TestEditionResolutionCLI:
    """--edition flag sets the env var for create_app."""

    def test_dashboard_start_has_edition_option(self):
        """dashboard start command has --edition flag."""
        from atlasbridge.cli._dashboard import dashboard_start

        param_names = [p.name for p in dashboard_start.params]
        assert "edition" in param_names

    def test_edition_choices(self):
        """--edition accepts core and enterprise."""
        from atlasbridge.cli._dashboard import dashboard_start

        for p in dashboard_start.params:
            if p.name == "edition":
                assert set(p.type.choices) == {"core", "enterprise"}
                break
        else:
            pytest.fail("edition param not found")

    def test_edition_default_is_none(self):
        """--edition defaults to None (falls back to env or 'core')."""
        from atlasbridge.cli._dashboard import dashboard_start

        for p in dashboard_start.params:
            if p.name == "edition":
                assert p.default is None
                break
