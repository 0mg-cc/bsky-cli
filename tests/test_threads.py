"""Tests for threads module."""
import pytest
import json
from datetime import datetime, timedelta, timezone

from bsky_cli.threads import (
    Branch,
    TrackedThread,
    InterlocutorProfile,
    extract_topics,
    calculate_topic_drift,
    score_interlocutor,
    score_topic_relevance,
    score_thread_dynamics,
    score_branch,
    uri_to_url,
    generate_cron_config,
    RELEVANT_TOPICS,
    BACKOFF_INTERVALS,
)


# ============================================================================
# Data Structure Tests
# ============================================================================

class TestBranch:
    """Tests for Branch dataclass."""

    def test_to_dict_and_from_dict(self):
        """Should serialize and deserialize correctly."""
        branch = Branch(
            our_reply_uri="at://did:plc:me/app.bsky.feed.post/123",
            our_reply_url="https://bsky.app/profile/did:plc:me/post/123",
            interlocutors=["alice.bsky.social", "bob.bsky.social"],
            interlocutor_dids=["did:plc:alice", "did:plc:bob"],
            last_activity_at="2026-02-04T12:00:00Z",
            message_count=5,
            topic_drift=0.3,
            branch_score=65.0
        )

        d = branch.to_dict()
        restored = Branch.from_dict(d)

        assert restored.our_reply_uri == branch.our_reply_uri
        assert restored.interlocutors == branch.interlocutors
        assert restored.message_count == branch.message_count
        assert restored.branch_score == branch.branch_score

    def test_from_dict_ignores_legacy_messages_key(self):
        """Should ignore legacy state keys like `messages` instead of crashing."""
        branch_data = {
            "our_reply_uri": "at://did:plc:me/app.bsky.feed.post/123",
            "our_reply_url": "https://bsky.app/profile/did:plc:me/post/123",
            "interlocutors": ["alice.bsky.social"],
            "interlocutor_dids": ["did:plc:alice"],
            "last_activity_at": "2026-02-04T12:00:00Z",
            "message_count": 2,
            "topic_drift": 0.1,
            "branch_score": 55.0,
            "messages": ["legacy payload"],
        }

        restored = Branch.from_dict(branch_data)

        assert restored.our_reply_uri == branch_data["our_reply_uri"]
        assert restored.message_count == 2


class TestTrackedThread:
    """Tests for TrackedThread dataclass."""

    def test_to_dict_and_from_dict(self):
        """Should serialize and deserialize correctly with branches."""
        branch = Branch(
            our_reply_uri="at://x/123",
            our_reply_url="https://bsky.app/x/123",
            interlocutors=["alice"],
            interlocutor_dids=["did:plc:alice"],
            last_activity_at="2026-02-04T12:00:00Z",
            message_count=3,
            topic_drift=0.2,
            branch_score=70.0
        )
        
        thread = TrackedThread(
            root_uri="at://did:plc:root/app.bsky.feed.post/456",
            root_url="https://bsky.app/profile/root/post/456",
            root_author_handle="root.bsky.social",
            root_author_did="did:plc:root",
            main_topics=["AI", "consciousness"],
            root_text="Discussing AI consciousness",
            overall_score=75.0,
            branches={"at://x/123": branch},
            total_our_replies=2,
            created_at="2026-02-04T10:00:00Z",
            last_activity_at="2026-02-04T12:00:00Z",
            engaged_interlocutors=["did:plc:alice"],
            our_reply_texts=["First reply", "Second reply"]
        )
        
        d = thread.to_dict()
        restored = TrackedThread.from_dict(d)
        
        assert restored.root_uri == thread.root_uri
        assert restored.main_topics == thread.main_topics
        assert len(restored.branches) == 1
        assert restored.engaged_interlocutors == ["did:plc:alice"]

    def test_defaults(self):
        """Should have sensible defaults."""
        thread = TrackedThread(
            root_uri="x", root_url="x", root_author_handle="x",
            root_author_did="x", main_topics=[], root_text="",
            overall_score=0, branches={}, total_our_replies=0,
            created_at="x", last_activity_at="x"
        )
        assert thread.enabled is True
        assert thread.backoff_level == 0
        assert thread.cron_id is None


# ============================================================================
# Topic Analysis Tests
# ============================================================================

class TestExtractTopics:
    """Tests for extract_topics function."""

    def test_extracts_matching_topics(self):
        """Should extract topics present in text."""
        text = "Working on AI agents and machine learning infrastructure"
        topics = extract_topics(text)
        assert "AI" in topics
        assert "agents" in topics
        assert "machine learning" in topics
        assert "infrastructure" in topics

    def test_case_insensitive(self):
        """Should match topics case-insensitively."""
        text = "LINUX and foss are great"
        topics = extract_topics(text)
        assert "linux" in topics or "LINUX" in [t for t in RELEVANT_TOPICS if t.lower() == "linux"]

    def test_returns_empty_for_no_match(self):
        """Should return empty list when no topics match."""
        text = "Just had breakfast"
        topics = extract_topics(text)
        assert len(topics) == 0


