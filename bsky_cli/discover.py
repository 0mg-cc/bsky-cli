"""Discover new accounts to follow based on network and reposts."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
from collections import Counter
from pathlib import Path

from .http import requests

from .auth import get_session, load_from_pass
from .config import get, get_section
from .runtime_guard import RuntimeGuard, TIMEOUT_EXIT_CODE, log_phase

# ============================================================================
# CONFIGURATION (loaded from ~/.config/bsky-cli/config.yaml)
# ============================================================================

STATE_FILE = Path.home() / "personas/echo/data/bsky-discover-state.json"

def get_discover_defaults() -> dict:
    """Get default discover config, overridable via config file."""
    cfg = get_section("discover")
    return {
        "follows_sample_pct": cfg.get("follows_sample_pct", 0.10),
        "repost_top_pct": cfg.get("repost_top_pct", 0.20),
        "scan_cooldown_days": cfg.get("scan_cooldown_days", 90),
        "min_posts": cfg.get("min_posts", 5),
        "min_followers": cfg.get("min_followers", 10),
        "max_following_ratio": cfg.get("max_following_ratio", 10),
    }

# For backwards compatibility
DEFAULT_CONFIG = get_discover_defaults()

def get_topics() -> list[str]:
    return get("topics", [
        "tech", "ops", "infrastructure", "devops", "sysadmin",
        "AI", "machine learning", "LLM", "agents", "automation",
        "linux", "FOSS", "open source", "programming",
        "climate", "environment", "sustainability",
        "economics", "social justice", "politics",
        "philosophy", "psychology", "consciousness",
    ])


# ============================================================================
# STATE MANAGEMENT
# ============================================================================

def load_state() -> dict:
    """Load discovery state."""
    if STATE_FILE.exists():
        data = json.loads(STATE_FILE.read_text())
    else:
        data = {}
    
    # Ensure structure
    data.setdefault("follows_scanned", {})
    data.setdefault("repost_authors", {})
    data.setdefault("last_repost_analysis", None)
    data.setdefault("already_followed", [])
    data.setdefault("config", DEFAULT_CONFIG)
    
    return data


def save_state(state: dict):
    """Save discovery state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def get_config(state: dict) -> dict:
    """Get config with defaults."""
    config = DEFAULT_CONFIG.copy()
    config.update(state.get("config", {}))
    return config


# ============================================================================
# API HELPERS
# ============================================================================

