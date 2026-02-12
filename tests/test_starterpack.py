"""Tests for starterpack module."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from bsky_cli.starterpack import create_starterpack, delete_starterpack, run


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


@patch("bsky_cli.starterpack.requests.post")
def test_delete_starterpack_by_uri(mock_post):
    mock_post.return_value = MagicMock(status_code=200)

    ok = delete_starterpack(
        "https://pds.test",
        "jwt",
        "did:plc:me",
        "at://did:plc:me/app.bsky.graph.starterpack/sp123",
    )

    assert ok is True
    body = mock_post.call_args.kwargs["json"]
    assert body["repo"] == "did:plc:me"
    assert body["collection"] == "app.bsky.graph.starterpack"
    assert body["rkey"] == "sp123"


@patch("bsky_cli.starterpack.get_session")
@patch("bsky_cli.starterpack.list_starterpacks")
@patch("bsky_cli.starterpack.delete_starterpack")
def test_run_delete_resolves_by_name(mock_delete, mock_list, mock_get_session, capsys):
    mock_get_session.return_value = ("https://pds.test", "did:plc:me", "jwt", "me.bsky.social")
    mock_list.return_value = [
        {
            "uri": "at://did:plc:me/app.bsky.graph.starterpack/sp123",
            "record": {"name": "AI Pack"},
        }
    ]
    mock_delete.return_value = True

    rc = run(SimpleNamespace(starterpack_command="delete", target="AI Pack"))

    assert rc == 0
    mock_delete.assert_called_once_with(
        "https://pds.test",
        "jwt",
        "did:plc:me",
        "at://did:plc:me/app.bsky.graph.starterpack/sp123",
    )
    assert "Deleted starter pack: AI Pack" in capsys.readouterr().out
