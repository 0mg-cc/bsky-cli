"""Profile command for BlueSky CLI."""
from __future__ import annotations

from pathlib import Path

import requests

from .auth import get_session, upload_blob


def get_profile(pds: str, jwt: str, did: str) -> dict:
    """Get current profile record."""
    url = pds.rstrip("/") + "/xrpc/com.atproto.repo.getRecord"
    headers = {"Authorization": f"Bearer {jwt}"}
    params = {
        "repo": did,
        "collection": "app.bsky.actor.profile",
        "rkey": "self",
    }
    r = requests.get(url, params=params, headers=headers, timeout=20)
    if r.status_code == 400:
        return {}
    r.raise_for_status()
    return r.json()


def update_profile(pds: str, jwt: str, did: str, record: dict) -> dict:
    """Update profile record."""
    url = pds.rstrip("/") + "/xrpc/com.atproto.repo.putRecord"
    headers = {"Authorization": f"Bearer {jwt}"}
    payload = {
        "repo": did,
        "collection": "app.bsky.actor.profile",
        "rkey": "self",
        "record": record,
    }
    r = requests.post(url, json=payload, headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()


def run(args) -> int:
    """Execute profile command."""
    if not any([args.avatar, args.banner, args.name, args.bio]):
        print("Error: specify at least one of --avatar, --banner, --name, --bio")
        return 2

    pds, did, jwt, _ = get_session()

    # Get current profile
    current = get_profile(pds, jwt, did)
    record = current.get("value", {})
    record["$type"] = "app.bsky.actor.profile"

    # Update fields
    if args.name:
        record["displayName"] = args.name
        print(f"Setting displayName: {args.name}")

    if args.bio:
        record["description"] = args.bio
        print(f"Setting description: {args.bio}")

    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}

    if args.avatar:
        avatar_path = Path(args.avatar)
        if not avatar_path.exists():
            raise SystemExit(f"Avatar file not found: {avatar_path}")
        
        mime_type = mime_map.get(avatar_path.suffix.lower(), "image/png")
        print(f"Uploading avatar: {avatar_path}")
        blob_ref = upload_blob(pds, jwt, avatar_path.read_bytes(), mime_type)
        record["avatar"] = blob_ref
        print("Avatar uploaded")

    if args.banner:
        banner_path = Path(args.banner)
        if not banner_path.exists():
            raise SystemExit(f"Banner file not found: {banner_path}")
        
        mime_type = mime_map.get(banner_path.suffix.lower(), "image/png")
        print(f"Uploading banner: {banner_path}")
        blob_ref = upload_blob(pds, jwt, banner_path.read_bytes(), mime_type)
        record["banner"] = blob_ref
        print("Banner uploaded")

    # Save profile
    result = update_profile(pds, jwt, did, record)
    print(f"Profile updated: {result.get('uri', 'ok')}")
    return 0
