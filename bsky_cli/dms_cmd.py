"""DM inbox / conversation viewer for BlueSky CLI.

This complements `bsky dm <handle> <text>` (send).

Commands added:
- `bsky dms --json`             list conversations with unread counts + preview
- `bsky dms show <handle> --json`  show recent messages for a conversation

We keep this intentionally simple and script-friendly.
"""

from __future__ import annotations

import json

from .auth import get_session
from . import dm as dm_mod


def _resolve_sender(members: list[dict], sender_did: str) -> dict:
    for m in members or []:
        if m.get("did") == sender_did:
            return m
    return {}


def run(args) -> int:
    """List DM conversations."""
    pds, my_did, jwt, _ = get_session()

    convos = dm_mod.get_dm_conversations(pds, jwt, limit=getattr(args, "limit", 20))
    preview_n = max(0, int(getattr(args, "preview", 1)))

    rows: list[dict] = []
    for convo in convos:
        unread = convo.get("unreadCount", 0)
        convo_id = convo.get("id")
        members = convo.get("members", [])

        preview_msgs = []
        if preview_n and convo_id:
            try:
                msgs = dm_mod.get_dm_messages(pds, jwt, convo_id, limit=max(1, preview_n))
                for msg in msgs[:preview_n]:
                    sender_did = (msg.get("sender") or {}).get("did", "")
                    sender = _resolve_sender(members, sender_did)
                    preview_msgs.append(
                        {
                            "sentAt": msg.get("sentAt"),
                            "sender": {
                                "did": sender_did,
                                "handle": sender.get("handle"),
                                "displayName": sender.get("displayName"),
                            },
                            "text": msg.get("text", ""),
                        }
                    )
            except Exception:
                preview_msgs = []

        rows.append(
            {
                "id": convo_id,
                "unreadCount": unread,
                "members": members,
                "preview": preview_msgs,
            }
        )

    if getattr(args, "json", False):
        print(json.dumps({"conversations": rows}, indent=2))
        return 0

    # Human-readable
    print(f"=== BlueSky DMs ({len(rows)} conversations) ===\n")
    for c in rows:
        unread = c.get("unreadCount", 0)
        members = c.get("members", [])
        others = [m.get("handle") for m in members if m.get("handle") and m.get("handle") != "echo.0mg.cc"]
        label = ", ".join([f"@{h}" for h in others]) or "(unknown)"
        print(f"• {label} — unread: {unread}")
        if c.get("preview"):
            p = c["preview"][0]
            sh = (p.get("sender") or {}).get("handle") or "unknown"
            txt = (p.get("text") or "").replace("\n", " ")
            print(f"  last: @{sh}: {txt[:120]}{'…' if len(txt) > 120 else ''}")
    return 0


def run_show(args) -> int:
    """Show messages for a conversation with a given handle."""
    pds, my_did, jwt, _ = get_session()

    handle = (getattr(args, "handle", "") or "").lstrip("@")
    if not handle:
        raise SystemExit("handle is required")

    convos = dm_mod.get_dm_conversations(pds, jwt, limit=50)

    # Find convo that contains this handle
    target = None
    for c in convos:
        for m in c.get("members", []) or []:
            if m.get("handle") == handle:
                target = c
                break
        if target:
            break

    if not target:
        if getattr(args, "json", False):
            print(json.dumps({"error": "conversation_not_found", "handle": handle}, indent=2))
            return 1
        print(f"No conversation found for @{handle}.")
        return 1

    convo_id = target.get("id")
    members = target.get("members", [])

    msgs = dm_mod.get_dm_messages(pds, jwt, convo_id, limit=int(getattr(args, "limit", 50)))

    out_msgs = []
    for msg in msgs:
        sender_did = (msg.get("sender") or {}).get("did", "")
        sender = _resolve_sender(members, sender_did)
        out_msgs.append(
            {
                "sentAt": msg.get("sentAt"),
                "sender": {
                    "did": sender_did,
                    "handle": sender.get("handle"),
                    "displayName": sender.get("displayName"),
                },
                "text": msg.get("text", ""),
            }
        )

    if getattr(args, "json", False):
        print(json.dumps({"convo": {"id": convo_id, "members": members}, "messages": out_msgs}, indent=2))
        return 0

    print(f"=== DM with @{handle} ===\n")
    for m in out_msgs:
        sh = (m.get("sender") or {}).get("handle") or "unknown"
        txt = m.get("text") or ""
        print(f"@{sh}: {txt}")
    return 0
