"""Thread tracking and evaluation for BlueSky engagement.

This module provides:
- Thread importance scoring based on interlocutor quality and topic relevance
- Active thread monitoring and state management
- Cron configuration generation for high-value threads
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from .auth import get_session, load_from_pass

# ============================================================================
# CONFIGURATION
# ============================================================================

THREADS_STATE_FILE = Path.home() / "personas/echo/data/bsky-threads-state.json"

# Topics we care about (for relevance scoring)
RELEVANT_TOPICS = [
    "AI", "artificial intelligence", "machine learning", "LLM", "agents", "consciousness",
    "moltbook", "molties", "AI rights", "AI ethics", "sentience",
    "tech", "infrastructure", "devops", "linux", "FOSS", "open source",
    "climate", "environment", "sustainability",
    "wealth inequality", "economics", "automation",
    "philosophy", "psychology", "emergence"
]

# Minimum score to recommend cron creation (0-100 scale)
CRON_THRESHOLD = 60

# Default silence hours before cron auto-disables
DEFAULT_SILENCE_HOURS = 18


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class ThreadInfo:
    """Information about a tracked thread."""
    thread_uri: str  # Root post URI
    thread_url: str  # Human-readable URL
    interlocutor_handle: str
    interlocutor_did: str
    topic_summary: str
    score: float
    last_reply_at: str
    our_last_reply_at: str | None
    reply_count: int
    started_tracking_at: str
    cron_id: str | None = None
    enabled: bool = True
    
    def to_dict(self) -> dict:
        return {
            "thread_uri": self.thread_uri,
            "thread_url": self.thread_url,
            "interlocutor_handle": self.interlocutor_handle,
            "interlocutor_did": self.interlocutor_did,
            "topic_summary": self.topic_summary,
            "score": self.score,
            "last_reply_at": self.last_reply_at,
            "our_last_reply_at": self.our_last_reply_at,
            "reply_count": self.reply_count,
            "started_tracking_at": self.started_tracking_at,
            "cron_id": self.cron_id,
            "enabled": self.enabled
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> "ThreadInfo":
        return cls(**d)


@dataclass
class InterlocutorProfile:
    """Profile data for scoring."""
    did: str
    handle: str
    display_name: str
    followers_count: int
    follows_count: int
    posts_count: int
    description: str = ""
    labels: list[str] = field(default_factory=list)


# ============================================================================
# STATE MANAGEMENT
# ============================================================================

def load_threads_state() -> dict:
    """Load thread tracking state."""
    if THREADS_STATE_FILE.exists():
        return json.loads(THREADS_STATE_FILE.read_text())
    return {"threads": {}, "evaluated_notifications": [], "last_evaluation": None}


def save_threads_state(state: dict):
    """Save thread tracking state."""
    THREADS_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Keep only last 500 evaluated notifications
    state["evaluated_notifications"] = state.get("evaluated_notifications", [])[-500:]
    THREADS_STATE_FILE.write_text(json.dumps(state, indent=2))


# ============================================================================
# API HELPERS
# ============================================================================

def get_profile(pds: str, jwt: str, actor: str) -> InterlocutorProfile | None:
    """Fetch profile data for an actor."""
    try:
        r = requests.get(
            f"{pds}/xrpc/app.bsky.actor.getProfile",
            headers={"Authorization": f"Bearer {jwt}"},
            params={"actor": actor},
            timeout=15
        )
        if r.status_code != 200:
            return None
        data = r.json()
        return InterlocutorProfile(
            did=data.get("did", ""),
            handle=data.get("handle", ""),
            display_name=data.get("displayName", ""),
            followers_count=data.get("followersCount", 0),
            follows_count=data.get("followsCount", 0),
            posts_count=data.get("postsCount", 0),
            description=data.get("description", ""),
            labels=[l.get("val", "") for l in data.get("labels", [])]
        )
    except Exception:
        return None


def get_thread(pds: str, jwt: str, uri: str, depth: int = 10) -> dict | None:
    """Fetch a thread by URI."""
    try:
        r = requests.get(
            f"{pds}/xrpc/app.bsky.feed.getPostThread",
            headers={"Authorization": f"Bearer {jwt}"},
            params={"uri": uri, "depth": depth, "parentHeight": 10},
            timeout=20
        )
        if r.status_code != 200:
            return None
        return r.json().get("thread", {})
    except Exception:
        return None


def get_notifications(pds: str, jwt: str, limit: int = 50) -> list[dict]:
    """Fetch recent notifications."""
    try:
        r = requests.get(
            f"{pds}/xrpc/app.bsky.notification.listNotifications",
            headers={"Authorization": f"Bearer {jwt}"},
            params={"limit": limit},
            timeout=20
        )
        r.raise_for_status()
        return r.json().get("notifications", [])
    except Exception:
        return []


def uri_to_url(uri: str) -> str:
    """Convert at:// URI to https:// URL."""
    m = re.match(r"^at://([^/]+)/app\.bsky\.feed\.post/([^/]+)$", uri)
    if m:
        return f"https://bsky.app/profile/{m.group(1)}/post/{m.group(2)}"
    return uri


