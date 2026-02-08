"""Search BlueSky posts by keywords."""
from __future__ import annotations

import argparse
import datetime as dt

from .http import requests

from .auth import get_session


def search_posts(
    pds: str, 
    jwt: str, 
    query: str, 
    limit: int = 25,
    author: str | None = None,
    since: str | None = None,
    until: str | None = None,
    sort: str = "latest"
) -> list[dict]:
    """
    Search posts by query.
    
    Args:
        pds: PDS endpoint
        jwt: Access token
        query: Search query
        limit: Max results (1-100)
        author: Filter by author handle/DID
        since: ISO timestamp or relative (e.g. "24h", "7d")
        until: ISO timestamp or relative
        sort: "latest" or "top"
    
    Returns:
        List of post records
    """
    params = {
        "q": query,
        "limit": min(limit, 100),
        "sort": sort
    }
    
    if author:
        # Add author filter
        params["author"] = author
    
    # Parse relative time strings
    now = dt.datetime.now(dt.timezone.utc)
    
    if since:
        since_dt = parse_relative_time(since, now)
        if since_dt:
            params["since"] = since_dt.isoformat().replace("+00:00", "Z")
    
    if until:
        until_dt = parse_relative_time(until, now)
        if until_dt:
            params["until"] = until_dt.isoformat().replace("+00:00", "Z")
    
    r = requests.get(
        f"{pds}/xrpc/app.bsky.feed.searchPosts",
        headers={"Authorization": f"Bearer {jwt}"},
        params=params,
        timeout=30
    )
    r.raise_for_status()
    return r.json().get("posts", [])


def parse_relative_time(value: str, now: dt.datetime) -> dt.datetime | None:
    """
    Parse relative time string like "24h", "7d", "2w" or ISO timestamp.
    Returns None if parsing fails.
    """
    value = value.strip()
    
    # Try parsing as ISO timestamp
    if "T" in value or value.endswith("Z"):
        try:
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    
    # Parse relative time
    units = {
        "h": "hours",
        "d": "days",
        "w": "weeks",
        "m": "minutes"
    }
    
    for suffix, unit in units.items():
        if value.endswith(suffix):
            try:
                amount = int(value[:-len(suffix)])
                delta = dt.timedelta(**{unit: amount})
                return now - delta
            except ValueError:
                pass
    
    return None


def format_post(post: dict, show_metrics: bool = True) -> str:
    """Format a post for display."""
    author = post.get("author", {})
    handle = author.get("handle", "unknown")
    display_name = author.get("displayName", "")
    
    record = post.get("record", {})
    text = record.get("text", "")
    created = record.get("createdAt", "")
    
    # Parse timestamp
    try:
        ts = dt.datetime.fromisoformat(created.replace("Z", "+00:00"))
        time_str = ts.strftime("%Y-%m-%d %H:%M")
    except Exception:
        time_str = created[:16] if created else "?"
    
    # Engagement metrics
    likes = post.get("likeCount", 0)
    reposts = post.get("repostCount", 0)
    replies = post.get("replyCount", 0)
    
    # Build output
    header = f"@{handle}"
    if display_name:
        header = f"{display_name} (@{handle})"
    
    lines = [
        f"─────────────────────────────",
        f"{header}  •  {time_str}",
        f"",
        text[:500] + ("..." if len(text) > 500 else ""),
    ]
    
    if show_metrics:
        lines.append(f"")
        lines.append(f"❤️ {likes}  🔁 {reposts}  💬 {replies}")
    
    # Post URL
    uri = post.get("uri", "")
    if uri:
        # at://did:plc:xxx/app.bsky.feed.post/yyy -> https://bsky.app/profile/xxx/post/yyy
        import re
        m = re.match(r"at://([^/]+)/app\.bsky\.feed\.post/([^/]+)", uri)
        if m:
            url = f"https://bsky.app/profile/{m.group(1)}/post/{m.group(2)}"
            lines.append(url)
    
    return "\n".join(lines)


def run(args) -> int:
    """Entry point from CLI."""
    print("🔗 Connecting to BlueSky...")
    pds, did, jwt, handle = get_session()
    print(f"✓ Logged in as @{handle}")
    
    query = args.query
    print(f"\n🔍 Searching for: {query}")
    
    if args.author:
        print(f"   Author filter: {args.author}")
    if args.since:
        print(f"   Since: {args.since}")
    
    posts = search_posts(
        pds, jwt, query,
        limit=args.limit,
        author=args.author,
        since=args.since,
        until=args.until,
        sort=args.sort
    )
    
    if not posts:
        print("\nNo posts found.")
        return 0
    
    print(f"\n📋 Found {len(posts)} posts:\n")
    
    for post in posts:
        print(format_post(post, show_metrics=not args.compact))
        print()
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Search BlueSky posts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  bsky search "AI agents"
  bsky search --author alice.bsky.social "machine learning"
  bsky search --since 24h "breaking news"
  bsky search --sort top "viral post"

TIME FORMATS:
  Relative: 24h, 7d, 2w, 30m
  Absolute: 2026-02-04T00:00:00Z
"""
    )
    parser.add_argument("query", help="Search query")
    parser.add_argument("--author", "-a", help="Filter by author handle or DID")
    parser.add_argument("--since", "-s", help="Posts after this time (e.g. 24h, 7d)")
    parser.add_argument("--until", "-u", help="Posts before this time")
    parser.add_argument("--limit", "-n", type=int, default=25, help="Max results (default: 25)")
    parser.add_argument("--sort", choices=["latest", "top"], default="latest", 
                       help="Sort order (default: latest)")
    parser.add_argument("--compact", "-c", action="store_true", help="Compact output (no metrics)")
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    exit(main())
