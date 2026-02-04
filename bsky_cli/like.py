"""Like and unlike posts on BlueSky."""
import argparse
import re
import requests
from datetime import datetime, timezone

from .auth import get_session


def resolve_post(pds: str, jwt: str, url: str) -> tuple[str, str] | None:
    """Resolve a post URL to its URI and CID.
    
    Args:
        url: BlueSky post URL (https://bsky.app/profile/handle/post/id)
        
    Returns:
        Tuple of (uri, cid) or None if not found
    """
    # Parse URL: https://bsky.app/profile/handle.bsky.social/post/abc123
    match = re.match(r'https://bsky\.app/profile/([^/]+)/post/([^/]+)', url)
    if not match:
        print(f"Invalid post URL: {url}")
        return None
    
    handle_or_did, post_id = match.groups()
    
    # Resolve handle to DID if needed
    if not handle_or_did.startswith("did:"):
        r = requests.get(
            f"{pds}/xrpc/com.atproto.identity.resolveHandle",
            params={"handle": handle_or_did},
            headers={"Authorization": f"Bearer {jwt}"},
            timeout=15
        )
        if r.status_code != 200:
            print(f"Could not resolve handle: {handle_or_did}")
            return None
        did = r.json().get("did")
    else:
        did = handle_or_did
    
    # Construct URI and get CID
    uri = f"at://{did}/app.bsky.feed.post/{post_id}"
    
    # Fetch post to get CID
    r = requests.get(
        f"{pds}/xrpc/app.bsky.feed.getPosts",
        params={"uris": uri},
        headers={"Authorization": f"Bearer {jwt}"},
        timeout=15
    )
    if r.status_code != 200:
        print(f"Could not fetch post: {uri}")
        return None
    
    posts = r.json().get("posts", [])
    if not posts:
        print(f"Post not found: {uri}")
        return None
    
    return uri, posts[0].get("cid")


def like_post(pds: str, jwt: str, did: str, post_uri: str, post_cid: str) -> dict | None:
    """Like a post.
    
    Args:
        pds: PDS URL
        jwt: Auth token
        did: Our DID
        post_uri: URI of post to like
        post_cid: CID of post to like
        
    Returns:
        Created record or None on failure
    """
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    record = {
        "$type": "app.bsky.feed.like",
        "subject": {
            "uri": post_uri,
            "cid": post_cid
        },
        "createdAt": now
    }
    
    r = requests.post(
        f"{pds}/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"},
        json={
            "repo": did,
            "collection": "app.bsky.feed.like",
            "record": record
        },
        timeout=30
    )
    
    if r.status_code == 200:
        return r.json()
    else:
        print(f"Failed to like: {r.status_code} {r.text}")
        return None


def unlike_post(pds: str, jwt: str, did: str, post_uri: str) -> bool:
    """Remove a like from a post.
    
    Args:
        pds: PDS URL
        jwt: Auth token  
        did: Our DID
        post_uri: URI of post to unlike
        
    Returns:
        True if successful
    """
    # First, find our like record
    r = requests.get(
        f"{pds}/xrpc/app.bsky.feed.getLikes",
        params={"uri": post_uri, "limit": 100},
        headers={"Authorization": f"Bearer {jwt}"},
        timeout=15
    )
    
    if r.status_code != 200:
        print(f"Could not fetch likes: {r.status_code}")
        return False
    
    likes = r.json().get("likes", [])
    our_like = None
    for like in likes:
        if like.get("actor", {}).get("did") == did:
            # Found our like - need to get the record key
            # The like URI is at://did/app.bsky.feed.like/rkey
            like_uri = like.get("uri", "")
            if like_uri:
                rkey = like_uri.split("/")[-1]
                our_like = rkey
                break
    
    if not our_like:
        print("You haven't liked this post")
        return False
    
    # Delete the like record
    r = requests.post(
        f"{pds}/xrpc/com.atproto.repo.deleteRecord",
        headers={"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"},
        json={
            "repo": did,
            "collection": "app.bsky.feed.like",
            "rkey": our_like
        },
        timeout=30
    )
    
    return r.status_code == 200


def run(args) -> int:
    """Entry point from CLI."""
    pds, did, jwt, handle = get_session()
    
    # Resolve post URL to URI/CID
    result = resolve_post(pds, jwt, args.post_url)
    if not result:
        return 1
    
    post_uri, post_cid = result
    
    if args.undo:
        # Unlike
        if args.dry_run:
            print(f"[DRY RUN] Would unlike: {args.post_url}")
            return 0
        
        if unlike_post(pds, jwt, did, post_uri):
            print(f"✓ Unliked: {args.post_url}")
            return 0
        else:
            print(f"✗ Failed to unlike")
            return 1
    else:
        # Like
        if args.dry_run:
            print(f"[DRY RUN] Would like: {args.post_url}")
            return 0
        
        result = like_post(pds, jwt, did, post_uri, post_cid)
        if result:
            print(f"✓ Liked: {args.post_url}")
            return 0
        else:
            print(f"✗ Failed to like")
            return 1


def main():
    parser = argparse.ArgumentParser(description="Like or unlike a post")
    parser.add_argument("post_url", help="URL of the post")
    parser.add_argument("--undo", action="store_true", help="Unlike instead of like")
    parser.add_argument("--dry-run", action="store_true", help="Print without acting")
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    exit(main())