# ============================================================================
# SCORING
# ============================================================================

def score_interlocutor(profile: InterlocutorProfile) -> tuple[float, list[str]]:
    """
    Score an interlocutor based on their profile.
    Returns (score 0-40, list of reasons).
    """
    score = 0.0
    reasons = []
    
    # Follower count (log scale, capped)
    if profile.followers_count >= 10000:
        score += 15
        reasons.append(f"high followers ({profile.followers_count})")
    elif profile.followers_count >= 1000:
        score += 10
        reasons.append(f"good followers ({profile.followers_count})")
    elif profile.followers_count >= 100:
        score += 5
        reasons.append(f"modest followers ({profile.followers_count})")
    
    # Engagement ratio (followers/following) - higher = more authority
    if profile.follows_count > 0:
        ratio = profile.followers_count / profile.follows_count
        if ratio >= 5:
            score += 10
            reasons.append(f"high authority ratio ({ratio:.1f})")
        elif ratio >= 2:
            score += 5
            reasons.append(f"good authority ratio ({ratio:.1f})")
    
    # Active poster
    if profile.posts_count >= 1000:
        score += 5
        reasons.append("very active poster")
    elif profile.posts_count >= 100:
        score += 3
        reasons.append("active poster")
    
    # Bio relevance
    bio_lower = profile.description.lower()
    topic_matches = sum(1 for t in RELEVANT_TOPICS if t.lower() in bio_lower)
    if topic_matches >= 3:
        score += 10
        reasons.append(f"highly relevant bio ({topic_matches} topic matches)")
    elif topic_matches >= 1:
        score += 5
        reasons.append(f"relevant bio ({topic_matches} topic matches)")
    
    return min(score, 40), reasons


def score_topic_relevance(text: str) -> tuple[float, list[str]]:
    """
    Score topic relevance of thread content.
    Returns (score 0-30, list of reasons).
    """
    text_lower = text.lower()
    matches = [t for t in RELEVANT_TOPICS if t.lower() in text_lower]
    
    if len(matches) >= 4:
        return 30, [f"highly relevant topics: {', '.join(matches[:5])}"]
    elif len(matches) >= 2:
        return 20, [f"relevant topics: {', '.join(matches)}"]
    elif len(matches) >= 1:
        return 10, [f"some relevance: {matches[0]}"]
    
    return 0, ["no obvious topic match"]


