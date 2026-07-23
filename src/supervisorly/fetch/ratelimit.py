"""Per-host politeness — a minimum interval between requests to the same host.

The politest source sets the pace (cost §5): Crossref's 3 req/s is the binding
constraint. The clock and sleep are injectable so tests don't actually sleep.
"""

from __future__ import annotations

import time
from collections.abc import Callable


class HostRateLimiter:
    def __init__(
        self,
        min_interval: float = 1.0,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._last: dict[str, float] = {}

    def wait(self, host: str) -> float:
        """Block until it is polite to hit ``host`` again. Returns the seconds slept."""
        now = self._clock()
        last = self._last.get(host)
        slept = 0.0
        if last is not None:
            gap = now - last
            if gap < self.min_interval:
                slept = self.min_interval - gap
                self._sleep(slept)
        self._last[host] = self._clock()
        return slept
