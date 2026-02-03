"""Follow a BlueSky account."""
from __future__ import annotations

import argparse
import datetime as dt

import requests

from .auth import get_session


def resolve_handle(handle: str) -> str | None:
    """Resolve a handle to DID."""
    handle = handle.lstrip("@")
    
    try:
        r = requests.get(
            f"https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile",
            params={"actor": handle},
            timeout=10
        )
        if r.status_code == 200:
            return r.json().get("did")
    except Exception:
        pass
    return None


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
    except Exception as e:
        print(f"Error: {e}")
        return False


def run(args: argparse.Namespace) -> int:
    """Follow a user by handle."""
    handle = args.handle.lstrip("@")
    
    # Resolve handle to DID
    target_did = resolve_handle(handle)
    if not target_did:
        print(f"❌ Could not resolve handle: {handle}")
        return 1
    
    if args.dry_run:
        print(f"Would follow: @{handle} ({target_did})")
        return 0
    
    # Authenticate - returns (pds, did, jwt, handle)
    try:
        pds, my_did, jwt, _ = get_session()
    except SystemExit as e:
        print(f"❌ {e}")
        return 1
    
    # Follow
    if follow_account(pds, jwt, my_did, target_did):
        print(f"✅ Followed @{handle}")
        return 0
    else:
        print(f"❌ Failed to follow @{handle}")
        return 1
