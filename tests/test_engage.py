"""Tests for engage module."""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from bsky_cli.engage import (
    Post,
    AlreadyRepliedFilter,
    AccountLimitFilter,
    MinTextLengthFilter,
    EngagementFilter,
    LowEngagementBonus,
    ConversationBonus,
    FreshPostBonus,
    FilterPipeline,
)


class TestPostDataclass:
    """Tests for Post dataclass."""
    
    def test_post_creation(self):
        """Test basic Post creation."""
        post = Post(
            uri="at://did:plc:test/app.bsky.feed.post/abc123",
            cid="bafyreiabc123",
            author_did="did:plc:test",
            author_handle="test.bsky.social",
            text="Hello world",
            created_at="2026-02-04T12:00:00Z",
        )
        assert post.uri == "at://did:plc:test/app.bsky.feed.post/abc123"
        assert post.author_handle == "test.bsky.social"
        assert post.base_score == 1.0
    
    def test_post_with_reply_info(self):
        """Test Post with reply information."""
        post = Post(
            uri="at://did:plc:test/app.bsky.feed.post/reply123",
            cid="bafyreireply",
            author_did="did:plc:test",
            author_handle="test.bsky.social",
            text="This is a reply",
            created_at="2026-02-04T12:00:00Z",
            is_reply=True,
            parent_uri="at://did:plc:other/app.bsky.feed.post/original",
            parent_cid="bafyreiparent",
            root_uri="at://did:plc:root/app.bsky.feed.post/thread",
            root_cid="bafyreiroot",
        )
        assert post.is_reply is True
        assert post.parent_uri is not None
        assert post.root_uri is not None
    
    def test_final_score_calculation(self):
        """Test score calculation with multipliers."""
        post = Post(
            uri="test", cid="test", author_did="test",
            author_handle="test", text="test", created_at="2026-02-04T12:00:00Z"
        )
        post.add_multiplier("fresh", 1.5)
        post.add_multiplier("conversation", 2.0)
        assert post.final_score == 3.0  # 1.0 * 1.5 * 2.0


class TestFilters:
    """Tests for filter classes."""
    
    def test_already_replied_filter(self):
        """Test AlreadyRepliedFilter."""
        f = AlreadyRepliedFilter()
        state = {"replied_posts": ["at://test/post/1", "at://test/post/2"]}
        
        post1 = Post(uri="at://test/post/1", cid="", author_did="", 
                     author_handle="", text="", created_at="")
        post2 = Post(uri="at://test/post/3", cid="", author_did="",
                     author_handle="", text="", created_at="")
        
        assert f.should_include(post1, state) is False  # Already replied
        assert f.should_include(post2, state) is True   # Not replied yet
    
    def test_min_text_length_filter(self):
        """Test MinTextLengthFilter."""
        f = MinTextLengthFilter(min_chars=20)
        state = {}
        
        short = Post(uri="", cid="", author_did="", author_handle="",
                     text="Hi", created_at="")
        long = Post(uri="", cid="", author_did="", author_handle="",
                    text="This is a much longer post with substance", created_at="")
        
        assert f.should_include(short, state) is False
        assert f.should_include(long, state) is True
    
    def test_engagement_filter(self):
        """Test EngagementFilter rejects crowded threads."""
        f = EngagementFilter(max_replies=50)
        state = {}
        
        crowded = Post(uri="", cid="", author_did="", author_handle="",
                       text="test", created_at="", reply_count=100)
        quiet = Post(uri="", cid="", author_did="", author_handle="",
                     text="test", created_at="", reply_count=5)
        
        assert f.should_include(crowded, state) is False
        assert f.should_include(quiet, state) is True


class TestMultipliers:
    """Tests for score multiplier classes."""
    
    def test_low_engagement_bonus(self):
        """Test LowEngagementBonus gives higher scores to less popular posts."""
        mult = LowEngagementBonus()
        
        viral = Post(uri="", cid="", author_did="", author_handle="",
                     text="test", created_at="", reply_count=50, like_count=200)
        quiet = Post(uri="", cid="", author_did="", author_handle="",
                     text="test", created_at="", reply_count=0, like_count=2)
        
        viral_score = mult.calculate(viral, {})
        quiet_score = mult.calculate(quiet, {})
        
        assert quiet_score > viral_score  # Quiet posts get bonus
    
    def test_fresh_post_bonus(self):
        """Test FreshPostBonus gives higher scores to recent posts."""
        mult = FreshPostBonus()
        
        now = datetime.now(timezone.utc)
        recent = Post(uri="", cid="", author_did="", author_handle="",
                      text="test", created_at=now.isoformat())
        old = Post(uri="", cid="", author_did="", author_handle="",
                   text="test", created_at=(now - timedelta(hours=10)).isoformat())
        
        recent_score = mult.calculate(recent, {})
        old_score = mult.calculate(old, {})
        
        assert recent_score >= old_score


class TestFilterPipeline:
    """Tests for FilterPipeline."""
    
    def test_pipeline_filters_posts(self):
        """Test pipeline filters and scores posts."""
        pipeline = FilterPipeline()
        pipeline.add_filter(MinTextLengthFilter(min_chars=10))
        
        posts = [
            Post(uri="1", cid="", author_did="d1", author_handle="a",
                 text="Short", created_at="2026-02-04T12:00:00Z"),
            Post(uri="2", cid="", author_did="d2", author_handle="b",
                 text="This is a longer post that passes", created_at="2026-02-04T12:00:00Z"),
        ]
        
        result = pipeline.process(posts, {})
        
        assert len(result) == 1
        assert result[0].uri == "2"
