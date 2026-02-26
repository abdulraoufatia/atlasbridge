"""Integration tests for the Settings page + /runtime/capabilities endpoint."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from starlette.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    """Create a test client with a minimal DB and trace file."""
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


class TestSettingsHTMLPage:
    """GET /settings returns a Core Settings page."""

    def test_settings_returns_200(self, client):
        resp = client.get("/settings")
        assert resp.status_code == 200

    def test_settings_contains_runtime_section(self, client):
        resp = client.get("/settings")
        assert "Runtime" in resp.text
        assert "Edition" in resp.text
        assert "Version" in resp.text
        assert "Python" in resp.text
        assert "Platform" in resp.text

    def test_settings_contains_config_paths(self, client):
        resp = client.get("/settings")
        assert "Config Paths" in resp.text
        assert "Config directory" in resp.text
        assert "Config file" in resp.text
        assert "Database" in resp.text
        assert "Audit log" in resp.text
        assert "Trace file" in resp.text

    def test_settings_contains_dashboard_binding(self, client):
        resp = client.get("/settings")
        assert "Dashboard Binding" in resp.text
        assert "127.0.0.1" in resp.text
        assert "8787" in resp.text
        assert "Loopback only" in resp.text

    def test_settings_contains_diagnostics(self, client):
        resp = client.get("/settings")
        assert "Diagnostics" in resp.text
        assert "Python version" in resp.text

    def test_settings_no_enterprise_strings(self, client):
        """Core settings must NOT contain enterprise/org/RBAC language."""
        resp = client.get("/settings")
        text = resp.text
        for forbidden in ("RBAC", "Organization", "Tenant", "GBAC"):
            assert forbidden not in text, f"Found forbidden string {forbidden!r} in settings page"

    def test_settings_contains_capabilities_section(self, client):
        """Settings page should show Capabilities section."""
        resp = client.get("/settings")
        assert "Capabilities" in resp.text

    def test_settings_contains_authority_mode(self, client):
        """Settings page should show Authority Mode."""
        resp = client.get("/settings")
        assert "Authority Mode" in resp.text


class TestSettingsJSONAPI:
    """GET /api/settings returns structured JSON."""

    def test_api_settings_returns_200(self, client):
        resp = client.get("/api/settings")
        assert resp.status_code == 200

    def test_api_settings_has_runtime(self, client):
        data = client.get("/api/settings").json()
        assert "runtime" in data
        runtime = data["runtime"]
        assert "edition" in runtime
        assert "authority_mode" in runtime
        assert "version" in runtime
        assert "python_version" in runtime
        assert "platform" in runtime

    def test_api_settings_has_config_paths(self, client):
        data = client.get("/api/settings").json()
        assert "config_paths" in data
        paths = data["config_paths"]
        assert "config_dir" in paths
        assert "config_file" in paths
        assert "db_path" in paths
        assert "audit_log" in paths
        assert "trace_file" in paths

    def test_api_settings_has_dashboard(self, client):
        data = client.get("/api/settings").json()
        assert "dashboard" in data
        dashboard = data["dashboard"]
        assert dashboard["host"] == "127.0.0.1"
        assert dashboard["port"] == 8787
        assert dashboard["loopback_only"] is True

    def test_api_settings_has_diagnostics(self, client):
        data = client.get("/api/settings").json()
        assert "diagnostics" in data
        assert isinstance(data["diagnostics"], list)
        assert len(data["diagnostics"]) > 0
        for check in data["diagnostics"]:
            assert "name" in check
            assert "status" in check
            assert "detail" in check

    def test_api_settings_edition_is_core(self, client):
        """Default edition is core."""
        data = client.get("/api/settings").json()
        assert data["runtime"]["edition"] == "core"

    def test_api_settings_has_capabilities(self, client):
        """All editions include capabilities."""
        data = client.get("/api/settings").json()
        assert "capabilities" in data
        caps = data["capabilities"]
        assert isinstance(caps, dict)
        assert len(caps) > 0
        # Verify structure
        for _name, info in caps.items():
            assert "allowed" in info
            assert "capability_class" in info


class TestRuntimeCapabilities:
    """GET /runtime/capabilities returns edition + capability summary."""

    def test_returns_200(self, client):
        resp = client.get("/runtime/capabilities")
        assert resp.status_code == 200

    def test_has_required_fields(self, client):
        data = client.get("/runtime/capabilities").json()
        assert "edition" in data
        assert "authority_mode" in data
        assert "enabled_capabilities" in data
        assert "enabled_capabilities_hash" in data
        assert "registry_version" in data

    def test_default_edition_is_core(self, client):
        data = client.get("/runtime/capabilities").json()
        assert data["edition"] == "core"
        assert data["authority_mode"] == "readonly"

    def test_enabled_capabilities_are_sorted(self, client):
        data = client.get("/runtime/capabilities").json()
        caps = data["enabled_capabilities"]
        assert caps == sorted(caps)

    def test_core_only_has_tooling(self, client):
        """CORE edition should only enable TOOLING capabilities."""
        data = client.get("/runtime/capabilities").json()
        for cap_id in data["enabled_capabilities"]:
            assert cap_id.startswith("tooling."), f"Non-tooling cap enabled in CORE: {cap_id}"

    def test_hash_is_sha256(self, client):
        data = client.get("/runtime/capabilities").json()
        h = data["enabled_capabilities_hash"]
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex

    def test_registry_version(self, client):
        data = client.get("/runtime/capabilities").json()
        assert data["registry_version"] == "1.0.0"


class TestEditionScopedSettings:
    """Settings page includes edition-specific data."""

    @pytest.fixture
    def core_client(self, tmp_path, monkeypatch):
        """Create a test client with CORE edition."""
        import sqlite3

        monkeypatch.setenv("ATLASBRIDGE_EDITION", "core")

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

    def test_core_settings_include_capabilities(self, core_client):
        """Core edition settings include capabilities."""
        data = core_client.get("/api/settings").json()
        assert "capabilities" in data
        assert "tooling.decision_trace_v2" in data["capabilities"]

    def test_core_settings_html_shows_capabilities(self, core_client):
        """Core edition settings page shows Capabilities section."""
        resp = core_client.get("/settings")
        assert resp.status_code == 200
        assert "Capabilities" in resp.text

    def test_core_edition_in_runtime(self, core_client):
        """Core edition reports correctly in runtime section."""
        data = core_client.get("/api/settings").json()
        assert data["runtime"]["edition"] == "core"

    def test_enterprise_settings_returns_404_on_core(self, core_client):
        """Enterprise settings route returns 404 on core edition."""
        resp = core_client.get("/enterprise/settings")
        assert resp.status_code == 404

    def test_enterprise_settings_404_is_json(self, core_client):
        """Enterprise settings 404 should be JSON with capability info."""
        resp = core_client.get("/enterprise/settings")
        assert resp.status_code == 404
        data = resp.json()
        assert "error" in data
        assert "authority.enterprise_settings" in data["error"]
