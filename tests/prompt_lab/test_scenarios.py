"""Parametrized pytest wrapper for all Prompt Lab scenarios."""

from __future__ import annotations

import pytest

from tests.prompt_lab.simulator import LabScenario, ScenarioRegistry, Simulator

# Discover all scenarios once at module import time.
ScenarioRegistry.discover()
_ALL_SCENARIOS = list(ScenarioRegistry.list_all().items())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "scenario_cls"),
    _ALL_SCENARIOS,
    ids=[name for name, _ in _ALL_SCENARIOS],
)
async def test_prompt_lab_scenario(name: str, scenario_cls: type[LabScenario]) -> None:
    """Run a single Prompt Lab scenario through the Simulator."""
    scenario = scenario_cls()
    results = await Simulator().run(scenario)
    assert results.passed, f"Scenario {scenario.scenario_id} ({name}) failed: {results.error}"