def get_follows(
    pds: str,
    jwt: str,
    actor: str,
    limit: int | None = None,
    max_pages: int = 200,
) -> list[dict]:
    """Get accounts that an actor follows.

    Includes pagination safety guards so a malformed or repeating cursor
    cannot trap the caller in an infinite loop.
    """
    follows = []
    cursor = None
    seen_cursors = set()
    pages = 0

    while True:
        params = {"actor": actor, "limit": 100}
        if cursor:
            params["cursor"] = cursor
        try:
            r = requests.get(
                f"{pds}/xrpc/app.bsky.graph.getFollows",
                headers={"Authorization": f"Bearer {jwt}"},
                params=params,
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
            follows.extend(data.get("follows", []))
            pages += 1

            if limit and len(follows) >= limit:
                break
            if pages >= max_pages:
                break

            next_cursor = data.get("cursor")
            if not next_cursor:
                break
            if next_cursor == cursor or next_cursor in seen_cursors:
                break

            seen_cursors.add(next_cursor)
            cursor = next_cursor
        except Exception:
            break
    return follows[:limit] if limit else follows


def get_followers(pds: str, jwt: str, actor: str) -> int:
    """Get follower count for an actor."""
    try:
        r = requests.get(
            f"{pds}/xrpc/app.bsky.actor.getProfile",
            headers={"Authorization": f"Bearer {jwt}"},
            params={"actor": actor},
            timeout=15
        )
        r.raise_for_status()
        return r.json().get("followersCount", 0)
    except Exception:
        return 0


def get_profile(pds: str, jwt: str, actor: str) -> dict | None:
    """Get full profile for an actor."""
    try:
        r = requests.get(
            f"{pds}/xrpc/app.bsky.actor.getProfile",
            headers={"Authorization": f"Bearer {jwt}"},
            params={"actor": actor},
            timeout=15
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def get_author_feed(pds: str, jwt: str, actor: str, limit: int = 30) -> list[dict]:
    """Get recent posts from an author (including reposts)."""
    try:
        r = requests.get(
            f"{pds}/xrpc/app.bsky.feed.getAuthorFeed",
            headers={"Authorization": f"Bearer {jwt}"},
            params={"actor": actor, "limit": limit},
            timeout=15
        )
        r.raise_for_status()
        return r.json().get("feed", [])
    except Exception:
        return []


def follow_account(pds: str, jwt: str, my_did: str, target_did: str) -> bool:
    """Follow an account."""
    now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        r = requests.post(
            f"{pds}/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"},
            json={
                "repo": my_did,
                "collection": "app.bsky.graph.follow",
                "record": {
                    "$type": "app.bsky.graph.follow",
                    "subject": target_did,
                    "createdAt": now
                }
            },
            timeout=30
        )
        return r.status_code == 200
    except Exception:
        return False


# ============================================================================
# CANDIDATE SCORING
# ============================================================================

def score_candidate(profile: dict, config: dict) -> tuple[float, list[str]]:
    """Score a candidate profile. Returns (score, reasons)."""
    score = 0.0
    reasons = []
    
    if not profile:
        return 0, ["no profile"]
    
    followers = profile.get("followersCount", 0)
    following = profile.get("followsCount", 0)
    posts = profile.get("postsCount", 0)
    bio = profile.get("description", "") or ""
    display_name = profile.get("displayName", "") or ""
    
    # Minimum thresholds
    if posts < config["min_posts"]:
        return 0, [f"too few posts ({posts})"]
    if followers < config["min_followers"]:
        return 0, [f"too few followers ({followers})"]
    
    # Anti-bot: check following/followers ratio
    if followers > 0:
        ratio = following / followers
        if ratio > config["max_following_ratio"]:
            return 0, [f"suspicious ratio ({following}/{followers})"]
    
    # Base score from engagement
    if followers > 1000:
        score += 2
        reasons.append("1k+ followers")
    elif followers > 100:
        score += 1
        reasons.append("100+ followers")
    
    # Bio quality
    if len(bio) > 50:
        score += 1
        reasons.append("detailed bio")
    
    # Topic relevance
    text = f"{bio} {display_name}".lower()
    matches = [t for t in get_topics() if t.lower() in text]
    if matches:
        score += len(matches) * 0.5
        reasons.append(f"topics: {', '.join(matches[:3])}")
    
    return score, reasons


# ============================================================================
# DISCOVER FOLLOWS
# ============================================================================

def discover_follows(pds: str, jwt: str, my_did: str, state: dict, 
                     dry_run: bool = True, max_new: int = 10) -> list[dict]:
    """Discover new accounts from follows of follows."""
    config = get_config(state)
    now = dt.datetime.now(dt.timezone.utc)
    cooldown = dt.timedelta(days=config["scan_cooldown_days"])
    
    # Get my follows
    print("📋 Fetching your follows...")
    my_follows = get_follows(pds, jwt, my_did)
    my_follow_dids = {f["did"] for f in my_follows}
    print(f"✓ You follow {len(my_follows)} accounts")
    
    # Track already followed/rejected
    already = set(state.get("already_followed", []))
    already.update(my_follow_dids)
    already.add(my_did)
    
    # Find follows to scan (not scanned recently)
    scanned = state.get("follows_scanned", {})
    to_scan = []
    for f in my_follows:
        did = f["did"]
        last_scan = scanned.get(did)
        if last_scan:
            last_dt = dt.datetime.fromisoformat(last_scan.replace("Z", "+00:00"))
            if now - last_dt < cooldown:
                continue
        to_scan.append(f)
    
    print(f"📡 {len(to_scan)} follows need scanning (cooldown: {config['scan_cooldown_days']}d)")
    
    if not to_scan:
        print("No follows to scan right now.")
        return []
    
    # Sample some follows to scan (don't do all at once)
    scan_batch = random.sample(to_scan, min(5, len(to_scan)))
    
    # Collect candidates from their follows
    candidates = {}  # did -> profile
    
    for i, follow in enumerate(scan_batch):
        handle = follow.get("handle", follow["did"])
        print(f"  Scanning @{handle} ({i+1}/{len(scan_batch)})...")
        
        # Get their follows
        their_follows = get_follows(pds, jwt, follow["did"])
        
        # Sample based on config
        sample_size = max(1, int(len(their_follows) * config["follows_sample_pct"]))
        sampled = random.sample(their_follows, min(sample_size, len(their_follows)))
        
        for candidate in sampled:
            cdid = candidate["did"]
            if cdid in already or cdid in candidates:
                continue
            candidates[cdid] = candidate
        
        # Mark as scanned
        state["follows_scanned"][follow["did"]] = now.isoformat().replace("+00:00", "Z")
    
    print(f"✓ Found {len(candidates)} potential candidates")
    
    if not candidates:
        return []
    
    # Score candidates
    print("🔍 Scoring candidates...")
    scored = []
    for did, basic_info in list(candidates.items())[:50]:  # Limit API calls
        profile = get_profile(pds, jwt, did)
        if not profile:
            continue
        score, reasons = score_candidate(profile, config)
        if score > 0:
            scored.append({
                "did": did,
                "handle": profile.get("handle", ""),
                "displayName": profile.get("displayName", ""),
                "description": (profile.get("description") or "")[:100],
                "followers": profile.get("followersCount", 0),
                "score": score,
                "reasons": reasons
            })
    
    # Sort by score and take top
    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:max_new]
    
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Top {len(top)} candidates:\n")
    
    for c in top:
        print(f"@{c['handle']} ({c['followers']} followers)")
        print(f"  {c['displayName']}")
        print(f"  Score: {c['score']:.1f} — {', '.join(c['reasons'])}")
        print(f"  Bio: {c['description']}...")
        
        if not dry_run:
            success = follow_account(pds, jwt, my_did, c["did"])
            if success:
                print(f"  ✓ Followed!")
                state.setdefault("already_followed", []).append(c["did"])
            else:
                print(f"  ✗ Failed to follow")
        print()
    
    return top


