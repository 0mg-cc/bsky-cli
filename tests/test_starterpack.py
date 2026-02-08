"""Tests for starterpack module."""

from unittest.mock import MagicMock, patch

from bsky_cli.starterpack import create_starterpack


@patch("bsky_cli.starterpack.requests.post")
def test_create_starterpack_success(mock_post):
    mock_post.return_value = MagicMock(status_code=200, json=lambda: {"uri": "at://sp/1"})
    res = create_starterpack(
        "https://pds.test",
        "jwt",
        "did:plc:me",
        "AI on BlueSky",
        "at://did:plc:me/app.bsky.graph.list/abc",
    )
    assert res is not None
    assert res["uri"] == "at://sp/1"
