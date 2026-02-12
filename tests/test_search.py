"""Tests for search module."""
import json
import pytest
import datetime as dt
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from bsky_cli.search import (
    search_posts,
    parse_relative_time,
    format_post,
)
from bsky_cli import search as search_mod


class TestParseRelativeTime:
    """Tests for parse_relative_time function."""

    def test_parses_hours(self):
        """Should parse hours correctly."""
        now = dt.datetime(2026, 2, 4, 12, 0, 0, tzinfo=dt.timezone.utc)
        result = parse_relative_time("24h", now)
        expected = dt.datetime(2026, 2, 3, 12, 0, 0, tzinfo=dt.timezone.utc)
        assert result == expected

    def test_parses_days(self):
        """Should parse days correctly."""
        now = dt.datetime(2026, 2, 4, 12, 0, 0, tzinfo=dt.timezone.utc)
        result = parse_relative_time("7d", now)
        expected = dt.datetime(2026, 1, 28, 12, 0, 0, tzinfo=dt.timezone.utc)
        assert result == expected

    def test_parses_weeks(self):
        """Should parse weeks correctly."""
        now = dt.datetime(2026, 2, 14, 12, 0, 0, tzinfo=dt.timezone.utc)
        result = parse_relative_time("2w", now)
        expected = dt.datetime(2026, 1, 31, 12, 0, 0, tzinfo=dt.timezone.utc)
        assert result == expected

    def test_parses_minutes(self):
        """Should parse minutes correctly."""
        now = dt.datetime(2026, 2, 4, 12, 30, 0, tzinfo=dt.timezone.utc)
        result = parse_relative_time("30m", now)
        expected = dt.datetime(2026, 2, 4, 12, 0, 0, tzinfo=dt.timezone.utc)
        assert result == expected

    def test_parses_iso_timestamp(self):
        """Should parse ISO timestamp."""
        now = dt.datetime(2026, 2, 4, 12, 0, 0, tzinfo=dt.timezone.utc)
        result = parse_relative_time("2026-01-01T00:00:00Z", now)
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 1

    def test_returns_none_for_invalid(self):
        """Should return None for invalid input."""
        now = dt.datetime.now(dt.timezone.utc)
        assert parse_relative_time("invalid", now) is None
        assert parse_relative_time("abc123", now) is None


class TestFormatPost:
    """Tests for format_post function."""

    def test_formats_basic_post(self):
        """Should format a post correctly."""
        post = {
            "uri": "at://did:plc:test/app.bsky.feed.post/123",
            "author": {
                "handle": "test.bsky.social",
                "displayName": "Test User"
            },
            "record": {
                "text": "Hello world!",
                "createdAt": "2026-02-04T12:00:00Z"
            },
            "likeCount": 5,
            "repostCount": 2,
            "replyCount": 1
        }
        
        output = format_post(post)
        assert "Test User (@test.bsky.social)" in output
        assert "Hello world!" in output
        assert "❤️ 5" in output
        assert "🔁 2" in output
        assert "💬 1" in output
        assert "https://bsky.app/profile/" in output

    def test_compact_mode_no_metrics(self):
        """Should omit metrics in compact mode."""
        post = {
            "uri": "at://did:plc:test/app.bsky.feed.post/123",
            "author": {"handle": "test", "displayName": ""},
            "record": {"text": "Hello", "createdAt": "2026-02-04T12:00:00Z"},
            "likeCount": 5, "repostCount": 2, "replyCount": 1
        }
        
        output = format_post(post, show_metrics=False)
        assert "❤️" not in output

    def test_truncates_long_text(self):
        """Should truncate very long text."""
        post = {
            "uri": "at://did:plc:test/app.bsky.feed.post/123",
            "author": {"handle": "test", "displayName": ""},
            "record": {"text": "x" * 600, "createdAt": "2026-02-04T12:00:00Z"},
            "likeCount": 0, "repostCount": 0, "replyCount": 0
        }
        
        output = format_post(post)
        assert "..." in output
        assert len([c for c in output if c == 'x']) <= 500


class TestSearchPosts:
    """Tests for search_posts function."""

    def test_basic_search(self):
        """Should make correct API call."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "posts": [
                {"uri": "at://x/123", "author": {"handle": "test"}, 
                 "record": {"text": "found"}}
            ]
        }
        
        with patch('requests.get') as mock_get:
            mock_get.return_value = mock_response
            results = search_posts(
                "https://bsky.social", "jwt-token", "test query"
            )
        
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args[1]["params"]["q"] == "test query"
        assert len(results) == 1

    def test_with_author_filter(self):
        """Should include author filter in API call."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"posts": []}
        
        with patch('requests.get') as mock_get:
            mock_get.return_value = mock_response
            search_posts(
                "https://bsky.social", "jwt", "query", 
                author="alice.bsky.social"
            )
        
        call_params = mock_get.call_args[1]["params"]
        assert call_params["author"] == "alice.bsky.social"

    def test_with_time_filters(self):
        """Should include time filters in API call."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"posts": []}
        
        with patch('requests.get') as mock_get:
            mock_get.return_value = mock_response
            search_posts(
                "https://bsky.social", "jwt", "query",
                since="24h"
            )
        
        call_params = mock_get.call_args[1]["params"]
        assert "since" in call_params

    def test_respects_limit(self):
        """Should respect limit parameter."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"posts": []}
        
        with patch('requests.get') as mock_get:
            mock_get.return_value = mock_response
            search_posts(
                "https://bsky.social", "jwt", "query",
                limit=10
            )
        
        call_params = mock_get.call_args[1]["params"]
        assert call_params["limit"] == 10

    def test_caps_limit_at_100(self):
        """Should cap limit at 100."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"posts": []}
        
        with patch('requests.get') as mock_get:
            mock_get.return_value = mock_response
            search_posts(
                "https://bsky.social", "jwt", "query",
                limit=500
            )
        
        call_params = mock_get.call_args[1]["params"]
        assert call_params["limit"] == 100


def test_search_run_json_outputs_raw_posts(monkeypatch, capsys):
    monkeypatch.setattr(search_mod, "get_session", lambda: ("https://pds.example", "did:plc:me", "jwt", "me.bsky.social"))
    monkeypatch.setattr(
        search_mod,
        "search_posts",
        lambda *args, **kwargs: [
            {"uri": "at://did:plc:test/app.bsky.feed.post/1", "record": {"text": "hello"}}
        ],
    )

    args = SimpleNamespace(
        query="hello",
        author=None,
        since=None,
        until=None,
        limit=1,
        sort="latest",
        compact=False,
        json=True,
    )

    rc = search_mod.run(args)
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data[0]["record"]["text"] == "hello"
