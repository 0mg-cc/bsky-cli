"""Client-side API rate limiting."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque

LOG = logging.getLogger(__name__)


class RateLimiter:
    """Sliding-window rate limiter (calls/minute)."""

    def __init__(self, calls_per_minute: int = 60):
        self.limit = max(1, int(calls_per_minute))
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def wait_if_needed(self) -> float:
        """Block if needed and return sleep duration (seconds)."""
        sleep_for = 0.0
        while True:
            with self._lock:
                now = time.time()
                cutoff = now - 60
                while self._calls and self._calls[0] < cutoff:
                    self._calls.popleft()

                if len(self._calls) < self.limit:
                    self._calls.append(now)
                    return sleep_for

                sleep_for = max(0.0, 60 - (now - self._calls[0]))

            if sleep_for > 0:
                LOG.info("Rate limiting BlueSky API calls: sleeping %.2fs (limit=%d/min)", sleep_for, self.limit)
                time.sleep(sleep_for)
