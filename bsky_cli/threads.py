"""Thread tracking and evaluation for BlueSky engagement.

This module provides:
- Thread-level scoring for cron relevance
- Branch tracking within threads
- Topic drift detection for branch relevance
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

# Minimum thread depth before recommending cron (root → reply → reply = 3)
MIN_THREAD_DEPTH = 3

# Maximum topic drift before skipping a branch (0-1 scale)
MAX_TOPIC_DRIFT = 0.7

# Default silence hours before cron auto-disables
DEFAULT_SILENCE_HOURS = 18

# Backoff intervals in minutes (exponential: 10 → 20 → 40 → 80 → 160 → 240 → final 18h check)
BACKOFF_INTERVALS = [10, 20, 40, 80, 160, 240]


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class Branch:
    """A conversation branch within a thread."""
    our_reply_uri: str          # Our reply that created this branch
    our_reply_url: str          # Human-readable URL
    interlocutors: list[str]    # Handles of people in this branch
    interlocutor_dids: list[str]  # DIDs of people in this branch
    last_activity_at: str
    message_count: int
    topic_drift: float          # 0 = on topic, 1 = completely off topic
    branch_score: float         # Overall branch quality score
    
    def to_dict(self) -> dict:
        return {
            "our_reply_uri": self.our_reply_uri,
            "our_reply_url": self.our_reply_url,
            "interlocutors": self.interlocutors,
            "interlocutor_dids": self.interlocutor_dids,
            "last_activity_at": self.last_activity_at,
            "message_count": self.message_count,
            "topic_drift": self.topic_drift,
            "branch_score": self.branch_score
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> "Branch":
        return cls(**d)


@dataclass
class TrackedThread:
    """A thread being tracked with all its branches."""
    root_uri: str               # Root post URI
    root_url: str               # Human-readable URL
    root_author_handle: str
    root_author_did: str
    main_topics: list[str]      # Topics extracted from root post
    root_text: str              # Original post text (for drift comparison)
    overall_score: float        # Thread-level score
    branches: dict[str, Branch] # Keyed by our_reply_uri
    total_our_replies: int
    created_at: str
    last_activity_at: str
    engaged_interlocutors: list[str] = field(default_factory=list)  # DIDs we've replied to
    our_reply_texts: list[str] = field(default_factory=list)  # Our replies for consistency check
    cron_id: str | None = None
    enabled: bool = True
    # Backoff state
    backoff_level: int = 0      # Index into BACKOFF_INTERVALS (0 = 10min, 5 = 240min)
    last_check_at: str | None = None  # When we last checked this thread
    last_new_activity_at: str | None = None  # When we last saw new activity
    
    def to_dict(self) -> dict:
        return {
            "root_uri": self.root_uri,
            "root_url": self.root_url,
            "root_author_handle": self.root_author_handle,
            "root_author_did": self.root_author_did,
            "main_topics": self.main_topics,
            "root_text": self.root_text,
            "overall_score": self.overall_score,
            "branches": {k: v.to_dict() for k, v in self.branches.items()},
            "total_our_replies": self.total_our_replies,
            "created_at": self.created_at,
            "last_activity_at": self.last_activity_at,
            "engaged_interlocutors": self.engaged_interlocutors,
            "our_reply_texts": self.our_reply_texts,
            "cron_id": self.cron_id,
            "enabled": self.enabled,
            "backoff_level": self.backoff_level,
            "last_check_at": self.last_check_at,
            "last_new_activity_at": self.last_new_activity_at
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> "TrackedThread":
        branches = {k: Branch.from_dict(v) for k, v in d.get("branches", {}).items()}
        return cls(
            root_uri=d["root_uri"],
            root_url=d["root_url"],
            root_author_handle=d["root_author_handle"],
            root_author_did=d["root_author_did"],
            main_topics=d["main_topics"],
            root_text=d.get("root_text", ""),
            overall_score=d["overall_score"],
            branches=branches,
            total_our_replies=d.get("total_our_replies", 0),
            created_at=d["created_at"],
            last_activity_at=d["last_activity_at"],
            engaged_interlocutors=d.get("engaged_interlocutors", []),
            our_reply_texts=d.get("our_reply_texts", []),
            cron_id=d.get("cron_id"),
            enabled=d.get("enabled", True),
            backoff_level=d.get("backoff_level", 0),
            last_check_at=d.get("last_check_at"),
            last_new_activity_at=d.get("last_new_activity_at")
        )


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
# TOPIC ANALYSIS
# ============================================================================

def extract_topics(text: str) -> list[str]:
    """Extract relevant topics from text."""
    text_lower = text.lower()
    return [t for t in RELEVANT_TOPICS if t.lower() in text_lower]


def calculate_topic_drift(root_text: str, branch_text: str) -> float:
    """
    Calculate how much a branch has drifted from the root topic.
    Returns 0-1 where 0 = on topic, 1 = completely off topic.
    """
    root_topics = set(t.lower() for t in extract_topics(root_text))
    branch_topics = set(t.lower() for t in extract_topics(branch_text))
    
    if not root_topics:
        # No clear topics in root - can't measure drift
        return 0.0
    
    if not branch_topics:
        # Branch has no recognizable topics - moderate drift
        return 0.5
    
    # Calculate overlap
    overlap = len(root_topics & branch_topics)
    total = len(root_topics | branch_topics)
    
    if total == 0:
        return 0.5
    
    similarity = overlap / total
    return 1.0 - similarity  # Convert similarity to drift


# ============================================================================
# SCORING
# ============================================================================

def score_interlocutor(profile: InterlocutorProfile) -> tuple[float, list[str]]:
    """Score an interlocutor (0-40 scale)."""
    score = 0.0
    reasons = []
    
    if profile.followers_count >= 10000:
        score += 15
        reasons.append(f"high followers ({profile.followers_count})")
    elif profile.followers_count >= 1000:
        score += 10
        reasons.append(f"good followers ({profile.followers_count})")
    elif profile.followers_count >= 100:
        score += 5
        reasons.append(f"modest followers ({profile.followers_count})")
    
    if profile.follows_count > 0:
        ratio = profile.followers_count / profile.follows_count
        if ratio >= 5:
            score += 10
            reasons.append(f"high authority ratio ({ratio:.1f})")
        elif ratio >= 2:
            score += 5
            reasons.append(f"good authority ratio ({ratio:.1f})")
    
    if profile.posts_count >= 1000:
        score += 5
        reasons.append("very active poster")
    elif profile.posts_count >= 100:
        score += 3
        reasons.append("active poster")
    
    bio_lower = profile.description.lower()
    topic_matches = sum(1 for t in RELEVANT_TOPICS if t.lower() in bio_lower)
    if topic_matches >= 3:
        score += 10
        reasons.append(f"highly relevant bio ({topic_matches} topics)")
    elif topic_matches >= 1:
        score += 5
        reasons.append(f"relevant bio ({topic_matches} topics)")
    
    return min(score, 40), reasons


def score_topic_relevance(text: str) -> tuple[float, list[str]]:
    """Score topic relevance (0-30 scale)."""
    matches = extract_topics(text)
    
    if len(matches) >= 4:
        return 30, [f"highly relevant: {', '.join(matches[:5])}"]
    elif len(matches) >= 2:
        return 20, [f"relevant: {', '.join(matches)}"]
    elif len(matches) >= 1:
        return 10, [f"some relevance: {matches[0]}"]
    
    return 0, ["no obvious topic match"]


def score_thread_dynamics(total_replies: int, our_replies: int, branch_count: int) -> tuple[float, list[str]]:
    """Score thread dynamics (0-30 scale)."""
    score = 0.0
    reasons = []
    
    if our_replies >= 3:
        score += 15
        reasons.append(f"heavily invested ({our_replies} replies)")
    elif our_replies >= 1:
        score += 8
        reasons.append(f"invested ({our_replies} replies)")
    
    if branch_count >= 3:
        score += 10
        reasons.append(f"multi-branch conversation ({branch_count} branches)")
    elif branch_count >= 2:
        score += 5
        reasons.append(f"branching conversation ({branch_count} branches)")
    
    if 3 <= total_replies <= 30:
        score += 5
        reasons.append("active but not crowded")
    elif total_replies > 30:
        reasons.append("crowded thread")
        score -= 5
    
    return max(0, min(score, 30)), reasons


def score_branch(
    branch: Branch, 
    main_topics: list[str], 
    profiles: dict[str, InterlocutorProfile],
    engaged_interlocutors: set[str] | None = None
) -> float:
    """
    Score a branch for response priority.
    Returns 0-100 where higher = more worth responding to.
    
    If engaged_interlocutors is provided, topic drift is ignored for
    interlocutors we've already engaged with (conversations evolve naturally).
    """
    score = 0.0
    
    # Check if we've already engaged with this interlocutor in this thread
    already_engaged = False
    if engaged_interlocutors:
        already_engaged = bool(set(branch.interlocutor_dids) & engaged_interlocutors)
    
    # Topic alignment (0-40) - BUT skip this penalty for engaged interlocutors
    if already_engaged:
        # Give full topic points - we're in an ongoing conversation
        score += 40
    else:
        topic_score = 40 * (1 - branch.topic_drift)
        score += topic_score
    
    # Interlocutor quality (0-30) - average of all interlocutors
    interlocutor_scores = []
    for did in branch.interlocutor_dids:
        if did in profiles:
            int_score, _ = score_interlocutor(profiles[did])
            interlocutor_scores.append(int_score)
    if interlocutor_scores:
        score += (sum(interlocutor_scores) / len(interlocutor_scores)) * 0.75  # Scale to 0-30
    
    # Activity (0-20)
    if branch.message_count >= 5:
        score += 20
    elif branch.message_count >= 3:
        score += 15
    elif branch.message_count >= 2:
        score += 10
    
    # Recency (0-10)
    try:
        last = datetime.fromisoformat(branch.last_activity_at.replace("Z", "+00:00"))
        age_hours = (datetime.now(timezone.utc) - last).total_seconds() / 3600
        if age_hours < 1:
            score += 10
        elif age_hours < 6:
            score += 5
    except Exception:
        pass
    
    return min(score, 100)


# ============================================================================
# THREAD ANALYSIS
# ============================================================================

def analyze_thread(pds: str, jwt: str, our_did: str, root_uri: str) -> TrackedThread | None:
    """
    Fully analyze a thread, extracting all branches we're involved in.
    """
    thread = get_thread(pds, jwt, root_uri, depth=20)
    if not thread:
        return None
    
    root_post = thread.get("post", {})
    root_record = root_post.get("record", {})
    root_text = root_record.get("text", "")
    root_author = root_post.get("author", {})
    
    main_topics = extract_topics(root_text)
    branches: dict[str, Branch] = {}
    our_reply_uris: list[str] = []
    our_reply_texts: list[str] = []  # For consistency checking
    all_interlocutor_dids: set[str] = set()
    engaged_interlocutors: set[str] = set()  # People we've replied to
    latest_activity = root_record.get("createdAt", "")
    
    def walk_thread(node: dict, parent_is_ours: bool = False, branch_key: str | None = None, parent_author_did: str | None = None):
        """Recursively walk thread to find our replies and track branches."""
        nonlocal latest_activity
        
        post = node.get("post", {})
        record = post.get("record", {})
        author = post.get("author", {})
        uri = post.get("uri", "")
        created = record.get("createdAt", "")
        text = record.get("text", "")
        author_did = author.get("did", "")
        author_handle = author.get("handle", "")
        is_ours = author_did == our_did
        
        if created and created > latest_activity:
            latest_activity = created
        
        # If this is our reply, it starts or continues a branch
        if is_ours:
            our_reply_uris.append(uri)
            our_reply_texts.append(text)  # Track our text for consistency
            # Track who we're engaging with
            if parent_author_did and parent_author_did != our_did:
                engaged_interlocutors.add(parent_author_did)
            if uri not in branches:
                branches[uri] = Branch(
                    our_reply_uri=uri,
                    our_reply_url=uri_to_url(uri),
                    interlocutors=[],
                    interlocutor_dids=[],
                    last_activity_at=created,
                    message_count=1,
                    topic_drift=0.0,
                    branch_score=0.0
                )
            branch_key = uri
        elif branch_key and branch_key in branches:
            # This is a reply to one of our branches
            branch = branches[branch_key]
            if author_handle and author_handle not in branch.interlocutors:
                branch.interlocutors.append(author_handle)
            if author_did and author_did not in branch.interlocutor_dids:
                branch.interlocutor_dids.append(author_did)
                all_interlocutor_dids.add(author_did)
            branch.message_count += 1
            if created > branch.last_activity_at:
                branch.last_activity_at = created
            # Accumulate text for topic drift calculation
            if not hasattr(branch, '_accumulated_text'):
                branch._accumulated_text = ""
            branch._accumulated_text += " " + text
        
        # Recurse into replies
        for reply in node.get("replies", []):
            walk_thread(reply, parent_is_ours=is_ours, branch_key=branch_key, parent_author_did=author_did)
    
    walk_thread(thread)
    
    # Calculate topic drift for each branch
    for branch in branches.values():
        branch_text = getattr(branch, '_accumulated_text', "")
        branch.topic_drift = calculate_topic_drift(root_text, branch_text)
        # Clean up temp attribute
        if hasattr(branch, '_accumulated_text'):
            delattr(branch, '_accumulated_text')
    
    # Fetch interlocutor profiles for scoring
    profiles: dict[str, InterlocutorProfile] = {}
    for did in all_interlocutor_dids:
        profile = get_profile(pds, jwt, did)
        if profile:
            profiles[did] = profile
    
    # Score branches (pass engaged_interlocutors to relax drift for ongoing conversations)
    for branch in branches.values():
        branch.branch_score = score_branch(branch, main_topics, profiles, engaged_interlocutors)
    
    # Calculate overall thread score
    total_replies = root_post.get("replyCount", 0)
    
    # Get root author profile for scoring
    root_profile = get_profile(pds, jwt, root_author.get("did", ""))
    interlocutor_score = 0
    if root_profile:
        interlocutor_score, _ = score_interlocutor(root_profile)
    
    topic_score, _ = score_topic_relevance(root_text)
    dynamics_score, _ = score_thread_dynamics(total_replies, len(our_reply_uris), len(branches))
    
    overall_score = interlocutor_score + topic_score + dynamics_score
    
    return TrackedThread(
        root_uri=root_uri,
        root_url=uri_to_url(root_uri),
        root_author_handle=root_author.get("handle", "unknown"),
        root_author_did=root_author.get("did", ""),
        main_topics=main_topics,
        root_text=root_text[:500],
        overall_score=overall_score,
        branches=branches,
        total_our_replies=len(our_reply_uris),
        created_at=root_record.get("createdAt", ""),
        last_activity_at=latest_activity,
        engaged_interlocutors=list(engaged_interlocutors),
        our_reply_texts=our_reply_texts[-10:]  # Keep last 10 for consistency checking
    )


# ============================================================================
# CRON GENERATION
# ============================================================================

def generate_cron_config(
    thread: TrackedThread,
    interval_minutes: int = 10,
    silence_hours: int = DEFAULT_SILENCE_HOURS,
    telegram_to: str = "843819294",
    key_facts: str = ""
) -> dict:
    """Generate OpenClaw cron configuration for thread monitoring."""
    
    # List active branches
    branch_info = []
    for uri, branch in thread.branches.items():
        if branch.branch_score >= 40:  # Only mention worthwhile branches
            is_engaged = bool(set(branch.interlocutor_dids) & set(thread.engaged_interlocutors))
            drift_status = "engaged" if is_engaged else ("on-topic" if branch.topic_drift < 0.3 else "drifting" if branch.topic_drift < 0.7 else "off-topic")
            branch_info.append(f"  - @{', @'.join(branch.interlocutors[:3])} ({drift_status}, score {branch.branch_score:.0f})")
    
    branches_text = "\n".join(branch_info) if branch_info else "  (no active branches yet)"
    
    # Include recent replies for consistency checking
    consistency_text = ""
    if thread.our_reply_texts:
        recent = thread.our_reply_texts[-3:]
        consistency_text = "\n**OUR RECENT REPLIES (check consistency):**\n" + "\n".join(
            f"  - \"{t[:80]}{'...' if len(t) > 80 else ''}\"" for t in recent
        )
    
    message = f"""Check BlueSky notifications for the thread at {thread.root_url}

