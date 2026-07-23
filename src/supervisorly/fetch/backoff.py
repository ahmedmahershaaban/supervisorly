"""Exponential backoff with jitter for transient failures (D-039, cost §5).

When a host answers 429 (rate-limited) or a 5xx, the polite response is to **wait longer
and try again a bounded number of times** — never to hammer it harder. Delays grow
exponentially, are capped, and carry jitter so a fleet of clients doesn't retry in
lockstep. After ``max_retries`` we give up and mark the source blocked/failed — we do not
escalate to a login or a faster loop (D-044).

The jitter source is injectable so tests are deterministic.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

# Statuses worth a polite retry: rate-limit + transient server errors.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 3
    base: float = 1.0       # seconds; first retry waits ~base
    cap: float = 30.0       # never wait longer than this, however many attempts

    def delay(self, attempt: int, jitter: Callable[[], float]) -> float:
        """Seconds to wait before retry number ``attempt`` (0-based).

        Exponential (``base * 2**attempt``) capped at ``cap``, plus a jitter fraction in
        ``[0, cap_of_step)``. ``jitter()`` returns a value in ``[0, 1)``; with 0 the delay
        is purely deterministic (used in tests).
        """
        step = min(self.cap, self.base * (2 ** max(0, attempt)))
        return step * (1.0 + jitter())
