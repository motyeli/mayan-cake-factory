"""Rate limiting for the expensive customer-facing actions.

Image generation costs real money, so the limit has to be enforced in the
backend. The frontend counter is a courtesy; this is the control.

ponytail: in-process fixed-window counter. Correct for a single instance,
which is what one bakery at five orders a day needs. If the backend is ever
scaled to more than one replica, each replica gets its own window and the
effective limit multiplies — move the counter to Postgres (a small
`rate_limit_hits` table with a unique key on bucket+window) at that point.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from app.core.errors import RateLimitError


@dataclass
class _Window:
    count: int = 0
    resets_at: float = 0.0


@dataclass
class RateLimiter:
    """Fixed-window counter keyed by an arbitrary bucket string."""

    _windows: dict[str, _Window] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def hit(self, bucket: str, limit: int, per_seconds: int) -> None:
        """Count one use of `bucket`. Raises RateLimitError when over limit."""
        now = time.monotonic()
        with self._lock:
            window = self._windows.get(bucket)
            if window is None or now >= window.resets_at:
                window = _Window(count=0, resets_at=now + per_seconds)
                self._windows[bucket] = window

            if window.count >= limit:
                retry_after = max(1, int(window.resets_at - now))
                raise RateLimitError(
                    "That is a bit too fast. Please wait a moment and try again.",
                    {"retry_after_seconds": retry_after},
                )

            window.count += 1
            self._prune(now)

    def _prune(self, now: float) -> None:
        # Called under the lock. Keeps the dict from growing without bound
        # when many one-off sessions come and go.
        if len(self._windows) < 2048:
            return
        expired = [key for key, w in self._windows.items() if now >= w.resets_at]
        for key in expired:
            del self._windows[key]

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()


limiter = RateLimiter()
