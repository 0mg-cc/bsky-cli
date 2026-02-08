"""Reply command for BlueSky CLI."""
from __future__ import annotations

import re

from .http import requests

from .auth import get_session, utc_now_iso, resolve_handle
from .post import detect_facets


def parse_post_url(url: str) -> tuple[str, str] | None:
    """Parse a bsky.app post URL into (did_or_handle, rkey)."""
    m = re.match(r"https?://bsky\.app/profile/([^/]+)/post/([^/]+)", url)
    if m:
        return m.group(1), m.group(2)
    return None


def get_post(pds: str, jwt: str, repo: str, rkey: str) -> dict:
    """Get a post record."""
    url = pds.rstrip("/") + "/xrpc/com.atproto.repo.getRecord"
    headers = {"Authorization": f"Bearer {jwt}"}
    params = {
        "repo": repo,
        "collection": "app.bsky.feed.post",
        "rkey": rkey,
    }
    r = requests.get(url, headers=headers, params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def create_reply(pds: str, jwt: str, repo_did: str, text: str, 
                 parent_uri: str, parent_cid: str, 
                 root_uri: str, root_cid: str) -> dict:
    """Create a reply post."""
    url = pds.rstrip("/") + "/xrpc/com.atproto.repo.createRecord"
    headers = {"Authorization": f"Bearer {jwt}"}
    
    facets = detect_facets(text)
    
    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": utc_now_iso(),
        "langs": ["en"],
        "reply": {
            "root": {"uri": root_uri, "cid": root_cid},
            "parent": {"uri": parent_uri, "cid": parent_cid}
        }
    }
    
    if facets:
        record["facets"] = facets
    
    payload = {
        "repo": repo_did,
        "collection": "app.bsky.feed.post",
        "record": record,
    }
    r = requests.post(url, json=payload, headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()


def run(args) -> int:
    """Execute reply command."""
    parsed = parse_post_url(args.post_url)
    if not parsed:
        raise SystemExit(f"Invalid post URL: {args.post_url}")
    
    target_handle, rkey = parsed

    text = args.text.strip()
    if len(text) > 300:
        raise SystemExit(f"Reply too long ({len(text)} chars, max 300)")

    pds, my_did, jwt, _ = get_session()

    # Resolve target handle to DID
    target_did = resolve_handle(pds, target_handle)
    
    # Get the parent post
    parent_post = get_post(pds, jwt, target_did, rkey)
    parent_uri = parent_post["uri"]
    parent_cid = parent_post["cid"]
    
    # Determine root (for threading)
    parent_record = parent_post.get("value", {})
    if "reply" in parent_record:
        root_uri = parent_record["reply"]["root"]["uri"]
        root_cid = parent_record["reply"]["root"]["cid"]
    else:
        root_uri = parent_uri
        root_cid = parent_cid

    if args.dry_run:
        print("DRY RUN")
        print(f"Replying to: {args.post_url}")
        print(f"Target DID: {target_did}")
        print(f"Parent URI: {parent_uri}")
        print(f"Text ({len(text)} chars):\n{text}")
        return 0

    res = create_reply(pds, jwt, my_did, text, parent_uri, parent_cid, root_uri, root_cid)
    
    uri = res.get("uri", "")
    m = re.match(r"^at://([^/]+)/app\.bsky\.feed\.post/([^/]+)$", uri)
    if m:
        print(f"✅ Reply posted: https://bsky.app/profile/{m.group(1)}/post/{m.group(2)}")
    else:
        print(res)
    return 0