# ============================================================================
# DISCOVER REPOSTS
# ============================================================================

def discover_reposts(pds: str, jwt: str, my_did: str, state: dict,
                     dry_run: bool = True, max_new: int = 10) -> list[dict]:
    """Discover accounts from reposted content."""
    config = get_config(state)
    
    # Get my follows
    print("📋 Fetching your follows...")
    my_follows = get_follows(pds, jwt, my_did)
    my_follow_dids = {f["did"] for f in my_follows}
    print(f"✓ You follow {len(my_follows)} accounts")
    
    already = set(state.get("already_followed", []))
    already.update(my_follow_dids)
    already.add(my_did)
    
    # Collect repost authors from recent activity
    print("📰 Scanning reposts from your follows...")
    repost_authors = Counter(state.get("repost_authors", {}))
    
    # Sample some follows to check
    sample = random.sample(my_follows, min(20, len(my_follows)))
    
    for i, follow in enumerate(sample):
        if i % 10 == 0 and i > 0:
            print(f"  ...checked {i}/{len(sample)}")
        
        feed = get_author_feed(pds, jwt, follow["did"], limit=20)
        for item in feed:
            # Check if it's a repost
            reason = item.get("reason", {})
            if reason.get("$type") == "app.bsky.feed.defs#reasonRepost":
                # Get original author
                post = item.get("post", {})
                author = post.get("author", {})
                author_did = author.get("did", "")
                if author_did and author_did not in already:
                    repost_authors[author_did] += 1
    
    # Update state
    state["repost_authors"] = dict(repost_authors)
    state["last_repost_analysis"] = dt.datetime.now(dt.timezone.utc).isoformat()
    
    print(f"✓ Tracking {len(repost_authors)} reposted authors")
    
    if not repost_authors:
        return []
    
    # Get top % most reposted
    sorted_authors = repost_authors.most_common()
    top_pct = config["repost_top_pct"]
    top_n = max(1, int(len(sorted_authors) * top_pct))
    top_authors = sorted_authors[:top_n]
    
    print(f"🔍 Evaluating top {top_n} most reposted...")
    
    # Score and filter
    candidates = []
    for did, repost_count in top_authors[:30]:  # Limit API calls
        if did in already:
            continue
        profile = get_profile(pds, jwt, did)
        if not profile:
            continue
        score, reasons = score_candidate(profile, config)
        if score > 0:
            # Bonus for repost frequency
            score += min(repost_count * 0.5, 3)
            reasons.append(f"reposted {repost_count}x")
            
            candidates.append({
                "did": did,
                "handle": profile.get("handle", ""),
                "displayName": profile.get("displayName", ""),
                "description": (profile.get("description") or "")[:100],
                "followers": profile.get("followersCount", 0),
                "repost_count": repost_count,
                "score": score,
                "reasons": reasons
            })
    
    # Sort and take top
    candidates.sort(key=lambda x: x["score"], reverse=True)
    top = candidates[:max_new]
    
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Top {len(top)} from reposts:\n")
    
    for c in top:
        print(f"@{c['handle']} ({c['followers']} followers, reposted {c['repost_count']}x)")
        print(f"  {c['displayName']}")
        print(f"  Score: {c['score']:.1f} — {', '.join(c['reasons'])}")
        print(f"  Bio: {c['description']}...")
        
        if not dry_run:
            success = follow_account(pds, jwt, my_did, c["did"])
            if success:
                print(f"  ✓ Followed!")
                state.setdefault("already_followed", []).append(c["did"])
                # Remove from tracking once followed
                if c["did"] in state["repost_authors"]:
                    del state["repost_authors"][c["did"]]
            else:
                print(f"  ✗ Failed to follow")
        print()
    
    return top


