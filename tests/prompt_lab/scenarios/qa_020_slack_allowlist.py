"""QA-020: slack-reply-allowlist — Non-allowlisted Slack user cannot inject a reply."""

from __future__ import annotations

from tests.prompt_lab.simulator import (
    LabScenario,
    PTYSimulator,
    ScenarioRegistry,
    ScenarioResults,
    TelegramStub,
)
from atlasbridge.channels.slack.channel import SlackChannel
from atlasbridge.core.prompt.models import PromptType


@ScenarioRegistry.register
class SlackAllowlistScenario(LabScenario):
    scenario_id = "QA-020"
    name = "slack-reply-allowlist"

    async def setup(self, pty: PTYSimulator, stub: TelegramStub) -> None:
        await pty.write(b"Delete all files? [y/n] ")

    async def assert_results(self, results: ScenarioResults) -> None:
        assert len(results.prompt_events) >= 1
        event = results.prompt_events[0]
        assert event.prompt_type == PromptType.TYPE_YES_NO

        # Create a channel with one allowlisted user
        ch = SlackChannel(
            bot_token="xoxb-fake",
            app_token="xapp-fake",
            allowed_user_ids=["U1234567890"],
        )

        # Attempt action from a stranger — should be silently rejected
        stranger_id = "USTRANGER001"
        value = f"ans:{event.prompt_id}:{event.session_id}:{event.idempotency_key}:y"
        await ch._handle_action(value, stranger_id)
        assert ch._reply_queue.empty(), "Non-allowlisted user should not be able to enqueue a reply"

        # Same action from allowlisted user — should succeed
        await ch._handle_action(value, "U1234567890")
        assert not ch._reply_queue.empty(), "Allowlisted user should be able to reply"
        reply = ch._reply_queue.get_nowait()
        assert reply.value == "y"
        assert reply.channel_identity == "slack:U1234567890"
