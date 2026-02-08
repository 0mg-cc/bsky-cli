"""Tests for bookmarks module."""

from unittest.mock import MagicMock, patch

from bsky_cli.bookmarks import (
    parse_post_url,
    resolve_post_uri,
    create_bookmark,
    delete_bookmark,
    get_bookmarks,
)


def test_parse_post_url_valid():
    parsed = parse_post_url("https://bsky.app/profile/alice.bsky.social/post/abc123")
    assert parsed == ("alice.bsky.social", "abc123")


def test_parse_post_url_invalid():
    assert parse_post_url("https://example.com") is None


@patch("bsky_cli.bookmarks.requests.get")
def test_resolve_post_uri_handle(mock_get):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"did": "did:plc:alice"})
    uri = resolve_post_uri("https://pds.test", "jwt", "https://bsky.app/profile/alice.bsky.social/post/abc123")
    assert uri == "at://did:plc:alice/app.bsky.feed.post/abc123"


@patch("bsky_cli.bookmarks.requests.post")
@patch("bsky_cli.bookmarks.resolve_post_uri")
def test_create_bookmark_success(mock_resolve, mock_post):
    mock_resolve.return_value = "at://did:plc:alice/app.bsky.feed.post/abc123"
    mock_post.return_value = MagicMock(status_code=200, text="")

    assert create_bookmark("https://pds.test", "jwt", "did:plc:me", "https://bsky.app/profile/a/post/b") is True


@patch("bsky_cli.bookmarks.requests.post")
@patch("bsky_cli.bookmarks.resolve_post_uri")
def test_delete_bookmark_success(mock_resolve, mock_post):
    mock_resolve.return_value = "at://did:plc:alice/app.bsky.feed.post/abc123"
    mock_post.return_value = MagicMock(status_code=200, text="")

    assert delete_bookmark("https://pds.test", "jwt", "did:plc:me", "https://bsky.app/profile/a/post/b") is True


@patch("bsky_cli.bookmarks.requests.get")
def test_get_bookmarks(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"bookmarks": [{"post": {"uri": "at://x"}}]},
        text="",
    )

    items = get_bookmarks("https://pds.test", "jwt", 10)
    assert len(items) == 1
