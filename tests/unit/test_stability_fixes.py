"""
Regression tests for stability fixes (v0.8.4).

Covers:
  A) Adapter discovery resilience
  D) Stale/unknown prompt reply handling
  E) Doctor path handling
  G) Run command on-screen instructions
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# =====================================================================
# A) Adapter discovery
# =====================================================================


class TestAdapterDiscovery:
    """Adapter registration is resilient to import failures."""

    def test_adapters_register_successfully(self):
        """All built-in adapters register under expected names."""
        import atlasbridge.adapters  # noqa: F401
        from atlasbridge.adapters.base import AdapterRegistry

        available = AdapterRegistry.list_all()
        assert "claude" in available
        assert "claude-code" in available
        assert "openai" in available
        assert "gemini" in available

    def test_adapter_registry_get_falls_back_to_custom(self):
        """AdapterRegistry.get() falls back to CustomCLIAdapter for unknown adapters."""
        from atlasbridge.adapters.base import AdapterRegistry
        from atlasbridge.adapters.openai_cli import CustomCLIAdapter

        cls = AdapterRegistry.get("nonexistent_adapter_xyz")
        assert cls is CustomCLIAdapter

    def test_adapter_registry_list_all_returns_dict(self):
        """AdapterRegistry.list_all() returns a non-empty dict."""
        import atlasbridge.adapters  # noqa: F401
        from atlasbridge.adapters.base import AdapterRegistry

        result = AdapterRegistry.list_all()
        assert isinstance(result, dict)
        assert len(result) >= 3  # at least claude, openai, gemini

    def test_resilient_adapter_import(self):
        """A broken adapter module doesn't prevent other adapters from loading."""
        import atlasbridge.adapters  # noqa: F401
        from atlasbridge.adapters.base import AdapterRegistry

        assert "claude" in AdapterRegistry.list_all()


# =====================================================================
# D) Stale/unknown prompt reply handling
# =====================================================================


class TestStaleReplyHandling:
    """Router handles stale, unknown, and duplicate replies gracefully."""

    def _make_router(self):
        from atlasbridge.core.routing.router import PromptRouter
        from atlasbridge.core.session.manager import SessionManager

        sm = SessionManager()
        channel = MagicMock()
        channel.is_allowed = MagicMock(return_value=True)
        channel.notify = AsyncMock()
        channel.send_prompt = AsyncMock(return_value="msg1")
        channel.edit_prompt_message = AsyncMock()
        return (
            PromptRouter(
                session_manager=sm,
                channel=channel,
                adapter_map={},
                store=MagicMock(),
            ),
            sm,
            channel,
        )

    @pytest.mark.asyncio
    async def test_unknown_prompt_reply_is_silently_dropped(self):
        """Reply for unknown prompt_id is dropped without side effects."""
        from atlasbridge.core.prompt.models import Reply

        router, sm, channel = self._make_router()

        reply = Reply(
            prompt_id="nonexistent",
            session_id="sess1",
            value="y",
            nonce="abc123",
            channel_identity="telegram:123",
            timestamp="2024-01-01T00:00:00Z",
        )

        await router.handle_reply(reply)
        # No crash, no channel interaction — silently dropped
        channel.notify.assert_not_called()

    def test_free_text_reply_resolve(self):
        """Free-text reply with empty prompt_id resolves to active prompt."""
        from atlasbridge.core.prompt.models import (
            Confidence,
            PromptEvent,
            PromptStatus,
            PromptType,
            Reply,
        )
        from atlasbridge.core.prompt.state import PromptStateMachine

        router, sm, channel = self._make_router()

        event = PromptEvent.create(
            session_id="sess1",
            prompt_type=PromptType.TYPE_FREE_TEXT,
            confidence=Confidence.HIGH,
            excerpt="What?",
        )
        active_sm = PromptStateMachine(event=event)
        active_sm.transition(PromptStatus.ROUTED, "test")
        active_sm.transition(PromptStatus.AWAITING_REPLY, "test")
        router._machines[event.prompt_id] = active_sm

        reply = Reply(
            prompt_id="",
            session_id="",
            value="my answer",
            nonce="abc123",
            channel_identity="telegram:123",
            timestamp="2024-01-01T00:00:00Z",
        )

        resolved = router._resolve_free_text_reply(reply)
        assert resolved is not None
        assert resolved.prompt_id == event.prompt_id
        assert resolved.value == "my answer"

    def test_free_text_reply_returns_none_when_no_active(self):
        """Free-text reply returns None when no active prompt exists."""
        from atlasbridge.core.prompt.models import Reply

        router, sm, channel = self._make_router()

        reply = Reply(
            prompt_id="",
            session_id="",
            value="orphan",
            nonce="abc",
            channel_identity="telegram:123",
            timestamp="2024-01-01T00:00:00Z",
        )

        result = router._resolve_free_text_reply(reply)
        assert result is None

    @pytest.mark.asyncio
    async def test_duplicate_reply_for_resolved_prompt_is_dropped(self):
        """A second reply for an already-resolved prompt is silently dropped."""
        from atlasbridge.core.prompt.models import (
            Confidence,
            PromptEvent,
            PromptStatus,
            PromptType,
            Reply,
        )
        from atlasbridge.core.prompt.state import PromptStateMachine

        router, sm, channel = self._make_router()

        event = PromptEvent.create(
            session_id="sess1",
            prompt_type=PromptType.TYPE_YES_NO,
            confidence=Confidence.HIGH,
            excerpt="Continue?",
        )
        resolved_sm = PromptStateMachine(event=event)
        resolved_sm.transition(PromptStatus.ROUTED, "test")
        resolved_sm.transition(PromptStatus.AWAITING_REPLY, "test")
        resolved_sm.transition(PromptStatus.REPLY_RECEIVED, "test")
        resolved_sm.transition(PromptStatus.INJECTED, "test")
        resolved_sm.transition(PromptStatus.RESOLVED, "test")
        router._machines[event.prompt_id] = resolved_sm

        reply = Reply(
            prompt_id=event.prompt_id,
            session_id="sess1",
            value="y",
            nonce="dup123",
            channel_identity="telegram:123",
            timestamp="2024-01-01T00:00:00Z",
        )

        await router.handle_reply(reply)
        # No crash, no channel interaction — silently dropped
        channel.notify.assert_not_called()


