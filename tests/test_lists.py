"""Tests for lists module."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from bsky_cli.lists import create_list, add_to_list, remove_from_list, delete_list, run


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


@patch("bsky_cli.lists.requests.post")
@patch("bsky_cli.lists.requests.get")
@patch("bsky_cli.lists.resolve_handle")
def test_remove_from_list_deletes_matching_list_item(mock_resolve, mock_get, mock_post):
    mock_resolve.return_value = "did:plc:alice"
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "items": [
                {
                    "uri": "at://did:plc:me/app.bsky.graph.listitem/item123",
                    "subject": {"did": "did:plc:alice", "handle": "alice.bsky.social"},
                }
            ]
        },
    )
    mock_post.return_value = MagicMock(status_code=200)

    ok = remove_from_list(
        "https://pds.test",
        "jwt",
        "did:plc:me",
        "at://did:plc:me/app.bsky.graph.list/list123",
        "alice.bsky.social",
    )

    assert ok is True
    body = mock_post.call_args.kwargs["json"]
    assert body["repo"] == "did:plc:me"
    assert body["collection"] == "app.bsky.graph.listitem"
    assert body["rkey"] == "item123"


@patch("bsky_cli.lists.requests.post")
def test_delete_list_deletes_list_record(mock_post):
    mock_post.return_value = MagicMock(status_code=200)

    ok = delete_list(
        "https://pds.test",
        "jwt",
        "did:plc:me",
        "at://did:plc:me/app.bsky.graph.list/list123",
    )

    assert ok is True
    body = mock_post.call_args.kwargs["json"]
    assert body["repo"] == "did:plc:me"
    assert body["collection"] == "app.bsky.graph.list"
    assert body["rkey"] == "list123"


@patch("bsky_cli.lists.get_session")
@patch("bsky_cli.lists.get_lists")
@patch("bsky_cli.lists.remove_from_list")
def test_run_remove_uses_target_list_and_actor(mock_remove, mock_get_lists, mock_get_session, capsys):
    mock_get_session.return_value = ("https://pds.test", "did:plc:me", "jwt", "me.bsky.social")
    mock_get_lists.return_value = [{"name": "AI", "uri": "at://did:plc:me/app.bsky.graph.list/list123"}]
    mock_remove.return_value = True

    rc = run(SimpleNamespace(lists_command="remove", list_name="AI", handle="@alice.bsky.social"))

    assert rc == 0
    mock_remove.assert_called_once_with(
        "https://pds.test",
        "jwt",
        "did:plc:me",
        "at://did:plc:me/app.bsky.graph.list/list123",
        "alice.bsky.social",
    )
    assert "Removed @alice.bsky.social from AI" in capsys.readouterr().out