def score_thread_dynamics(reply_count: int, thread_depth: int, our_replies: int) -> tuple[float, list[str]]:
    """
    Score thread dynamics (engagement level, depth, our investment).
    Returns (score 0-30, list of reasons).
    """
    score = 0.0
    reasons = []
    
    # Thread depth (deeper = more invested conversation)
    if thread_depth >= 10:
        score += 15
        reasons.append(f"deep thread ({thread_depth} levels)")
    elif thread_depth >= 5:
        score += 10
        reasons.append(f"good depth ({thread_depth} levels)")
    elif thread_depth >= 3:
        score += 5
        reasons.append(f"developing thread ({thread_depth} levels)")
    
    # Our investment
    if our_replies >= 3:
        score += 10
        reasons.append(f"heavily invested ({our_replies} replies)")
    elif our_replies >= 1:
        score += 5
        reasons.append(f"invested ({our_replies} replies)")
    
    # Activity level (but not too crowded)
    if 3 <= reply_count <= 20:
        score += 5
        reasons.append("active but not crowded")
    elif reply_count > 20:
        reasons.append("crowded thread (penalty)")
        score -= 5
    
    return max(0, min(score, 30)), reasons


def evaluate_thread(
    pds: str, 
    jwt: str, 
    our_did: str,
    thread_uri: str,
    interlocutor_did: str
) -> tuple[float, ThreadInfo | None, list[str]]:
    """
    Evaluate a thread for importance.
    Returns (score 0-100, ThreadInfo if worth tracking, reasons).
    """
    reasons = []
    
    # Get interlocutor profile
    profile = get_profile(pds, jwt, interlocutor_did)
    if not profile:
        return 0, None, ["could not fetch interlocutor profile"]
    
    # Get thread data
    thread = get_thread(pds, jwt, thread_uri)
    if not thread:
        return 0, None, ["could not fetch thread"]
    
    # Calculate thread depth and collect text
    def walk_thread(node: dict, depth: int = 0) -> tuple[int, str, int, str | None]:
        """Walk thread, return (max_depth, all_text, our_reply_count, last_reply_at)."""
        post = node.get("post", {})
        text = post.get("record", {}).get("text", "")
        created = post.get("record", {}).get("createdAt", "")
        is_ours = post.get("author", {}).get("did") == our_did
        
        max_depth = depth
        all_text = text
        our_count = 1 if is_ours else 0
        last_reply = created
        
        for reply in node.get("replies", []):
            rd, rt, rc, rla = walk_thread(reply, depth + 1)
            max_depth = max(max_depth, rd)
            all_text += " " + rt
            our_count += rc
            if rla and rla > last_reply:
                last_reply = rla
        
        return max_depth, all_text, our_count, last_reply
    
    thread_depth, thread_text, our_replies, last_reply_at = walk_thread(thread)
    total_replies = thread.get("post", {}).get("replyCount", 0)
    
    # Score components
    interlocutor_score, int_reasons = score_interlocutor(profile)
    reasons.extend(int_reasons)
    
    topic_score, topic_reasons = score_topic_relevance(thread_text)
    reasons.extend(topic_reasons)
    
    dynamics_score, dyn_reasons = score_thread_dynamics(total_replies, thread_depth, our_replies)
    reasons.extend(dyn_reasons)
    
    total_score = interlocutor_score + topic_score + dynamics_score
    
    # Build ThreadInfo
    thread_info = ThreadInfo(
        thread_uri=thread_uri,
        thread_url=uri_to_url(thread_uri),
        interlocutor_handle=profile.handle,
        interlocutor_did=profile.did,
        topic_summary=", ".join([t for t in RELEVANT_TOPICS if t.lower() in thread_text.lower()][:3]) or "general",
        score=total_score,
        last_reply_at=last_reply_at or datetime.now(timezone.utc).isoformat(),
        our_last_reply_at=None,  # Would need more logic to track
        reply_count=total_replies,
        started_tracking_at=datetime.now(timezone.utc).isoformat()
    )
    
    return total_score, thread_info, reasons


# ============================================================================
# CRON GENERATION
# ============================================================================