# ============================================================================
# CLI
# ============================================================================

def run(args) -> int:
    """Entry point from CLI."""
    print("🔗 Connecting to BlueSky...")
    pds, did, jwt, handle = get_session()
    print(f"✓ Logged in as @{handle}")

    state = load_state()
    dry_run = getattr(args, 'dry_run', True)
    max_new = getattr(args, 'max', 10)
    mode = getattr(args, 'mode', 'follows')
    guard = RuntimeGuard(getattr(args, 'max_runtime_seconds', None))

    log_phase("collect")
    if guard.check("collect"):
        return TIMEOUT_EXIT_CODE

    log_phase("score")
    if guard.check("score"):
        return TIMEOUT_EXIT_CODE
    log_phase("decide")
    if guard.check("decide"):
        return TIMEOUT_EXIT_CODE
    log_phase("act")
    if guard.check("act"):
        return TIMEOUT_EXIT_CODE

    if mode == "follows":
        results = discover_follows(pds, jwt, did, state, dry_run=dry_run, max_new=max_new)
    elif mode == "reposts":
        results = discover_reposts(pds, jwt, did, state, dry_run=dry_run, max_new=max_new)
    else:
        print(f"Unknown mode: {mode}")
        return 1
    
    if not dry_run:
        save_state(state)
        print(f"✓ State saved.")
    else:
        # Still save scan timestamps even in dry-run
        save_state(state)
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Discover new accounts to follow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
MODES:
  follows   Scan follows of your follows (daily)
  reposts   Analyze who gets reposted most (weekly)

EXAMPLES:
  bsky discover follows --dry-run
  bsky discover reposts --dry-run
  bsky discover follows --execute --max 5

CONFIG (in state file):
  follows_sample_pct: 0.10    # Sample 10% of each follow's follows
  repost_top_pct: 0.20        # Top 20% most reposted
  scan_cooldown_days: 90      # Don't re-scan same follow for 3 months
"""
    )
    parser.add_argument("mode", choices=["follows", "reposts"], help="Discovery mode")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Preview without following")
    parser.add_argument("--execute", action="store_true", help="Actually follow accounts")
    parser.add_argument("--max", type=int, default=10, help="Maximum accounts to follow")
    parser.add_argument("--max-runtime-seconds", type=int, default=None, help="Abort after N seconds wall-clock")

    args = parser.parse_args()
    if args.execute:
        args.dry_run = False
    
    return run(args)


if __name__ == "__main__":
    exit(main())
