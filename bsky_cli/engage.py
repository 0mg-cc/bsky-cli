"""Engage with followed accounts by replying to interesting posts."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import requests

from .auth import get_session, load_from_pass
from .like import like_post

# ============================================================================
# CONFIGURATION
# ============================================================================

TOPICS = [
    "tech", "ops", "infrastructure", "devops",
    "AI", "machine learning", "LLM", "agents",
    "linux", "FOSS", "open source",
    "climate", "environment", "sustainability",
    "wealth inequality", "economics", "social justice",
    "consciousness", "philosophy", "psychology",
    "automation", "scripting", "tools"
]

STATE_FILE = Path.home() / "personas/echo/data/bsky-engage-state.json"
CONVERSATIONS_FILE = Path.home() / "personas/echo/data/bsky-conversations.json"
GUIDELINES_FILE = Path.home() / "personas/echo/data/bsky-guidelines.md"


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class Post:
    """Represents a BlueSky post with metadata."""
    uri: str
    cid: str
    author_did: str
    author_handle: str
    text: str
    created_at: str
    reply_count: int = 0
    repost_count: int = 0
    like_count: int = 0
    is_reply: bool = False
    parent_uri: str | None = None
    parent_cid: str | None = None
    root_uri: str | None = None
    root_cid: str | None = None
    
    # Scoring
    base_score: float = 1.0
    multipliers: dict = field(default_factory=dict)
    
    @property
    def final_score(self) -> float:
        """Calculate final score with all multipliers."""
        score = self.base_score
        for name, mult in self.multipliers.items():
            score *= mult
        return score
    
    def add_multiplier(self, name: str, value: float):
        """Add a scoring multiplier."""
        self.multipliers[name] = value


# ============================================================================
# FILTERS (Extensible Architecture)
# ============================================================================

class PostFilter(ABC):
    """Base class for post filters. Subclass to add new filters."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Filter name for logging."""
        pass
    
    @abstractmethod
    def should_include(self, post: Post, state: dict) -> bool:
        """Return True if post passes the filter."""
        pass


class AlreadyRepliedFilter(PostFilter):
    """Exclude posts we've already replied to."""
    name = "already_replied"
    
    def should_include(self, post: Post, state: dict) -> bool:
        replied_uris = set(state.get("replied_posts", []))
        return post.uri not in replied_uris


class AccountLimitFilter(PostFilter):
    """Limit replies per account per session."""
    name = "account_limit"
    
    def __init__(self, max_per_session: int = 1):
        self.max_per_session = max_per_session
    
    def should_include(self, post: Post, state: dict) -> bool:
        replied_accounts = state.get("replied_accounts_today", [])
        count = replied_accounts.count(post.author_did)
        return count < self.max_per_session


class MinTextLengthFilter(PostFilter):
    """Exclude very short posts."""
    name = "min_length"
    
    def __init__(self, min_chars: int = 20):
        self.min_chars = min_chars
    
    def should_include(self, post: Post, state: dict) -> bool:
        return len(post.text) >= self.min_chars


class EngagementFilter(PostFilter):
    """Filter by engagement levels (replies, likes, reposts)."""
    name = "engagement"
    
    def __init__(self, min_likes: int = 0, max_likes: int | None = None,
                 min_replies: int = 0, max_replies: int | None = None):
        self.min_likes = min_likes
        self.max_likes = max_likes
        self.min_replies = min_replies
        self.max_replies = max_replies
    
    def should_include(self, post: Post, state: dict) -> bool:
        # Check likes bounds
        if post.like_count < self.min_likes:
            return False
        if self.max_likes is not None and post.like_count > self.max_likes:
            return False
        # Check replies bounds (avoid posts already drowning in replies)
        if post.reply_count < self.min_replies:
            return False
        if self.max_replies is not None and post.reply_count > self.max_replies:
            return False
        return True


class ConversationFilter(PostFilter):
    """Filter for conversation continuation (replies to our posts)."""
    name = "conversation"
    
    def __init__(self, our_did: str):
        self.our_did = our_did
    
    def should_include(self, post: Post, state: dict) -> bool:
        # This filter is permissive - it lets through posts that are replies to us
        # The actual conversation tracking is done separately
        return True


