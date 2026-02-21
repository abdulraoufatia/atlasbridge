"""
Prompt Lab simulator.

The simulator provides the infrastructure for deterministic QA scenarios.
Each scenario:
  1. Spawns a synthetic child process that writes scripted PTY output
  2. Feeds that output through the PromptDetector
  3. Uses a TelegramStub to intercept bot API calls
  4. Verifies assertions defined by the scenario

Usage::

    # Run a scenario directly
    results = await Simulator().run(PartialLinePromptScenario())
    assert results.passed

    # Via CLI
    atlasbridge lab run partial-line-prompt
    atlasbridge lab run --all

Architecture:
  Simulator
    ├── TelegramStub     — intercepts sendMessage / getUpdates
    ├── PTYSimulator     — write scripted bytes to a fake PTY master
    ├── ScenarioRunner   — wires detector → router → stub → assertions
    └── ScenarioRegistry — auto-discovers scenario classes in scenarios/

Timing:
  All timing in scenarios is deterministic. The PTYSimulator uses
  asyncio.sleep() for delays, not wall clock time. Tests run with a
  configurable time scale factor (default 1.0 = real time in CI,
  0.1 = 10x faster for unit test runs).
"""

from __future__ import annotations

import asyncio
import fnmatch
import importlib
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Callable
from typing import Any

from atlasbridge.core.prompt.detector import PromptDetector
from atlasbridge.core.prompt.models import PromptEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Telegram stub
# ---------------------------------------------------------------------------


@dataclass
class TelegramMessage:
    chat_id: int
    text: str
    reply_markup: dict[str, Any] | None = None
    message_id: int = 0


class TelegramStub:
    """
    Intercepts all Telegram Bot API calls made by TelegramChannel.

    Replaces the httpx.AsyncClient with a stub that records all outbound
    messages and allows scenarios to inject replies.
    """

    def __init__(self) -> None:
        self.messages: list[TelegramMessage] = []
        self._next_message_id = 1
        self._callback_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._outage_until: float = 0.0
        self._auto_reply_value: str | None = None
        self._update_id = 1

    def auto_reply(self, value: str) -> None:
        """Automatically deliver a button tap for the next prompt."""
        self._auto_reply_value = value

    async def deliver_callback(
        self,
        callback_data: str,
        user_id: int = 12345,
        update_id: int | None = None,
    ) -> None:
        """Inject a callback_query update (simulates button tap)."""
        uid = update_id if update_id is not None else self._update_id
        self._update_id = uid + 1
        await self._callback_queue.put(
            {
                "update_id": uid,
                "callback_query": {
                    "id": str(uid),
                    "from": {"id": user_id},
                    "data": callback_data,
                },
            }
        )

    def simulate_outage(self, seconds: float) -> None:
        """Make all API calls fail for *seconds* seconds."""
        self._outage_until = time.monotonic() + seconds

    def get_messages(self) -> list[TelegramMessage]:
        return list(self.messages)

    @property
    def message_count(self) -> int:
        return len(self.messages)

    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> dict[str, Any]:
        """Stub for sendMessage."""
        if time.monotonic() < self._outage_until:
            raise ConnectionError("Telegram stub: simulated outage")

        msg_id = self._next_message_id
        self._next_message_id += 1
        self.messages.append(
            TelegramMessage(
                chat_id=chat_id,
                text=text,
                reply_markup=kwargs.get("reply_markup"),
                message_id=msg_id,
            )
        )

        # Auto-reply: parse callback_data from keyboard and deliver automatically
        if self._auto_reply_value is not None:
            reply_markup = kwargs.get("reply_markup", {})
            for row in reply_markup.get("inline_keyboard", []):
                for btn in row:
                    if self._auto_reply_value in (btn.get("text", "").lower(), btn.get("text", "")):
                        cb_data = btn.get("callback_data", "")
                        if cb_data:
                            asyncio.create_task(self.deliver_callback(cb_data))
                            self._auto_reply_value = None
                            break

        return {"ok": True, "result": {"message_id": msg_id}}

    async def get_updates(  # noqa: E501
        self, offset: int = 0, timeout: int = 30, **kwargs: Any
    ) -> dict[str, Any]:
        """Stub for getUpdates (long-poll)."""
        if time.monotonic() < self._outage_until:
            await asyncio.sleep(1.0)
            raise ConnectionError("Telegram stub: simulated outage")

        try:
            update = await asyncio.wait_for(self._callback_queue.get(), timeout=0.1)
            return {"ok": True, "result": [update]}
        except asyncio.TimeoutError:
            return {"ok": True, "result": []}


# ---------------------------------------------------------------------------
# PTY simulator
# ---------------------------------------------------------------------------


