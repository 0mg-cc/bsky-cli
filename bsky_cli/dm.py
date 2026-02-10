"""Direct Messages support for BlueSky CLI."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .http import requests

from .auth import get_session
from .post import detect_facets

CHAT_PROXY_DID = "did:web:api.bsky.chat"
DM_STATE_FILE = Path("/home/echo/.local/state/bsky_dm_last_seen.txt")


def get_dm_conversations(pds: str, jwt: str, limit: int = 20) -> list[dict]:
    """Fetch recent DM conversations."""
    url = pds.rstrip("/") + "/xrpc/chat.bsky.convo.listConvos"
    headers = {
        "Authorization": f"Bearer {jwt}",
        "atproto-proxy": f"{CHAT_PROXY_DID}#bsky_chat",
    }
    params = {"limit": limit}
    r = requests.get(url, headers=headers, params=params, timeout=20)
    r.raise_for_status()
    return r.json().get("convos", [])


def get_dm_messages(pds: str, jwt: str, convo_id: str, limit: int = 20) -> list[dict]:
    """Fetch messages from a conversation."""
    url = pds.rstrip("/") + "/xrpc/chat.bsky.convo.getMessages"
    headers = {
        "Authorization": f"Bearer {jwt}",
        "atproto-proxy": f"{CHAT_PROXY_DID}#bsky_chat",
    }
    params = {"convoId": convo_id, "limit": limit}
    r = requests.get(url, headers=headers, params=params, timeout=20)
    r.raise_for_status()
    return r.json().get("messages", [])


def get_dm_last_seen() -> str | None:
    """Get last seen DM timestamp from state file."""
    if DM_STATE_FILE.exists():
        return DM_STATE_FILE.read_text().strip() or None
    return None


def save_dm_last_seen(timestamp: str) -> None:
    """Save last seen DM timestamp to state file."""
    DM_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    DM_STATE_FILE.write_text(timestamp)


def check_new_dms(pds: str, jwt: str, *, my_did: str | None = None) -> list[dict]:
    """Check for new DMs since last check.
    
    Returns a list of new messages with conversation context.
    """
    last_seen = get_dm_last_seen()
    new_messages = []
    newest_ts = last_seen or ""
    
    try:
        convos = get_dm_conversations(pds, jwt)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 400 and "Bad token scope" in e.response.text:
            return []  # App password doesn't have DM access, silently skip
        raise
    
    for convo in convos:
        # Get the other member(s) - filter out self
        members = [m for m in convo.get("members", [])]
        
        # Check unread count
        unread = convo.get("unreadCount", 0)
        if unread == 0:
            continue
            
        # Fetch recent messages
        try:
            messages = get_dm_messages(pds, jwt, convo["id"], limit=unread + 5)
        except:
            continue
            
        for msg in messages:
            sent_at = msg.get("sentAt", "")
            
            # Skip if we've seen this already
            if last_seen and sent_at <= last_seen:
                continue
                
            sender = msg.get("sender", {})

            # Skip if it's from us (optional)
            if my_did and sender.get("did") == my_did:
                continue

            # Track newest
            if sent_at > newest_ts:
                newest_ts = sent_at
                
            new_messages.append({
                "convo_id": convo["id"],
                "members": members,
                "message_id": msg.get("id") or "",
                "sender": sender,
                "text": msg.get("text", ""),
                "facets": msg.get("facets"),
                "sent_at": sent_at,
            })
    
    # Save state
    if newest_ts and newest_ts != last_seen:
        save_dm_last_seen(newest_ts)
    
    return new_messages


def format_dm(dm: dict) -> str:
    """Format a DM for human reading."""
    sender = dm.get("sender", {})
    handle = sender.get("handle", "unknown")
    display_name = sender.get("displayName", handle)
    text = dm.get("text", "")
    sent_at = dm.get("sent_at", "")
    
    try:
        dt = datetime.fromisoformat(sent_at.replace("Z", "+00:00"))
        time_str = dt.strftime("%Y-%m-%d %H:%M UTC")
    except:
        time_str = sent_at
    
    return f"📩 DM from @{handle} ({display_name}) at {time_str}:\n   \"{text[:300]}{'...' if len(text) > 300 else ''}\""


def get_or_create_convo(pds: str, jwt: str, member_did: str) -> dict:
    """Get or create a conversation with a user by their DID."""
    url = pds.rstrip("/") + "/xrpc/chat.bsky.convo.getConvoForMembers"
    headers = {
        "Authorization": f"Bearer {jwt}",
        "atproto-proxy": f"{CHAT_PROXY_DID}#bsky_chat",
    }
    params = {"members": member_did}
    r = requests.get(url, headers=headers, params=params, timeout=20)
    r.raise_for_status()
    return r.json().get("convo", {})


def send_dm(pds: str, jwt: str, convo_id: str, text: str) -> dict:
    """Send a DM to a conversation."""
    url = pds.rstrip("/") + "/xrpc/chat.bsky.convo.sendMessage"
    headers = {
        "Authorization": f"Bearer {jwt}",
        "Content-Type": "application/json",
        "atproto-proxy": f"{CHAT_PROXY_DID}#bsky_chat",
    }
    msg = {"text": text}
    facets = detect_facets(text, pds=pds)
    if facets:
        msg["facets"] = facets

    payload = {
        "convoId": convo_id,
        "message": msg,
    }
    r = requests.post(url, headers=headers, json=payload, timeout=20)
    r.raise_for_status()
    return r.json()


def send_dm_to_handle(handle: str, text: str) -> dict:
    """Send a DM to a user by handle. Returns the sent message."""
    from .auth import get_session, resolve_handle
    
    pds, my_did, jwt, _ = get_session()
    
    # Resolve handle to DID
    target_did = resolve_handle(pds, handle)
    
    # Get or create conversation
    convo = get_or_create_convo(pds, jwt, target_did)
    convo_id = convo.get("id")
    
    if not convo_id:
        raise ValueError(f"Could not get/create conversation with {handle}")
    
    # Send message
    return send_dm(pds, jwt, convo_id, text)
