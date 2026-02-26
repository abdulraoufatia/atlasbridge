"""QA-019: slack-multiple-choice — Slack MULTIPLE_CHOICE numbered buttons."""

from __future__ import annotations

from tests.prompt_lab.simulator import (
    LabScenario,
    PTYSimulator,
    ScenarioRegistry,
    ScenarioResults,
    TelegramStub,
)
from atlasbridge.channels.slack.channel import SlackChannel
from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptType


@ScenarioRegistry.register
class SlackMultipleChoiceScenario(LabScenario):
    scenario_id = "QA-019"
    name = "slack-multiple-choice"

    async def setup(self, pty: PTYSimulator, stub: TelegramStub) -> None:
        await pty.write(
            b"Pick a strategy:\n  1) Fast\n  2) Balanced\n  3) Thorough\nEnter choice: "
        )

    def assert_results(self, results: ScenarioResults) -> None:
        assert len(results.prompt_events) >= 1, "Expected a MULTIPLE_CHOICE prompt event"
        event = results.prompt_events[0]
        assert event.prompt_type == PromptType.TYPE_MULTIPLE_CHOICE, (
            f"Expected MULTIPLE_CHOICE, got {event.prompt_type}"
        )

        # Build blocks for an event with 3 choices and verify numbering
        synthetic = PromptEvent(
            prompt_id="testpromptid001",
            session_id="sess-0000-0000-0000-0001",
            prompt_type=PromptType.TYPE_MULTIPLE_CHOICE,
            excerpt="Pick a strategy:\n  1) Fast\n  2) Balanced\n  3) Thorough",
            choices=["Fast", "Balanced", "Thorough"],
            confidence=Confidence.HIGH,
            idempotency_key="nonce001",
        )
        blocks = SlackChannel._build_blocks(synthetic)
        actions = next(b for b in blocks if b["type"] == "actions")
        elements = actions["elements"]
        assert len(elements) == 3
        labels = [e["text"]["text"] for e in elements]
        assert labels == ["Fast", "Balanced", "Thorough"]
        values = [e["value"] for e in elements]
        assert values[0].endswith(":1")
        assert values[1].endswith(":2")
        assert values[2].endswith(":3")
