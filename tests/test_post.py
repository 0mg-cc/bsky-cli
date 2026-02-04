"""Tests for post module."""
import pytest
from unittest.mock import patch, MagicMock

from bsky_cli.post import (
    detect_facets,
    resolve_post,
    create_quote_embed,
)


class TestDetectFacets:
    """Tests for detect_facets function."""

    def test_detects_urls(self):
        """Should detect URLs in text."""
        text = "Check out https://example.com for more info"
        facets = detect_facets(text)
        assert facets is not None
        assert len(facets) == 1
        assert facets[0]["features"][0]["$type"] == "app.bsky.richtext.facet#link"
        assert facets[0]["features"][0]["uri"] == "https://example.com"

    def test_detects_hashtags(self):
        """Should detect hashtags in text."""
        text = "Working on #AI and #ML projects"
        facets = detect_facets(text)
        assert facets is not None
        assert len(facets) == 2
        tags = [f["features"][0]["tag"] for f in facets if f["features"][0]["$type"] == "app.bsky.richtext.facet#tag"]
        assert "AI" in tags
        assert "ML" in tags

    def test_detects_mixed(self):
        """Should detect both URLs and hashtags."""
        text = "See https://example.com #tech"
        facets = detect_facets(text)
        assert facets is not None
        assert len(facets) == 2

    def test_returns_none_for_no_facets(self):
        """Should return None when no facets found."""
        text = "Plain text with nothing special"
        facets = detect_facets(text)
        assert facets is None

    def test_strips_trailing_punctuation_from_urls(self):
        """Should strip trailing punctuation from URLs."""
        text = "Visit https://example.com!"
        facets = detect_facets(text)
        assert facets[0]["features"][0]["uri"] == "https://example.com"


class TestResolvePost:
    """Tests for resolve_post function."""

    def test_resolves_post_url_with_handle(self):
        """Should resolve post URL with handle."""
        mock_handle_response = MagicMock()
        mock_handle_response.json.return_value = {"did": "did:plc:test123"}
        
        mock_posts_response = MagicMock()
        mock_posts_response.json.return_value = {
            "posts": [{"cid": "cid123"}]
        }
        
        with patch('requests.get') as mock_get:
            mock_get.side_effect = [mock_handle_response, mock_posts_response]
            result = resolve_post(
                "https://bsky.social", "jwt",
                "https://bsky.app/profile/test.bsky.social/post/abc123"
            )
        
        assert result is not None
        uri, cid = result
        assert uri == "at://did:plc:test123/app.bsky.feed.post/abc123"
        assert cid == "cid123"

    def test_resolves_post_url_with_did(self):
        """Should resolve post URL with DID (no handle resolution needed)."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "posts": [{"cid": "cid456"}]
        }
        
        with patch('requests.get') as mock_get:
            mock_get.return_value = mock_response
            result = resolve_post(
                "https://bsky.social", "jwt",
                "https://bsky.app/profile/did:plc:xyz/post/def456"
            )
        
        assert result is not None
        uri, cid = result
        assert uri == "at://did:plc:xyz/app.bsky.feed.post/def456"
        assert cid == "cid456"

    def test_returns_none_for_invalid_url(self):
        """Should return None for invalid URL format."""
        result = resolve_post(
            "https://bsky.social", "jwt",
            "https://example.com/not/a/bsky/url"
        )
        assert result is None


class TestCreateQuoteEmbed:
    """Tests for create_quote_embed function."""

    def test_creates_correct_embed_structure(self):
        """Should create correct quote embed structure."""
        embed = create_quote_embed(
            "at://did:plc:test/app.bsky.feed.post/123",
            "cid123"
        )
        
        assert embed["$type"] == "app.bsky.embed.record"
        assert embed["record"]["uri"] == "at://did:plc:test/app.bsky.feed.post/123"
        assert embed["record"]["cid"] == "cid123"
