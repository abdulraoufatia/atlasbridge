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


class TestMissingDependency:
    def test_start_rejects_non_loopback(self):
        """CLI should reject non-loopback host before even trying to import fastapi."""
        from atlasbridge.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["dashboard", "start", "--host", "0.0.0.0"])
        assert result.exit_code != 0
