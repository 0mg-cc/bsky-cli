"""Tests for threads module."""
import pytest
from bsky_cli.threads import BACKOFF_INTERVALS, Branch, TrackedThread


class TestBackoffIntervals:
    """Tests for backoff interval logic."""
    
    def test_backoff_intervals_exist(self):
        """Test backoff intervals are defined."""
        assert len(BACKOFF_INTERVALS) > 0
        assert BACKOFF_INTERVALS[0] == 10  # Start at 10 minutes
    
    def test_backoff_intervals_increase(self):
        """Test intervals increase exponentially."""
        for i in range(1, len(BACKOFF_INTERVALS)):
            assert BACKOFF_INTERVALS[i] > BACKOFF_INTERVALS[i-1]
    
    def test_max_interval_reasonable(self):
        """Test maximum interval is reasonable (< 5 hours)."""
        assert BACKOFF_INTERVALS[-1] <= 300  # 5 hours max


class TestBranch:
    """Tests for Branch dataclass."""
    
    def test_branch_creation(self):
        """Test Branch creation."""
        branch = Branch(
            our_reply_uri="at://did:plc:test/post/reply1",
            our_reply_url="https://bsky.app/profile/test/post/reply1",
            interlocutors=["user1.bsky.social"],
            interlocutor_dids=["did:plc:user1"],
            last_activity_at="2026-02-04T12:00:00Z",
            message_count=2,
            topic_drift=0.1,
            branch_score=75.0,
        )
        assert branch.our_reply_uri.startswith("at://")
        assert len(branch.interlocutors) == 1
        assert branch.topic_drift < 0.5
    
    def test_branch_to_dict(self):
        """Test Branch serialization."""
        branch = Branch(
            our_reply_uri="at://test",
            our_reply_url="https://test",
            interlocutors=["user"],
            interlocutor_dids=["did:plc:user"],
            last_activity_at="2026-02-04T12:00:00Z",
            message_count=1,
            topic_drift=0.0,
            branch_score=50.0,
        )
        d = branch.to_dict()
        assert d["our_reply_uri"] == "at://test"
        assert d["message_count"] == 1
    
    def test_branch_from_dict(self):
        """Test Branch deserialization."""
        data = {
            "our_reply_uri": "at://test",
            "our_reply_url": "https://test",
            "interlocutors": ["user"],
            "interlocutor_dids": ["did:plc:user"],
            "last_activity_at": "2026-02-04T12:00:00Z",
            "message_count": 3,
            "topic_drift": 0.2,
            "branch_score": 60.0,
        }
        branch = Branch.from_dict(data)
        assert branch.message_count == 3
        assert branch.topic_drift == 0.2


class TestTrackedThread:
    """Tests for TrackedThread dataclass."""
    
    def test_thread_creation(self):
        """Test TrackedThread creation."""
        thread = TrackedThread(
            root_uri="at://did:plc:root/post/1",
            root_url="https://bsky.app/profile/root/post/1",
            root_author_handle="root.bsky.social",
            root_author_did="did:plc:root",
            main_topics=["AI", "automation"],
            root_text="Original post text",
            overall_score=80.0,
            branches={},
            total_our_replies=0,
            created_at="2026-02-04T12:00:00Z",
            last_activity_at="2026-02-04T12:00:00Z",
        )
        assert thread.root_author_handle == "root.bsky.social"
        assert "AI" in thread.main_topics
        assert thread.backoff_level == 0
    
    def test_thread_backoff_default(self):
        """Test default backoff level is 0."""
        thread = TrackedThread(
            root_uri="at://test", root_url="", root_author_handle="",
            root_author_did="", main_topics=[], root_text="",
            overall_score=0, branches={}, total_our_replies=0,
            created_at="", last_activity_at="",
        )
        assert thread.backoff_level == 0
        assert thread.last_check_at is None
    
    def test_thread_serialization_roundtrip(self):
        """Test thread can be serialized and deserialized."""
        thread = TrackedThread(
            root_uri="at://test",
            root_url="https://test",
            root_author_handle="test.bsky.social",
            root_author_did="did:plc:test",
            main_topics=["topic1"],
            root_text="Test post",
            overall_score=50.0,
            branches={},
            total_our_replies=2,
            created_at="2026-02-04T12:00:00Z",
            last_activity_at="2026-02-04T13:00:00Z",
            backoff_level=2,
        )
        d = thread.to_dict()
        restored = TrackedThread.from_dict(d)
        
        assert restored.root_uri == thread.root_uri
        assert restored.backoff_level == 2
        assert restored.total_our_replies == 2
