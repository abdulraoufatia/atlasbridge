"""Unit tests for ConversationRegistry — thread-to-session binding."""

from __future__ import annotations

import time

from atlasbridge.core.conversation.session_binding import (
    VALID_CONVERSATION_TRANSITIONS,
    ConversationBinding,
    ConversationRegistry,
    ConversationState,
)


class TestConversationState:
    def test_all_states_exist(self) -> None:
        assert ConversationState.IDLE == "idle"
        assert ConversationState.RUNNING == "running"
        assert ConversationState.STREAMING == "streaming"
        assert ConversationState.AWAITING_INPUT == "awaiting_input"
        assert ConversationState.STOPPED == "stopped"

    def test_state_count(self) -> None:
        assert len(ConversationState) == 5

    def test_streaming_state_exists(self) -> None:
        assert ConversationState.STREAMING == "streaming"


class TestBindResolve:
    def test_bind_and_resolve(self) -> None:
        reg = ConversationRegistry()
        reg.bind("telegram", "12345", "sess-001")
        assert reg.resolve("telegram", "12345") == "sess-001"

    def test_resolve_unbound_returns_none(self) -> None:
        reg = ConversationRegistry()
        assert reg.resolve("telegram", "99999") is None

    def test_bind_replaces_existing(self) -> None:
        reg = ConversationRegistry()
        reg.bind("telegram", "12345", "sess-001")
        reg.bind("telegram", "12345", "sess-002")
        assert reg.resolve("telegram", "12345") == "sess-002"

    def test_bind_returns_binding(self) -> None:
        reg = ConversationRegistry()
        b = reg.bind("telegram", "12345", "sess-001")
        assert isinstance(b, ConversationBinding)
        assert b.channel_name == "telegram"
        assert b.thread_id == "12345"
        assert b.session_id == "sess-001"
        assert b.state == ConversationState.RUNNING

    def test_different_channels_do_not_collide(self) -> None:
        reg = ConversationRegistry()
        reg.bind("telegram", "12345", "sess-001")
        reg.bind("slack", "12345", "sess-002")
        assert reg.resolve("telegram", "12345") == "sess-001"
        assert reg.resolve("slack", "12345") == "sess-002"


class TestGetBinding:
    def test_get_binding_returns_full_object(self) -> None:
        reg = ConversationRegistry()
        reg.bind("telegram", "12345", "sess-001")
        b = reg.get_binding("telegram", "12345")
        assert b is not None
        assert b.session_id == "sess-001"

    def test_get_binding_unbound_returns_none(self) -> None:
        reg = ConversationRegistry()
        assert reg.get_binding("telegram", "99999") is None


class TestStateTransitions:
    def test_update_state(self) -> None:
        reg = ConversationRegistry()
        reg.bind("telegram", "12345", "sess-001")
        reg.update_state("telegram", "12345", ConversationState.AWAITING_INPUT)
        b = reg.get_binding("telegram", "12345")
        assert b is not None
        assert b.state == ConversationState.AWAITING_INPUT

    def test_update_state_nonexistent_is_noop(self) -> None:
        reg = ConversationRegistry()
        # Should not raise
        reg.update_state("telegram", "99999", ConversationState.STOPPED)

    def test_full_lifecycle(self) -> None:
        reg = ConversationRegistry()
        reg.bind("telegram", "12345", "sess-001")

        b = reg.get_binding("telegram", "12345")
        assert b is not None
        assert b.state == ConversationState.RUNNING

        reg.update_state("telegram", "12345", ConversationState.AWAITING_INPUT)
        b = reg.get_binding("telegram", "12345")
        assert b is not None
        assert b.state == ConversationState.AWAITING_INPUT

        reg.update_state("telegram", "12345", ConversationState.RUNNING)
        b = reg.get_binding("telegram", "12345")
        assert b is not None
        assert b.state == ConversationState.RUNNING

        reg.update_state("telegram", "12345", ConversationState.STOPPED)
        b = reg.get_binding("telegram", "12345")
        assert b is not None
        assert b.state == ConversationState.STOPPED


class TestUnbind:
    def test_unbind_removes_all_for_session(self) -> None:
        reg = ConversationRegistry()
        reg.bind("telegram", "111", "sess-001")
        reg.bind("slack", "222", "sess-001")
        reg.bind("telegram", "333", "sess-002")

        removed = reg.unbind("sess-001")
        assert removed == 2
        assert reg.resolve("telegram", "111") is None
        assert reg.resolve("slack", "222") is None
        assert reg.resolve("telegram", "333") == "sess-002"

    def test_unbind_nonexistent_returns_zero(self) -> None:
        reg = ConversationRegistry()
        assert reg.unbind("sess-999") == 0


