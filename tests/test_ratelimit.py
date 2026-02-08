"""Tests for rate limiting."""

from unittest.mock import patch

from bsky_cli.ratelimit import RateLimiter
from bsky_cli import http


def test_rate_limiter_waits_when_limit_reached():
    limiter = RateLimiter(calls_per_minute=2)

    with patch("bsky_cli.ratelimit.time.time", side_effect=[0.0, 0.1, 0.2, 0.2, 60.1]), patch(
        "bsky_cli.ratelimit.time.sleep"
    ) as mock_sleep:
        limiter.wait_if_needed()
        limiter.wait_if_needed()
        limiter.wait_if_needed()

    assert mock_sleep.call_count >= 1
    # ~59.8s for third call in same minute window
    assert mock_sleep.call_args_list[0].args[0] > 59


@patch("bsky_cli.http._requests.get")
def test_http_wrapper_calls_underlying_requests(mock_get):
    http._limiter = RateLimiter(calls_per_minute=100)
    http.requests.get("https://example.com", timeout=1)
    mock_get.assert_called_once()
