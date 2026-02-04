"""Tests for repost module."""
import pytest
from unittest.mock import MagicMock, patch

from bsky_cli.repost import repost, unrepost


class TestRepost:
    """Tests for repost function."""
    
    @patch('bsky_cli.repost.requests.post')
    def test_repost_success(self, mock_post):
        """Test successful repost."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"uri": "at://did:plc:test/app.bsky.feed.repost/abc123"}
        )
        
        result = repost(
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
        assert json_data["collection"] == "app.bsky.feed.repost"
        assert json_data["record"]["$type"] == "app.bsky.feed.repost"
        assert json_data["record"]["subject"]["uri"] == "at://did:plc:other/app.bsky.feed.post/xyz"
    
    @patch('bsky_cli.repost.requests.post')
    def test_repost_failure(self, mock_post):
        """Test failed repost returns None."""
        mock_post.return_value = MagicMock(
            status_code=400,
            text="Bad request"
        )
        
        result = repost(
            "https://pds.test",
            "jwt-token", 
            "did:plc:myid",
            "at://did:plc:other/app.bsky.feed.post/xyz",
            "bafyreicid"
        )
        
        assert result is None


class TestUnrepost:
    """Tests for unrepost function."""
    
    @patch('bsky_cli.repost.requests.post')
    @patch('bsky_cli.repost.requests.get')
    def test_unrepost_success(self, mock_get, mock_post):
        """Test successful unrepost."""
        # First call: getRepostedBy
        # Second call: listRecords
        mock_get.side_effect = [
            MagicMock(
                status_code=200,
                json=lambda: {
                    "repostedBy": [{"did": "did:plc:myid"}]
                }
            ),
            MagicMock(
                status_code=200,
                json=lambda: {
                    "records": [
                        {
                            "uri": "at://did:plc:myid/app.bsky.feed.repost/repostkey123",
                            "value": {
                                "subject": {
                                    "uri": "at://did:plc:other/app.bsky.feed.post/xyz"
                                }
                            }
                        }
                    ]
                }
            )
        ]
        
        # Mock deleteRecord response
        mock_post.return_value = MagicMock(status_code=200)
        
        result = unrepost(
            "https://pds.test",
            "jwt-token",
            "did:plc:myid",
            "at://did:plc:other/app.bsky.feed.post/xyz"
        )
        
        assert result is True
        
        # Verify delete was called with correct rkey
        call_args = mock_post.call_args
        json_data = call_args.kwargs.get("json") or call_args[1].get("json")
        assert json_data["rkey"] == "repostkey123"
    
    @patch('bsky_cli.repost.requests.get')
    def test_unrepost_not_reposted(self, mock_get):
        """Test unrepost when post wasn't reposted."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"repostedBy": []}  # We're not in the list
        )
        
        result = unrepost(
            "https://pds.test",
            "jwt-token",
            "did:plc:myid",
            "at://did:plc:other/app.bsky.feed.post/xyz"
        )
        
        assert result is False
