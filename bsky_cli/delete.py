"""Delete command for BlueSky CLI."""
from __future__ import annotations

import requests

from .auth import get_session


def list_posts(pds: str, jwt: str, did: str, limit: int = 50) -> list:
    """List recent posts."""
    r = requests.get(
        f"{pds}/xrpc/app.bsky.feed.getAuthorFeed",
        headers={"Authorization": f"Bearer {jwt}"},
        params={"actor": did, "limit": limit},
        timeout=10
    )
    r.raise_for_status()
    return r.json()["feed"]


def delete_post(pds: str, jwt: str, did: str, rkey: str) -> None:
    """Delete a post."""
    r = requests.post(
        f"{pds}/xrpc/com.atproto.repo.deleteRecord",
        headers={"Authorization": f"Bearer {jwt}"},
        json={"repo": did, "collection": "app.bsky.feed.post", "rkey": rkey},
        timeout=10
    )
    r.raise_for_status()


def run(args) -> int:
    """Execute delete command."""
    pds, did, jwt, _ = get_session()
    
    posts = list_posts(pds, jwt, did, limit=args.count + 10)
    
    if args.dry_run:
        print(f"DRY RUN: Would delete up to {args.count} posts")
        for i, item in enumerate(posts[:args.count]):
            uri = item["post"]["uri"]
            text = item["post"]["record"].get("text", "")[:50]
            print(f"  {i+1}. {text}...")
        return 0
    
    deleted = 0
    for item in posts:
        if deleted >= args.count:
            break
        uri = item["post"]["uri"]
        rkey = uri.split("/")[-1]
        try:
            delete_post(pds, jwt, did, rkey)
            print(f"Deleted: {rkey}")
            deleted += 1
        except Exception as e:
            print(f"Error deleting {rkey}: {e}")
    
    print(f"Deleted {deleted} posts")
    return 0
