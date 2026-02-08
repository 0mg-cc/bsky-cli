"""Bookmark management for BlueSky posts."""

from __future__ import annotations

import argparse
import re
from typing import Any

from .http import requests

from .auth import get_session


def parse_post_url(url: str) -> tuple[str, str] | None:
    """Parse BlueSky post URL into (actor, rkey)."""
    match = re.match(r"https://bsky\.app/profile/([^/]+)/post/([^/]+)", url)
    if not match:
        return None
    return match.group(1), match.group(2)


def resolve_post_uri(pds: str, jwt: str, url: str) -> str | None:
    """Resolve BlueSky post URL to at:// URI."""
    parsed = parse_post_url(url)
    if not parsed:
        print(f"Invalid post URL: {url}")
        return None

    actor, rkey = parsed
    if actor.startswith("did:"):
        did = actor
    else:
        r = requests.get(
            f"{pds}/xrpc/com.atproto.identity.resolveHandle",
            headers={"Authorization": f"Bearer {jwt}"},
            params={"handle": actor},
            timeout=15,
        )
        if r.status_code != 200:
            print(f"Could not resolve handle: {actor}")
            return None
        did = r.json().get("did")
        if not did:
            print(f"No DID found for handle: {actor}")
            return None

    return f"at://{did}/app.bsky.feed.post/{rkey}"


def create_bookmark(pds: str, jwt: str, did: str, post_url: str) -> bool:
    """Create a bookmark for a post URL."""
    uri = resolve_post_uri(pds, jwt, post_url)
    if not uri:
        return False

    r = requests.post(
        f"{pds}/xrpc/app.bsky.bookmark.createBookmark",
        headers={"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"},
        json={"repo": did, "subject": uri},
        timeout=30,
    )
    if r.status_code == 200:
        return True

    print(f"Failed to bookmark: {r.status_code} {r.text}")
    return False


def delete_bookmark(pds: str, jwt: str, did: str, post_url: str) -> bool:
    """Delete a bookmark for a post URL."""
    uri = resolve_post_uri(pds, jwt, post_url)
    if not uri:
        return False

    r = requests.post(
        f"{pds}/xrpc/app.bsky.bookmark.deleteBookmark",
        headers={"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"},
        json={"repo": did, "subject": uri},
        timeout=30,
    )
    if r.status_code == 200:
        return True

    print(f"Failed to remove bookmark: {r.status_code} {r.text}")
    return False


def get_bookmarks(pds: str, jwt: str, limit: int = 25) -> list[dict[str, Any]]:
    """Fetch bookmarks."""
    r = requests.get(
        f"{pds}/xrpc/app.bsky.bookmark.getBookmarks",
        headers={"Authorization": f"Bearer {jwt}"},
        params={"limit": limit},
        timeout=30,
    )
    if r.status_code != 200:
        print(f"Failed to fetch bookmarks: {r.status_code} {r.text}")
        return []
    return r.json().get("bookmarks", [])


def run_bookmark(args) -> int:
    pds, did, jwt, _handle = get_session()

    if args.remove:
        ok = delete_bookmark(pds, jwt, did, args.post_url)
        if ok:
            print(f"✓ Removed bookmark: {args.post_url}")
            return 0
        return 1

    ok = create_bookmark(pds, jwt, did, args.post_url)
    if ok:
        print(f"✓ Bookmarked: {args.post_url}")
        return 0
    return 1


def run_bookmarks(args) -> int:
    pds, _did, jwt, _handle = get_session()
    bookmarks = get_bookmarks(pds, jwt, limit=args.limit)

    if not bookmarks:
        print("No bookmarks found.")
        return 0

    for idx, b in enumerate(bookmarks, 1):
        post = b.get("post", {})
        author = post.get("author", {}).get("handle", "unknown")
        text = post.get("record", {}).get("text", "").replace("\n", " ")
        short = text[:120] + ("..." if len(text) > 120 else "")
        uri = post.get("uri", "")
        print(f"{idx:2d}. @{author} - {short}")
        if uri:
            print(f"    {uri}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="BlueSky bookmarks")
    sub = parser.add_subparsers(dest="command", required=True)

    p_bookmark = sub.add_parser("bookmark", help="Create or remove bookmark")
    p_bookmark.add_argument("post_url")
    p_bookmark.add_argument("--remove", action="store_true")

    p_list = sub.add_parser("bookmarks", help="List bookmarks")
    p_list.add_argument("list", nargs="?")
    p_list.add_argument("--limit", type=int, default=25)

    args = parser.parse_args()
    if args.command == "bookmark":
        return run_bookmark(args)
    return run_bookmarks(args)


if __name__ == "__main__":
    raise SystemExit(main())
