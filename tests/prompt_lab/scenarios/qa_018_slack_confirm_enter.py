"""QA-018: slack-confirm-enter — Slack CONFIRM_ENTER Block Kit structure."""

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
class SlackConfirmEnterScenario(LabScenario):
    scenario_id = "QA-018"
    name = "slack-confirm-enter"

    async def setup(self, pty: PTYSimulator, stub: TelegramStub) -> None:
        await pty.write(b"Press Enter to continue...")

    def assert_results(self, results: ScenarioResults) -> None:
        assert len(results.prompt_events) >= 1, "Expected at least one prompt event"
        event = results.prompt_events[0]
        assert event.prompt_type == PromptType.TYPE_CONFIRM_ENTER, (
            f"Expected CONFIRM_ENTER, got {event.prompt_type}"
        )
        blocks = SlackChannel._build_blocks(event)
        actions = next(b for b in blocks if b["type"] == "actions")
        elements = actions["elements"]
        assert len(elements) == 2
        labels = [e["text"]["text"] for e in elements]
        assert "Send Enter" in labels
        assert "Cancel" in labels
        values = [e["value"] for e in elements]
        assert any(v.endswith(":enter") for v in values)
        assert any(v.endswith(":cancel") for v in values)
        # Cancel should be danger-styled
        cancel_el = next(e for e in elements if e["value"].endswith(":cancel"))
        assert cancel_el.get("style") == "danger"