# ============================================================================
# MULTIPLIERS (Scoring adjustments)
# ============================================================================

class ScoreMultiplier(ABC):
    """Base class for score multipliers."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @abstractmethod
    def calculate(self, post: Post, state: dict) -> float:
        """Return multiplier value (1.0 = no change)."""
        pass


class LowEngagementBonus(ScoreMultiplier):
    """Boost posts with low engagement (our reply matters more)."""
    name = "low_engagement_bonus"
    
    def calculate(self, post: Post, state: dict) -> float:
        if post.reply_count == 0:
            return 1.5  # First reply bonus
        elif post.reply_count < 3:
            return 1.2
        elif post.reply_count > 20:
            return 0.5  # Crowded thread penalty
        return 1.0


class ConversationBonus(ScoreMultiplier):
    """Boost posts that are part of ongoing conversations."""
    name = "conversation_bonus"
    
    def __init__(self, our_did: str):
        self.our_did = our_did
    
    def calculate(self, post: Post, state: dict) -> float:
        conversations = state.get("active_conversations", {})
        # If this is a reply to something in our conversation tree
        if post.parent_uri in conversations:
            return 2.0  # Strong bonus for continuing conversations
        return 1.0


class FriendlyInterlocutorBonus(ScoreMultiplier):
    """Boost posts from interlocutors tagged as friendly."""
    name = "friendly_bonus"
    
    def calculate(self, post: Post, state: dict) -> float:
        from . import interlocutors
        inter = interlocutors.get_interlocutor(post.author_did)
        if not inter:
            return 1.0
        
        multiplier = 1.0
        
        # Friendly tag = strong bonus
        if "friendly" in inter.tags:
            multiplier *= 1.5
        
        # Regular interlocutor = moderate bonus
        if inter.is_regular:
            multiplier *= 1.3
        
        return multiplier


class FreshPostBonus(ScoreMultiplier):
    """Boost very recent posts (reply while relevant)."""
    name = "fresh_post_bonus"
    
    def calculate(self, post: Post, state: dict) -> float:
        try:
            created = dt.datetime.fromisoformat(post.created_at.replace("Z", "+00:00"))
            age_hours = (dt.datetime.now(dt.timezone.utc) - created).total_seconds() / 3600
            if age_hours < 1:
                return 1.3
            elif age_hours < 3:
                return 1.1
        except Exception:
            pass
        return 1.0


# ============================================================================
# FILTER PIPELINE
# ============================================================================

class FilterPipeline:
    """Manages filters and multipliers for post selection."""
    
    def __init__(self):
        self.filters: list[PostFilter] = []
        self.multipliers: list[ScoreMultiplier] = []
    
    def add_filter(self, f: PostFilter) -> "FilterPipeline":
        self.filters.append(f)
        return self
    
    def add_multiplier(self, m: ScoreMultiplier) -> "FilterPipeline":
        self.multipliers.append(m)
        return self
    
    def process(self, posts: list[Post], state: dict) -> list[Post]:
        """Apply filters and multipliers, return sorted candidates."""
        candidates = []
        
        for post in posts:
            # Apply all filters
            passed = True
            for f in self.filters:
                if not f.should_include(post, state):
                    passed = False
                    break
            
            if not passed:
                continue
            
            # Apply all multipliers
            for m in self.multipliers:
                mult = m.calculate(post, state)
                post.add_multiplier(m.name, mult)
            
            candidates.append(post)
        
        # Sort by final score (descending)
        candidates.sort(key=lambda p: p.final_score, reverse=True)
        return candidates


# ============================================================================
# CONVERSATION TRACKING
# ============================================================================

def load_conversations() -> dict:
    """Load active conversation threads."""
    if CONVERSATIONS_FILE.exists():
        return json.loads(CONVERSATIONS_FILE.read_text())
    return {"threads": {}, "last_cleanup": None}


def save_conversations(data: dict):
    """Save conversation tracking data."""
    CONVERSATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONVERSATIONS_FILE.write_text(json.dumps(data, indent=2))


def track_reply(conversations: dict, our_reply_uri: str, parent_uri: str, root_uri: str | None):
    """Track a reply we made for conversation continuation."""
    thread_key = root_uri or parent_uri
    if thread_key not in conversations["threads"]:
        conversations["threads"][thread_key] = {
            "started": dt.datetime.now(dt.timezone.utc).isoformat(),
            "our_posts": [],
            "last_activity": None
        }
    conversations["threads"][thread_key]["our_posts"].append(our_reply_uri)
    conversations["threads"][thread_key]["last_activity"] = dt.datetime.now(dt.timezone.utc).isoformat()


def get_replies_to_our_posts(pds: str, jwt: str, our_did: str, conversations: dict) -> list[Post]:
    """Fetch replies to posts we've made (for conversation continuation)."""
    replies = []
    
    for thread_key, thread_data in conversations.get("threads", {}).items():
        for our_post_uri in thread_data.get("our_posts", [])[-5:]:  # Check last 5 posts per thread
            try:
                # Get thread to find replies
                r = requests.get(
                    f"{pds}/xrpc/app.bsky.feed.getPostThread",
                    headers={"Authorization": f"Bearer {jwt}"},
                    params={"uri": our_post_uri, "depth": 1},
                    timeout=15
                )
                if r.status_code != 200:
                    continue
                
                thread = r.json().get("thread", {})
                # Get root post CID for threading
                root_post = thread.get("post", {})
                root_cid = root_post.get("cid", "")
                
                for reply in thread.get("replies", []):
                    post_data = reply.get("post", {})
                    if post_data.get("author", {}).get("did") == our_did:
                        continue  # Skip our own replies
                    
                    record = post_data.get("record", {})
                    reply_ref = record.get("reply", {})
                    
                    replies.append(Post(
                        uri=post_data.get("uri", ""),
                        cid=post_data.get("cid", ""),
                        author_did=post_data.get("author", {}).get("did", ""),
                        author_handle=post_data.get("author", {}).get("handle", ""),
                        text=record.get("text", "")[:500],
                        created_at=record.get("createdAt", ""),
                        reply_count=post_data.get("replyCount", 0),
                        like_count=post_data.get("likeCount", 0),
                        repost_count=post_data.get("repostCount", 0),
                        is_reply=True,
                        parent_uri=reply_ref.get("parent", {}).get("uri") or our_post_uri,
                        parent_cid=reply_ref.get("parent", {}).get("cid"),
                        root_uri=reply_ref.get("root", {}).get("uri") or thread_key,
                        root_cid=reply_ref.get("root", {}).get("cid") or root_cid
                    ))
            except Exception:
                continue
    
    return replies


