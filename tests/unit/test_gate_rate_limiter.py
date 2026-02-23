"""Unit tests for channel message rate limiter."""

from __future__ import annotations

from atlasbridge.core.gate.rate_limiter import ChannelRateLimiter, _TokenBucket


class TestTokenBucket:
    """Low-level token bucket tests."""

    def test_initial_burst_allowance(self):
        bucket = _TokenBucket(rate=10.0, burst=3)
        assert bucket.tokens == 3.0

    def test_consume_reduces_tokens(self):
        bucket = _TokenBucket(rate=10.0, burst=3)
        assert bucket.consume() is True
        assert bucket.tokens < 3.0

    def test_burst_allows_rapid_messages(self):
        bucket = _TokenBucket(rate=10.0, burst=3)
        assert bucket.consume() is True
        assert bucket.consume() is True
        assert bucket.consume() is True

    def test_rejects_after_burst_exhausted(self):
        bucket = _TokenBucket(rate=10.0, burst=3)
        bucket.consume()
        bucket.consume()
        bucket.consume()
        assert bucket.consume() is False

    def test_refills_over_time(self):
        bucket = _TokenBucket(rate=10.0, burst=3)
        # Exhaust burst
        bucket.consume()
        bucket.consume()
        bucket.consume()
        assert bucket.consume() is False

        # Simulate 6 seconds passing (10/min = 1 token per 6 seconds)
        bucket.last_refill -= 6.0
        assert bucket.consume() is True

    def test_never_exceeds_burst(self):
        bucket = _TokenBucket(rate=60.0, burst=3)
        # Simulate a long wait — tokens should cap at burst
        bucket.last_refill -= 600.0
        bucket.consume()
        assert bucket.tokens <= 3.0


class TestChannelRateLimiter:
    """Rate limiter integration tests."""

    def test_allows_under_burst(self):
        limiter = ChannelRateLimiter(max_per_minute=10, burst=3)
        assert limiter.check("telegram", "user-1") is True
        assert limiter.check("telegram", "user-1") is True
        assert limiter.check("telegram", "user-1") is True

    def test_rejects_over_burst(self):
        limiter = ChannelRateLimiter(max_per_minute=10, burst=3)
        limiter.check("telegram", "user-1")
        limiter.check("telegram", "user-1")
        limiter.check("telegram", "user-1")
        assert limiter.check("telegram", "user-1") is False

    def test_independent_user_buckets(self):
        limiter = ChannelRateLimiter(max_per_minute=10, burst=2)
        # Exhaust user-1
        limiter.check("telegram", "user-1")
        limiter.check("telegram", "user-1")
        assert limiter.check("telegram", "user-1") is False
        # user-2 still has full burst
        assert limiter.check("telegram", "user-2") is True

    def test_independent_channel_buckets(self):
        limiter = ChannelRateLimiter(max_per_minute=10, burst=2)
        # Exhaust telegram
        limiter.check("telegram", "user-1")
        limiter.check("telegram", "user-1")
        assert limiter.check("telegram", "user-1") is False
        # Same user on slack has a separate bucket
        assert limiter.check("slack", "user-1") is True

    def test_floor_enforcement_zero(self):
        """max_per_minute=0 still allows at least 1/min."""
        limiter = ChannelRateLimiter(max_per_minute=0, burst=1)
        assert limiter.max_per_minute == 1
        assert limiter.check("telegram", "user-1") is True

    def test_floor_enforcement_negative(self):
        limiter = ChannelRateLimiter(max_per_minute=-5, burst=1)
        assert limiter.max_per_minute == 1

    def test_burst_floor(self):
        """Burst cannot be less than 1."""
        limiter = ChannelRateLimiter(max_per_minute=10, burst=0)
        assert limiter.burst == 1
        assert limiter.check("telegram", "user-1") is True

    def test_higher_rate_override(self):
        """Policy can raise rate above default."""
        limiter = ChannelRateLimiter(max_per_minute=30, burst=5)
        assert limiter.max_per_minute == 30
        assert limiter.burst == 5
        # Should allow 5 rapid messages
        for _ in range(5):
            assert limiter.check("telegram", "user-1") is True

    def test_reset_clears_all_buckets(self):
        limiter = ChannelRateLimiter(max_per_minute=10, burst=2)
        limiter.check("telegram", "user-1")
        limiter.check("telegram", "user-1")
        assert limiter.check("telegram", "user-1") is False
        limiter.reset()
        # After reset, burst is available again
        assert limiter.check("telegram", "user-1") is True

    def test_lazy_bucket_creation(self):
        limiter = ChannelRateLimiter()
        assert len(limiter._buckets) == 0
        limiter.check("telegram", "user-1")
        assert len(limiter._buckets) == 1
        limiter.check("slack", "user-2")
        assert len(limiter._buckets) == 2


class TestNoExternalDependencies:
    """Rate limiter must have no database or network dependencies."""

    def test_no_database_imports(self):
        import ast
        from pathlib import Path

        src = Path(__file__).resolve().parent.parent.parent / "src" / "atlasbridge"
        rl_path = src / "core" / "gate" / "rate_limiter.py"
        source = rl_path.read_text()
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        forbidden = ["sqlite3", "aiohttp", "httpx", "requests", "asyncio"]
        for imp in imports:
            for f in forbidden:
                assert not imp.startswith(f), f"rate_limiter imports {imp}"
