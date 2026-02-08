"""Starter pack management for BlueSky."""

from __future__ import annotations

from datetime import datetime, timezone

from .auth import get_session
from .http import requests
from .lists import get_lists


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def create_starterpack(pds: str, jwt: str, did: str, name: str, list_uri: str, description: str = "") -> dict | None:
    record = {
        "$type": "app.bsky.graph.starterpack",
        "name": name,
        "list": list_uri,
        "createdAt": _now(),
    }
    if description:
        record["description"] = description

    r = requests.post(
        f"{pds}/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"},
        json={"repo": did, "collection": "app.bsky.graph.starterpack", "record": record},
        timeout=30,
    )
    return r.json() if r.status_code == 200 else None


def list_starterpacks(pds: str, jwt: str, actor: str) -> list[dict]:
    r = requests.get(
        f"{pds}/xrpc/app.bsky.graph.getActorStarterPacks",
        headers={"Authorization": f"Bearer {jwt}"},
        params={"actor": actor, "limit": 100},
        timeout=30,
    )
    if r.status_code != 200:
        return []
    return r.json().get("starterPacks", [])


def run(args) -> int:
    pds, did, jwt, _handle = get_session()

    if args.starterpack_command == "create":
        lists = get_lists(pds, jwt, did)
        target = next((x for x in lists if x.get("name") == args.list_name), None)
        if not target:
            print(f"✗ List not found: {args.list_name}")
            return 1

        res = create_starterpack(pds, jwt, did, args.name, target["uri"], args.description or "")
        if not res:
            print("✗ Failed to create starter pack")
            return 1
        print(f"✓ Created starter pack: {args.name}")
        print(res.get("uri", ""))
        return 0

    packs = list_starterpacks(pds, jwt, did)
    if not packs:
        print("No starter packs found.")
        return 0
    for i, p in enumerate(packs, 1):
        rec = p.get("record", {})
        print(f"{i:2d}. {rec.get('name', '(unnamed)')}")
        if p.get("uri"):
            print(f"    {p['uri']}")
    return 0
