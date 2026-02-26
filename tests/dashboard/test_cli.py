"""Tests for dashboard CLI commands."""

from __future__ import annotations

from click.testing import CliRunner


class TestDashboardHelp:
    def test_dashboard_help(self):
        from atlasbridge.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["dashboard", "--help"])
        assert result.exit_code == 0
        assert "start" in result.output
        assert "status" in result.output

    def test_dashboard_start_help(self):
        from atlasbridge.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["dashboard", "start", "--help"])
        assert result.exit_code == 0
        assert "--host" in result.output
        assert "--port" in result.output
        assert "--no-browser" in result.output


class TestHostValidation:
    def test_rejects_all_interfaces(self):
        from atlasbridge.dashboard.sanitize import is_loopback

        assert not is_loopback("0.0.0.0")

    def test_accepts_localhost(self):
        from atlasbridge.dashboard.sanitize import is_loopback

        assert is_loopback("localhost")

    def test_accepts_127_0_0_1(self):
        from atlasbridge.dashboard.sanitize import is_loopback

        assert is_loopback("127.0.0.1")

    def test_accepts_ipv6_loopback(self):
        from atlasbridge.dashboard.sanitize import is_loopback

        assert is_loopback("::1")

    def test_rejects_public_ip(self):
        from atlasbridge.dashboard.sanitize import is_loopback

        assert not is_loopback("192.168.1.1")


class TestRiskFlag:
    def test_rejects_non_loopback_without_risk_flag(self):
        """Non-loopback host without --i-understand-risk must exit with error."""
        from atlasbridge.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["dashboard", "start", "--host", "0.0.0.0"])
        assert result.exit_code != 0
        assert "--i-understand-risk" in result.output

    def test_allows_non_loopback_with_risk_flag(self):
        """Non-loopback host with --i-understand-risk should be allowed (legacy mode)."""
        import pytest

        pytest.importorskip("fastapi")
        from unittest.mock import patch

        from atlasbridge.cli.main import cli

        runner = CliRunner()
        with patch("atlasbridge.dashboard.app.start_server") as mock_start:
            result = runner.invoke(
                cli,
                ["dashboard", "start", "--legacy", "--host", "0.0.0.0", "--i-understand-risk"],
            )
            assert result.exit_code == 0
            mock_start.assert_called_once()
            call_kwargs = mock_start.call_args
            assert call_kwargs.kwargs.get("allow_non_loopback") is True

    def test_loopback_does_not_require_risk_flag(self):
        """Loopback address should work without --i-understand-risk (legacy mode)."""
        import pytest

        pytest.importorskip("fastapi")
        from unittest.mock import patch

        from atlasbridge.cli.main import cli

        runner = CliRunner()
        with patch("atlasbridge.dashboard.app.start_server") as mock_start:
            result = runner.invoke(cli, ["dashboard", "start", "--legacy", "--host", "127.0.0.1"])
            assert result.exit_code == 0
            mock_start.assert_called_once()

    def test_risk_flag_hidden_but_works(self):
        """--i-understand-risk should be hidden in help but functional."""
        from atlasbridge.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["dashboard", "start", "--help"])
        # Hidden flag should not appear in help text
        assert "--i-understand-risk" not in result.output


class TestMissingDependency:
    def test_start_rejects_non_loopback(self):
        """CLI should reject non-loopback host before even trying to import fastapi."""
        from atlasbridge.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["dashboard", "start", "--host", "0.0.0.0"])
        assert result.exit_code != 0
