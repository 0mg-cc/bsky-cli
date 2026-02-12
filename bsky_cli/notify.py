"""Notifications command for BlueSky CLI."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .http import requests

from .auth import get_session
from .dm import check_new_dms, format_dm

STATE_FILE = Path("/home/echo/.local/state/bsky_last_seen.txt")


def get_notifications(pds: str, jwt: str, limit: int = 50) -> list[dict]:
    """Fetch recent notifications."""
    url = pds.rstrip("/") + "/xrpc/app.bsky.notification.listNotifications"
    headers = {"Authorization": f"Bearer {jwt}"}
    params = {"limit": limit}
    r = requests.get(url, headers=headers, params=params, timeout=20)
    r.raise_for_status()
    return r.json().get("notifications", [])


def update_seen(pds: str, jwt: str, seen_at: str) -> None:
    """Mark notifications as seen up to timestamp."""
    url = pds.rstrip("/") + "/xrpc/app.bsky.notification.updateSeen"
    headers = {"Authorization": f"Bearer {jwt}"}
    r = requests.post(url, json={"seenAt": seen_at}, headers=headers, timeout=20)
    r.raise_for_status()


def get_last_seen() -> str | None:
    """Get last seen timestamp from state file."""
    if STATE_FILE.exists():
        return STATE_FILE.read_text().strip() or None
    return None


def save_last_seen(timestamp: str) -> None:
    """Save last seen timestamp to state file."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(timestamp)


def format_notification(n: dict, show_relationship: bool = True) -> str:
    """Format a notification for human reading."""
    from . import interlocutors
    
    reason = n.get("reason", "unknown")
    author = n.get("author", {})
    handle = author.get("handle", "unknown")
    did = author.get("did", "")
    display_name = author.get("displayName", handle)
    indexed_at = n.get("indexedAt", "")
    
    try:
        dt = datetime.fromisoformat(indexed_at.replace("Z", "+00:00"))
        time_str = dt.strftime("%Y-%m-%d %H:%M UTC")
    except:
        time_str = indexed_at
    
    record = n.get("record", {})
    text = record.get("text", "")
    
    # Interlocutor badge
    badge = ""
    if show_relationship and did:
        badge = interlocutors.format_notification_badge(did)
        if badge:
            badge = f" {badge}"
    
    if reason == "reply":
        return f"💬 REPLY from @{handle}{badge} ({display_name}) at {time_str}:\n   \"{text[:200]}{'...' if len(text) > 200 else ''}\""
    elif reason == "mention":
        return f"📢 MENTION from @{handle}{badge} ({display_name}) at {time_str}:\n   \"{text[:200]}{'...' if len(text) > 200 else ''}\""
    elif reason == "like":
        return f"❤️  LIKE from @{handle}{badge} ({display_name}) at {time_str}"
    elif reason == "repost":
        return f"🔁 REPOST from @{handle}{badge} ({display_name}) at {time_str}"
    elif reason == "follow":
        return f"👤 FOLLOW from @{handle}{badge} ({display_name}) at {time_str}"
    elif reason == "quote":
        return f"💭 QUOTE from @{handle}{badge} ({display_name}) at {time_str}:\n   \"{text[:200]}{'...' if len(text) > 200 else ''}\""
    else:
        return f"🔔 {reason.upper()} from @{handle}{badge} ({display_name}) at {time_str}"


def get_post_url(n: dict) -> str | None:
    """Extract a URL to the relevant post if available."""
    uri = n.get("uri", "")
    
    if uri.startswith("at://"):
        m = re.match(r"^at://([^/]+)/app\.bsky\.feed\.post/([^/]+)$", uri)
        if m:
            return f"https://bsky.app/profile/{m.group(1)}/post/{m.group(2)}"
    
    return None


def run(args) -> int:
    """Execute notify command."""
    pds, did, jwt, account_handle = get_session()

    # New: scoring/triage mode
    if getattr(args, "score", False) or getattr(args, "execute", False):
        from .notify_scored import run_scored
        return run_scored(args, pds, did, jwt)

    notifications = get_notifications(pds, jwt, limit=args.limit)
    
    # Check DMs
    new_dms = []
    if not args.no_dm:
        try:
            new_dms = check_new_dms(pds, jwt, my_did=did)

            # Best-effort: persist DMs into per-account SQLite for context/memory
            if new_dms:
                try:
                    from .storage import open_db, ensure_schema, import_interlocutors_json
                    from .storage.db import ingest_new_dms

                    conn = open_db(account_handle)
                    ensure_schema(conn)

                    # Seed legacy interlocutors once (optional, anti-regression)
                    c = conn.execute("SELECT COUNT(1) AS n FROM actors").fetchone()["n"]
                    if int(c) == 0:
                        import_interlocutors_json(conn)

                    ingest_new_dms(conn, new_dms, my_did=did)
                except Exception:
                    pass
        except Exception as e:
            if not args.json:
                print(f"⚠️  Could not check DMs: {e}\n")
    
    if args.json:
        print(json.dumps({"notifications": notifications, "dms": new_dms}, indent=2))
        return 0

    # Filter to new ones only (unless --all)
    last_seen = get_last_seen()
    if not args.all and last_seen:
        notifications = [n for n in notifications if n.get("indexedAt", "") > last_seen]

    if not notifications and not new_dms:
        print("No new notifications.")
        return 0

    newest = max((n.get("indexedAt", "") for n in notifications), default="")
    
    # Group by type
    replies = [n for n in notifications if n.get("reason") == "reply"]
    mentions = [n for n in notifications if n.get("reason") == "mention"]
    quotes = [n for n in notifications if n.get("reason") == "quote"]
    likes = [n for n in notifications if n.get("reason") == "like"]
    reposts = [n for n in notifications if n.get("reason") == "repost"]
    follows = [n for n in notifications if n.get("reason") == "follow"]
    
    header_count = (
        f"{len(notifications)} notifications, all recent"
        if args.all
        else f"{len(notifications)} new"
    )
    print(f"=== BlueSky Notifications ({header_count}) ===\n")
    
    # Show important ones in full
    important = replies + mentions + quotes
    if important:
        print("--- Replies/Mentions/Quotes (need attention) ---")
        for n in sorted(important, key=lambda x: x.get("indexedAt", ""), reverse=True):
            print(format_notification(n))
            url = get_post_url(n)
            if url:
                print(f"   → {url}")
            print()
    
    # Summarize the rest
    if likes:
        print(f"❤️  {len(likes)} likes")
    if reposts:
        print(f"🔁 {len(reposts)} reposts")
    if follows:
        print(f"👤 {len(follows)} new followers")
        for n in follows[:5]:
            author = n.get("author", {})
            print(f"   - @{author.get('handle')} ({author.get('displayName', '')})")
        if len(follows) > 5:
            print(f"   ... and {len(follows) - 5} more")
    
    # Show DMs
    if new_dms:
        print("\n--- Direct Messages (need attention) ---")
        for dm in sorted(new_dms, key=lambda x: x.get("sent_at", ""), reverse=True):
            print(format_dm(dm))
            print()
    
    # Save state
    if newest:
        save_last_seen(newest)
    
    # Mark as read on BlueSky if requested
    if args.mark_read and newest:
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        update_seen(pds, jwt, now)
        print("\n✓ Marked as read on BlueSky")

    return 0