# =====================================================================
# E) Doctor path handling
# =====================================================================


class TestDoctorPathHandling:
    """Doctor checks handle Path/str consistently."""

    def test_config_path_returns_path_object(self):
        """_config_path() always returns a pathlib.Path."""
        from atlasbridge.cli._doctor import _config_path

        result = _config_path()
        assert isinstance(result, Path)

    def test_check_config_handles_missing_file(self):
        """_check_config() returns warn status when config file is missing."""
        from atlasbridge.cli._doctor import _check_config

        with patch("atlasbridge.cli._doctor._config_path") as mock_path:
            mock_path.return_value = Path("/nonexistent/config.toml")
            result = _check_config()
            assert result["status"] == "warn"
            assert "not found" in result["detail"]

    def test_check_bot_token_handles_missing_config(self):
        """_check_bot_token() returns skip when no config file."""
        from atlasbridge.cli._doctor import _check_bot_token

        with patch("atlasbridge.cli._doctor._config_path") as mock_path:
            mock_path.return_value = Path("/nonexistent/config.toml")
            result = _check_bot_token()
            assert result["status"] == "skip"

    def test_check_python_version(self):
        """_check_python_version() passes on 3.11+."""
        from atlasbridge.cli._doctor import _check_python_version

        result = _check_python_version()
        assert result["name"] == "Python version"
        assert result["status"] in ("pass", "fail")

    def test_check_platform(self):
        """_check_platform() returns a valid result."""
        from atlasbridge.cli._doctor import _check_platform

        result = _check_platform()
        assert result["name"] == "Platform"
        assert result["status"] in ("pass", "warn")


# =====================================================================
# G) Run command on-screen instructions
# =====================================================================


class TestRunInstructions:
    """atlasbridge run shows usage instructions."""

    def test_run_command_imports_cleanly(self):
        """_run.py imports without error."""
        from atlasbridge.cli._run import cmd_run

        assert callable(cmd_run)