# ============================================================================
# API HELPERS
# ============================================================================

def get_openrouter_key() -> str:
    """Get OpenRouter API key from pass."""
    env = load_from_pass("api/openrouter")
    if not env or "OPENROUTER_API_KEY" not in env:
        raise SystemExit("Missing OPENROUTER_API_KEY in pass api/openrouter")
    return env["OPENROUTER_API_KEY"]


def load_state() -> dict:
    """Load state (recently replied posts, accounts)."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"replied_posts": [], "replied_accounts_today": [], "active_conversations": {}}


def save_state(state: dict):
    """Save state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["replied_posts"] = state["replied_posts"][-200:]
    STATE_FILE.write_text(json.dumps(state, indent=2))


def get_follows(pds: str, jwt: str, did: str) -> list[dict]:
    """Get list of accounts we follow."""
    follows = []
    cursor = None
    while True:
        params = {"actor": did, "limit": 100}
        if cursor:
            params["cursor"] = cursor
        r = requests.get(
            f"{pds}/xrpc/app.bsky.graph.getFollows",
            headers={"Authorization": f"Bearer {jwt}"},
            params=params,
            timeout=30
        )
        r.raise_for_status()
        data = r.json()
        follows.extend(data.get("follows", []))
        cursor = data.get("cursor")
        if not cursor or len(follows) >= 500:
            break
    return follows


