"""Tests for lists module."""

from unittest.mock import MagicMock, patch

from bsky_cli.lists import create_list, add_to_list


@patch("bsky_cli.lists.requests.post")
def test_create_list_success(mock_post):
    mock_post.return_value = MagicMock(status_code=200, json=lambda: {"uri": "at://list/1"})
    res = create_list("https://pds.test", "jwt", "did:plc:me", "AI Agents")
    assert res is not None
    assert res["uri"] == "at://list/1"


@patch("bsky_cli.lists.requests.post")
@patch("bsky_cli.lists.resolve_handle")
def test_add_to_list_resolves_handle(mock_resolve, mock_post):
    mock_resolve.return_value = "did:plc:alice"
    mock_post.return_value = MagicMock(status_code=200, json=lambda: {"uri": "at://listitem/1"})
    res = add_to_list("https://pds.test", "jwt", "did:plc:me", "at://list/1", "alice.bsky.social")
    assert res is not None
    body = mock_post.call_args.kwargs["json"]
    assert body["record"]["subject"] == "did:plc:alice"