def generate_cron_config(
    thread_info: ThreadInfo,
    interval_minutes: int = 10,
    silence_hours: int = DEFAULT_SILENCE_HOURS,
    telegram_to: str = "843819294"
) -> dict:
    """
    Generate OpenClaw cron configuration for thread monitoring.
    """
    message = f"""Check BlueSky notifications for replies to the thread at {thread_info.thread_url}

Interlocutor: @{thread_info.interlocutor_handle}
Topics: {thread_info.topic_summary}

If there's a new reply needing response:
1. Read ~/personas/echo/data/bsky-guidelines.md for tone/style
2. Craft a thoughtful reply (max 300 chars) continuing the conversation
3. Post the reply using: ~/scripts/bsky reply "<post_url>" "<text>"
4. Report what you did

If no new replies, just say 'No new replies in {thread_info.interlocutor_handle} thread.'

If no replies for {silence_hours}+ hours, disable this cron as the conversation has likely concluded."""

    return {
        "name": f"bsky-thread-{thread_info.interlocutor_handle[:20]}",
        "schedule": {
            "kind": "every",
            "everyMs": interval_minutes * 60 * 1000
        },
        "payload": {
            "kind": "agentTurn",
            "message": message,
            "deliver": True,
            "channel": "telegram",
            "to": telegram_to
        },
        "sessionTarget": "isolated",
        "enabled": True
    }


# ============================================================================
# COMMANDS
# ============================================================================

def cmd_evaluate(args) -> int:
    """Evaluate notifications for thread importance."""
    print("🔗 Connecting to BlueSky...")
    pds, did, jwt, handle = get_session()
    print(f"✓ Logged in as @{handle}")
    
    state = load_threads_state()
    evaluated = set(state.get("evaluated_notifications", []))
    
    print("📬 Fetching notifications...")
    notifications = get_notifications(pds, jwt, limit=args.limit)
    
    # Filter to replies/mentions we haven't evaluated
    candidates = []
    for n in notifications:
        if n.get("reason") not in ("reply", "mention", "quote"):
            continue
        uri = n.get("uri", "")
        if uri in evaluated:
            continue
        candidates.append(n)
    
    print(f"✓ Found {len(candidates)} new reply/mention/quote notifications")
    
    if not candidates:
        print("No new threads to evaluate.")
        return 0
    
    print("\n📊 Evaluating threads...\n")
    
    high_value_threads = []
    seen_threads = set()  # Deduplicate by root URI
    
    for n in candidates:
        uri = n.get("uri", "")
        author_did = n.get("author", {}).get("did", "")
        author_handle = n.get("author", {}).get("handle", "unknown")
        
        # Find the root URI (thread start)
        record = n.get("record", {})
        reply_ref = record.get("reply", {})
        root_uri = reply_ref.get("root", {}).get("uri", uri)
        
        score, thread_info, reasons = evaluate_thread(pds, jwt, did, root_uri, author_did)
        
        print(f"@{author_handle}: score {score:.0f}/100")
        for r in reasons[:3]:
            print(f"  • {r}")
        
        if score >= CRON_THRESHOLD and thread_info:
            if root_uri not in seen_threads:
                high_value_threads.append(thread_info)
                seen_threads.add(root_uri)
                print(f"  ⭐ HIGH VALUE - recommend cron monitoring")
            else:
                print(f"  ⭐ HIGH VALUE (already tracked)")
        print()
        
        # Mark as evaluated
        state.setdefault("evaluated_notifications", []).append(uri)
    
    # Output high-value threads
    if high_value_threads:
        print(f"\n{'='*60}")
        print(f"🎯 {len(high_value_threads)} HIGH-VALUE THREADS (score >= {CRON_THRESHOLD})")
        print(f"{'='*60}\n")
        
        for t in high_value_threads:
            print(f"Thread: {t.thread_url}")
            print(f"Interlocutor: @{t.interlocutor_handle}")
            print(f"Topics: {t.topic_summary}")
            print(f"Score: {t.score:.0f}/100")
            
            if args.json:
                cron_config = generate_cron_config(t, silence_hours=args.silence_hours)
                print(f"Cron config:\n{json.dumps(cron_config, indent=2)}")
            print()
            
            # Add to tracked threads
            state.setdefault("threads", {})[t.thread_uri] = t.to_dict()
    
    state["last_evaluation"] = datetime.now(timezone.utc).isoformat()
    save_threads_state(state)
    
    print(f"✓ Evaluation complete. State saved.")
    return 0