**THREAD INFO:**
- Root author: @{thread.root_author_handle}
- Topics: {', '.join(thread.main_topics) or 'general'}
- Our replies: {thread.total_our_replies}
- Branches:
{branches_text}
{consistency_text}

{f"**KEY FACTS:**{chr(10)}{key_facts}{chr(10)}" if key_facts else ""}
**INSTRUCTIONS:**
1. Run `~/scripts/bsky threads branches {thread.root_author_handle}` to see branch status
2. For engaged interlocutors (people we've already replied to): ALWAYS respond regardless of topic drift
3. For new interlocutors: skip if drift > 70% or score < 40
4. **CHECK CONSISTENCY**: Read our recent replies above. Don't contradict yourself!
5. Read ~/personas/echo/data/bsky-guidelines.md for tone/style
6. Craft thoughtful replies (max 300 chars)
7. STAY FACTUAL - don't make claims you're unsure about
8. Post replies and report what you did

If no new activity, just say 'No new replies in {thread.root_author_handle} thread.'

If no replies for {silence_hours}+ hours, disable this cron as the conversation has likely concluded."""

    return {
        "name": f"bsky-thread-{thread.root_author_handle[:20]}",
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
    
    print("\n📊 Analyzing threads...\n")
    
    # Group by root URI to avoid duplicate analysis
    root_uris: dict[str, list[dict]] = {}
    for n in candidates:
        record = n.get("record", {})
        reply_ref = record.get("reply", {})
        root_uri = reply_ref.get("root", {}).get("uri") or n.get("uri", "")
        root_uris.setdefault(root_uri, []).append(n)
    
    high_value_threads: list[TrackedThread] = []
    
    for root_uri, notifs in root_uris.items():
        print(f"Analyzing thread: {uri_to_url(root_uri)[:60]}...")
        
        thread = analyze_thread(pds, jwt, did, root_uri)
        if not thread:
            print("  ✗ Could not fetch thread")
            continue
        
        print(f"  @{thread.root_author_handle}: score {thread.overall_score:.0f}/100")
        print(f"  Topics: {', '.join(thread.main_topics) or 'general'}")
        print(f"  Branches: {len(thread.branches)}, Our replies: {thread.total_our_replies}")
        
        # Show branch details
        for uri, branch in thread.branches.items():
            drift_pct = int(branch.topic_drift * 100)
            print(f"    └─ @{', @'.join(branch.interlocutors[:2]) or 'unknown'}: "
                  f"drift {drift_pct}%, score {branch.branch_score:.0f}")
        
        # Check if thread qualifies for cron
        if thread.overall_score >= CRON_THRESHOLD:
            if thread.total_our_replies >= MIN_THREAD_DEPTH - 1:
                high_value_threads.append(thread)
                print(f"  ⭐ HIGH VALUE - recommend cron monitoring")
            else:
                print(f"  ⭐ HIGH VALUE (too shallow: {thread.total_our_replies + 1}/{MIN_THREAD_DEPTH} exchanges)")
        print()
        
        # Mark notifications as evaluated
        for n in notifs:
            state.setdefault("evaluated_notifications", []).append(n.get("uri", ""))
        
        # Save thread to state
        state.setdefault("threads", {})[root_uri] = thread.to_dict()
    
    # Output high-value threads
    if high_value_threads:
        print(f"\n{'='*60}")
        print(f"🎯 {len(high_value_threads)} HIGH-VALUE THREADS (score >= {CRON_THRESHOLD})")
        print(f"{'='*60}\n")
        
        for t in high_value_threads:
            print(f"Thread: {t.root_url}")
            print(f"Root author: @{t.root_author_handle}")
            print(f"Topics: {', '.join(t.main_topics) or 'general'}")
            print(f"Score: {t.overall_score:.0f}/100")
            print(f"Branches: {len(t.branches)}")
            
            if args.json:
                cron_config = generate_cron_config(t, silence_hours=args.silence_hours)
                print(f"Cron config:\n{json.dumps(cron_config, indent=2)}")
            print()
    
    state["last_evaluation"] = datetime.now(timezone.utc).isoformat()
    save_threads_state(state)
    
    print(f"✓ Evaluation complete. State saved.")
    return 0


def cmd_list(args) -> int:
    """List tracked threads."""
    state = load_threads_state()
    threads_data = state.get("threads", {})
    
    if not threads_data:
        print("No threads being tracked.")
        return 0
    
    print(f"📋 Tracked Threads ({len(threads_data)})\n")
    
    for uri, t_data in threads_data.items():
        t = TrackedThread.from_dict(t_data)
        status = "✓" if t.enabled else "⏸"
        print(f"{status} @{t.root_author_handle} (score: {t.overall_score:.0f})")
        print(f"  {t.root_url}")
        print(f"  Topics: {', '.join(t.main_topics) or 'general'}")
        print(f"  Branches: {len(t.branches)}, Our replies: {t.total_our_replies}")
        print(f"  Last activity: {t.last_activity_at}")
        
        # Show branches
        for branch_uri, branch in t.branches.items():
            drift_pct = int(branch.topic_drift * 100)
            print(f"    └─ @{', @'.join(branch.interlocutors[:2]) or '?'}: "
                  f"drift {drift_pct}%, score {branch.branch_score:.0f}, "
                  f"{branch.message_count} msgs")
        
        if t.cron_id:
            print(f"  Cron: {t.cron_id}")
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
        uri = url
    
    print(f"📊 Analyzing thread...")
    thread = analyze_thread(pds, jwt, did, uri)
    
    if not thread:
        print(f"❌ Could not fetch thread: {url}")
        return 1
    
    print(f"\nThread: {thread.root_url}")
    print(f"Root author: @{thread.root_author_handle}")
    print(f"Topics: {', '.join(thread.main_topics) or 'general'}")
    print(f"Score: {thread.overall_score:.0f}/100")
    print(f"Branches: {len(thread.branches)}, Our replies: {thread.total_our_replies}")
    
    for branch_uri, branch in thread.branches.items():
        drift_pct = int(branch.topic_drift * 100)
        print(f"  └─ @{', @'.join(branch.interlocutors[:2]) or '?'}: "
              f"drift {drift_pct}%, score {branch.branch_score:.0f}")
    
    # Save to state
    state = load_threads_state()
    state.setdefault("threads", {})[uri] = thread.to_dict()
    save_threads_state(state)
    
    print(f"\n✓ Now tracking thread")
    
    # Output cron config
    cron_config = generate_cron_config(thread, silence_hours=args.silence_hours)
    print(f"\nCron configuration:")
    print(json.dumps(cron_config, indent=2))
    
    return 0


def cmd_unwatch(args) -> int:
    """Stop watching a thread."""
    state = load_threads_state()
    threads = state.get("threads", {})
    
    target = args.target
    found_uri = None
    
    for uri, t_data in threads.items():
        if (target in uri or 
            target in t_data.get("root_url", "") or 
            target == t_data.get("root_author_handle")):
            found_uri = uri
            break
    
    if not found_uri:
        print(f"❌ Thread not found: {target}")
        return 1
    
    t_data = threads[found_uri]
    del state["threads"][found_uri]
    save_threads_state(state)
    
    print(f"✓ Stopped tracking thread with @{t_data.get('root_author_handle')}")
    if t_data.get("cron_id"):
        print(f"  Note: Cron {t_data['cron_id']} should be disabled separately")
    
    return 0


def cmd_check_branches(args) -> int:
    """Check branch relevance for a tracked thread."""
    print("🔗 Connecting to BlueSky...")
    pds, did, jwt, handle = get_session()
    
    state = load_threads_state()
    threads = state.get("threads", {})
    
    # Find thread
    target = args.target
    found_uri = None
    for uri, t_data in threads.items():
        if (target in uri or 
            target in t_data.get("root_url", "") or 
            target == t_data.get("root_author_handle")):
            found_uri = uri
            break
    
    if not found_uri:
        print(f"❌ Thread not found: {target}")
        return 1
    
    print(f"📊 Re-analyzing thread...")
    thread = analyze_thread(pds, jwt, did, found_uri)
    
    if not thread:
        print("❌ Could not fetch thread")
        return 1
    
    print(f"\nThread: {thread.root_url}")
    print(f"Topics: {', '.join(thread.main_topics) or 'general'}")
    print(f"Engaged interlocutors: {len(thread.engaged_interlocutors)}")
    print(f"\nBranch Analysis:")
    print("-" * 50)
    
    for branch_uri, branch in thread.branches.items():
        drift_pct = int(branch.topic_drift * 100)
        # Check if we've engaged with this interlocutor before
        is_engaged = bool(set(branch.interlocutor_dids) & set(thread.engaged_interlocutors))
        
        # More permissive for engaged interlocutors
        if is_engaged:
            status = "✓ RESPOND (engaged)" if branch.branch_score >= 30 else "⏭ SKIP"
        else:
            status = "✓ RESPOND" if branch.topic_drift < MAX_TOPIC_DRIFT and branch.branch_score >= 40 else "⏭ SKIP"
        
        print(f"\n{status} Branch with @{', @'.join(branch.interlocutors[:3]) or 'unknown'}")
        print(f"  URL: {branch.our_reply_url}")
        print(f"  Messages: {branch.message_count}")
        print(f"  Topic drift: {drift_pct}%{' (ignored - engaged)' if is_engaged else ' (off-topic)' if drift_pct >= 70 else ' (on-topic)' if drift_pct < 30 else ' (drifting)'}")
        print(f"  Branch score: {branch.branch_score:.0f}/100")
        print(f"  Last activity: {branch.last_activity_at}")
    
    # Show our previous replies for consistency checking
    if thread.our_reply_texts:
        print(f"\n{'='*50}")
        print("📝 Our previous replies (for consistency):")
        print("-" * 50)
        for i, text in enumerate(thread.our_reply_texts[-5:], 1):
            print(f"{i}. {text[:100]}{'...' if len(text) > 100 else ''}")
    
    # Update state
    state["threads"][found_uri] = thread.to_dict()
    save_threads_state(state)
    
    return 0


def cmd_backoff_check(args) -> int:
    """
    Check if we should run a thread check based on backoff state.
    Returns 0 if should check, 1 if should skip, 2 on error.
    
    This implements exponential backoff:
    - Start at 10 minutes
    - If no new activity: 10 → 20 → 40 → 80 → 160 → 240 minutes
    - After 240 min with no activity: one final check at 18h, then disable
    - If new activity detected: reset to 10 minutes
    
    IMPORTANT: Even during backoff, we peek at notifications. If new activity
    is detected, we reset backoff and proceed with check immediately.
    """
    # First, peek at notifications to detect new activity during backoff
    try:
        pds, did, jwt, handle = get_session()
        notifications = get_notifications(pds, jwt, limit=20)
        
        # Check for recent replies/mentions (last 10 minutes)
        recent_cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        new_activity = False
        
        for n in notifications:
            if n.get("reason") not in ("reply", "mention", "quote"):
                continue
            indexed = n.get("indexedAt", "")
            if indexed:
                try:
                    ts = datetime.fromisoformat(indexed.replace("Z", "+00:00"))
                    if ts > recent_cutoff:
                        new_activity = True
                        print(f"🔔 New activity detected! Resetting backoff...")
                        break
                except Exception:
                    pass
        
        if new_activity:
            # Reset backoff and proceed with check
            state = load_threads_state()
            threads = state.get("threads", {})
            target = args.target
            for uri, t_data in threads.items():
                if (target in uri or 
                    target in t_data.get("root_url", "") or 
                    target == t_data.get("root_author_handle")):
                    t_data["backoff_level"] = 0
                    t_data["last_new_activity_at"] = datetime.now(timezone.utc).isoformat()
                    state["threads"][uri] = t_data
                    save_threads_state(state)
                    break
            print(f"✓ CHECK - New activity, backoff reset to 0")
            return 0
    except Exception as e:
        # If notification check fails, fall through to normal backoff logic
        print(f"⚠️ Could not check notifications: {e}")
    
    state = load_threads_state()
    threads = state.get("threads", {})
    
    target = args.target
    found_uri = None
    for uri, t_data in threads.items():
        if (target in uri or 
            target in t_data.get("root_url", "") or 
            target == t_data.get("root_author_handle")):
            found_uri = uri
            break
    
    if not found_uri:
        print(f"❌ Thread not found: {target}")
        return 2
    
    thread = TrackedThread.from_dict(threads[found_uri])
    now = datetime.now(timezone.utc)
    
    # Get current backoff interval
    backoff_level = thread.backoff_level
    if backoff_level >= len(BACKOFF_INTERVALS):
        # We're past all intervals - check if 18h have passed for final check
        if thread.last_check_at:
            last_check = datetime.fromisoformat(thread.last_check_at.replace("Z", "+00:00"))
            hours_since = (now - last_check).total_seconds() / 3600
            if hours_since < DEFAULT_SILENCE_HOURS:
                remaining = DEFAULT_SILENCE_HOURS - hours_since
                print(f"⏸ SKIP - Final 18h check not due yet ({remaining:.1f}h remaining)")
                print(f"  Thread: @{thread.root_author_handle}")
                print(f"  Backoff: FINAL (18h)")
                return 1
            else:
                print(f"🔚 FINAL CHECK - 18h silence reached")
                print(f"  Thread: @{thread.root_author_handle}")
                print(f"  Recommendation: Disable cron if no activity")
                return 0
        current_interval = DEFAULT_SILENCE_HOURS * 60  # In minutes
    else:
        current_interval = BACKOFF_INTERVALS[backoff_level]
    
    # Check if enough time has passed
    if thread.last_check_at:
        last_check = datetime.fromisoformat(thread.last_check_at.replace("Z", "+00:00"))
        minutes_since = (now - last_check).total_seconds() / 60
        
        if minutes_since < current_interval:
            remaining = current_interval - minutes_since
            print(f"⏸ SKIP - Not due yet ({remaining:.0f}min remaining)")
            print(f"  Thread: @{thread.root_author_handle}")
            print(f"  Backoff level: {backoff_level} ({current_interval}min interval)")
            return 1
    
    # Should check - output status
    print(f"✓ CHECK - Due now")
    print(f"  Thread: @{thread.root_author_handle}")
    print(f"  Backoff level: {backoff_level} ({current_interval}min interval)")
    print(f"  Last activity: {thread.last_activity_at}")
    return 0


def cmd_backoff_update(args) -> int:
    """
    Update backoff state after a check.
    Call with --activity if new activity was found, otherwise backoff increases.
    """
    state = load_threads_state()
    threads = state.get("threads", {})
    
    target = args.target
    found_uri = None
    for uri, t_data in threads.items():
        if (target in uri or 
            target in t_data.get("root_url", "") or 
            target == t_data.get("root_author_handle")):
            found_uri = uri
            break
    
    if not found_uri:
        print(f"❌ Thread not found: {target}")
        return 2
    
    thread_data = threads[found_uri]
    now = datetime.now(timezone.utc).isoformat()
    
    # Update last check time
    thread_data["last_check_at"] = now
    
    if args.activity:
        # New activity - reset backoff to 0
        old_level = thread_data.get("backoff_level", 0)
        thread_data["backoff_level"] = 0
        thread_data["last_new_activity_at"] = now
        print(f"✓ Backoff RESET (was level {old_level}, now 0)")
        print(f"  Next check: 10 minutes")
    else:
        # No activity - increase backoff
        old_level = thread_data.get("backoff_level", 0)
        new_level = min(old_level + 1, len(BACKOFF_INTERVALS))
        thread_data["backoff_level"] = new_level
        
        if new_level >= len(BACKOFF_INTERVALS):
            print(f"⏫ Backoff MAXED (level {old_level} → FINAL)")
            print(f"  Next check: 18 hours (final check before disable)")
        else:
            next_interval = BACKOFF_INTERVALS[new_level]
            print(f"⏫ Backoff INCREASED (level {old_level} → {new_level})")
            print(f"  Next check: {next_interval} minutes")
    
    state["threads"][found_uri] = thread_data
    save_threads_state(state)
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
    elif args.threads_command == "branches":
        return cmd_check_branches(args)
    elif args.threads_command == "backoff-check":
        return cmd_backoff_check(args)
    elif args.threads_command == "backoff-update":
        return cmd_backoff_update(args)
    else:
        print("Unknown threads command")
        return 2
