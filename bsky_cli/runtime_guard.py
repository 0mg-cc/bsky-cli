from __future__ import annotations

import time

TIMEOUT_EXIT_CODE = 124


class RuntimeGuard:
    """Simple wall-clock runtime guard for long-running commands."""

    def __init__(self, max_runtime_seconds: int | None = None):
        self.max_runtime_seconds = max_runtime_seconds
        self._deadline = None
        if max_runtime_seconds is not None and max_runtime_seconds >= 0:
            self._deadline = time.monotonic() + max_runtime_seconds

    def check(self, phase: str) -> bool:
        """Return True when deadline is exceeded."""
        if self._deadline is None:
            return False
        if time.monotonic() <= self._deadline:
            return False
        print(f"⏱️ Timed out after {self.max_runtime_seconds}s during phase: {phase}")
        return True


def log_phase(phase: str):
    print(f"⏱️ Phase: {phase}")