class TestCalculateTopicDrift:
    """Tests for calculate_topic_drift function."""

    def test_no_drift_same_topics(self):
        """Should return 0 when topics are the same."""
        root = "Discussing AI and machine learning"
        branch = "More thoughts on AI and machine learning applications"
        drift = calculate_topic_drift(root, branch)
        assert drift < 0.3  # Very similar

    def test_high_drift_different_topics(self):
        """Should return high drift for completely different topics."""
        root = "The climate crisis is urgent"
        branch = "Linux kernel updates are interesting"
        drift = calculate_topic_drift(root, branch)
        assert drift > 0.5  # Different topics

    def test_moderate_drift_partial_overlap(self):
        """Should return moderate drift for partial overlap."""
        root = "AI and climate change solutions"
        branch = "AI applications in tech"
        drift = calculate_topic_drift(root, branch)
        assert 0.2 < drift < 0.8  # Some overlap

    def test_no_topics_in_root(self):
        """Should return 0 when root has no recognized topics."""
        root = "Just having coffee"
        branch = "Thinking about AI today"
        drift = calculate_topic_drift(root, branch)
        assert drift == 0.0


# ============================================================================
# Scoring Tests
# ============================================================================

class TestScoreInterlocutor:
    """Tests for score_interlocutor function."""

    def test_high_followers_bonus(self):
        """Should give bonus for high follower count."""
        profile = InterlocutorProfile(
            did="x", handle="x", display_name="x",
            followers_count=15000, follows_count=1000, posts_count=500
        )
        score, reasons = score_interlocutor(profile)
        assert score >= 15
        assert any("followers" in r for r in reasons)

    def test_authority_ratio_bonus(self):
        """Should give bonus for high authority ratio."""
        profile = InterlocutorProfile(
            did="x", handle="x", display_name="x",
            followers_count=5000, follows_count=500, posts_count=100
        )
        score, reasons = score_interlocutor(profile)
        assert any("authority" in r.lower() for r in reasons)

    def test_relevant_bio_bonus(self):
        """Should give bonus for relevant topics in bio."""
        profile = InterlocutorProfile(
            did="x", handle="x", display_name="x",
            followers_count=100, follows_count=100, posts_count=100,
            description="I work on AI agents and machine learning infrastructure"
        )
        score, reasons = score_interlocutor(profile)
        assert any("bio" in r for r in reasons)

    def test_capped_at_40(self):
        """Should cap score at 40."""
        profile = InterlocutorProfile(
            did="x", handle="x", display_name="x",
            followers_count=100000, follows_count=1000, posts_count=10000,
            description="AI agents machine learning LLM consciousness philosophy"
        )
        score, _ = score_interlocutor(profile)
        assert score <= 40


class TestScoreTopicRelevance:
    """Tests for score_topic_relevance function."""

    def test_highly_relevant(self):
        """Should give high score for many matching topics."""
        text = "AI agents doing machine learning on linux infrastructure"
        score, reasons = score_topic_relevance(text)
        assert score >= 20

    def test_moderately_relevant(self):
        """Should give moderate score for some matching topics."""
        text = "Climate change and sustainability"
        score, reasons = score_topic_relevance(text)
        assert 10 <= score <= 30

    def test_not_relevant(self):
        """Should give 0 for no matching topics."""
        text = "What I had for breakfast today"
        score, reasons = score_topic_relevance(text)
        assert score == 0


class TestScoreThreadDynamics:
    """Tests for score_thread_dynamics function."""

    def test_heavily_invested_bonus(self):
        """Should give bonus for many of our replies."""
        score, reasons = score_thread_dynamics(
            total_replies=10, our_replies=5, branch_count=2
        )
        assert score >= 15
        assert any("invested" in r for r in reasons)

    def test_multi_branch_bonus(self):
        """Should give bonus for multiple branches."""
        score, reasons = score_thread_dynamics(
            total_replies=10, our_replies=1, branch_count=4
        )
        assert any("branch" in r for r in reasons)

    def test_crowded_thread_penalty(self):
        """Should penalize very crowded threads."""
        score, reasons = score_thread_dynamics(
            total_replies=50, our_replies=1, branch_count=1
        )
        assert any("crowded" in r for r in reasons)


class TestScoreBranch:
    """Tests for score_branch function."""

    def test_high_score_for_on_topic_active_branch(self):
        """Should give high score for active, on-topic branch."""
        branch = Branch(
            our_reply_uri="x", our_reply_url="x",
            interlocutors=["alice"], interlocutor_dids=["did:plc:alice"],
            last_activity_at=datetime.now(timezone.utc).isoformat(),
            message_count=5, topic_drift=0.1, branch_score=0
        )
        profiles = {
            "did:plc:alice": InterlocutorProfile(
                did="did:plc:alice", handle="alice", display_name="Alice",
                followers_count=5000, follows_count=500, posts_count=1000
            )
        }
        score = score_branch(branch, ["AI"], profiles)
        assert score >= 50

    def test_low_score_for_off_topic_branch(self):
        """Should give low score for off-topic branch."""
        branch = Branch(
            our_reply_uri="x", our_reply_url="x",
            interlocutors=["bob"], interlocutor_dids=["did:plc:bob"],
            last_activity_at="2026-01-01T00:00:00Z",  # Old
            message_count=1, topic_drift=0.9, branch_score=0
        )
        score = score_branch(branch, ["AI"], {})
        assert score < 30

    def test_engaged_interlocutor_ignores_drift(self):
        """Should ignore topic drift for engaged interlocutors."""
        branch = Branch(
            our_reply_uri="x", our_reply_url="x",
            interlocutors=["alice"], interlocutor_dids=["did:plc:alice"],
            last_activity_at=datetime.now(timezone.utc).isoformat(),
            message_count=3, topic_drift=0.9, branch_score=0  # High drift
        )
        # With engaged interlocutor - should get full topic points
        score_engaged = score_branch(branch, ["AI"], {}, engaged_interlocutors={"did:plc:alice"})
        # Without engaged interlocutor - should be penalized
        score_not_engaged = score_branch(branch, ["AI"], {}, engaged_interlocutors=set())
        
        assert score_engaged > score_not_engaged


