"""aegis lab — Prompt Lab CLI commands."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from rich.console import Console


def _ensure_tests_importable() -> None:
    """Add project root to sys.path so tests.prompt_lab can be imported."""
    # This file: src/aegis/cli/_lab.py  →  parents[3] = project root
    project_root = Path(__file__).parents[3]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))


def _import_scenario_registry() -> object:
    """Import ScenarioRegistry, raising a user-friendly error if tests/ is not available."""
    _ensure_tests_importable()
    try:
        from tests.prompt_lab.simulator import ScenarioRegistry  # type: ignore[import]

        return ScenarioRegistry
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "atlasbridge lab requires the source repository.\n"
            "Install in editable mode: pip install -e '.[dev]'\n"
            "Then run from the repo root."
        ) from exc


def cmd_lab_list(as_json: bool, console: Console) -> None:
    registry = _import_scenario_registry()

    registry.discover()  # type: ignore[attr-defined]
    scenarios = registry.list_all()  # type: ignore[attr-defined]

    if as_json:
        rows = [{"id": cls.scenario_id, "name": name} for name, cls in scenarios.items()]  # type: ignore[attr-defined]
        print(json.dumps(rows, indent=2))
        return

    console.print("[bold]AtlasBridge Prompt Lab — Registered Scenarios[/bold]\n")
    if not scenarios:
        console.print("  [dim]No scenarios registered.[/dim]")
        console.print("\n  Add scenario modules to tests/prompt_lab/scenarios/")
        return

    console.print(f"  {'QA ID':<10} {'Name':<35} Status")
    console.print(f"  {'─' * 10} {'─' * 35} {'─' * 10}")
    for name, cls in sorted(scenarios.items(), key=lambda x: x[1].scenario_id):  # type: ignore[attr-defined]
        console.print(f"  {cls.scenario_id:<10} {name:<35} [green]registered[/green]")
    console.print(f"\n{len(scenarios)} scenarios registered.")


def cmd_lab_run(
    scenario: str,
    run_all: bool,
    pattern: str,
    verbose: bool,
    as_json: bool,
    console: Console,
) -> None:
    registry = _import_scenario_registry()
    import asyncio

    _ensure_tests_importable()
    from tests.prompt_lab.simulator import Simulator  # type: ignore[import]

    registry.discover()  # type: ignore[attr-defined]

    if run_all:
        targets = registry.list_all()  # type: ignore[attr-defined]
    elif pattern:
        targets = registry.filter(pattern)  # type: ignore[attr-defined]
    elif scenario:
        try:
            targets = {scenario: registry.get(scenario)}  # type: ignore[attr-defined]
        except KeyError as exc:
            console.print(f"[red]Error:[/red] {exc}")
            return
    else:
        console.print("[red]Error:[/red] Specify a scenario name, --all, or --filter PATTERN")
        return

    if not targets:
        console.print("[yellow]No matching scenarios found.[/yellow]")
        return

    sim = Simulator()
    all_results = []
    passed = 0

    for name, cls in targets.items():
        instance = cls()
        if verbose:
            console.print(f"  Running [cyan]{cls.scenario_id}[/cyan] {name}...")
        results = asyncio.run(sim.run(instance))
        all_results.append(results)
        if results.passed:
            passed += 1

    if as_json:
        print(
            json.dumps(
                [
                    {
                        "id": r.scenario_id,
                        "name": r.name,
                        "passed": r.passed,
                        "elapsed_ms": r.elapsed_ms,
                        "error": r.error,
                    }
                    for r in all_results
                ],
                indent=2,
            )
        )
        return

    console.print()
    for r in all_results:
        status = "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]"
        console.print(f"  {r.scenario_id:<10} {r.name:<35} {status}  ({r.elapsed_ms:.0f}ms)")
        if not r.passed and r.error:
            console.print(f"             [dim]{r.error}[/dim]")

    total = len(all_results)
    console.print(f"\n{passed}/{total} passed.")
    if passed < total:
        raise SystemExit(1)
