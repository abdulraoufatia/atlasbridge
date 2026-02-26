"""Unit tests for Edition/AuthorityMode detection (v2 — CORE/ENTERPRISE only)."""

from __future__ import annotations

from atlasbridge.enterprise.edition import (
    AuthorityMode,
    Edition,
    detect_authority_mode,
    detect_edition,
)


class TestEditionEnum:
    def test_core_value(self) -> None:
        assert Edition.CORE.value == "core"

    def test_enterprise_value(self) -> None:
        assert Edition.ENTERPRISE.value == "enterprise"

    def test_only_two_editions(self) -> None:
        assert set(Edition) == {Edition.CORE, Edition.ENTERPRISE}


class TestAuthorityModeEnum:
    def test_readonly_value(self) -> None:
        assert AuthorityMode.READONLY.value == "readonly"

    def test_write_enabled_value(self) -> None:
        assert AuthorityMode.WRITE_ENABLED.value == "write_enabled"

    def test_only_two_modes(self) -> None:
        assert set(AuthorityMode) == {AuthorityMode.READONLY, AuthorityMode.WRITE_ENABLED}


class TestDetectEdition:
    def test_defaults_to_core(self, monkeypatch) -> None:
        monkeypatch.delenv("ATLASBRIDGE_EDITION", raising=False)
        assert detect_edition() == Edition.CORE

    def test_empty_string_defaults_to_core(self, monkeypatch) -> None:
        monkeypatch.setenv("ATLASBRIDGE_EDITION", "")
        assert detect_edition() == Edition.CORE

    def test_core_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("ATLASBRIDGE_EDITION", "core")
        assert detect_edition() == Edition.CORE

    def test_enterprise_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("ATLASBRIDGE_EDITION", "enterprise")
        assert detect_edition() == Edition.ENTERPRISE

    def test_case_insensitive_enterprise(self, monkeypatch) -> None:
        monkeypatch.setenv("ATLASBRIDGE_EDITION", "ENTERPRISE")
        assert detect_edition() == Edition.ENTERPRISE

    def test_case_insensitive_core(self, monkeypatch) -> None:
        monkeypatch.setenv("ATLASBRIDGE_EDITION", "CORE")
        assert detect_edition() == Edition.CORE

    def test_community_maps_to_core(self, monkeypatch) -> None:
        """Deprecated 'community' alias maps to CORE."""
        monkeypatch.setenv("ATLASBRIDGE_EDITION", "community")
        assert detect_edition() == Edition.CORE

    def test_community_emits_warning(self, monkeypatch, caplog) -> None:
        """Setting ATLASBRIDGE_EDITION=community should log a deprecation warning."""
        monkeypatch.setenv("ATLASBRIDGE_EDITION", "community")
        import logging

        with caplog.at_level(logging.WARNING, logger="atlasbridge.enterprise.edition"):
            detect_edition()
        assert "deprecated" in caplog.text.lower()

    def test_invalid_falls_back_to_core(self, monkeypatch) -> None:
        monkeypatch.setenv("ATLASBRIDGE_EDITION", "invalid_value")
        assert detect_edition() == Edition.CORE


class TestDetectAuthorityMode:
    def test_defaults_to_readonly(self, monkeypatch) -> None:
        monkeypatch.delenv("ATLASBRIDGE_AUTHORITY_MODE", raising=False)
        assert detect_authority_mode() == AuthorityMode.READONLY

    def test_empty_string_defaults_to_readonly(self, monkeypatch) -> None:
        monkeypatch.setenv("ATLASBRIDGE_AUTHORITY_MODE", "")
        assert detect_authority_mode() == AuthorityMode.READONLY

    def test_readonly_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("ATLASBRIDGE_AUTHORITY_MODE", "readonly")
        assert detect_authority_mode() == AuthorityMode.READONLY

    def test_write_enabled_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("ATLASBRIDGE_AUTHORITY_MODE", "write_enabled")
        assert detect_authority_mode() == AuthorityMode.WRITE_ENABLED

    def test_case_insensitive(self, monkeypatch) -> None:
        monkeypatch.setenv("ATLASBRIDGE_AUTHORITY_MODE", "WRITE_ENABLED")
        assert detect_authority_mode() == AuthorityMode.WRITE_ENABLED

    def test_invalid_falls_back_to_readonly(self, monkeypatch) -> None:
        monkeypatch.setenv("ATLASBRIDGE_AUTHORITY_MODE", "invalid")
        assert detect_authority_mode() == AuthorityMode.READONLY
