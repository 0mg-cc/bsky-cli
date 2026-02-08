"""Manage BlueSky lists."""

from __future__ import annotations

from datetime import datetime, timezone

from .auth import get_session, resolve_handle
from .http import requests


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_lists(pds: str, jwt: str, actor: str) -> list[dict]:
    r = requests.get(
        f"{pds}/xrpc/app.bsky.graph.getLists",
        headers={"Authorization": f"Bearer {jwt}"},
        params={"actor": actor, "limit": 100},
        timeout=30,
    )
    if r.status_code != 200:
        return []
    return r.json().get("lists", [])


def create_list(pds: str, jwt: str, did: str, name: str, description: str = "") -> dict | None:
    record = {
        "$type": "app.bsky.graph.list",
        "name": name,
        "purpose": "app.bsky.graph.defs#curatelist",
        "createdAt": _now(),
    }
    if description:
        record["description"] = description

    r = requests.post(
        f"{pds}/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"},
        json={"repo": did, "collection": "app.bsky.graph.list", "record": record},
        timeout=30,
    )
    return r.json() if r.status_code == 200 else None


def add_to_list(pds: str, jwt: str, did: str, list_uri: str, actor: str) -> dict | None:
    subject = actor if actor.startswith("did:") else resolve_handle(pds, actor)
    record = {
        "$type": "app.bsky.graph.listitem",
        "subject": subject,
        "list": list_uri,
        "createdAt": _now(),
    }
    r = requests.post(
        f"{pds}/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"},
        json={"repo": did, "collection": "app.bsky.graph.listitem", "record": record},
        timeout=30,
    )
    return r.json() if r.status_code == 200 else None


def run(args) -> int:
    pds, did, jwt, handle = get_session()

    if args.lists_command == "create":
        res = create_list(pds, jwt, did, args.name, args.description or "")
        if not res:
            print("✗ Failed to create list")
            return 1
        print(f"✓ Created list: {args.name}")
        print(res.get("uri", ""))
        return 0

    all_lists = get_lists(pds, jwt, did)

    if args.lists_command == "list":
        if not all_lists:
            print("No lists found.")
            return 0
        for i, item in enumerate(all_lists, 1):
            name = item.get("name", "(unnamed)")
            uri = item.get("uri", "")
            print(f"{i:2d}. {name}")
            if uri:
                print(f"    {uri}")
        return 0

    target = next((x for x in all_lists if x.get("name") == args.list_name), None)
    if not target:
        print(f"✗ List not found: {args.list_name}")
        return 1

    if args.lists_command == "add":
        res = add_to_list(pds, jwt, did, target["uri"], args.handle.lstrip("@"))
        if not res:
            print("✗ Failed to add account to list")
            return 1
        print(f"✓ Added @{args.handle.lstrip('@')} to {args.list_name}")
        return 0

    # show
    r = requests.get(
        f"{pds}/xrpc/app.bsky.graph.getList",
        headers={"Authorization": f"Bearer {jwt}"},
        params={"list": target["uri"], "limit": 100},
        timeout=30,
    )
    if r.status_code != 200:
        print("✗ Failed to fetch list items")
        return 1
    items = r.json().get("items", [])
    print(f"{target.get('name')} ({len(items)} accounts)")
    for it in items:
        actor = it.get("subject", {})
        print(f"- @{actor.get('handle', 'unknown')}")
    return 0
