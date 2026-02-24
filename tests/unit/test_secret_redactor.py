"""Tests for the centralized SecretRedactor."""

from __future__ import annotations

import pytest

from atlasbridge.core.security.redactor import SecretRedactor, get_redactor

# ---------------------------------------------------------------------------
# Pattern coverage — every known format must be caught
# ---------------------------------------------------------------------------


class TestBuiltinPatterns:
    """Each built-in pattern must match its target format."""

    @pytest.fixture()
    def r(self):
        return SecretRedactor()

    def test_telegram_token(self, r: SecretRedactor):
        text = "token is 123456789:ABCDefGHIjklMNOpqrSTUvwxyz123456789_0"
        assert r.contains_secret(text)
        assert "[REDACTED]" in r.redact(text)

    def test_slack_bot_token(self, r: SecretRedactor):
        # Use FAKE- prefix to avoid GitHub push protection false positive
        text = "SLACK_TOKEN=xoxb-FAKE-TESTTOKEN0000"
        assert r.contains_secret(text)
        assert "[REDACTED]" in r.redact(text)

    def test_slack_app_token(self, r: SecretRedactor):
        text = "xapp-1-A1B2C3D4E5F6G7H8I9J0K1L2M3"
        assert r.contains_secret(text)

    def test_openai_key(self, r: SecretRedactor):
        text = "key: sk-abcdefghijklmnopqrstuvwxyz"
        assert r.contains_secret(text)
        assert "[REDACTED]" in r.redact(text)

    def test_github_pat(self, r: SecretRedactor):
        text = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijkl"
        assert r.contains_secret(text)
        assert "[REDACTED]" in r.redact(text)

    def test_aws_access_key(self, r: SecretRedactor):
        text = "AWS_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE"
        assert r.contains_secret(text)
        assert "[REDACTED]" in r.redact(text)

    def test_google_api_key(self, r: SecretRedactor):
        text = "key=AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q"
        assert r.contains_secret(text)

    def test_anthropic_key(self, r: SecretRedactor):
        text = "sk-ant-abc123-XYZXYZXYZXYZXYZXYZ"
        assert r.contains_secret(text)

    def test_hex_secret_64chars(self, r: SecretRedactor):
        text = "a" * 64
        assert r.contains_secret(text)

    def test_bearer_token(self, r: SecretRedactor):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"
        assert r.contains_secret(text)

    def test_env_secret_api_key(self, r: SecretRedactor):
        text = "api_key=abcdefghijklmnopqrstuvwxyz1234"
        assert r.contains_secret(text)

    def test_env_secret_password(self, r: SecretRedactor):
        text = "password=MyS3cretP@ssw0rd!"
        assert r.contains_secret(text)

    def test_no_false_positive_short(self, r: SecretRedactor):
        """Short benign strings should NOT be flagged."""
        assert not r.contains_secret("hello world")
        assert not r.contains_secret("y")
        assert not r.contains_secret("Continue? [y/n]")

    def test_no_false_positive_uuid(self, r: SecretRedactor):
        """Standard UUIDs (32 hex + dashes) should not match."""
        text = "session-id: 550e8400-e29b-41d4-a716-446655440000"
        assert not r.contains_secret(text)


# ---------------------------------------------------------------------------
# Redaction behavior
# ---------------------------------------------------------------------------


class TestRedaction:
    def test_redact_replaces_all(self):
        r = SecretRedactor()
        text = "key1=sk-abcdefghijklmnopqrstuvwx key2=AKIAIOSFODNN7EXAMPLE"
        result = r.redact(text)
        assert "sk-" not in result
        assert "AKIA" not in result
        assert result.count("[REDACTED]") >= 2

    def test_redact_labeled(self):
        r = SecretRedactor()
        text = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijkl"
        result = r.redact_labeled(text)
        assert "[REDACTED:github-pat]" in result

    def test_custom_pattern(self):
        r = SecretRedactor(custom_patterns=[r"MYCORP-[A-Z]{20,}"])
        text = "token: MYCORP-ABCDEFGHIJKLMNOPQRSTU"
        assert r.contains_secret(text)
        assert "[REDACTED]" in r.redact(text)

    def test_add_pattern(self):
        r = SecretRedactor()
        count_before = r.pattern_count
        r.add_pattern(r"INTERNAL-\d{10}", label="internal")
        assert r.pattern_count == count_before + 1
        assert r.contains_secret("INTERNAL-1234567890")
        assert "[REDACTED:internal]" in r.redact_labeled("INTERNAL-1234567890")

    def test_idempotent_redaction(self):
        """Redacting already-redacted text should be stable."""
        r = SecretRedactor()
        text = "sk-abcdefghijklmnopqrstuvwxyz"
        once = r.redact(text)
        twice = r.redact(once)
        assert once == twice


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_redactor_returns_same_instance(self):
        import atlasbridge.core.security.redactor as mod

        mod._default_redactor = None  # reset
        a = get_redactor()
        b = get_redactor()
        assert a is b
        mod._default_redactor = None  # cleanup

    def test_get_redactor_adds_custom(self):
        import atlasbridge.core.security.redactor as mod

        mod._default_redactor = None  # reset
        r = get_redactor(custom_patterns=[r"CUSTOM-\d+"])
        count = r.pattern_count
        get_redactor(custom_patterns=[r"ANOTHER-\d+"])
        assert r.pattern_count == count + 1
        mod._default_redactor = None  # cleanup


# ---------------------------------------------------------------------------
# Integration — audit writer safe_excerpt uses centralized redactor
# ---------------------------------------------------------------------------


class TestAuditWriterIntegration:
    def test_safe_excerpt_redacts_via_centralized(self):
        from atlasbridge.core.audit.writer import safe_excerpt

        text = "token=sk-abcdefghijklmnopqrstuvwxyz and AKIAIOSFODNN7EXAMPLE"
        result = safe_excerpt(text)
        assert "sk-" not in result
        assert "AKIA" not in result

    def test_safe_excerpt_password(self):
        from atlasbridge.core.audit.writer import safe_excerpt

        assert safe_excerpt("anything", is_password=True) == "[REDACTED]"

    def test_safe_excerpt_rate_limited(self):
        from atlasbridge.core.audit.writer import safe_excerpt

        assert safe_excerpt("anything", is_rate_limited=True) == "[rate limited]"


# ---------------------------------------------------------------------------
# Integration — dashboard sanitize uses centralized redactor
# ---------------------------------------------------------------------------


class TestDashboardIntegration:
    def test_redact_tokens_catches_secrets(self):
        from atlasbridge.dashboard.sanitize import redact_tokens

        text = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijkl"
        result = redact_tokens(text)
        assert "ghp_" not in result
        assert "REDACTED" in result

    def test_sanitize_for_display_redacts(self):
        from atlasbridge.dashboard.sanitize import sanitize_for_display

        text = "output: sk-abcdefghijklmnopqrstuvwxyz"
        result = sanitize_for_display(text)
        assert "sk-" not in result


# ---------------------------------------------------------------------------
# Integration — output forwarder uses centralized redactor
# ---------------------------------------------------------------------------


class TestOutputForwarderIntegration:
    def test_forwarder_redact_static(self):
        from atlasbridge.core.interaction.output_forwarder import OutputForwarder

        text = "AKIAIOSFODNN7EXAMPLE leaked"
        result = OutputForwarder._redact(text)
        assert "AKIA" not in result
        assert "[REDACTED]" in result
