from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod

from briefing.schemas import CollectorResult


class BaseCollector(ABC):
    """All data source collectors implement this interface."""

    @abstractmethod
    async def collect(self, tickers: list[str]) -> CollectorResult:
        """Fetch data for the given tickers. Returns normalized result."""
        ...

    @abstractmethod
    def name(self) -> str:
        """Human-readable name for logging."""
        ...


class RateLimiter:
    """Simple token bucket rate limiter for API calls."""

    def __init__(self, calls_per_period: int, period_seconds: float) -> None:
        self._calls_per_period = calls_per_period
        self._period = period_seconds
        self._tokens = calls_per_period
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a call slot is available."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            refill = int(elapsed / self._period * self._calls_per_period)
            if refill > 0:
                self._tokens = min(self._calls_per_period, self._tokens + refill)
                self._last_refill = now

            if self._tokens <= 0:
                wait_time = self._period / self._calls_per_period
                await asyncio.sleep(wait_time)
                self._tokens = 1

            self._tokens -= 1