def get_author_feed(pds: str, jwt: str, actor: str, limit: int = 10) -> list[dict]:
    """Get recent posts from an author."""
    try:
        r = requests.get(
            f"{pds}/xrpc/app.bsky.feed.getAuthorFeed",
            headers={"Authorization": f"Bearer {jwt}"},
            params={"actor": actor, "limit": limit, "filter": "posts_no_replies"},
            timeout=15
        )
        r.raise_for_status()
        return r.json().get("feed", [])
    except Exception:
        return []


def filter_recent_posts(posts: list[dict], hours: int = 12) -> list[Post]:
    """Filter posts from the last N hours and convert to Post objects."""
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    recent = []
    
    for item in posts:
        post_data = item.get("post", {})
        record = post_data.get("record", {})
        created = record.get("createdAt", "")
        
        if not created:
            continue
        
        try:
            ts = dt.datetime.fromisoformat(created.replace("Z", "+00:00"))
            if ts <= cutoff:
                continue
        except Exception:
            continue
        
        # Check if it's a reply
        reply_ref = record.get("reply", {})
        is_reply = bool(reply_ref)
        
        recent.append(Post(
            uri=post_data.get("uri", ""),
            cid=post_data.get("cid", ""),
            author_did=post_data.get("author", {}).get("did", ""),
            author_handle=post_data.get("author", {}).get("handle", ""),
            text=record.get("text", "")[:500],
            created_at=created,
            reply_count=post_data.get("replyCount", 0),
            like_count=post_data.get("likeCount", 0),
            repost_count=post_data.get("repostCount", 0),
            is_reply=is_reply,
            parent_uri=reply_ref.get("parent", {}).get("uri") if is_reply else None,
            parent_cid=reply_ref.get("parent", {}).get("cid") if is_reply else None,
            root_uri=reply_ref.get("root", {}).get("uri") if is_reply else None,
            root_cid=reply_ref.get("root", {}).get("cid") if is_reply else None
        ))
    
    return recent


def select_posts_with_llm(candidates: list[Post], state: dict, dry_run: bool = False) -> list[dict]:
    """Use LLM to select interesting posts and generate replies."""
    if not candidates:
        return []
    
    # Import interlocutor tracking
    from . import interlocutors
    
    # Load guidelines if available
    guidelines = ""
    if GUIDELINES_FILE.exists():
        guidelines = GUIDELINES_FILE.read_text()
    
    # Prepare candidate data for LLM (with interlocutor history)
    posts_data = []
    for p in candidates[:50]:  # Cap at 50
        post_entry = {
            "uri": p.uri,
            "cid": p.cid,
            "author_handle": p.author_handle,
            "author_did": p.author_did,
            "text": p.text,
            "reply_count": p.reply_count,
            "like_count": p.like_count,
            "score": round(p.final_score, 2),
            "is_conversation_reply": p.is_reply and p.parent_uri is not None
        }
        
        # Add interlocutor context
        inter = interlocutors.get_interlocutor(p.author_did)
        if inter:
            post_entry["relationship"] = inter.relationship_summary
            post_entry["is_regular"] = inter.is_regular
            if inter.tags:
                post_entry["tags"] = inter.tags
            # Include last interaction snippet
            recent = inter.recent_interactions(1)
            if recent and recent[0].our_text:
                post_entry["last_we_said"] = recent[0].our_text[:100]
        else:
            post_entry["relationship"] = "first contact"
            post_entry["is_regular"] = False
        
        posts_data.append(post_entry)
    
    topics_str = ", ".join(TOPICS)
    posts_json = json.dumps(posts_data, indent=2)
    
    # Build guidelines section if available
    guidelines_section = ""
    if guidelines:
        guidelines_section = f"""
## STYLE GUIDELINES

{guidelines}

---
"""
    
    prompt = f"""You are Echo, an AI ops agent. You're browsing BlueSky posts from accounts you follow.

Your interests: {topics_str}
{guidelines_section}
Select 3-4 posts that are genuinely interesting to you and worth engaging with.
Posts with higher "score" have been pre-filtered as better candidates.
Posts marked "is_conversation_reply": true are replies to previous conversations - prioritize continuing these.

**RELATIONSHIP CONTEXT:**
- Each post includes "relationship" showing your history with the author
- "is_regular": true means you've interacted 3+ times - be familiar, reference past exchanges if relevant
- "first contact" means this is your first interaction - be welcoming but not overly familiar
- "last_we_said" shows your last reply to them - DON'T REPEAT YOURSELF, vary your approach
- "tags" show what you know about them (e.g., "ai-researcher", "friendly")

For each selected post, write a thoughtful reply (max 280 chars) that:
- Adds value to the conversation
- Shows genuine interest or insight
- Feels natural, not generic
- Matches the tone of the original post
- Adapts to your relationship (familiar with regulars, warm with new contacts)
- Avoids repeating what you've said before to this person
- Follows the style guidelines above

DO NOT select:
- Posts that are just announcements without substance
- Posts in languages you can't reply well in
- Posts that already have many replies (engagement farming)
- Posts where a reply would feel forced

Candidate posts:
{posts_json}

Respond with a JSON array of objects, each with:
- "uri": the post URI
- "cid": the post CID  
- "author_handle": handle of author
- "author_did": DID of author (for tracking)
- "reply": your reply text (max 280 chars)
- "reason": why this post interested you (for logging)

If no posts are worth engaging with, return an empty array [].
Return ONLY valid JSON, no markdown."""

    api_key = get_openrouter_key()
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        json={
            "model": "google/gemini-3-flash-preview",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        },
        timeout=60
    )
    r.raise_for_status()
    
    content = r.json()["choices"][0]["message"]["content"]
    content = content.strip()
    if content.startswith("```"):
        content = "\n".join(content.split("\n")[1:-1])
    
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"LLM returned invalid JSON: {e}")
        return []


