"""Tests for AgentProfile model and ProfileStore."""

from __future__ import annotations

from pathlib import Path

import pytest

from atlasbridge.core.profile import AgentProfile, ProfileStore

# ---------------------------------------------------------------------------
# AgentProfile model validation
# ---------------------------------------------------------------------------


class TestAgentProfileModel:
    def test_valid_profile(self):
        p = AgentProfile(name="ci", session_label="ci", description="CI sessions")
        assert p.name == "ci"
        assert p.session_label == "ci"
        assert p.adapter == "claude"
        assert p.metadata == {}

    def test_defaults(self):
        p = AgentProfile(name="test")
        assert p.description == ""
        assert p.session_label == ""
        assert p.policy_file == ""
        assert p.adapter == "claude"

    @pytest.mark.parametrize(
        "name",
        [
            "a",
            "ci",
            "code-review",
            "my_profile",
            "a123",
            "0test",
        ],
    )
    def test_valid_names(self, name: str):
        p = AgentProfile(name=name)
        assert p.name == name

    @pytest.mark.parametrize(
        "name",
        [
            "",
            "A",  # uppercase not allowed
            "CI",
            "has space",
            "-starts-with-dash",
            "_starts-with-underscore",
            "name!",
            "a" * 65,  # too long
        ],
    )
    def test_invalid_names(self, name: str):
        with pytest.raises(Exception):  # noqa: B017 — ValidationError
            AgentProfile(name=name)

    def test_full_profile(self):
        p = AgentProfile(
            name="full",
            description="Full profile",
            session_label="full-session",
            policy_file="/path/to/policy.yaml",
            adapter="openai_cli",
            metadata={"env": "staging"},
        )
        assert p.policy_file == "/path/to/policy.yaml"
        assert p.adapter == "openai_cli"
        assert p.metadata["env"] == "staging"


# ---------------------------------------------------------------------------
# ProfileStore CRUD
# ---------------------------------------------------------------------------


class TestProfileStore:
    def test_list_empty(self, tmp_path: Path):
        store = ProfileStore(profiles_dir=tmp_path / "profiles")
        assert store.list_profiles() == []

    def test_save_and_get(self, tmp_path: Path):
        store = ProfileStore(profiles_dir=tmp_path / "profiles")
        profile = AgentProfile(name="ci", session_label="ci")
        path = store.save(profile)
        assert path.exists()
        assert path.suffix == ".yaml"

        loaded = store.get("ci")
        assert loaded is not None
        assert loaded.name == "ci"
        assert loaded.session_label == "ci"

    def test_get_nonexistent(self, tmp_path: Path):
        store = ProfileStore(profiles_dir=tmp_path / "profiles")
        assert store.get("missing") is None

    def test_list_profiles(self, tmp_path: Path):
        store = ProfileStore(profiles_dir=tmp_path / "profiles")
        store.save(AgentProfile(name="bravo"))
        store.save(AgentProfile(name="alpha"))
        store.save(AgentProfile(name="charlie"))

        names = [p.name for p in store.list_profiles()]
        assert names == ["alpha", "bravo", "charlie"]  # sorted

    def test_save_overwrites(self, tmp_path: Path):
        store = ProfileStore(profiles_dir=tmp_path / "profiles")
        store.save(AgentProfile(name="ci", session_label="old"))
        store.save(AgentProfile(name="ci", session_label="new"))

        loaded = store.get("ci")
        assert loaded is not None
        assert loaded.session_label == "new"

    def test_delete(self, tmp_path: Path):
        store = ProfileStore(profiles_dir=tmp_path / "profiles")
        store.save(AgentProfile(name="ci"))
        assert store.delete("ci") is True
        assert store.get("ci") is None
        assert store.delete("ci") is False  # already gone

    def test_delete_clears_default(self, tmp_path: Path):
        store = ProfileStore(profiles_dir=tmp_path / "profiles")
        store.save(AgentProfile(name="ci"))
        store.set_default("ci")
        assert store.get_default() == "ci"

        store.delete("ci")
        assert store.get_default() is None


# ---------------------------------------------------------------------------
# Default profile
# ---------------------------------------------------------------------------


class TestDefaultProfile:
    def test_no_default(self, tmp_path: Path):
        store = ProfileStore(profiles_dir=tmp_path / "profiles")
        assert store.get_default() is None

    def test_set_and_get_default(self, tmp_path: Path):
        store = ProfileStore(profiles_dir=tmp_path / "profiles")
        store.save(AgentProfile(name="ci"))
        store.set_default("ci")
        assert store.get_default() == "ci"

    def test_set_default_nonexistent_raises(self, tmp_path: Path):
        store = ProfileStore(profiles_dir=tmp_path / "profiles")
        with pytest.raises(FileNotFoundError):
            store.set_default("missing")

    def test_change_default(self, tmp_path: Path):
        store = ProfileStore(profiles_dir=tmp_path / "profiles")
        store.save(AgentProfile(name="ci"))
        store.save(AgentProfile(name="dev"))
        store.set_default("ci")
        store.set_default("dev")
        assert store.get_default() == "dev"
