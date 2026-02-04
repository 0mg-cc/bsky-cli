"""Tests for interlocutors module."""
import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from bsky_cli import interlocutors
from bsky_cli.interlocutors import (
    Interaction,
    Interlocutor,
    record_interaction,
    get_interlocutor,
    get_by_handle,
    is_regular,
    get_history,
    format_context_for_llm,
    format_notification_badge,
    REGULAR_THRESHOLD,
)


@pytest.fixture
def temp_storage(tmp_path):
    """Use a temporary file for storage during tests."""
    test_file = tmp_path / "interlocutors.json"
    with patch.object(interlocutors, 'INTERLOCUTORS_FILE', test_file):
        yield test_file


class TestInteraction:
    """Tests for Interaction dataclass."""

    def test_to_dict_and_from_dict(self):
        """Should serialize and deserialize correctly."""
        interaction = Interaction(
            date="2026-02-04",
            type="reply_to_them",
            post_uri="at://did:plc:test/post/123",
            our_text="Hello!",
            their_text="Hi there!"
        )
        
        d = interaction.to_dict()
        restored = Interaction.from_dict(d)
        
        assert restored.date == interaction.date
        assert restored.type == interaction.type
        assert restored.our_text == interaction.our_text

    def test_to_dict_omits_none(self):
        """Should omit None values from dict."""
        interaction = Interaction(
            date="2026-02-04",
            type="reply_to_them",
        )
        d = interaction.to_dict()
        assert "post_uri" not in d
        assert "our_text" not in d


class TestInterlocutor:
    """Tests for Interlocutor dataclass."""

    def test_is_regular(self):
        """Should correctly identify regulars."""
        inter = Interlocutor(
            did="did:plc:test",
            handle="test.bsky.social",
            total_count=REGULAR_THRESHOLD
        )
        assert inter.is_regular is True
        
        inter.total_count = REGULAR_THRESHOLD - 1
        assert inter.is_regular is False

    def test_relationship_summary(self):
        """Should generate correct summaries."""
        inter = Interlocutor(did="x", handle="test")
        assert "never" in inter.relationship_summary
        
        inter.total_count = 1
        inter.last_interaction = "2026-02-04"
        assert "1 interaction" in inter.relationship_summary
        
        inter.total_count = 5
        inter.first_seen = "2026-01-01"
        assert "regular" in inter.relationship_summary

    def test_add_interaction(self):
        """Should add interactions and update metadata."""
        inter = Interlocutor(did="x", handle="test")
        
        interaction = Interaction(date="2026-02-04", type="reply_to_them")
        inter.add_interaction(interaction)
        
        assert inter.total_count == 1
        assert inter.first_seen == "2026-02-04"
        assert inter.last_interaction == "2026-02-04"
        assert len(inter.interactions) == 1

    def test_recent_interactions(self):
        """Should return most recent N interactions."""
        inter = Interlocutor(did="x", handle="test")
        for i in range(10):
            inter.add_interaction(Interaction(date=f"2026-02-{i+1:02d}", type="reply_to_them"))
        
        recent = inter.recent_interactions(3)
        assert len(recent) == 3
        assert recent[-1].date == "2026-02-10"


class TestRecordInteraction:
    """Tests for record_interaction function."""

    def test_creates_new_interlocutor(self, temp_storage):
        """Should create new interlocutor if not exists."""
        inter = record_interaction(
            did="did:plc:new",
            handle="new.bsky.social",
            interaction_type="reply_to_them",
            our_text="Hello!"
        )
        
        assert inter.handle == "new.bsky.social"
        assert inter.total_count == 1

    def test_updates_existing_interlocutor(self, temp_storage):
        """Should update existing interlocutor."""
        record_interaction(did="did:plc:test", handle="test", interaction_type="reply_to_them")
        inter = record_interaction(did="did:plc:test", handle="test", interaction_type="they_replied")
        
        assert inter.total_count == 2

    def test_truncates_long_text(self, temp_storage):
        """Should truncate text over 200 chars."""
        long_text = "x" * 300
        inter = record_interaction(
            did="did:plc:test",
            handle="test",
            interaction_type="reply_to_them",
            our_text=long_text
        )
        
        assert len(inter.interactions[0].our_text) == 200


class TestGetters:
    """Tests for getter functions."""

    def test_get_interlocutor(self, temp_storage):
        """Should retrieve by DID."""
        record_interaction(did="did:plc:test", handle="test", interaction_type="reply_to_them")
        
        inter = get_interlocutor("did:plc:test")
        assert inter is not None
        assert inter.handle == "test"
        
        assert get_interlocutor("did:plc:nonexistent") is None

    def test_get_by_handle(self, temp_storage):
        """Should retrieve by handle."""
        record_interaction(did="did:plc:test", handle="Test.Bsky.Social", interaction_type="reply_to_them")
        
        # Should be case-insensitive
        inter = get_by_handle("test.bsky.social")
        assert inter is not None
        
        # Should handle @ prefix
        inter = get_by_handle("@test.bsky.social")
        assert inter is not None

    def test_is_regular_function(self, temp_storage):
        """Should check regular status."""
        assert is_regular("did:plc:nonexistent") is False
        
        for i in range(REGULAR_THRESHOLD):
            record_interaction(did="did:plc:test", handle="test", interaction_type="reply_to_them")
        
        assert is_regular("did:plc:test") is True


class TestFormatters:
    """Tests for formatting functions."""

    def test_format_notification_badge_new(self, temp_storage):
        """Should return 🆕 for unknown users."""
        badge = format_notification_badge("did:plc:unknown")
        assert badge == "🆕"

    def test_format_notification_badge_regular(self, temp_storage):
        """Should return 🔄 for regulars."""
        for i in range(REGULAR_THRESHOLD):
            record_interaction(did="did:plc:test", handle="test", interaction_type="reply_to_them")
        
        badge = format_notification_badge("did:plc:test")
        assert badge == "🔄"

    def test_format_notification_badge_known(self, temp_storage):
        """Should return empty for known non-regulars."""
        record_interaction(did="did:plc:test", handle="test", interaction_type="reply_to_them")
        
        badge = format_notification_badge("did:plc:test")
        assert badge == ""

    def test_format_context_for_llm(self, temp_storage):
        """Should format context string."""
        record_interaction(
            did="did:plc:test",
            handle="test.bsky.social",
            interaction_type="reply_to_them",
            our_text="Great post!"
        )
        
        context = format_context_for_llm("did:plc:test")
        assert "@test.bsky.social" in context
        assert "Great post!" in context

    def test_format_context_empty_for_unknown(self, temp_storage):
        """Should return empty string for unknown users."""
        context = format_context_for_llm("did:plc:unknown")
        assert context == ""
