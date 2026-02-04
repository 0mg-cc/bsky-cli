"""Tests for engage module."""
import pytest
import datetime as dt
from unittest.mock import patch, MagicMock

from bsky_cli.engage import (
    Post,
    PostFilter,
    AlreadyRepliedFilter,
    AccountLimitFilter,
    MinTextLengthFilter,
    EngagementFilter,
    ScoreMultiplier,
    LowEngagementBonus,
    FreshPostBonus,
    FilterPipeline,
    filter_recent_posts,
    create_default_pipeline,
)


# ============================================================================
# Post Data Class Tests
# ============================================================================

class TestPost:
    """Tests for Post dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        post = Post(
            uri="at://did:plc:test/app.bsky.feed.post/123",
            cid="cid123",
            author_did="did:plc:test",
            author_handle="test.bsky.social",
            text="Hello world",
            created_at="2026-02-04T12:00:00Z"
        )
        assert post.reply_count == 0
        assert post.like_count == 0
        assert post.base_score == 1.0
        assert post.is_reply is False

    def test_final_score_calculation(self):
        """Should calculate final score with multipliers."""
        post = Post(
            uri="x", cid="x", author_did="x", author_handle="x",
            text="test", created_at="2026-01-01T00:00:00Z",
            base_score=1.0
        )
        post.add_multiplier("bonus1", 1.5)
        post.add_multiplier("bonus2", 2.0)
        assert post.final_score == 3.0  # 1.0 * 1.5 * 2.0

    def test_multipliers_replace_same_name(self):
        """Should replace multipliers with same name."""
        post = Post(
            uri="x", cid="x", author_did="x", author_handle="x",
            text="test", created_at="2026-01-01T00:00:00Z"
        )
        post.add_multiplier("bonus", 2.0)
        post.add_multiplier("bonus", 3.0)
        assert post.final_score == 3.0


# ============================================================================
# Filter Tests
# ============================================================================

class TestAlreadyRepliedFilter:
    """Tests for AlreadyRepliedFilter."""

    def test_excludes_replied_posts(self):
        """Should exclude posts already replied to."""
        f = AlreadyRepliedFilter()
        post = Post(
            uri="at://x/post/123", cid="x", author_did="x",
            author_handle="x", text="test", created_at="x"
        )
        state = {"replied_posts": ["at://x/post/123"]}
        assert f.should_include(post, state) is False

    def test_includes_new_posts(self):
        """Should include posts not yet replied to."""
        f = AlreadyRepliedFilter()
        post = Post(
            uri="at://x/post/456", cid="x", author_did="x",
            author_handle="x", text="test", created_at="x"
        )
        state = {"replied_posts": ["at://x/post/123"]}
        assert f.should_include(post, state) is True


class TestAccountLimitFilter:
    """Tests for AccountLimitFilter."""

    def test_allows_first_reply_to_account(self):
        """Should allow first reply to an account."""
        f = AccountLimitFilter(max_per_session=1)
        post = Post(
            uri="x", cid="x", author_did="did:plc:new",
            author_handle="x", text="test", created_at="x"
        )
        state = {"replied_accounts_today": ["did:plc:other"]}
        assert f.should_include(post, state) is True

    def test_blocks_second_reply_to_same_account(self):
        """Should block second reply to same account."""
        f = AccountLimitFilter(max_per_session=1)
        post = Post(
            uri="x", cid="x", author_did="did:plc:existing",
            author_handle="x", text="test", created_at="x"
        )
        state = {"replied_accounts_today": ["did:plc:existing"]}
        assert f.should_include(post, state) is False

    def test_respects_custom_limit(self):
        """Should respect custom max_per_session."""
        f = AccountLimitFilter(max_per_session=3)
        post = Post(
            uri="x", cid="x", author_did="did:plc:user",
            author_handle="x", text="test", created_at="x"
        )
        # Already replied twice
        state = {"replied_accounts_today": ["did:plc:user", "did:plc:user"]}
        assert f.should_include(post, state) is True
        
        # Already replied three times
        state = {"replied_accounts_today": ["did:plc:user", "did:plc:user", "did:plc:user"]}
        assert f.should_include(post, state) is False


class TestMinTextLengthFilter:
    """Tests for MinTextLengthFilter."""

    def test_excludes_short_posts(self):
        """Should exclude posts shorter than minimum."""
        f = MinTextLengthFilter(min_chars=20)
        post = Post(
            uri="x", cid="x", author_did="x",
            author_handle="x", text="Short", created_at="x"
        )
        assert f.should_include(post, {}) is False

    def test_includes_long_posts(self):
        """Should include posts meeting minimum length."""
        f = MinTextLengthFilter(min_chars=20)
        post = Post(
            uri="x", cid="x", author_did="x",
            author_handle="x", text="This is a sufficiently long post text", created_at="x"
        )
        assert f.should_include(post, {}) is True


class TestEngagementFilter:
    """Tests for EngagementFilter."""

    def test_filters_by_min_likes(self):
        """Should filter by minimum likes."""
        f = EngagementFilter(min_likes=5)
        post = Post(
            uri="x", cid="x", author_did="x",
            author_handle="x", text="test", created_at="x",
            like_count=3
        )
        assert f.should_include(post, {}) is False

    def test_filters_by_max_likes(self):
        """Should filter by maximum likes (avoid viral posts)."""
        f = EngagementFilter(max_likes=100)
        post = Post(
            uri="x", cid="x", author_did="x",
            author_handle="x", text="test", created_at="x",
            like_count=500
        )
        assert f.should_include(post, {}) is False

    def test_filters_by_max_replies(self):
        """Should filter by maximum replies (avoid crowded threads)."""
        f = EngagementFilter(max_replies=50)
        post = Post(
            uri="x", cid="x", author_did="x",
            author_handle="x", text="test", created_at="x",
            reply_count=100
        )
        assert f.should_include(post, {}) is False


# ============================================================================
# Multiplier Tests
# ============================================================================

class TestLowEngagementBonus:
    """Tests for LowEngagementBonus."""

    def test_first_reply_bonus(self):
        """Should give bonus for being first to reply."""
        m = LowEngagementBonus()
        post = Post(
            uri="x", cid="x", author_did="x",
            author_handle="x", text="test", created_at="x",
            reply_count=0
        )
        assert m.calculate(post, {}) == 1.5

    def test_low_reply_count_bonus(self):
        """Should give smaller bonus for low reply count."""
        m = LowEngagementBonus()
        post = Post(
            uri="x", cid="x", author_did="x",
            author_handle="x", text="test", created_at="x",
            reply_count=2
        )
        assert m.calculate(post, {}) == 1.2

    def test_crowded_thread_penalty(self):
        """Should penalize crowded threads."""
        m = LowEngagementBonus()
        post = Post(
            uri="x", cid="x", author_did="x",
            author_handle="x", text="test", created_at="x",
            reply_count=25
        )
        assert m.calculate(post, {}) == 0.5


class TestFreshPostBonus:
    """Tests for FreshPostBonus."""

    def test_very_fresh_post_bonus(self):
        """Should give bonus for posts less than 1 hour old."""
        m = FreshPostBonus()
        now = dt.datetime.now(dt.timezone.utc)
        recent = (now - dt.timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
        post = Post(
            uri="x", cid="x", author_did="x",
            author_handle="x", text="test", created_at=recent
        )
        assert m.calculate(post, {}) == 1.3

    def test_moderately_fresh_post_bonus(self):
        """Should give smaller bonus for posts 1-3 hours old."""
        m = FreshPostBonus()
        now = dt.datetime.now(dt.timezone.utc)
        older = (now - dt.timedelta(hours=2)).isoformat().replace("+00:00", "Z")
        post = Post(
            uri="x", cid="x", author_did="x",
            author_handle="x", text="test", created_at=older
        )
        assert m.calculate(post, {}) == 1.1

    def test_old_post_no_bonus(self):
        """Should give no bonus for older posts."""
        m = FreshPostBonus()
        now = dt.datetime.now(dt.timezone.utc)
        old = (now - dt.timedelta(hours=5)).isoformat().replace("+00:00", "Z")
        post = Post(
            uri="x", cid="x", author_did="x",
            author_handle="x", text="test", created_at=old
        )
        assert m.calculate(post, {}) == 1.0


# ============================================================================
# Pipeline Tests
# ============================================================================

class TestFilterPipeline:
    """Tests for FilterPipeline."""

    def test_filters_applied_in_order(self):
        """Should apply all filters."""
        pipeline = FilterPipeline()
        pipeline.add_filter(MinTextLengthFilter(min_chars=10))
        pipeline.add_filter(AlreadyRepliedFilter())
        
        posts = [
            Post(uri="at://1", cid="1", author_did="d1", author_handle="h1",
                 text="Short", created_at="x"),  # Fails min length
            Post(uri="at://2", cid="2", author_did="d2", author_handle="h2",
                 text="This is long enough text", created_at="x"),  # Passes
            Post(uri="at://3", cid="3", author_did="d3", author_handle="h3",
                 text="Also long enough text here", created_at="x"),  # Already replied
        ]
        
        state = {"replied_posts": ["at://3"]}
        result = pipeline.process(posts, state)
        
        assert len(result) == 1
        assert result[0].uri == "at://2"

    def test_multipliers_applied(self):
        """Should apply all multipliers to passing posts."""
        pipeline = FilterPipeline()
        pipeline.add_multiplier(LowEngagementBonus())
        
        post = Post(
            uri="at://1", cid="1", author_did="d1", author_handle="h1",
            text="test", created_at="x", reply_count=0
        )
        
        result = pipeline.process([post], {})
        assert len(result) == 1
        assert result[0].final_score == 1.5  # LowEngagementBonus for 0 replies

    def test_sorts_by_final_score(self):
        """Should sort results by final score descending."""
        pipeline = FilterPipeline()
        pipeline.add_multiplier(LowEngagementBonus())
        
        posts = [
            Post(uri="at://1", cid="1", author_did="d1", author_handle="h1",
                 text="test", created_at="x", reply_count=25),  # penalty: 0.5
            Post(uri="at://2", cid="2", author_did="d2", author_handle="h2",
                 text="test", created_at="x", reply_count=0),   # bonus: 1.5
            Post(uri="at://3", cid="3", author_did="d3", author_handle="h3",
                 text="test", created_at="x", reply_count=5),   # neutral: 1.0
        ]
        
        result = pipeline.process(posts, {})
        assert [p.uri for p in result] == ["at://2", "at://3", "at://1"]


# ============================================================================
# Helper Function Tests
# ============================================================================

class TestFilterRecentPosts:
    """Tests for filter_recent_posts helper."""

    def test_filters_by_time(self):
        """Should filter posts older than specified hours."""
        now = dt.datetime.now(dt.timezone.utc)
        recent = (now - dt.timedelta(hours=2)).isoformat().replace("+00:00", "Z")
        old = (now - dt.timedelta(hours=24)).isoformat().replace("+00:00", "Z")
        
        posts = [
            {"post": {"uri": "at://1", "cid": "1", "author": {"did": "d1", "handle": "h1"},
                      "replyCount": 0, "likeCount": 0, "repostCount": 0,
                      "record": {"text": "recent", "createdAt": recent}}},
            {"post": {"uri": "at://2", "cid": "2", "author": {"did": "d2", "handle": "h2"},
                      "replyCount": 0, "likeCount": 0, "repostCount": 0,
                      "record": {"text": "old", "createdAt": old}}},
        ]
        
        result = filter_recent_posts(posts, hours=12)
        assert len(result) == 1
        assert result[0].text == "recent"

    def test_handles_reply_metadata(self):
        """Should correctly parse reply metadata."""
        now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        posts = [
            {"post": {"uri": "at://1", "cid": "1", "author": {"did": "d1", "handle": "h1"},
                      "replyCount": 0, "likeCount": 0, "repostCount": 0,
                      "record": {
                          "text": "reply", "createdAt": now,
                          "reply": {
                              "parent": {"uri": "at://parent", "cid": "pcid"},
                              "root": {"uri": "at://root", "cid": "rcid"}
                          }
                      }}},
        ]
        
        result = filter_recent_posts(posts, hours=1)
        assert len(result) == 1
        assert result[0].is_reply is True
        assert result[0].parent_uri == "at://parent"
        assert result[0].root_uri == "at://root"


class TestCreateDefaultPipeline:
    """Tests for create_default_pipeline."""

    def test_creates_pipeline_with_filters_and_multipliers(self):
        """Should create pipeline with all default components."""
        pipeline = create_default_pipeline("did:plc:me")
        
        # Check filters exist
        assert len(pipeline.filters) >= 4  # At least 4 filters
        filter_names = [f.name for f in pipeline.filters]
        assert "already_replied" in filter_names
        assert "account_limit" in filter_names
        assert "min_length" in filter_names
        assert "engagement" in filter_names
        
        # Check multipliers exist
        assert len(pipeline.multipliers) >= 3
        multiplier_names = [m.name for m in pipeline.multipliers]
        assert "low_engagement_bonus" in multiplier_names
        assert "fresh_post_bonus" in multiplier_names
