"""QA-016: slack-yes-no — Slack YES/NO Block Kit delivery verified."""

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
class SlackYesNoScenario(LabScenario):
    scenario_id = "QA-016"
    name = "slack-yes-no"

    async def setup(self, pty: PTYSimulator, stub: TelegramStub) -> None:
        # Write a YES/NO prompt that should be detected
        await pty.write(b"Continue? [y/n] ")

    def assert_results(self, results: ScenarioResults) -> None:
        assert len(results.prompt_events) >= 1, "Expected at least one prompt event"
        event = results.prompt_events[0]
        assert event.prompt_type == PromptType.TYPE_YES_NO, (
            f"Expected YES_NO, got {event.prompt_type}"
        )
        # Verify that SlackChannel._build_blocks generates the correct Block Kit structure
        blocks = SlackChannel._build_blocks(event)
        actions = next(b for b in blocks if b["type"] == "actions")
        elements = actions["elements"]
        assert len(elements) == 2
        values = [e["value"] for e in elements]
        assert any(v.endswith(":y") for v in values), "Missing 'Yes' button value"
        assert any(v.endswith(":n") for v in values), "Missing 'No' button value"
        # Verify button styles
        styles = {e["text"]["text"]: e.get("style") for e in elements}
        assert styles.get("Yes") == "primary"
        assert styles.get("No") == "danger"