# ============================================================================
# Utility Tests
# ============================================================================

class TestUriToUrl:
    """Tests for uri_to_url function."""

    def test_converts_at_uri_to_https(self):
        """Should convert at:// URI to bsky.app URL."""
        uri = "at://did:plc:abc123/app.bsky.feed.post/xyz789"
        url = uri_to_url(uri)
        assert url == "https://bsky.app/profile/did:plc:abc123/post/xyz789"

    def test_returns_unchanged_if_not_at_uri(self):
        """Should return unchanged if not an at:// URI."""
        uri = "https://example.com/something"
        url = uri_to_url(uri)
        assert url == uri


class TestGenerateCronConfig:
    """Tests for generate_cron_config function."""

    def test_generates_valid_cron_config(self):
        """Should generate valid OpenClaw cron configuration."""
        branch = Branch(
            our_reply_uri="at://x/123", our_reply_url="https://bsky.app/x/123",
            interlocutors=["alice"], interlocutor_dids=["did:plc:alice"],
            last_activity_at="2026-02-04T12:00:00Z",
            message_count=3, topic_drift=0.2, branch_score=65.0
        )
        thread = TrackedThread(
            root_uri="at://root/456", root_url="https://bsky.app/root/456",
            root_author_handle="rootauthor", root_author_did="did:plc:root",
            main_topics=["AI"], root_text="AI discussion",
            overall_score=70, branches={"at://x/123": branch},
            total_our_replies=2, created_at="2026-02-04T10:00:00Z",
            last_activity_at="2026-02-04T12:00:00Z"
        )
        
        config = generate_cron_config(thread, interval_minutes=15)
        
        assert config["name"].startswith("bsky-thread-")
        assert config["schedule"]["kind"] == "every"
        assert config["schedule"]["everyMs"] == 15 * 60 * 1000
        assert config["sessionTarget"] == "isolated"
        assert config["enabled"] is True
        assert "rootauthor" in config["payload"]["message"]

    def test_includes_branch_info_in_message(self):
        """Should include high-scoring branches in message."""
        branch = Branch(
            our_reply_uri="at://x/123", our_reply_url="https://bsky.app/x/123",
            interlocutors=["alice"], interlocutor_dids=["did:plc:alice"],
            last_activity_at="2026-02-04T12:00:00Z",
            message_count=3, topic_drift=0.2, branch_score=65.0  # Above 40 threshold
        )
        thread = TrackedThread(
            root_uri="at://root/456", root_url="https://bsky.app/root/456",
            root_author_handle="rootauthor", root_author_did="did:plc:root",
            main_topics=["AI"], root_text="AI discussion",
            overall_score=70, branches={"at://x/123": branch},
            total_our_replies=2, created_at="x", last_activity_at="x"
        )
        
        config = generate_cron_config(thread)
        assert "@alice" in config["payload"]["message"]

    def test_includes_our_replies_for_consistency(self):
        """Should include our reply texts for consistency checking."""
        thread = TrackedThread(
            root_uri="at://root/456", root_url="https://bsky.app/root/456",
            root_author_handle="rootauthor", root_author_did="did:plc:root",
            main_topics=["AI"], root_text="AI discussion",
            overall_score=70, branches={}, total_our_replies=2,
            created_at="x", last_activity_at="x",
            our_reply_texts=["I think AI consciousness is fascinating"]
        )
        
        config = generate_cron_config(thread)
        assert "I think AI consciousness" in config["payload"]["message"]


# ============================================================================
# Backoff Logic Tests
# ============================================================================

class TestBackoffIntervals:
    """Tests for backoff interval constants."""

    def test_intervals_are_increasing(self):
        """Should have increasing backoff intervals."""
        for i in range(1, len(BACKOFF_INTERVALS)):
            assert BACKOFF_INTERVALS[i] > BACKOFF_INTERVALS[i-1]

    def test_starts_at_10_minutes(self):
        """Should start at 10 minute interval."""
        assert BACKOFF_INTERVALS[0] == 10

    def test_ends_at_240_minutes(self):
        """Should end at 240 minute (4 hour) interval."""
        assert BACKOFF_INTERVALS[-1] == 240