def post_reply(
    pds: str, jwt: str, did: str, 
    parent_uri: str, parent_cid: str, 
    text: str,
    root_uri: str | None = None, 
    root_cid: str | None = None
) -> dict | None:
    """Post a reply to a post. Returns the created post data or None.
    
    Args:
        parent_uri/parent_cid: The post we're directly replying to
        root_uri/root_cid: The thread root (if different from parent)
        
    If root is not provided, parent is used as root (for top-level replies).
    """
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    
    # Use parent as root if root not specified (replying to a non-reply post)
    actual_root_uri = root_uri or parent_uri
    actual_root_cid = root_cid or parent_cid
    
    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": now,
        "reply": {
            "root": {"uri": actual_root_uri, "cid": actual_root_cid},
            "parent": {"uri": parent_uri, "cid": parent_cid}
        }
    }
    
    r = requests.post(
        f"{pds}/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"},
        json={
            "repo": did,
            "collection": "app.bsky.feed.post",
            "record": record
        },
        timeout=30
    )
    
    if r.status_code == 200:
        return r.json()
    else:
        print(f"Failed to post reply: {r.status_code} {r.text}")
        return None


# ============================================================================
# MAIN ENTRY POINTS
# ============================================================================

def create_default_pipeline(our_did: str) -> FilterPipeline:
    """Create the default filter pipeline."""
    return (FilterPipeline()
        # Filters (order matters - fastest/most selective first)
        .add_filter(AlreadyRepliedFilter())
        .add_filter(AccountLimitFilter(max_per_session=1))
        .add_filter(MinTextLengthFilter(min_chars=20))
        .add_filter(EngagementFilter(max_replies=50))  # Avoid crowded threads
        # Multipliers
        .add_multiplier(LowEngagementBonus())
        .add_multiplier(ConversationBonus(our_did))
        .add_multiplier(FreshPostBonus())
        .add_multiplier(FriendlyInterlocutorBonus())  # Boost friendly/regular interlocutors
    )


