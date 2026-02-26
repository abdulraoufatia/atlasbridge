"""Unit tests for edition detection — backward-compat surface.

The full v2 edition tests live in test_edition_v2.py.
This file validates that the public API re-exports from enterprise/__init__.py work.
"""

from __future__ import annotations

from atlasbridge.enterprise import (
    AuthorityMode,
    Edition,
    FeatureRegistry,
    detect_authority_mode,
    detect_edition,
)


class TestEdition:
    def test_core_is_default(self, monkeypatch) -> None:
        monkeypatch.delenv("ATLASBRIDGE_EDITION", raising=False)
        assert detect_edition() == Edition.CORE

    def test_edition_values(self) -> None:
        assert Edition.CORE.value == "core"
        assert Edition.ENTERPRISE.value == "enterprise"

    def test_detect_edition_from_env_core(self, monkeypatch) -> None:
        monkeypatch.setenv("ATLASBRIDGE_EDITION", "core")
        assert detect_edition() == Edition.CORE

    def test_detect_edition_from_env_enterprise(self, monkeypatch) -> None:
        monkeypatch.setenv("ATLASBRIDGE_EDITION", "enterprise")
        assert detect_edition() == Edition.ENTERPRISE

    def test_detect_edition_community_maps_to_core(self, monkeypatch) -> None:
        monkeypatch.setenv("ATLASBRIDGE_EDITION", "community")
        assert detect_edition() == Edition.CORE

    def test_detect_edition_case_insensitive(self, monkeypatch) -> None:
        monkeypatch.setenv("ATLASBRIDGE_EDITION", "CORE")
        assert detect_edition() == Edition.CORE

    def test_detect_edition_invalid_falls_back_to_core(self, monkeypatch) -> None:
        monkeypatch.setenv("ATLASBRIDGE_EDITION", "invalid")
        assert detect_edition() == Edition.CORE


class TestAuthorityMode:
    def test_readonly_is_default(self, monkeypatch) -> None:
        monkeypatch.delenv("ATLASBRIDGE_AUTHORITY_MODE", raising=False)
        assert detect_authority_mode() == AuthorityMode.READONLY

    def test_write_enabled_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("ATLASBRIDGE_AUTHORITY_MODE", "write_enabled")
        assert detect_authority_mode() == AuthorityMode.WRITE_ENABLED


class TestFeatureRegistryReExport:
    """Verify FeatureRegistry is accessible from enterprise.__init__."""

    def test_list_capabilities(self) -> None:
        caps = FeatureRegistry.list_capabilities(Edition.CORE, AuthorityMode.READONLY)
        assert isinstance(caps, dict)
        assert len(caps) > 0

    def test_capabilities_hash(self) -> None:
        h = FeatureRegistry.capabilities_hash(Edition.CORE, AuthorityMode.READONLY)
        assert isinstance(h, str)
        assert len(h) == 64
