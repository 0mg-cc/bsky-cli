"""Build and print a context pack for interacting with a handle.

V1 goals:
- Per-account SQLite store (seeded from legacy interlocutors.json)
- HOT context: recent DMs (live fetch)
- COLD context: actor notes/tags + last shared threads inferred from past interactions

This is designed to be injected into LLM prompts with explicit HOT vs COLD.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict

from .auth import get_session, resolve_handle
from .http import requests
from .dm import get_dm_conversations, get_dm_messages
from .storage import open_db, ensure_schema, import_interlocutors_json
from .storage.db import upsert_thread_actor_state
from .threads_mod.utils import uri_to_url
from .threads_mod.api import get_thread as _api_get_thread


def _parse_at_uri(uri: str) -> tuple[str, str] | None:
    m = re.match(r"^at://([^/]+)/app\.bsky\.feed\.post/([^/]+)$", uri or "")
    if not m:
        return None
    return m.group(1), m.group(2)


def _get_record(pds: str, jwt: str, repo: str, rkey: str) -> dict:
    url = pds.rstrip("/") + "/xrpc/com.atproto.repo.getRecord"
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {jwt}"},
        params={"repo": repo, "collection": "app.bsky.feed.post", "rkey": rkey},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def _get_root_uri_for_post_uri(pds: str, jwt: str, post_uri: str) -> str:
    parsed = _parse_at_uri(post_uri)
    if not parsed:
        return post_uri
    repo, rkey = parsed
    rec = _get_record(pds, jwt, repo, rkey)
    value = rec.get("value") or {}
    reply = value.get("reply")
    if reply and (reply.get("root") or {}).get("uri"):
        return reply["root"]["uri"]
    # Top-level post
    return rec.get("uri") or post_uri


def _get_post_text(pds: str, jwt: str, uri: str) -> str:
    parsed = _parse_at_uri(uri)
    if not parsed:
        return ""
    repo, rkey = parsed
    rec = _get_record(pds, jwt, repo, rkey)
    return ((rec.get("value") or {}).get("text") or "").strip()


def _resolve_focus_uri(pds: str, jwt: str, focus: str) -> str:
    """Resolve a focus target (at:// URI or bsky.app URL) to an at:// URI."""
    focus = (focus or "").strip()
    if not focus:
        return ""
    if focus.startswith("at://"):
        return focus

    m = re.match(r"^https://bsky\.app/profile/([^/]+)/post/([^/]+)$", focus)
    if not m:
        raise SystemExit(f"Invalid focus URL/URI: {focus}")

    actor, rkey = m.group(1), m.group(2)
    did = actor if actor.startswith("did:") else resolve_handle(pds, actor)
    return f"at://{did}/app.bsky.feed.post/{rkey}"


def _get_post_thread(pds: str, jwt: str, uri: str, depth: int = 10) -> dict | None:
    return _api_get_thread(pds, jwt, uri, depth=depth)


def _node_post_summary(node: dict | None) -> dict:
    if not node:
        return {}
    post = node.get("post") or {}
    uri = post.get("uri") or ""
    author = post.get("author") or {}
    record = post.get("record") or post.get("value") or {}
    txt = (record.get("text") or "").strip()
    created_at = record.get("createdAt") or ""
    return {
        "uri": uri,
        "url": uri_to_url(uri) if uri else "",
        "author": {
            "handle": author.get("handle") or "",
            "did": author.get("did") or "",
            "displayName": author.get("displayName") or "",
        },
        "createdAt": created_at,
        "text": txt,
    }


def _extract_context_path(thread_node: dict) -> list[dict]:
    """Return root→…→focus path from a getPostThread response."""
    cur = thread_node
    rev: list[dict] = []
    while cur:
        rev.append(_node_post_summary(cur))
        cur = cur.get("parent")
    path = list(reversed([p for p in rev if p.get("uri")]))
    return path


def _extract_branching_answers(thread_node: dict, *, limit: int = 5) -> list[dict]:
    replies = thread_node.get("replies") or []
    out: list[dict] = []
    for r in replies:
        if not r:
            continue
        out.append(_node_post_summary(r))
        if len(out) >= int(limit):
            break
    return out


def _fetch_dm_context_from_db(conn, *, my_did: str, target_did: str, limit: int) -> list[dict]:
    # Find convo(s) that include the target DID
    rows = conn.execute(
        "SELECT c.convo_id, c.last_message_at FROM dm_conversations c "
        "JOIN dm_convo_members m ON m.convo_id=c.convo_id "
        "WHERE m.did=? ORDER BY COALESCE(c.last_message_at,'') DESC LIMIT 1",
        (target_did,),
    ).fetchall()

    if not rows:
        return []

    convo_id = rows[0]["convo_id"]

    msgs = conn.execute(
        "SELECT sent_at, actor_did, text FROM dm_messages WHERE convo_id=? ORDER BY sent_at DESC, msg_id DESC LIMIT ?",
        (convo_id, max(1, int(limit))),
    ).fetchall()

    out = []
    for r in reversed(msgs):
        did = r["actor_did"]
        handle = conn.execute("SELECT handle FROM actors WHERE did=?", (did,)).fetchone()
        sender_handle = (handle[0] if handle else "") or ("(you)" if did == my_did else "unknown")
        out.append(
            {
                "sentAt": r["sent_at"],
                "senderDid": did,
                "senderHandle": sender_handle,
                "text": r["text"],
            }
        )

    return out


def _fetch_dm_context(pds: str, jwt: str, account_handle: str, target_handle: str, limit: int) -> list[dict]:
    target_handle = (target_handle or "").lstrip("@").lower()
    if not target_handle:
        return []

    convos = get_dm_conversations(pds, jwt, limit=50)
    convo = None
    for c in convos:
        for m in c.get("members", []) or []:
            if (m.get("handle") or "").lower() == target_handle:
                convo = c
                break
        if convo:
            break

    if not convo:
        return []

    msgs = get_dm_messages(pds, jwt, convo.get("id"), limit=max(1, int(limit)))

    # Build quick DID->handle mapping for this convo
    did_to_handle = {m.get("did"): m.get("handle") for m in convo.get("members", []) or []}

    out = []
    for msg in msgs:
        sender_did = (msg.get("sender") or {}).get("did")
        out.append(
            {
                "sentAt": msg.get("sentAt"),
                "senderDid": sender_did,
                "senderHandle": did_to_handle.get(sender_did),
                "text": msg.get("text") or "",
            }
        )
    return out


def _format_context_pack(pack: dict) -> str:
    hot = pack.get("hot") or {}
    cold = pack.get("cold") or {}

    lines: list[str] = []

    lines.append("[HOT CONTEXT — current conversation]")
    dms = hot.get("dms") or []
    if not dms:
        lines.append("- (no recent DMs found)")
    else:
        for m in dms:
            h = m.get("senderHandle") or "unknown"
            txt = (m.get("text") or "").replace("\n", " ").strip()
            if len(txt) > 220:
                txt = txt[:220] + "…"
            lines.append(f"- @{h}: {txt}")

    lines.append("")
    lines.append("[COLD CONTEXT — past interactions / memory]")

    actor = cold.get("actor") or {}
    if actor:
        handle = actor.get("handle") or ""
        lines.append(f"- Actor: @{handle} ({actor.get('did','')})")
        lines.append(f"- First seen: {actor.get('first_seen','') or 'unknown'}")
        lines.append(f"- Last interaction: {actor.get('last_interaction','') or 'unknown'}")
        lines.append(f"- Total interactions: {actor.get('total_count',0)}")
        if actor.get("tags"):
            lines.append(f"- Tags: {', '.join(actor['tags'])}")
        if actor.get("notes_manual"):
            lines.append(f"- Notes (manual): {actor['notes_manual']}")
        if actor.get("notes_auto"):
            lines.append(f"- Notes (auto): {actor['notes_auto']}")

    threads = cold.get("threads") or []
    if threads:
        lines.append("")
        lines.append("Last shared threads (most recent first):")
        for t in threads:
            lines.append(f"\n• {t.get('url')}")
            root = (t.get("root_text") or "").replace("\n", " ").strip()
            if root:
                lines.append(f"  root: {root[:300]}{'…' if len(root) > 300 else ''}")

            # Focus-aware excerpts (when we know the current position in the thread)
            if t.get("focus_url"):
                lines.append(f"  focus: {t.get('focus_url')}")

                path = t.get("context_path") or []
                if path:
                    lines.append("  path:")
                    for p in path:
                        ah = ((p.get("author") or {}).get("handle") or "unknown")
                        txt = (p.get("text") or "").replace("\n", " ").strip()
                        if len(txt) > 180:
                            txt = txt[:180] + "…"
                        lines.append(f"    - @{ah}: {txt}")

                branches = t.get("branching_answers") or []
                if branches:
                    lines.append("  branches:")
                    for b in branches:
                        ah = ((b.get("author") or {}).get("handle") or "unknown")
                        txt = (b.get("text") or "").replace("\n", " ").strip()
                        if len(txt) > 180:
                            txt = txt[:180] + "…"
                        lines.append(f"    - @{ah}: {txt}")

            if t.get("last_us"):
                u = (t["last_us"] or "").replace("\n", " ").strip()
                lines.append(f"  us:   {u[:260]}{'…' if len(u) > 260 else ''}")
            if t.get("last_them"):
                th = (t["last_them"] or "").replace("\n", " ").strip()
                lines.append(f"  them: {th[:260]}{'…' if len(th) > 260 else ''}")

    return "\n".join(lines).strip() + "\n"


def run(args) -> int:
    handle = (getattr(args, "handle", "") or "").lstrip("@")
    if not handle:
        raise SystemExit("handle is required")

    dm_limit = int(getattr(args, "dm", 10))
    threads_limit = int(getattr(args, "threads", 10))
    focus = getattr(args, "focus", None)

    pds, my_did, jwt, account_handle = get_session()

    # Open per-account DB and ensure schema
    conn = open_db(account_handle)
    ensure_schema(conn)

    # Seed from legacy JSON (best-effort). We do it lazily if DB looks empty.
    c = conn.execute("SELECT COUNT(1) AS n FROM actors").fetchone()["n"]
    if int(c) == 0:
        import_interlocutors_json(conn)

    target_did = resolve_handle(pds, handle)

    # Fetch actor info from DB
    row = conn.execute(
        "SELECT did, handle, display_name, first_seen, last_interaction, total_count, notes_manual, notes_auto FROM actors WHERE did=?",
        (target_did,),
    ).fetchone()

    if not row:
        # Create a stub actor row
        with conn:
            conn.execute("INSERT OR IGNORE INTO actors(did, handle) VALUES (?,?)", (target_did, handle))
        row = conn.execute(
            "SELECT did, handle, display_name, first_seen, last_interaction, total_count, notes_manual, notes_auto FROM actors WHERE did=?",
            (target_did,),
        ).fetchone()

    tags = [r["tag"] for r in conn.execute("SELECT tag FROM actor_tags WHERE did=? ORDER BY tag", (target_did,))]

    # HOT: recent DMs (DB-first, live fallback)
    dm_msgs = _fetch_dm_context_from_db(conn, my_did=my_did, target_did=target_did, limit=dm_limit)
    if not dm_msgs:
        dm_msgs = _fetch_dm_context(pds, jwt, account_handle, handle, dm_limit)

    # COLD: thread index (DB as source of truth, best-effort refresh from interactions)
    inter_rows = conn.execute(
        "SELECT date, post_uri, our_text, their_text FROM interactions "
        "WHERE actor_did=? AND post_uri IS NOT NULL "
        "ORDER BY date DESC, id DESC LIMIT 200",
        (target_did,),
    ).fetchall()

    # Refresh thread_actor_state from recent interactions (best-effort)
    for r in inter_rows:
        post_uri = r["post_uri"]
        if not post_uri:
            continue
        try:
            root_uri = _get_root_uri_for_post_uri(pds, jwt, post_uri)
        except Exception:
            root_uri = post_uri

        upsert_thread_actor_state(
            conn,
            root_uri=root_uri,
            actor_did=target_did,
            last_interaction_at=r["date"],
            last_post_uri=post_uri,
            last_us=r["our_text"] or "",
            last_them=r["their_text"] or "",
        )

    # Pull last shared threads from index
    state_rows = conn.execute(
        "SELECT root_uri, last_post_uri, last_us, last_them, last_interaction_at "
        "FROM thread_actor_state WHERE actor_did=? "
        "ORDER BY last_interaction_at DESC LIMIT ?",
        (target_did, threads_limit),
    ).fetchall()

    threads: list[dict] = []

    # Decide focus: explicit, else fallback to most recent thread position
    focus_uri = ""
    if focus:
        focus_uri = _resolve_focus_uri(pds, jwt, str(focus))
    elif state_rows:
        focus_uri = state_rows[0]["last_post_uri"] or ""

    focus_root_uri = ""
    focus_pack: dict | None = None
    if focus_uri:
        try:
            thread_node = _get_post_thread(pds, jwt, focus_uri, depth=8)
        except Exception:
            thread_node = None
        if thread_node:
            path = _extract_context_path(thread_node)
            branches = _extract_branching_answers(thread_node, limit=5)
            focus_root_uri = (path[0].get("uri") if path else "") or focus_uri
            focus_pack = {
                "focus_uri": focus_uri,
                "focus_url": uri_to_url(focus_uri),
                "context_path": path,
                "branching_answers": branches,
                "root_text": (path[0].get("text") if path else "") or "",
            }

    for r in state_rows:
        root_uri = r["root_uri"]

        root_text = ""
        if focus_pack and root_uri == focus_root_uri and focus_pack.get("root_text"):
            root_text = focus_pack["root_text"]
        else:
            try:
                root_text = _get_post_text(pds, jwt, root_uri)
            except Exception:
                root_text = ""

        t = {
            "root_uri": root_uri,
            "url": uri_to_url(root_uri),
            "root_text": root_text,
            "last_us": r["last_us"] or "",
            "last_them": r["last_them"] or "",
        }

        if focus_pack and root_uri == focus_root_uri:
            t.update(
                {
                    "focus_uri": focus_pack.get("focus_uri"),
                    "focus_url": focus_pack.get("focus_url"),
                    "context_path": focus_pack.get("context_path"),
                    "branching_answers": focus_pack.get("branching_answers"),
                }
            )

        threads.append(t)

    pack = {
        "hot": {"dms": dm_msgs},
        "cold": {
            "actor": {
                "did": row["did"],
                "handle": row["handle"],
                "display_name": row["display_name"],
                "first_seen": row["first_seen"],
                "last_interaction": row["last_interaction"],
                "total_count": row["total_count"],
                "notes_manual": row["notes_manual"],
                "notes_auto": row["notes_auto"],
                "tags": tags,
            },
            "threads": threads,
        },
    }

    if getattr(args, "json", False):
        print(json.dumps(pack, indent=2, ensure_ascii=False))
        return 0

    print(_format_context_pack(pack))
    return 0
