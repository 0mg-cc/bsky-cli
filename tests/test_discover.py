from unittest.mock import patch

from bsky_cli.discover import get_follows, DiscoverRuntimeTimeout


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@patch("bsky_cli.discover.requests.get")
def test_get_follows_stops_when_cursor_does_not_advance(mock_get):
    # Reproduces a pagination loop where API keeps returning same cursor.
    mock_get.return_value = _Resp({
        "follows": [{"did": "did:example:a"}],
        "cursor": "same-cursor",
    })

    follows = get_follows("https://example", "jwt", "did:me")

    # Should terminate instead of looping forever.
    assert len(follows) == 2
    assert mock_get.call_count == 2


@patch("bsky_cli.discover.requests.get")
def test_get_follows_honors_max_pages_guard(mock_get):
    counter = {"n": 0}

    def _side_effect(*args, **kwargs):
        counter["n"] += 1
        return _Resp({
            "follows": [{"did": f"did:example:{counter['n']}"}],
            "cursor": f"cursor-{counter['n']}",
        })

    mock_get.side_effect = _side_effect

    follows = get_follows("https://example", "jwt", "did:me", max_pages=3)

    assert len(follows) == 3
    assert mock_get.call_count == 3


@patch("bsky_cli.discover.requests.get")
def test_get_follows_respects_runtime_guard_between_pages(mock_get):
    """Guard is checked between pagination pages inside get_follows()."""

    class PageGuard:
        def __init__(self):
            self.checks = 0
        def check(self, phase):
            self.checks += 1
            return self.checks >= 3  # timeout on 3rd page

    counter = {"n": 0}

    def _side_effect(*args, **kwargs):
        counter["n"] += 1
        return _Resp({
            "follows": [{"did": f"did:example:{counter['n']}"}],
            "cursor": f"cursor-{counter['n']}",
        })

    mock_get.side_effect = _side_effect
    guard = PageGuard()

    try:
        follows = get_follows("https://example", "jwt", "did:me", max_pages=100, guard=guard)
        assert False, "Should have raised DiscoverRuntimeTimeout"
    except DiscoverRuntimeTimeout:
        pass

    # Guard fired on 3rd check → only 2 pages completed
    assert mock_get.call_count == 2
    assert guard.checks == 3