class PTYSimulator:
    """
    Simulates a PTY master: accepts scripted byte sequences and feeds them
    to registered callbacks as if they came from a real child process.
    """

    def __init__(self) -> None:
        self._output_callbacks: list[Callable[[bytes], None]] = []
        self._is_alive = True

    def register_callback(self, cb: Callable[[bytes], None]) -> None:
        self._output_callbacks.append(cb)

    async def write(self, data: bytes, delay_s: float = 0.0) -> None:
        """Write bytes to the simulated PTY (feed to callbacks)."""
        if delay_s > 0:
            await asyncio.sleep(delay_s)
        for cb in self._output_callbacks:
            cb(data)

    async def write_partial(self, text: str, delay_s: float = 0.0) -> None:
        """Write text without a trailing newline."""
        await self.write(text.encode("utf-8"), delay_s=delay_s)

    async def block(self, seconds: float) -> None:
        """Simulate the child blocking on read() for *seconds* seconds."""
        await asyncio.sleep(seconds)

    def kill(self) -> None:
        """Simulate child process death."""
        self._is_alive = False

    def is_alive(self) -> bool:
        return self._is_alive


# ---------------------------------------------------------------------------
# Scenario interface
# ---------------------------------------------------------------------------


@dataclass
class ScenarioResults:
    """Results collected during a scenario run."""

    scenario_id: str = ""
    name: str = ""
    passed: bool = False
    elapsed_ms: float = 0.0
    prompt_events: list[PromptEvent] = field(default_factory=list)
    telegram_messages: list[TelegramMessage] = field(default_factory=list)
    injection_log: list[dict[str, Any]] = field(default_factory=list)
    audit_events: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""

    @property
    def injection_count(self) -> int:
        return len(self.injection_log)

    @property
    def telegram_message_count(self) -> int:
        return len(self.telegram_messages)

    def audit_events_contain(self, event_type: str) -> bool:
        return any(e.get("event_type") == event_type for e in self.audit_events)


class LabScenario:
    """Base class for all Prompt Lab scenarios."""

    scenario_id: str = ""  # e.g. "QA-001"
    name: str = ""  # e.g. "partial-line-prompt"
    platforms: list[str] = field(default_factory=lambda: ["macos", "linux"])

    async def setup(self, pty: PTYSimulator, stub: TelegramStub) -> None:
        """
        Write scripted output to the PTY and configure the stub.

        This coroutine is the scenario body. It controls what the simulated
        child process outputs and how the Telegram stub responds.
        """
        raise NotImplementedError

    def assert_results(self, results: ScenarioResults) -> None:
        """Raise AssertionError if results do not meet expected criteria."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Scenario registry
# ---------------------------------------------------------------------------


class ScenarioRegistry:
    """Auto-discovers and stores LabScenario subclasses."""

    _scenarios: dict[str, type[LabScenario]] = {}

    @classmethod
    def register(cls, scenario_cls: type[LabScenario]) -> type[LabScenario]:
        """Decorator: @ScenarioRegistry.register"""
        cls._scenarios[scenario_cls.name] = scenario_cls
        return scenario_cls

    @classmethod
    def get(cls, name: str) -> type[LabScenario]:
        if name not in cls._scenarios:
            available = ", ".join(sorted(cls._scenarios.keys())) or "(none)"
            raise KeyError(f"Unknown scenario: {name!r}. Available: {available}")
        return cls._scenarios[name]

    @classmethod
    def list_all(cls) -> dict[str, type[LabScenario]]:
        return dict(cls._scenarios)

    @classmethod
    def filter(cls, pattern: str) -> dict[str, type[LabScenario]]:
        return {
            name: sc
            for name, sc in cls._scenarios.items()
            if fnmatch.fnmatch(sc.scenario_id, pattern) or fnmatch.fnmatch(name, pattern)
        }

    @classmethod
    def discover(cls, scenarios_dir: Path | None = None) -> None:
        """Import all scenario modules from the scenarios/ directory."""
        if scenarios_dir is None:
            scenarios_dir = Path(__file__).parent / "scenarios"
        for path in sorted(scenarios_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            module_name = f"tests.prompt_lab.scenarios.{path.stem}"
            try:
                importlib.import_module(module_name)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to import scenario %s: %s", path.stem, exc)


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------


class Simulator:
    """
    Runs a LabScenario and collects results.

    Usage::

        results = await Simulator().run(MyScenario())
        assert results.passed
    """

    def __init__(self, time_scale: float = 1.0) -> None:
        self._time_scale = time_scale

    async def run(self, scenario: LabScenario) -> ScenarioResults:
        results = ScenarioResults(
            scenario_id=scenario.scenario_id,
            name=scenario.name,
        )
        pty = PTYSimulator()
        stub = TelegramStub()

        # Wire the detector to collect prompt events
        detector = PromptDetector(session_id=f"lab-{scenario.name}")
        detected: list[PromptEvent] = []

        def on_output(chunk: bytes) -> None:
            event = detector.analyse(chunk)
            if event:
                detected.append(event)

        pty.register_callback(on_output)

        start = time.monotonic()
        error = ""
        try:
            await scenario.setup(pty, stub)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            logger.exception("Scenario %s setup failed: %s", scenario.name, exc)

        results.elapsed_ms = (time.monotonic() - start) * 1000
        results.prompt_events = detected
        results.telegram_messages = stub.get_messages()
        results.error = error

        if not error:
            try:
                ret = scenario.assert_results(results)
                # Support async assert_results (e.g. scenarios that need await)
                if asyncio.iscoroutine(ret):
                    await ret
                results.passed = True
            except AssertionError as exc:
                results.error = str(exc)

        return results
