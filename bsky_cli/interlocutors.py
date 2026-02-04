"""Track interaction history with BlueSky users.

Maintains a persistent record of who we've interacted with, enabling:
- Context-aware responses (familiar vs new interlocutors)
- Avoiding repetition in conversations
- Identifying "regulars" vs drive-by interactions
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

# ============================================================================
# CONFIGURATION
# ============================================================================

INTERLOCUTORS_FILE = Path.home() / ".bsky-cli" / "interlocutors.json"

# Threshold for "regular" status
REGULAR_THRESHOLD = 3

# Maximum interactions to store per user (keep recent ones)
MAX_INTERACTIONS_PER_USER = 50


# ============================================================================
# DATA STRUCTURES
# ============================================================================

InteractionType = Literal[
    "reply_to_them",    # We replied to their post
    "they_replied",     # They replied to our post
    "reply_in_thread",  # We replied in a thread they're in
    "dm_sent",          # We sent them a DM
    "dm_received",      # They sent us a DM
    "mentioned_them",   # We mentioned them
    "they_mentioned",   # They mentioned us
    "liked_their_post", # We liked their post
    "they_liked_ours",  # They liked our post
]


@dataclass
class Interaction:
    """A single interaction with a user."""
    date: str
    type: InteractionType
    post_uri: str | None = None
    our_text: str | None = None  # What we said (truncated)
    their_text: str | None = None  # What they said (truncated)
    
    def to_dict(self) -> dict:
        return {k: v for k, v in {
            "date": self.date,
            "type": self.type,
            "post_uri": self.post_uri,
            "our_text": self.our_text,
            "their_text": self.their_text,
        }.items() if v is not None}
    
    @classmethod
    def from_dict(cls, d: dict) -> "Interaction":
        return cls(**d)


@dataclass
class Interlocutor:
    """A user we've interacted with."""
    did: str
    handle: str
    display_name: str = ""
    first_seen: str = ""
    last_interaction: str = ""
    total_count: int = 0
    interactions: list[Interaction] = field(default_factory=list)
    notes: str = ""  # Manual notes about this person
    tags: list[str] = field(default_factory=list)  # e.g., ["friendly", "technical", "ai-researcher"]
    
    @property
    def is_regular(self) -> bool:
        """Is this a regular interlocutor?"""
        return self.total_count >= REGULAR_THRESHOLD
    
    @property
    def relationship_summary(self) -> str:
        """One-line summary of relationship."""
        if self.total_count == 0:
            return "never interacted"
        elif self.total_count == 1:
            return f"1 interaction ({self.last_interaction})"
        elif self.is_regular:
            return f"regular ({self.total_count} interactions, since {self.first_seen})"
        else:
            return f"{self.total_count} interactions (since {self.first_seen})"
    
    def add_interaction(self, interaction: Interaction):
        """Add an interaction, maintaining limits."""
        self.interactions.append(interaction)
        self.total_count += 1
        self.last_interaction = interaction.date
        if not self.first_seen:
            self.first_seen = interaction.date
        
        # Trim old interactions if over limit
        if len(self.interactions) > MAX_INTERACTIONS_PER_USER:
            self.interactions = self.interactions[-MAX_INTERACTIONS_PER_USER:]
    
    def recent_interactions(self, n: int = 5) -> list[Interaction]:
        """Get N most recent interactions."""
        return self.interactions[-n:]
    
    def to_dict(self) -> dict:
        return {
            "did": self.did,
            "handle": self.handle,
            "display_name": self.display_name,
            "first_seen": self.first_seen,
            "last_interaction": self.last_interaction,
            "total_count": self.total_count,
            "interactions": [i.to_dict() for i in self.interactions],
            "notes": self.notes,
            "tags": self.tags,
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> "Interlocutor":
        interactions = [Interaction.from_dict(i) for i in d.get("interactions", [])]
        return cls(
            did=d["did"],
            handle=d["handle"],
            display_name=d.get("display_name", ""),
            first_seen=d.get("first_seen", ""),
            last_interaction=d.get("last_interaction", ""),
            total_count=d.get("total_count", 0),
            interactions=interactions,
            notes=d.get("notes", ""),
            tags=d.get("tags", []),
        )


# ============================================================================
# STORAGE
# ============================================================================

def _load_data() -> dict[str, Interlocutor]:
    """Load interlocutors from disk."""
    if not INTERLOCUTORS_FILE.exists():
        return {}
    try:
        raw = json.loads(INTERLOCUTORS_FILE.read_text())
        return {did: Interlocutor.from_dict(data) for did, data in raw.items()}
    except Exception:
        return {}


def _save_data(data: dict[str, Interlocutor]):
    """Save interlocutors to disk."""
    INTERLOCUTORS_FILE.parent.mkdir(parents=True, exist_ok=True)
    raw = {did: inter.to_dict() for did, inter in data.items()}
    INTERLOCUTORS_FILE.write_text(json.dumps(raw, indent=2))


# ============================================================================
# PUBLIC API
# ============================================================================

def record_interaction(
    did: str,
    handle: str,
    interaction_type: InteractionType,
    post_uri: str | None = None,
    our_text: str | None = None,
    their_text: str | None = None,
    display_name: str = "",
) -> Interlocutor:
    """
    Record an interaction with a user.
    
    Args:
        did: User's DID
        handle: User's handle
        interaction_type: Type of interaction
        post_uri: URI of the post involved (if any)
        our_text: What we said (truncated for storage)
        their_text: What they said (truncated for storage)
        display_name: User's display name
    
    Returns:
        Updated Interlocutor object
    """
    data = _load_data()
    
    if did not in data:
        data[did] = Interlocutor(did=did, handle=handle, display_name=display_name)
    
    interlocutor = data[did]
    # Update handle/display_name in case they changed
    interlocutor.handle = handle
    if display_name:
        interlocutor.display_name = display_name
    
    interaction = Interaction(
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        type=interaction_type,
        post_uri=post_uri,
        our_text=our_text[:200] if our_text else None,
        their_text=their_text[:200] if their_text else None,
    )
    
    interlocutor.add_interaction(interaction)
    _save_data(data)
    
    return interlocutor


def get_interlocutor(did: str) -> Interlocutor | None:
    """Get an interlocutor by DID."""
    data = _load_data()
    return data.get(did)


def get_by_handle(handle: str) -> Interlocutor | None:
    """Get an interlocutor by handle (slower, searches all)."""
    handle = handle.lower().lstrip("@")
    data = _load_data()
    for inter in data.values():
        if inter.handle.lower() == handle:
            return inter
    return None


def is_regular(did: str) -> bool:
    """Check if a user is a regular interlocutor."""
    inter = get_interlocutor(did)
    return inter.is_regular if inter else False


def get_history(did: str) -> str | None:
    """
    Get a brief history summary for a user.
    Returns None if no history.
    """
    inter = get_interlocutor(did)
    if not inter:
        return None
    return inter.relationship_summary


def format_context_for_llm(did: str, max_interactions: int = 3) -> str:
    """
    Format interaction history as context for LLM prompts.
    
    Returns a string suitable for including in prompts, or empty string
    if no history.
    """
    inter = get_interlocutor(did)
    if not inter:
        return ""
    
    lines = [f"**History with @{inter.handle}:** {inter.relationship_summary}"]
    
    if inter.tags:
        lines.append(f"Tags: {', '.join(inter.tags)}")
    
    if inter.notes:
        lines.append(f"Notes: {inter.notes}")
    
    recent = inter.recent_interactions(max_interactions)
    if recent:
        lines.append("Recent interactions:")
        for i in recent:
            parts = [f"  - {i.date}: {i.type}"]
            if i.their_text:
                parts.append(f'    They said: "{i.their_text[:100]}..."' if len(i.their_text or "") > 100 else f'    They said: "{i.their_text}"')
            if i.our_text:
                parts.append(f'    We said: "{i.our_text[:100]}..."' if len(i.our_text or "") > 100 else f'    We said: "{i.our_text}"')
            lines.extend(parts)
    
    return "\n".join(lines)


def format_notification_badge(did: str) -> str:
    """
    Return a badge for notifications display.
    
    Returns:
        "🔄" for regulars, "🆕" for new, "" for in-between
    """
    inter = get_interlocutor(did)
    if not inter:
        return "🆕"
    elif inter.is_regular:
        return "🔄"
    else:
        return ""


def add_note(did: str, note: str):
    """Add/update a note for an interlocutor."""
    data = _load_data()
    if did in data:
        data[did].notes = note
        _save_data(data)


def add_tag(did: str, tag: str):
    """Add a tag to an interlocutor."""
    data = _load_data()
    if did in data and tag not in data[did].tags:
        data[did].tags.append(tag)
        _save_data(data)


def remove_tag(did: str, tag: str):
    """Remove a tag from an interlocutor."""
    data = _load_data()
    if did in data and tag in data[did].tags:
        data[did].tags.remove(tag)
        _save_data(data)


def list_regulars() -> list[Interlocutor]:
    """List all regular interlocutors."""
    data = _load_data()
    return [i for i in data.values() if i.is_regular]


def list_all(min_interactions: int = 1) -> list[Interlocutor]:
    """List all interlocutors with at least N interactions."""
    data = _load_data()
    return sorted(
        [i for i in data.values() if i.total_count >= min_interactions],
        key=lambda x: x.last_interaction,
        reverse=True
    )


def stats() -> dict:
    """Get statistics about interlocutors."""
    data = _load_data()
    total = len(data)
    regulars = sum(1 for i in data.values() if i.is_regular)
    total_interactions = sum(i.total_count for i in data.values())
    
    return {
        "total_users": total,
        "regulars": regulars,
        "total_interactions": total_interactions,
        "avg_per_user": total_interactions / total if total > 0 else 0,
    }