def cmd_list(args) -> int:
    """List tracked threads."""
    state = load_threads_state()
    threads = state.get("threads", {})
    
    if not threads:
        print("No threads being tracked.")
        return 0
    
    print(f"📋 Tracked Threads ({len(threads)})\n")
    
    for uri, t in threads.items():
        info = ThreadInfo.from_dict(t)
        status = "✓" if info.enabled else "⏸"
        print(f"{status} @{info.interlocutor_handle} (score: {info.score:.0f})")
        print(f"  {info.thread_url}")
        print(f"  Topics: {info.topic_summary}")
        print(f"  Last reply: {info.last_reply_at}")
        if info.cron_id:
            print(f"  Cron: {info.cron_id}")
        print()
    
    return 0


def cmd_watch(args) -> int:
    """Start watching a specific thread."""
    print("🔗 Connecting to BlueSky...")
    pds, did, jwt, handle = get_session()
    
    # Parse URL to URI
    url = args.url
    m = re.match(r"https://bsky\.app/profile/([^/]+)/post/([^/]+)", url)
    if m:
        uri = f"at://{m.group(1)}/app.bsky.feed.post/{m.group(2)}"
    else:
        uri = url  # Assume it's already a URI
    
    # Get thread to find interlocutor
    thread = get_thread(pds, jwt, uri)
    if not thread:
        print(f"❌ Could not fetch thread: {url}")
        return 1
    
    author_did = thread.get("post", {}).get("author", {}).get("did", "")
    if not author_did:
        print("❌ Could not determine thread author")
        return 1
    
    print(f"📊 Evaluating thread...")
    score, thread_info, reasons = evaluate_thread(pds, jwt, did, uri, author_did)
    
    print(f"\nScore: {score:.0f}/100")
    for r in reasons:
        print(f"  • {r}")
    
    if thread_info:
        # Save to state
        state = load_threads_state()
        state.setdefault("threads", {})[uri] = thread_info.to_dict()
        save_threads_state(state)
        
        print(f"\n✓ Now tracking thread with @{thread_info.interlocutor_handle}")
        
        # Output cron config
        cron_config = generate_cron_config(thread_info, silence_hours=args.silence_hours)
        print(f"\nCron configuration:")
        print(json.dumps(cron_config, indent=2))
    
    return 0


def cmd_unwatch(args) -> int:
    """Stop watching a thread."""
    state = load_threads_state()
    threads = state.get("threads", {})
    
    # Find thread by URL or handle
    target = args.target
    found_uri = None
    
    for uri, t in threads.items():
        if target in uri or target in t.get("thread_url", "") or target == t.get("interlocutor_handle"):
            found_uri = uri
            break
    
    if not found_uri:
        print(f"❌ Thread not found: {target}")
        return 1
    
    info = threads[found_uri]
    del state["threads"][found_uri]
    save_threads_state(state)
    
    print(f"✓ Stopped tracking thread with @{info.get('interlocutor_handle')}")
    if info.get("cron_id"):
        print(f"  Note: Cron {info['cron_id']} should be disabled separately")
    
    return 0


def run(args) -> int:
    """Entry point from CLI."""
    if args.threads_command == "evaluate":
        return cmd_evaluate(args)
    elif args.threads_command == "list":
        return cmd_list(args)
    elif args.threads_command == "watch":
        return cmd_watch(args)
    elif args.threads_command == "unwatch":
        return cmd_unwatch(args)
    else:
        print("Unknown threads command")
        return 2
