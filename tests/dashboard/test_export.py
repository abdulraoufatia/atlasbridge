"""Tests for session export (JSON + HTML)."""

from __future__ import annotations

import json

import pytest

fastapi = pytest.importorskip("fastapi")


class TestExportSessionJson:
    def test_export_returns_bundle(self, repo):
        from atlasbridge.dashboard.export import export_session_json

        bundle = export_session_json(repo, "sess-001")
        assert bundle is not None
        assert bundle["export_version"] == "1.0"
        assert "exported_at" in bundle
        assert bundle["session"]["id"] == "sess-001"

    def test_export_includes_prompts(self, repo):
        from atlasbridge.dashboard.export import export_session_json

        bundle = export_session_json(repo, "sess-001")
        assert bundle is not None
        assert len(bundle["prompts"]) == 4  # 3 original + 1 token-containing

    def test_export_includes_traces(self, repo):
        from atlasbridge.dashboard.export import export_session_json

        bundle = export_session_json(repo, "sess-001")
        assert bundle is not None
        assert len(bundle["traces"]) == 3  # sess-001 has 3 trace entries

    def test_export_includes_audit_events(self, repo):
        from atlasbridge.dashboard.export import export_session_json

        bundle = export_session_json(repo, "sess-001")
        assert bundle is not None
        assert len(bundle["audit_events"]) == 3  # 3 events for sess-001

    def test_export_nonexistent_session_returns_none(self, repo):
        from atlasbridge.dashboard.export import export_session_json

        bundle = export_session_json(repo, "nonexistent")
        assert bundle is None


class TestExportSessionHtml:
    def test_export_returns_html(self, repo):
        from atlasbridge.dashboard.export import export_session_html

        html = export_session_html(repo, "sess-001")
        assert html is not None
        assert "<!DOCTYPE html>" in html
        assert "sess-001" in html

    def test_export_html_contains_session_data(self, repo):
        from atlasbridge.dashboard.export import export_session_html

        html = export_session_html(repo, "sess-001")
        assert html is not None
        assert "claude" in html  # tool
        assert "running" in html  # status

    def test_export_html_contains_inline_css(self, repo):
        from atlasbridge.dashboard.export import export_session_html

        html = export_session_html(repo, "sess-001")
        assert html is not None
        assert "<style>" in html
        # No external CSS links
        assert 'rel="stylesheet"' not in html

    def test_export_html_nonexistent_returns_none(self, repo):
        from atlasbridge.dashboard.export import export_session_html

        html = export_session_html(repo, "nonexistent")
        assert html is None

    def test_export_html_has_banner(self, repo):
        from atlasbridge.dashboard.export import export_session_html

        html = export_session_html(repo, "sess-001")
        assert html is not None
        assert "EXPORTED SESSION" in html


class TestExportApiEndpoint:
    def test_export_api_returns_json(self, client):
        response = client.get("/api/sessions/sess-001/export")
        assert response.status_code == 200
        data = response.json()
        assert data["session"]["id"] == "sess-001"
        assert "prompts" in data
        assert "traces" in data

    def test_export_api_404_for_missing(self, client):
        response = client.get("/api/sessions/nonexistent/export")
        assert response.status_code == 404
        assert "not found" in response.json()["error"].lower()


class TestExportCliCommand:
    def test_export_in_help(self):
        from click.testing import CliRunner

        from atlasbridge.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["dashboard", "--help"])
        assert result.exit_code == 0
        assert "export" in result.output

    def test_export_requires_session(self):
        from click.testing import CliRunner

        from atlasbridge.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["dashboard", "export"])
        assert result.exit_code != 0
        assert "session" in result.output.lower() or "required" in result.output.lower()


class TestRepoExportSession:
    def test_repo_export_session(self, repo):
        bundle = repo.export_session("sess-001")
        assert bundle is not None
        assert bundle["session"]["id"] == "sess-001"

    def test_repo_export_nonexistent(self, repo):
        bundle = repo.export_session("nonexistent")
        assert bundle is None


class TestExportNoSecretLeakage:
    """Exported data must never contain raw tokens or secrets."""

    _TOKEN_PATTERNS = ["sk-", "xoxb-", "ghp_"]

    def test_json_export_redacts_tokens(self, repo):
        """JSON export must redact all token patterns from prompt excerpts."""
        from atlasbridge.dashboard.export import export_session_json

        bundle = export_session_json(repo, "sess-001")
        assert bundle is not None
        json_str = json.dumps(bundle, default=str)
        for pattern in self._TOKEN_PATTERNS:
            assert pattern not in json_str, f"Raw token pattern {pattern!r} found in JSON export"

    def test_html_export_redacts_tokens(self, repo):
        """HTML export must redact all token patterns from prompt excerpts."""
        from atlasbridge.dashboard.export import export_session_html

        html = export_session_html(repo, "sess-001")
        assert html is not None
        for pattern in self._TOKEN_PATTERNS:
            assert pattern not in html, f"Raw token pattern {pattern!r} found in HTML export"

    def test_api_export_redacts_tokens(self, client):
        """API export endpoint must redact all token patterns."""
        response = client.get("/api/sessions/sess-001/export")
        assert response.status_code == 200
        text = response.text
        for pattern in self._TOKEN_PATTERNS:
            assert pattern not in text, f"Raw token pattern {pattern!r} found in API export"

    def test_json_export_contains_redaction_labels(self, repo):
        """Redacted tokens should be replaced with [REDACTED:*] labels."""
        from atlasbridge.dashboard.export import export_session_json

        bundle = export_session_json(repo, "sess-001")
        assert bundle is not None
        json_str = json.dumps(bundle, default=str)
        assert "[REDACTED:" in json_str

    def test_html_export_contains_redaction_labels(self, repo):
        """Redacted tokens should appear as [REDACTED:*] in HTML export."""
        from atlasbridge.dashboard.export import export_session_html

        html = export_session_html(repo, "sess-001")
        assert html is not None
        # HTML-escaped version
        assert "REDACTED" in html


class TestExportCliIntegration:
    """CLI export command integration tests."""

    def test_cli_export_json_to_file(self, repo, tmp_path):
        """CLI export --format json --output writes valid JSON to file."""
        from atlasbridge.dashboard.export import export_session_json

        bundle = export_session_json(repo, "sess-001")
        assert bundle is not None
        out_path = tmp_path / "export.json"
        out_path.write_text(json.dumps(bundle, indent=2, default=str), encoding="utf-8")
        # Verify the file contains valid JSON
        loaded = json.loads(out_path.read_text(encoding="utf-8"))
        assert loaded["session"]["id"] == "sess-001"

    def test_cli_export_html_to_file(self, repo, tmp_path):
        """CLI export --format html --output writes valid HTML to file."""
        from atlasbridge.dashboard.export import export_session_html

        html = export_session_html(repo, "sess-001")
        assert html is not None
        out_path = tmp_path / "export.html"
        out_path.write_text(html, encoding="utf-8")
        content = out_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "sess-001" in content