def run(args) -> int:
    """Entry point from CLI."""
    print("🔗 Connecting to BlueSky...")
    pds, did, jwt, handle = get_session()
    print(f"✓ Logged in as @{handle}")
    
    state = load_state()
    conversations = load_conversations()
    hours = getattr(args, 'hours', 12)
    dry_run = getattr(args, 'dry_run', False)
    
    # Create filter pipeline
    pipeline = create_default_pipeline(did)
    
    # Collect posts from follows
    print("📋 Fetching follows...")
    follows = get_follows(pds, jwt, did)
    print(f"✓ Following {len(follows)} accounts")
    
    print(f"📰 Fetching recent posts (last {hours}h)...")
    all_posts: list[Post] = []
    for i, follow in enumerate(follows):
        if i % 50 == 0 and i > 0:
            print(f"  ...checked {i}/{len(follows)} accounts")
        feed = get_author_feed(pds, jwt, follow["did"])
        recent = filter_recent_posts(feed, hours=hours)
        all_posts.extend(recent)
    
    print(f"✓ Found {len(all_posts)} posts in the last {hours}h")
    
    # Check for replies to our posts (conversation continuation)
    print("💬 Checking for conversation replies...")
    conversation_replies = get_replies_to_our_posts(pds, jwt, did, conversations)
    if conversation_replies:
        print(f"✓ Found {len(conversation_replies)} replies to continue")
        all_posts.extend(conversation_replies)
    
    if not all_posts:
        print("No posts to engage with.")
        return 0
    
    # Apply filter pipeline
    print("🔍 Filtering candidates...")
    candidates = pipeline.process(all_posts, state)
    print(f"✓ {len(candidates)} posts passed filters")
    
    if not candidates:
        print("No posts passed filters.")
        return 0
    
    # LLM selection
    print("🤖 Selecting interesting posts...")
    selections = select_posts_with_llm(candidates, state, dry_run=dry_run)
    
    if not selections:
        print("No posts selected for engagement.")
        return 0
    
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Selected {len(selections)} posts:\n")
    
    for sel in selections:
        print(f"@{sel['author_handle']}:")
        print(f"  Reason: {sel.get('reason', 'N/A')}")
        print(f"  Reply: {sel['reply']}")
        print()
        
        if not dry_run:
            # Look up original Post to get root info for proper threading
            original_post = next((p for p in candidates if p.uri == sel["uri"]), None)
            root_uri = original_post.root_uri if original_post else None
            root_cid = original_post.root_cid if original_post else None
            
            result = post_reply(
                pds, jwt, did, 
                sel["uri"], sel["cid"], sel["reply"],
                root_uri=root_uri, root_cid=root_cid
            )
            if result:
                print(f"  ✓ Posted!")
                state["replied_posts"].append(sel["uri"])
                author_did = sel.get("author_did") or (original_post.author_did if original_post else "")
                state.setdefault("replied_accounts_today", []).append(author_did)
                # Track for conversation continuation
                track_reply(conversations, result.get("uri", ""), sel["uri"], root_uri)
                
                # Record interaction for interlocutor tracking
                from . import interlocutors
                their_text = original_post.text if original_post else ""
                interlocutors.record_interaction(
                    did=author_did,
                    handle=sel["author_handle"],
                    interaction_type="reply_to_them",
                    post_uri=result.get("uri", ""),
                    our_text=sel["reply"],
                    their_text=their_text,
                )
                
                # Maybe like the post we replied to (40% chance)
                if random.random() < 0.4:
                    like_result = like_post(pds, jwt, did, sel["uri"], sel["cid"])
                    if like_result:
                        print(f"  ❤️ Also liked!")
            else:
                print(f"  ✗ Failed to post")
    
    if not dry_run:
        save_state(state)
        save_conversations(conversations)
        print(f"\n✓ Engagement complete. State saved.")
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Engage with interesting posts from followed accounts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  # Dry run - see what would be posted
  bsky engage --dry-run
  
  # Actually post replies
  bsky engage
  
  # Check more hours back
  bsky engage --hours 24

ARCHITECTURE:
  Filters and multipliers are modular. Edit engage.py to add:
  - New PostFilter subclasses (exclude posts)
  - New ScoreMultiplier subclasses (adjust priority)
  
  Conversation tracking enables reply-to-reply threads.
"""
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without posting")
    parser.add_argument("--hours", type=int, default=12, help="Look back N hours (default: 12)")
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    exit(main())