class TestTTLExpiry:
    def test_resolve_expired_returns_none(self) -> None:
        reg = ConversationRegistry(ttl_seconds=1.0)
        reg.bind("telegram", "12345", "sess-001")

        # Expire the binding by advancing last_activity
        b = reg.get_binding("telegram", "12345")
        assert b is not None
        b.last_activity = time.monotonic() - 2.0

        assert reg.resolve("telegram", "12345") is None

    def test_prune_expired(self) -> None:
        reg = ConversationRegistry(ttl_seconds=1.0)
        reg.bind("telegram", "111", "sess-001")
        reg.bind("telegram", "222", "sess-002")

        # Expire only the first
        b1 = reg.get_binding("telegram", "111")
        assert b1 is not None
        b1.last_activity = time.monotonic() - 2.0

        pruned = reg.prune_expired()
        assert pruned == 1
        assert reg.resolve("telegram", "111") is None
        assert reg.resolve("telegram", "222") == "sess-002"

    def test_resolve_refreshes_activity(self) -> None:
        reg = ConversationRegistry(ttl_seconds=10.0)
        reg.bind("telegram", "12345", "sess-001")

        before = reg.get_binding("telegram", "12345")
        assert before is not None
        old_activity = before.last_activity

        # Small sleep to ensure time.monotonic() advances
        time.sleep(0.01)
        reg.resolve("telegram", "12345")

        after = reg.get_binding("telegram", "12345")
        assert after is not None
        assert after.last_activity > old_activity


class TestBindingsForSession:
    def test_returns_all_bindings(self) -> None:
        reg = ConversationRegistry()
        reg.bind("telegram", "111", "sess-001")
        reg.bind("slack", "222", "sess-001")
        reg.bind("telegram", "333", "sess-002")

        bindings = reg.bindings_for_session("sess-001")
        assert len(bindings) == 2
        session_ids = {b.session_id for b in bindings}
        assert session_ids == {"sess-001"}

    def test_excludes_expired(self) -> None:
        reg = ConversationRegistry(ttl_seconds=1.0)
        reg.bind("telegram", "111", "sess-001")
        reg.bind("slack", "222", "sess-001")

        # Expire one
        b = reg.get_binding("telegram", "111")
        assert b is not None
        b.last_activity = time.monotonic() - 2.0

        bindings = reg.bindings_for_session("sess-001")
        assert len(bindings) == 1
        assert bindings[0].channel_name == "slack"


class TestActiveCount:
    def test_active_count(self) -> None:
        reg = ConversationRegistry()
        assert reg.active_count == 0
        reg.bind("telegram", "111", "sess-001")
        assert reg.active_count == 1
        reg.bind("slack", "222", "sess-002")
        assert reg.active_count == 2
        reg.unbind("sess-001")
        assert reg.active_count == 1


class TestValidatedTransitions:
    def test_valid_transitions_running_to_streaming(self) -> None:
        valid = VALID_CONVERSATION_TRANSITIONS[ConversationState.RUNNING]
        assert ConversationState.STREAMING in valid

    def test_valid_transitions_streaming_to_running(self) -> None:
        valid = VALID_CONVERSATION_TRANSITIONS[ConversationState.STREAMING]
        assert ConversationState.RUNNING in valid

    def test_invalid_transition_stopped_to_streaming(self) -> None:
        valid = VALID_CONVERSATION_TRANSITIONS[ConversationState.STOPPED]
        assert ConversationState.STREAMING not in valid
        assert len(valid) == 0

    def test_transition_state_validates(self) -> None:
        reg = ConversationRegistry()
        reg.bind("telegram", "12345", "sess-001")
        # RUNNING → STREAMING should succeed
        assert reg.transition_state("telegram", "12345", ConversationState.STREAMING) is True
        b = reg.get_binding("telegram", "12345")
        assert b is not None
        assert b.state == ConversationState.STREAMING

    def test_transition_state_rejects_invalid(self) -> None:
        reg = ConversationRegistry()
        reg.bind("telegram", "12345", "sess-001")
        reg.update_state("telegram", "12345", ConversationState.STOPPED)
        # STOPPED → STREAMING should fail
        assert reg.transition_state("telegram", "12345", ConversationState.STREAMING) is False

    def test_transition_state_nonexistent_returns_false(self) -> None:
        reg = ConversationRegistry()
        assert reg.transition_state("telegram", "99999", ConversationState.RUNNING) is False


class TestGetStateForSession:
    def test_get_state_for_session(self) -> None:
        reg = ConversationRegistry()
        reg.bind("telegram", "12345", "sess-001")
        assert reg.get_state_for_session("sess-001") == ConversationState.RUNNING

    def test_get_state_for_session_none(self) -> None:
        reg = ConversationRegistry()
        assert reg.get_state_for_session("nonexistent") is None


class TestQueuedMessages:
    def test_queued_messages_accumulate(self) -> None:
        reg = ConversationRegistry()
        b = reg.bind("telegram", "12345", "sess-001")
        b.queued_messages.append("hello")
        b.queued_messages.append("world")
        assert len(b.queued_messages) == 2

    def test_drain_queued_messages(self) -> None:
        reg = ConversationRegistry()
        b = reg.bind("telegram", "12345", "sess-001")
        b.queued_messages.extend(["msg1", "msg2", "msg3"])
        drained = reg.drain_queued_messages("sess-001")
        assert drained == ["msg1", "msg2", "msg3"]
        assert len(b.queued_messages) == 0

    def test_drain_empty_returns_empty(self) -> None:
        reg = ConversationRegistry()
        reg.bind("telegram", "12345", "sess-001")
        assert reg.drain_queued_messages("sess-001") == []

    def test_drain_nonexistent_session_returns_empty(self) -> None:
        reg = ConversationRegistry()
        assert reg.drain_queued_messages("nonexistent") == []
