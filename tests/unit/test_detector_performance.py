"""Performance tests for PromptDetector — GA latency requirements.

Acceptance criteria (#67):
1. detect() completes within 5ms for a single call
2. Event loop latency stays below 50ms under 100k-line output flood
   (CI threshold: 100ms to tolerate shared-runner variability)
3. Pre-compiled regex patterns (no runtime compilation in hot path)
4. Benchmark results documented
"""

from __future__ import annotations

import re
import statistics
import time

import pytest

from atlasbridge.core.prompt.detector import (
    _CONFIRM_ENTER_PATTERNS,
    _FREE_TEXT_PATTERNS,
    _MULTIPLE_CHOICE_PATTERNS,
    _YES_NO_PATTERNS,
    PromptDetector,
)


@pytest.mark.performance
class TestDetectLatency:
    """Verify detect() completes within 5ms per call."""

    @pytest.fixture
    def detector(self):
        return PromptDetector(session_id="perf-test")

    def test_detect_plain_text_under_5ms(self, detector):
        """Ordinary output (no prompt) should return None in <5ms."""
        chunk = b"Building project... [=====>          ] 45%\r\n" * 10
        times = []
        for _ in range(200):
            start = time.perf_counter()
            result = detector.analyse(chunk)
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)
            assert result is None

        p99 = sorted(times)[int(len(times) * 0.99)]
        avg = statistics.mean(times)
        assert p99 < 5.0, f"p99 detect latency {p99:.2f}ms exceeds 5ms limit"
        assert avg < 2.0, f"avg detect latency {avg:.2f}ms exceeds 2ms limit"

    def test_detect_prompt_text_under_5ms(self, detector):
        """Prompt detection (pattern match hit) should complete in <5ms."""
        chunk = b"Do you want to proceed? [Y/n]: "
        times = []
        for _ in range(200):
            det = PromptDetector(session_id="perf-prompt")
            start = time.perf_counter()
            result = det.analyse(chunk)
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)
            assert result is not None

        p99 = sorted(times)[int(len(times) * 0.99)]
        assert p99 < 5.0, f"p99 prompt detect latency {p99:.2f}ms exceeds 5ms limit"

    def test_detect_long_output_under_5ms(self, detector):
        """Large single chunk (4KB) should still detect in <5ms."""
        # Simulate a large output chunk with a prompt at the end
        filler = b"x" * 4000 + b"\nContinue? [y/n]: "
        times = []
        for _ in range(100):
            det = PromptDetector(session_id="perf-long")
            start = time.perf_counter()
            det.analyse(filler)
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)

        p99 = sorted(times)[int(len(times) * 0.99)]
        assert p99 < 5.0, f"p99 long-output latency {p99:.2f}ms exceeds 5ms limit"

    def test_detect_ansi_heavy_under_5ms(self, detector):
        """ANSI-heavy output (color codes, cursor moves) should detect in <5ms."""
        ansi_line = b"\x1b[32m[OK]\x1b[0m Building module \x1b[1mfoo\x1b[0m...\r\n"
        chunk = ansi_line * 50
        times = []
        for _ in range(100):
            start = time.perf_counter()
            detector.analyse(chunk)
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)

        p99 = sorted(times)[int(len(times) * 0.99)]
        assert p99 < 5.0, f"p99 ANSI-heavy latency {p99:.2f}ms exceeds 5ms limit"


