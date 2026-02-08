from unittest.mock import patch

from bsky_cli.discover import get_follows


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
