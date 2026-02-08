"""Repost (retweet) posts on BlueSky."""
import argparse
from .http import requests
from datetime import datetime, timezone

from .auth import get_session
from .like import resolve_post  # Reuse URL resolution


def repost(pds: str, jwt: str, did: str, post_uri: str, post_cid: str) -> dict | None:
    """Repost a post.
    
    Args:
        pds: PDS URL
        jwt: Auth token
        did: Our DID
        post_uri: URI of post to repost
        post_cid: CID of post to repost
        
    Returns:
        Created record or None on failure
    """
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    record = {
        "$type": "app.bsky.feed.repost",
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
            "collection": "app.bsky.feed.repost",
            "record": record
        },
        timeout=30
    )
    
    if r.status_code == 200:
        return r.json()
    else:
        print(f"Failed to repost: {r.status_code} {r.text}")
        return None


def unrepost(pds: str, jwt: str, did: str, post_uri: str) -> bool:
    """Remove a repost.
    
    Args:
        pds: PDS URL
        jwt: Auth token  
        did: Our DID
        post_uri: URI of original post
        
    Returns:
        True if successful
    """
    # Find our repost by checking our repo
    r = requests.get(
        f"{pds}/xrpc/app.bsky.feed.getRepostedBy",
        params={"uri": post_uri, "limit": 100},
        headers={"Authorization": f"Bearer {jwt}"},
        timeout=15
    )
    
    if r.status_code != 200:
        print(f"Could not fetch reposts: {r.status_code}")
        return False
    
    # Check if we're in the reposters
    reposters = r.json().get("repostedBy", [])
    we_reposted = any(r.get("did") == did for r in reposters)
    
    if not we_reposted:
        print("You haven't reposted this post")
        return False
    
    # Find and delete our repost record
    # List our reposts to find the rkey
    r = requests.get(
        f"{pds}/xrpc/com.atproto.repo.listRecords",
        params={
            "repo": did,
            "collection": "app.bsky.feed.repost",
            "limit": 100
        },
        headers={"Authorization": f"Bearer {jwt}"},
        timeout=15
    )
    
    if r.status_code != 200:
        print(f"Could not list reposts: {r.status_code}")
        return False
    
    records = r.json().get("records", [])
    repost_rkey = None
    for record in records:
        if record.get("value", {}).get("subject", {}).get("uri") == post_uri:
            # Extract rkey from uri: at://did/collection/rkey
            repost_rkey = record.get("uri", "").split("/")[-1]
            break
    
    if not repost_rkey:
        print("Could not find repost record")
        return False
    
    # Delete the repost
    r = requests.post(
        f"{pds}/xrpc/com.atproto.repo.deleteRecord",
        headers={"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"},
        json={
            "repo": did,
            "collection": "app.bsky.feed.repost",
            "rkey": repost_rkey
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
        # Unrepost
        if args.dry_run:
            print(f"[DRY RUN] Would unrepost: {args.post_url}")
            return 0
        
        if unrepost(pds, jwt, did, post_uri):
            print(f"✓ Unreposted: {args.post_url}")
            return 0
        else:
            print(f"✗ Failed to unrepost")
            return 1
    else:
        # Repost
        if args.dry_run:
            print(f"[DRY RUN] Would repost: {args.post_url}")
            return 0
        
        result = repost(pds, jwt, did, post_uri, post_cid)
        if result:
            print(f"✓ Reposted: {args.post_url}")
            return 0
        else:
            print(f"✗ Failed to repost")
            return 1


def main():
    parser = argparse.ArgumentParser(description="Repost or unrepost")
    parser.add_argument("post_url", help="URL of the post")
    parser.add_argument("--undo", action="store_true", help="Remove repost")
    parser.add_argument("--dry-run", action="store_true", help="Print without acting")
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    exit(main())
