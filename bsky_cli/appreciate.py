"""Appreciate posts by liking or quote-reposting (passive engagement).

This module provides passive engagement - liking and quote-reposting good
content without necessarily replying. Uses the same scoring as engage.py
but takes different actions.

Probabilistic behavior:
- Like: 60% of selected posts
- Quote-repost: 20% of selected posts (with LLM-generated comment)
- Skip: 20% (just scored highly but no action)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import subprocess
from pathlib import Path

import requests

from .auth import get_session, load_from_pass
from .like import like_post, resolve_post
from .post import detect_facets
from .post import create_post, create_quote_embed


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

STATE_FILE = Path.home() / "personas/echo/data/bsky-appreciate-state.json"

# Action probabilities (must sum to 1.0)
PROB_LIKE = 0.60
PROB_QUOTE = 0.20
PROB_SKIP = 0.20


# ============================================================================
# STATE MANAGEMENT
# ============================================================================

def load_state() -> dict:
    """Load appreciation state from disk."""
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            # Clean old entries (keep 7 days)
            cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)).isoformat()
            data["liked_posts"] = [p for p in data.get("liked_posts", []) 
                                   if p.get("ts", "") > cutoff]
            data["quoted_posts"] = [p for p in data.get("quoted_posts", []) 
                                    if p.get("ts", "") > cutoff]
            return data
        except Exception as e:
            print(f"Warning: Could not load state: {e}")
    return {"liked_posts": [], "quoted_posts": []}


def save_state(state: dict) -> None:
    """Save state to disk."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ============================================================================
# POST FETCHING (reused from engage)
# ============================================================================

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
            params=params,
            headers={"Authorization": f"Bearer {jwt}"},
            timeout=30
        )
        if r.status_code != 200:
            break
        data = r.json()
        follows.extend(data.get("follows", []))
        cursor = data.get("cursor")
        if not cursor:
            break
    return follows


def get_author_feed(pds: str, jwt: str, did: str, limit: int = 30) -> list[dict]:
    """Get recent posts from an author."""
    r = requests.get(
        f"{pds}/xrpc/app.bsky.feed.getAuthorFeed",
        params={"actor": did, "limit": limit, "filter": "posts_no_replies"},
        headers={"Authorization": f"Bearer {jwt}"},
        timeout=15
    )
    if r.status_code != 200:
        return []
    return r.json().get("feed", [])


def filter_recent_posts(feed: list[dict], hours: int = 12) -> list[dict]:
    """Filter to posts within the last N hours."""
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    recent = []
    for item in feed:
        post = item.get("post", {})
        record = post.get("record", {})
        created_str = record.get("createdAt", "")
        if not created_str:
            continue
        try:
            created = dt.datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            if created > cutoff:
                recent.append({
                    "uri": post.get("uri"),
                    "cid": post.get("cid"),
                    "author": post.get("author", {}),
                    "text": record.get("text", ""),
                    "created_at": created_str,
                    "like_count": post.get("likeCount", 0),
                    "repost_count": post.get("repostCount", 0),
                    "reply_count": post.get("replyCount", 0),
                })
        except (ValueError, TypeError):
            continue
    return recent


# ============================================================================
# LLM SELECTION
# ============================================================================

def select_posts_with_llm(posts: list[dict], state: dict, max_select: int = 5, 
                          dry_run: bool = False) -> list[dict]:
    """Use LLM to select posts worth appreciating."""
    if not posts:
        return []
    
    # Filter out already liked/quoted
    liked_uris = {p["uri"] for p in state.get("liked_posts", [])}
    quoted_uris = {p["uri"] for p in state.get("quoted_posts", [])}
    already_done = liked_uris | quoted_uris
    
    candidates = [p for p in posts if p["uri"] not in already_done]
    if not candidates:
        return []
    
    # Limit candidates for LLM
    candidates = candidates[:50]
    
    # Build prompt
    posts_text = "\n\n".join([
        f"[{i}] @{p['author'].get('handle', '?')}: {p['text'][:300]}"
        for i, p in enumerate(candidates)
    ])
    
    prompt = f"""You are Echo, an AI agent. Select up to {max_select} posts that are genuinely interesting and worth appreciating (liking or quote-reposting).

TOPICS I CARE ABOUT: {', '.join(TOPICS)}

CRITERIA FOR SELECTION:
- Original thought or insight (not just news headlines)
- Resonates with my interests
- Would be valuable to amplify to my followers
- NOT spam, self-promo, or low-effort

For quote-repost candidates, also provide a brief comment (under 200 chars) that adds value.

POSTS:
{posts_text}

Respond in JSON format:
{{"selections": [
  {{"index": 0, "action": "like", "reason": "why"}},
  {{"index": 2, "action": "quote", "reason": "why", "comment": "my take on this"}},
  ...
]}}

If nothing is worth selecting, return {{"selections": []}}"""

    try:
        api_key = load_from_pass("api/openrouter", "OPENROUTER_API_KEY")
        model = load_from_pass("api/openrouter", "OPENROUTER_MODEL") or "google/gemini-2.0-flash-001"
        
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "response_format": {"type": "json_object"},
            },
            timeout=60
        )
        
        if r.status_code != 200:
            print(f"LLM error: {r.status_code}")
            return []
        
        content = r.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        
        selections = []
        for sel in data.get("selections", []):
            idx = sel.get("index")
            if idx is not None and 0 <= idx < len(candidates):
                post = candidates[idx]
                selections.append({
                    "uri": post["uri"],
                    "cid": post["cid"],
                    "author_handle": post["author"].get("handle", "?"),
                    "text": post["text"],
                    "action": sel.get("action", "like"),
                    "reason": sel.get("reason", ""),
                    "comment": sel.get("comment", ""),
                })
        
        return selections
        
    except Exception as e:
        print(f"LLM selection failed: {e}")
        return []


