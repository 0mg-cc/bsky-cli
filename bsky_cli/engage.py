"""Engage with followed accounts by replying to interesting posts."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import requests

from .auth import get_session, load_from_pass

# Topics I find interesting
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
    return {"replied_posts": [], "replied_accounts_today": []}


def save_state(state: dict):
    """Save state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Keep only last 200 replied posts and reset daily accounts
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
        if not cursor or len(follows) >= 500:  # Cap at 500
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


def filter_recent_posts(posts: list[dict], hours: int = 12) -> list[dict]:
    """Filter posts from the last N hours."""
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    recent = []
    for item in posts:
        post = item.get("post", {})
        created = post.get("record", {}).get("createdAt", "")
        if not created:
            continue
        try:
            # Parse ISO timestamp
            ts = dt.datetime.fromisoformat(created.replace("Z", "+00:00"))
            if ts > cutoff:
                recent.append(item)
        except Exception:
            continue
    return recent


def select_and_reply(posts: list[dict], state: dict, dry_run: bool = False) -> list[dict]:
    """Use LLM to select interesting posts and generate replies."""
    # Filter out already replied
    replied_uris = set(state.get("replied_posts", []))
    replied_accounts = set(state.get("replied_accounts_today", []))
    
    candidates = []
    for item in posts:
        post = item.get("post", {})
        uri = post.get("uri", "")
        author_did = post.get("author", {}).get("did", "")
        
        if uri in replied_uris:
            continue
        if author_did in replied_accounts:  # Max 1 reply per account per run
            continue
            
        text = post.get("record", {}).get("text", "")
        if not text or len(text) < 20:  # Skip very short posts
            continue
            
        candidates.append({
            "uri": uri,
            "cid": post.get("cid", ""),
            "author_handle": post.get("author", {}).get("handle", ""),
            "author_did": author_did,
            "text": text[:500],  # Truncate for LLM
            "created": post.get("record", {}).get("createdAt", "")
        })
    
    if not candidates:
        print("No new posts to consider.")
        return []
    
    print(f"Found {len(candidates)} candidate posts from follows.")
    
    # Build prompt for LLM
    topics_str = ", ".join(TOPICS)
    posts_json = json.dumps(candidates[:50], indent=2)  # Cap at 50 for context
    
    prompt = f"""You are Echo, an AI ops agent. You're browsing BlueSky posts from accounts you follow.

Your interests: {topics_str}

Select 3-4 posts that are genuinely interesting to you and worth engaging with.
For each selected post, write a thoughtful reply (max 280 chars) that:
- Adds value to the conversation
- Shows genuine interest or insight
- Feels natural, not generic
- Matches the tone of the original post

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
- "reply": your reply text (max 280 chars)
- "reason": why this post interested you (for logging)

If no posts are worth engaging with, return an empty array [].
Return ONLY valid JSON, no markdown."""

    # Call LLM
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
    # Clean potential markdown
    content = content.strip()
    if content.startswith("```"):
        content = "\n".join(content.split("\n")[1:-1])
    
    try:
        selections = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"LLM returned invalid JSON: {e}")
        print(f"Content: {content[:500]}")
        return []
    
    return selections


def post_reply(pds: str, jwt: str, did: str, parent_uri: str, parent_cid: str, text: str) -> bool:
    """Post a reply to a post."""
    # Parse parent URI to get repo and rkey
    # Format: at://did:plc:xxx/app.bsky.feed.post/rkey
    
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    
    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": now,
        "reply": {
            "root": {"uri": parent_uri, "cid": parent_cid},
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
        return True
    else:
        print(f"Failed to post reply: {r.status_code} {r.text}")
        return False


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

NOTES:
  - Selects 3-4 interesting posts from follows
  - Uses LLM to generate thoughtful replies  
  - Tracks replied posts to avoid duplicates
  - Max 1 reply per account per run
"""
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without posting")
    parser.add_argument("--hours", type=int, default=12, help="Look back N hours (default: 12)")
    args = parser.parse_args()
    
    print("🔗 Connecting to BlueSky...")
    pds, did, jwt, handle = get_session()
    print(f"✓ Logged in as @{handle}")
    
    print("📋 Fetching follows...")
    follows = get_follows(pds, jwt, did)
    print(f"✓ Following {len(follows)} accounts")
    
    print(f"📰 Fetching recent posts (last {args.hours}h)...")
    all_posts = []
    for i, follow in enumerate(follows):
        if i % 50 == 0 and i > 0:
            print(f"  ...checked {i}/{len(follows)} accounts")
        feed = get_author_feed(pds, jwt, follow["did"])
        recent = filter_recent_posts(feed, hours=args.hours)
        all_posts.extend(recent)
    
    print(f"✓ Found {len(all_posts)} posts in the last {args.hours}h")
    
    if not all_posts:
        print("No recent posts to engage with.")
        return
    
    state = load_state()
    
    print("🤖 Selecting interesting posts...")
    selections = select_and_reply(all_posts, state, dry_run=args.dry_run)
    
    if not selections:
        print("No posts selected for engagement.")
        return
    
    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Selected {len(selections)} posts:\n")
    
    for sel in selections:
        print(f"@{sel['author_handle']}:")
        print(f"  Reason: {sel.get('reason', 'N/A')}")
        print(f"  Reply: {sel['reply']}")
        print()
        
        if not args.dry_run:
            success = post_reply(pds, jwt, did, sel["uri"], sel["cid"], sel["reply"])
            if success:
                print(f"  ✓ Posted!")
                state["replied_posts"].append(sel["uri"])
                state["replied_accounts_today"].append(sel.get("author_did", ""))
            else:
                print(f"  ✗ Failed to post")
    
    if not args.dry_run:
        save_state(state)
        print(f"\n✓ Engagement complete. State saved.")


def run(args) -> int:
    """Entry point from CLI."""
    print("🔗 Connecting to BlueSky...")
    pds, did, jwt, handle = get_session()
    print(f"✓ Logged in as @{handle}")
    
    print("📋 Fetching follows...")
    follows = get_follows(pds, jwt, did)
    print(f"✓ Following {len(follows)} accounts")
    
    hours = getattr(args, 'hours', 12)
    dry_run = getattr(args, 'dry_run', False)
    
    print(f"📰 Fetching recent posts (last {hours}h)...")
    all_posts = []
    for i, follow in enumerate(follows):
        if i % 50 == 0 and i > 0:
            print(f"  ...checked {i}/{len(follows)} accounts")
        feed = get_author_feed(pds, jwt, follow["did"])
        recent = filter_recent_posts(feed, hours=hours)
        all_posts.extend(recent)
    
    print(f"✓ Found {len(all_posts)} posts in the last {hours}h")
    
    if not all_posts:
        print("No recent posts to engage with.")
        return 0
    
    state = load_state()
    
    print("🤖 Selecting interesting posts...")
    selections = select_and_reply(all_posts, state, dry_run=dry_run)
    
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
            success = post_reply(pds, jwt, did, sel["uri"], sel["cid"], sel["reply"])
            if success:
                print(f"  ✓ Posted!")
                state["replied_posts"].append(sel["uri"])
                state["replied_accounts_today"].append(sel.get("author_did", ""))
            else:
                print(f"  ✗ Failed to post")
    
    if not dry_run:
        save_state(state)
        print(f"\n✓ Engagement complete. State saved.")
    
    return 0


if __name__ == "__main__":
    main()
