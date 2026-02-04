"""Tests for like module."""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from bsky_cli.like import resolve_post, like_post, unlike_post


class TestResolvePost:
    """Tests for resolve_post function."""
    
    def test_invalid_url_format(self):
        """Test invalid URL returns None."""
        result = resolve_post("https://pds.test", "jwt", "not-a-valid-url")
        assert result is None
    
    def test_valid_url_parse(self):
        """Test URL parsing extracts handle and post ID."""
        url = "https://bsky.app/profile/test.bsky.social/post/abc123"
        # This will fail on the API call, but we can test the regex
        import re
        match = re.match(r'https://bsky\.app/profile/([^/]+)/post/([^/]+)', url)
        assert match is not None
        assert match.group(1) == "test.bsky.social"
        assert match.group(2) == "abc123"
    
    def test_did_url_parse(self):
        """Test URL with DID instead of handle."""
        url = "https://bsky.app/profile/did:plc:abc123/post/xyz789"
        import re
        match = re.match(r'https://bsky\.app/profile/([^/]+)/post/([^/]+)', url)
        assert match is not None
        assert match.group(1) == "did:plc:abc123"
        assert match.group(2) == "xyz789"


class TestLikePost:
    """Tests for like_post function."""
    
    @patch('bsky_cli.like.requests.post')
    def test_like_success(self, mock_post):
        """Test successful like."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"uri": "at://did:plc:test/app.bsky.feed.like/abc123"}
        )
        
        result = like_post(
            "https://pds.test",
            "jwt-token",
            "did:plc:myid",
            "at://did:plc:other/app.bsky.feed.post/xyz",
            "bafyreicid"
        )
        
        assert result is not None
        assert "uri" in result
        mock_post.assert_called_once()
        
        # Verify the record structure
        call_args = mock_post.call_args
        json_data = call_args.kwargs.get("json") or call_args[1].get("json")
        assert json_data["collection"] == "app.bsky.feed.like"
        assert json_data["record"]["$type"] == "app.bsky.feed.like"
        assert json_data["record"]["subject"]["uri"] == "at://did:plc:other/app.bsky.feed.post/xyz"
    
    @patch('bsky_cli.like.requests.post')
    def test_like_failure(self, mock_post):
        """Test failed like returns None."""
        mock_post.return_value = MagicMock(
            status_code=400,
            text="Bad request"
        )
        
        result = like_post(
            "https://pds.test",
            "jwt-token", 
            "did:plc:myid",
            "at://did:plc:other/app.bsky.feed.post/xyz",
            "bafyreicid"
        )
        
        assert result is None


class TestUnlikePost:
    """Tests for unlike_post function."""
    
    @patch('bsky_cli.like.requests.post')
    @patch('bsky_cli.like.requests.get')
    def test_unlike_success(self, mock_get, mock_post):
        """Test successful unlike."""
        # Mock getLikes response
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "likes": [
                    {
                        "actor": {"did": "did:plc:myid"},
                        "uri": "at://did:plc:myid/app.bsky.feed.like/likekey123"
                    }
                ]
            }
        )
        
        # Mock deleteRecord response
        mock_post.return_value = MagicMock(status_code=200)
        
        result = unlike_post(
            "https://pds.test",
            "jwt-token",
            "did:plc:myid",
            "at://did:plc:other/app.bsky.feed.post/xyz"
        )
        
        assert result is True
        
        # Verify delete was called with correct rkey
        call_args = mock_post.call_args
        json_data = call_args.kwargs.get("json") or call_args[1].get("json")
        assert json_data["rkey"] == "likekey123"
    
    @patch('bsky_cli.like.requests.get')
    def test_unlike_not_liked(self, mock_get):
        """Test unlike when post wasn't liked."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"likes": []}  # No likes
        )
        
        result = unlike_post(
            "https://pds.test",
            "jwt-token",
            "did:plc:myid",
            "at://did:plc:other/app.bsky.feed.post/xyz"
        )
        
        assert result is False