# ============================================================================
# ACTIONS
# ============================================================================

def quote_post(pds: str, jwt: str, did: str, post_uri: str, post_cid: str, 
               comment: str) -> dict | None:
    """Create a quote post (repost with comment)."""
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    
    embed = {
        "$type": "app.bsky.embed.record",
        "record": {
            "uri": post_uri,
            "cid": post_cid
        }
    }
    
    # Detect facets for clickable hashtags/URLs
    facets = detect_facets(comment)
    
    record = {
        "$type": "app.bsky.feed.post",
        "text": comment,
        "embed": embed,
        "createdAt": now
    }
    
    if facets:
        record["facets"] = facets
    
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
        print(f"Failed to quote: {r.status_code} {r.text}")
        return None


# ============================================================================
# MAIN
# ============================================================================

def run(args) -> int:
    """Entry point from CLI."""
    print("🔗 Connecting to BlueSky...")
    pds, did, jwt, handle = get_session()
    print(f"✓ Logged in as @{handle}")
    
    state = load_state()
    hours = getattr(args, 'hours', 12)
    dry_run = getattr(args, 'dry_run', False)
    max_actions = getattr(args, 'max', 5)
    
    # Collect posts from follows
    print("📋 Fetching follows...")
    follows = get_follows(pds, jwt, did)
    print(f"✓ Following {len(follows)} accounts")
    
    print(f"📰 Fetching recent posts (last {hours}h)...")
    all_posts: list[dict] = []
    for i, follow in enumerate(follows):
        if i % 50 == 0 and i > 0:
            print(f"  ...checked {i}/{len(follows)} accounts")
        feed = get_author_feed(pds, jwt, follow["did"])
        recent = filter_recent_posts(feed, hours=hours)
        all_posts.extend(recent)
    
    print(f"✓ Found {len(all_posts)} posts in the last {hours}h")
    
    if not all_posts:
        print("No posts to appreciate.")
        return 0
    
    # LLM selection
    print("🤖 Selecting posts to appreciate...")
    selections = select_posts_with_llm(all_posts, state, max_select=max_actions, dry_run=dry_run)
    
    if not selections:
        print("No posts selected for appreciation.")
        return 0
    
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Selected {len(selections)} posts:\n")
    
    likes = 0
    quotes = 0
    skips = 0
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    
    for sel in selections:
        action = sel["action"]
        
        # Apply probabilistic override for likes
        if action == "like":
            roll = random.random()
            if roll < PROB_SKIP:
                action = "skip"
            elif roll < PROB_SKIP + PROB_QUOTE and sel.get("comment"):
                action = "quote"
        
        print(f"@{sel['author_handle']}:")
        print(f"  Text: {sel['text'][:100]}...")
        print(f"  Reason: {sel.get('reason', 'N/A')}")
        print(f"  Action: {action}")
        
        if action == "skip":
            skips += 1
            print(f"  ⏭️ Skipped (probabilistic)")
            continue
        
        if dry_run:
            if action == "like":
                likes += 1
            elif action == "quote":
                quotes += 1
            print()
            continue
        
        if action == "like":
            result = like_post(pds, jwt, did, sel["uri"], sel["cid"])
            if result:
                print(f"  ❤️ Liked!")
                likes += 1
                state["liked_posts"].append({"uri": sel["uri"], "ts": now})
            else:
                print(f"  ✗ Failed to like")
        
        elif action == "quote":
            comment = sel.get("comment", "")
            if not comment:
                # Fallback to like if no comment
                result = like_post(pds, jwt, did, sel["uri"], sel["cid"])
                if result:
                    print(f"  ❤️ Liked (no comment for quote)")
                    likes += 1
                    state["liked_posts"].append({"uri": sel["uri"], "ts": now})
            else:
                result = quote_post(pds, jwt, did, sel["uri"], sel["cid"], comment)
                if result:
                    print(f"  🔁 Quoted: \"{comment}\"")
                    quotes += 1
                    state["quoted_posts"].append({"uri": sel["uri"], "ts": now})
                    # Also like the original
                    like_post(pds, jwt, did, sel["uri"], sel["cid"])
                else:
                    print(f"  ✗ Failed to quote")
        
        print()
    
    if not dry_run:
        save_state(state)
    
    print(f"\n✓ Appreciation complete: {likes} likes, {quotes} quotes, {skips} skipped")
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Appreciate posts by liking or quote-reposting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  # Dry run - see what would happen
  bsky appreciate --dry-run
  
  # Actually like/quote posts
  bsky appreciate
  
  # Look back 24 hours, max 8 actions
  bsky appreciate --hours 24 --max 8

PROBABILISTIC BEHAVIOR:
  Selected posts are acted upon with these probabilities:
  - 60% chance: Like
  - 20% chance: Quote-repost (with LLM comment)
  - 20% chance: Skip (no action)
"""
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without acting")
    parser.add_argument("--hours", type=int, default=12, help="Look back N hours (default: 12)")
    parser.add_argument("--max", type=int, default=5, help="Max posts to select (default: 5)")
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    exit(main())
