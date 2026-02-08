"""Rate-limited HTTP helpers used for BlueSky API calls."""

from __future__ import annotations

import requests as _requests

from .config import get
from .ratelimit import RateLimiter


_limiter: RateLimiter | None = None


def get_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        calls_per_minute = get("api.calls_per_minute", 60)
        _limiter = RateLimiter(calls_per_minute=calls_per_minute)
    return _limiter


class _RateLimitedRequests:
    """Drop-in subset of requests module with rate limiting."""

    @staticmethod
    def get(url: str, **kwargs):
        get_limiter().wait_if_needed()
        return _requests.get(url, **kwargs)

    @staticmethod
    def post(url: str, **kwargs):
        get_limiter().wait_if_needed()
        return _requests.post(url, **kwargs)


requests = _RateLimitedRequests()