@pytest.mark.performance
class TestFloodLatency:
    """Verify event-loop latency under 100k-line output flood."""

    def test_100k_line_flood_p99_under_100ms(self):
        """Simulate 100k lines of output and measure per-call latency.

        Target: p99 <50ms on dedicated hardware. CI threshold relaxed to
        100ms to tolerate shared-runner variability (context switches,
        noisy neighbors). Avg and p50 should remain well under 50ms.
        """
        detector = PromptDetector(session_id="flood-test")
        line = b"2025-01-15T10:00:00 INFO  processing item 12345 of 99999\r\n"

        # Pre-allocate chunks (1000 lines each, ~100 chunks)
        chunk_size = 1000
        chunk = line * chunk_size
        n_chunks = 100  # 100 * 1000 = 100k lines

        times = []
        for _ in range(n_chunks):
            start = time.perf_counter()
            detector.analyse(chunk)
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)

        p99 = sorted(times)[int(len(times) * 0.99)]
        p50 = sorted(times)[int(len(times) * 0.50)]
        max_t = max(times)
        avg = statistics.mean(times)

        assert p99 < 100.0, (
            f"p99 flood latency {p99:.2f}ms exceeds 100ms CI limit "
            f"(avg={avg:.2f}ms, p50={p50:.2f}ms, max={max_t:.2f}ms)"
        )
        # Soft check: avg should stay well under 50ms
        assert avg < 50.0, f"avg flood latency {avg:.2f}ms exceeds 50ms target"

    def test_100k_line_flood_with_ansi(self):
        """100k lines of ANSI-colored output — p99 under 100ms (CI-safe)."""
        detector = PromptDetector(session_id="flood-ansi")
        line = (
            b"\x1b[36m2025-01-15T10:00:00\x1b[0m "
            b"\x1b[32mINFO\x1b[0m "
            b"processing \x1b[1mitem\x1b[0m 12345\r\n"
        )
        chunk = line * 1000
        n_chunks = 100

        times = []
        for _ in range(n_chunks):
            start = time.perf_counter()
            detector.analyse(chunk)
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)

        p99 = sorted(times)[int(len(times) * 0.99)]
        avg = statistics.mean(times)
        assert p99 < 100.0, f"p99 ANSI flood latency {p99:.2f}ms exceeds 100ms CI limit"
        assert avg < 50.0, f"avg ANSI flood latency {avg:.2f}ms exceeds 50ms target"

    def test_prompt_detection_after_flood(self):
        """After 100k lines of output, prompt detection still works instantly."""
        detector = PromptDetector(session_id="flood-then-prompt")

        # Flood phase — 100k lines
        flood_chunk = b"output line\r\n" * 1000
        for _ in range(100):
            detector.analyse(flood_chunk)

        # Prompt phase — should detect immediately
        start = time.perf_counter()
        event = detector.analyse(b"Continue? [y/n]: ")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert event is not None, "Prompt not detected after flood"
        assert elapsed_ms < 5.0, f"Post-flood prompt detection took {elapsed_ms:.2f}ms (limit: 5ms)"


@pytest.mark.performance
class TestPreCompiledPatterns:
    """Verify regex patterns are pre-compiled (not compiled at runtime)."""

    def test_yes_no_patterns_are_compiled(self):
        for i, pat in enumerate(_YES_NO_PATTERNS):
            assert isinstance(pat, re.Pattern), (
                f"YES_NO pattern {i} is {type(pat).__name__}, not compiled"
            )

    def test_confirm_enter_patterns_are_compiled(self):
        for i, pat in enumerate(_CONFIRM_ENTER_PATTERNS):
            assert isinstance(pat, re.Pattern), (
                f"CONFIRM_ENTER pattern {i} is {type(pat).__name__}, not compiled"
            )

    def test_multiple_choice_patterns_are_compiled(self):
        for i, pat in enumerate(_MULTIPLE_CHOICE_PATTERNS):
            assert isinstance(pat, re.Pattern), (
                f"MULTIPLE_CHOICE pattern {i} is {type(pat).__name__}, not compiled"
            )

    def test_free_text_patterns_are_compiled(self):
        for i, pat in enumerate(_FREE_TEXT_PATTERNS):
            assert isinstance(pat, re.Pattern), (
                f"FREE_TEXT pattern {i} is {type(pat).__name__}, not compiled"
            )

    def test_total_pattern_count(self):
        """Verify expected number of patterns (detect regressions)."""
        total = (
            len(_YES_NO_PATTERNS)
            + len(_CONFIRM_ENTER_PATTERNS)
            + len(_MULTIPLE_CHOICE_PATTERNS)
            + len(_FREE_TEXT_PATTERNS)
        )
        assert total == 16, f"Expected 16 pre-compiled patterns, got {total}"
