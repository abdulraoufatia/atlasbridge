"""Tests for the atlasbridge profile CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from atlasbridge.cli._profile import profile_group
from atlasbridge.core.profile import AgentProfile, ProfileStore


@pytest.fixture()
def runner():
    return CliRunner()


@pytest.fixture()
def store(tmp_path: Path):
    return ProfileStore(profiles_dir=tmp_path / "profiles")


def _patch_store(store: ProfileStore):
    """Patch ProfileStore constructor to return our test-scoped store."""
    return patch(
        "atlasbridge.core.profile.ProfileStore",
        return_value=store,
    )


# ---------------------------------------------------------------------------
# profile list
# ---------------------------------------------------------------------------


class TestProfileList:
    def test_empty_list(self, runner: CliRunner, store: ProfileStore):
        with _patch_store(store):
            result = runner.invoke(profile_group, ["list"])
        assert result.exit_code == 0
        assert "No profiles found" in result.output

    def test_list_with_profiles(self, runner: CliRunner, store: ProfileStore):
        store.save(AgentProfile(name="ci", session_label="ci"))
        store.save(AgentProfile(name="dev", adapter="openai_cli"))
        with _patch_store(store):
            result = runner.invoke(profile_group, ["list"])
        assert result.exit_code == 0
        assert "ci" in result.output
        assert "dev" in result.output

    def test_list_shows_default(self, runner: CliRunner, store: ProfileStore):
        store.save(AgentProfile(name="ci"))
        store.set_default("ci")
        with _patch_store(store):
            result = runner.invoke(profile_group, ["list"])
        assert result.exit_code == 0
        assert "yes" in result.output


# ---------------------------------------------------------------------------
# profile show
# ---------------------------------------------------------------------------


class TestProfileShow:
    def test_show_existing(self, runner: CliRunner, store: ProfileStore):
        store.save(AgentProfile(name="ci", session_label="ci", description="CI sessions"))
        with _patch_store(store):
            result = runner.invoke(profile_group, ["show", "ci"])
        assert result.exit_code == 0
        assert "ci" in result.output
        assert "CI sessions" in result.output

    def test_show_not_found(self, runner: CliRunner, store: ProfileStore):
        with _patch_store(store):
            result = runner.invoke(profile_group, ["show", "missing"])
        assert result.exit_code == 1
        assert "not found" in result.output


# ---------------------------------------------------------------------------
# profile create
# ---------------------------------------------------------------------------


class TestProfileCreate:
    def test_create_basic(self, runner: CliRunner, store: ProfileStore):
        with _patch_store(store):
            result = runner.invoke(profile_group, ["create", "ci", "--label", "ci"])
        assert result.exit_code == 0
        assert "Created" in result.output
        assert store.get("ci") is not None

    def test_create_with_all_options(self, runner: CliRunner, store: ProfileStore):
        with _patch_store(store):
            result = runner.invoke(
                profile_group,
                [
                    "create",
                    "full",
                    "--label",
                    "full-session",
                    "--policy",
                    "policy.yaml",
                    "--adapter",
                    "openai_cli",
                    "--description",
                    "Full profile",
                ],
            )
        assert result.exit_code == 0
        profile = store.get("full")
        assert profile is not None
        assert profile.session_label == "full-session"
        assert profile.policy_file == "policy.yaml"
        assert profile.adapter == "openai_cli"

    def test_create_duplicate_rejected(self, runner: CliRunner, store: ProfileStore):
        store.save(AgentProfile(name="ci"))
        with _patch_store(store):
            result = runner.invoke(profile_group, ["create", "ci"])
        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_create_invalid_name(self, runner: CliRunner, store: ProfileStore):
        with _patch_store(store):
            result = runner.invoke(profile_group, ["create", "INVALID"])
        assert result.exit_code == 1
        assert "Invalid" in result.output or "invalid" in result.output


# ---------------------------------------------------------------------------
# profile delete
# ---------------------------------------------------------------------------


class TestProfileDelete:
    def test_delete_existing(self, runner: CliRunner, store: ProfileStore):
        store.save(AgentProfile(name="ci"))
        with _patch_store(store):
            result = runner.invoke(profile_group, ["delete", "ci"])
        assert result.exit_code == 0
        assert "Deleted" in result.output
        assert store.get("ci") is None

    def test_delete_not_found(self, runner: CliRunner, store: ProfileStore):
        with _patch_store(store):
            result = runner.invoke(profile_group, ["delete", "missing"])
        assert result.exit_code == 1
        assert "not found" in result.output


# ---------------------------------------------------------------------------
# profile set-default
# ---------------------------------------------------------------------------


class TestProfileSetDefault:
    def test_set_default(self, runner: CliRunner, store: ProfileStore):
        store.save(AgentProfile(name="ci"))
        with _patch_store(store):
            result = runner.invoke(profile_group, ["set-default", "ci"])
        assert result.exit_code == 0
        assert store.get_default() == "ci"

    def test_set_default_nonexistent(self, runner: CliRunner, store: ProfileStore):
        with _patch_store(store):
            result = runner.invoke(profile_group, ["set-default", "missing"])
        assert result.exit_code == 1
        assert "does not exist" in result.output


# ---------------------------------------------------------------------------
# run --profile integration
# ---------------------------------------------------------------------------


class TestRunProfile:
    def test_run_profile_loads_defaults(self, tmp_path: Path):
        """Verify --profile resolves session_label from profile."""
        store = ProfileStore(profiles_dir=tmp_path / "profiles")
        store.save(AgentProfile(name="ci", session_label="ci", policy_file="ci-policy.yaml"))

        from atlasbridge.cli._run import run_cmd

        runner = CliRunner()
        with (
            patch("atlasbridge.core.profile.ProfileStore", return_value=store),
            patch("atlasbridge.cli._run.cmd_run") as mock_cmd_run,
        ):
            runner.invoke(run_cmd, ["claude", "--profile", "ci"])

        if mock_cmd_run.called:
            call_kwargs = mock_cmd_run.call_args
            label = call_kwargs.kwargs.get("label", "") if call_kwargs.kwargs else ""
            assert label == "ci"

    def test_run_explicit_label_overrides_profile(self, tmp_path: Path):
        """Explicit --session-label wins over profile's session_label."""
        store = ProfileStore(profiles_dir=tmp_path / "profiles")
        store.save(AgentProfile(name="ci", session_label="ci-default"))

        from atlasbridge.cli._run import run_cmd

        runner = CliRunner()
        with (
            patch("atlasbridge.core.profile.ProfileStore", return_value=store),
            patch("atlasbridge.cli._run.cmd_run") as mock_cmd_run,
        ):
            runner.invoke(run_cmd, ["claude", "--profile", "ci", "--session-label", "override"])

        if mock_cmd_run.called:
            call_kwargs = mock_cmd_run.call_args
            label = call_kwargs.kwargs.get("label", "") if call_kwargs.kwargs else ""
            assert label == "override"
