"""View and manage people/notes.

PR-006: DB-first (per-account SQLite).

This command intentionally stays lightweight and text-first.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone

from .auth import get_session, load_from_pass, resolve_handle
from .http import requests
from .interlocutors import get_friendly_threshold, get_regular_threshold
from .storage.db import ensure_schema, import_interlocutors_json, open_db


def _norm_handle(s: str) -> str:
    return (s or "").strip().lstrip("@").lower()


def _split_tags(s: str | None) -> list[str]:
    if not s:
        return []
    return [t.strip() for t in s.split(",") if t.strip()]


def _ensure_seeded(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT COUNT(*) AS n FROM actors").fetchone()
    if int(row["n"]) == 0:
        # Anti-regression during migration period.
        import_interlocutors_json(conn, overwrite=False)


def _find_actor_did(conn: sqlite3.Connection, handle_or_did: str, *, pds: str | None = None) -> str | None:
    s = (handle_or_did or "").strip()
    if not s:
        return None
    if s.startswith("did:"):
        return s

    handle = _norm_handle(s)
    row = conn.execute("SELECT did FROM actors WHERE lower(handle)=?", (handle,)).fetchone()
    if row:
        return str(row["did"])

    if pds:
        try:
            did = resolve_handle(pds, handle)
        except Exception:
            did = None
        if did:
            conn.execute(
                "INSERT OR IGNORE INTO actors(did, handle) VALUES (?,?)",
                (did, handle),
            )
            conn.commit()
            return str(did)

    return None


def _parse_any_ts(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None

    # DM timestamps are ISO (usually with Z)
    if "T" in s:
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None

    # interactions.date is often date-only (YYYY-MM-DD)
    try:
        d = datetime.fromisoformat(s)
        # date-only parses as datetime at midnight (naive) in some py versions;
        # normalize to UTC-aware.
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except Exception:
        return None


def _actor_stats(conn: sqlite3.Connection, did: str) -> dict:
    n_inter = int(conn.execute("SELECT COUNT(*) AS n FROM interactions WHERE actor_did=?", (did,)).fetchone()["n"])
    n_dm = int(conn.execute("SELECT COUNT(*) AS n FROM dm_messages WHERE actor_did=?", (did,)).fetchone()["n"])
    last_inter = conn.execute("SELECT MAX(date) AS v FROM interactions WHERE actor_did=?", (did,)).fetchone()["v"] or ""
    last_dm = conn.execute("SELECT MAX(sent_at) AS v FROM dm_messages WHERE actor_did=?", (did,)).fetchone()["v"] or ""

    di = _parse_any_ts(str(last_inter))
    dd = _parse_any_ts(str(last_dm))

    if di and dd:
        last = last_inter if di >= dd else last_dm
    else:
        last = last_dm or last_inter

    return {
        "n_interactions": n_inter,
        "n_dms": n_dm,
        "total": n_inter + n_dm,
        "last": last,
        "last_interaction": last_inter,
        "last_dm": last_dm,
    }


def _upsert_note_and_tags(
    conn: sqlite3.Connection,
    *,
    did: str,
    note: str | None,
    add_tags: list[str] | None,
    remove_tags: list[str] | None,
) -> None:
    with conn:
        if note is not None:
            conn.execute("UPDATE actors SET notes_manual=? WHERE did=?", (note, did))

        for t in add_tags or []:
            conn.execute("INSERT OR IGNORE INTO actor_tags(did, tag) VALUES (?,?)", (did, t))

        for t in remove_tags or []:
            conn.execute("DELETE FROM actor_tags WHERE did=? AND tag=?", (did, t))


def _extract_json_obj(raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("empty LLM content")

    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else ""
        raw = raw.rsplit("```", 1)[0].strip()

    try:
        return json.loads(raw)
    except Exception:
        pass

    i = raw.find("{")
    j = raw.rfind("}")
    if i != -1 and j != -1 and j > i:
        return json.loads(raw[i : j + 1])

    raise ValueError("could not parse JSON from LLM content")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso_z(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _get_openrouter() -> tuple[str, str]:
    env = load_from_pass("api/openrouter") or {}
    api_key = env.get("OPENROUTER_API_KEY")
    model = env.get("OPENROUTER_MODEL") or "google/gemini-2.0-flash-001"
    if not api_key:
        raise RuntimeError("Missing OPENROUTER_API_KEY in pass api/openrouter")
    return api_key, model


def _llm_enrich_person(*, handle: str, display_name: str, tags: list[str], notes_manual: str, recent_dms: list[dict], recent_interactions: list[dict]) -> dict:
    """Return JSON: {notes_auto, interests_auto, relationship_tone}."""

    prompt = f"""You are an assistant helping maintain a lightweight contact card for a BlueSky interlocutor.

TARGET:
- handle: @{handle}
- display_name: {display_name or ''}
- tags: {', '.join(tags) if tags else '(none)'}
- manual_notes: {notes_manual or '(none)'}

RECENT DMs (newest first):
""" + "\n".join(
        [f"- [{m.get('sent_at')}] {m.get('direction')}: {m.get('text')}" for m in recent_dms]
    ) + "\n\nRECENT thread interactions (newest first):\n" + "\n".join(
        [
            f"- [{i.get('date')}] {i.get('type')}: them={i.get('their_text') or ''} | us={i.get('our_text') or ''}"
            for i in recent_interactions
        ]
    ) + """

TASK:
- Produce a short, reliable contact card based ONLY on the data above.
- notes_auto: 2-4 sentences max.
- interests_auto: a short comma-separated list of interests.
- relationship_tone: 1 short phrase (e.g. 'friendly, technical', 'formal, brief', 'warm, playful').
- If unsure, say so explicitly.

Respond ONLY as JSON:
{"notes_auto":"...","interests_auto":"...","relationship_tone":"..."}
"""

    api_key, model = _get_openrouter()
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.4,
            "response_format": {"type": "json_object"},
        },
        timeout=60,
    )

    if r.status_code != 200:
        raise RuntimeError(f"LLM error: {r.status_code}")

    content = r.json()["choices"][0]["message"].get("content")
    if isinstance(content, dict):
        return content
    return _extract_json_obj(str(content) if content is not None else "")


def _save_auto_snapshot(conn: sqlite3.Connection, *, did: str, kind: str, content: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO actor_auto_notes(did, kind, content) VALUES (?,?,?)",
            (did, kind, content),
        )

        if kind == "notes":
            conn.execute("UPDATE actors SET notes_auto=? WHERE did=?", (content, did))
        elif kind == "interests":
            conn.execute("UPDATE actors SET interests_auto=? WHERE did=?", (content, did))
        elif kind == "tone":
            conn.execute("UPDATE actors SET relationship_tone=? WHERE did=?", (content, did))


def _should_skip_enrich(conn: sqlite3.Connection, *, did: str, min_age_hours: int, force: bool) -> tuple[bool, str | None]:
    if force:
        return False, None

    row = conn.execute(
        "SELECT MAX(created_at) AS v FROM actor_auto_notes WHERE did=? AND kind='notes'",
        (did,),
    ).fetchone()
    last = (row["v"] if row else None) or None
    if not last:
        return False, None

    try:
        age_h = (_utcnow() - _parse_iso_z(str(last))).total_seconds() / 3600
    except Exception:
        return False, None

    if age_h < float(min_age_hours):
        return True, str(last)

    return False, str(last)

def run(args) -> int:
    """Entry point from CLI."""

    pds, _my_did, _jwt, account_handle = get_session()
    conn = open_db(account_handle)
    ensure_schema(conn)
    _ensure_seeded(conn)

    # --- Stats mode
    if getattr(args, "stats", False):
        # Consider only actors that have any activity.
        dids = [
            r["did"]
            for r in conn.execute(
                "SELECT did FROM actors WHERE did IN (SELECT actor_did FROM interactions UNION SELECT actor_did FROM dm_messages)"
            ).fetchall()
        ]

        total_users = len(dids)
        totals = [_actor_stats(conn, d)["total"] for d in dids]
        total_interactions = sum(totals)
        regular_threshold = get_regular_threshold()
        regulars = sum(1 for t in totals if t >= regular_threshold)

        print("📊 Interlocutor Statistics\n")
        print(f"Total users tracked: {total_users}")
        print(f"Regulars ({regular_threshold}+ interactions): {regulars}")
        print(f"Total interactions: {total_interactions}")
        print(f"Average per user: {total_interactions / total_users:.1f}" if total_users else "Average per user: 0")
        return 0

    # --- Single user lookup / edit
    if getattr(args, "handle", None):
        did = _find_actor_did(conn, str(args.handle), pds=pds)
        if not did:
            print(f"❌ No history with {args.handle}")
            return 0

        # Apply edits (notes/tags) before display
        note = getattr(args, "set_note", None)
        add_tags = getattr(args, "add_tag", None)
        remove_tags = getattr(args, "remove_tag", None)

        if isinstance(add_tags, str):
            add_tags = _split_tags(add_tags)
        if isinstance(remove_tags, str):
            remove_tags = _split_tags(remove_tags)

        if note is not None or add_tags or remove_tags:
            _upsert_note_and_tags(conn, did=did, note=note, add_tags=add_tags, remove_tags=remove_tags)

        row = conn.execute(
            "SELECT did, handle, display_name, first_seen, last_interaction, notes_manual, notes_auto, interests_auto, relationship_tone FROM actors WHERE did=?",
            (did,),
        ).fetchone()
        if not row:
            print(f"❌ No history with {args.handle}")
            return 0

        tags = [r["tag"] for r in conn.execute("SELECT tag FROM actor_tags WHERE did=? ORDER BY tag", (did,)).fetchall()]
        st = _actor_stats(conn, did)

        regular = st["total"] >= get_regular_threshold()
        friendly = st["total"] >= get_friendly_threshold()
        badge = "🔄 Regular" if regular else ("🙂 Friendly" if friendly else "👤 Known")

        print(f"{badge}: @{row['handle']}")
        if row["display_name"]:
            print(f"Display name: {row['display_name']}")
        print(f"DID: {row['did']}")
        if row["first_seen"]:
            print(f"First seen: {row['first_seen']}")
        if st["last"]:
            print(f"Last activity: {st['last']}")
        print(f"Total interactions: {st['total']} (threads={st['n_interactions']}, dms={st['n_dms']})")

        if tags:
            print(f"Tags: {', '.join(tags)}")

        if row["notes_manual"]:
            print(f"Notes (manual): {row['notes_manual']}")

        if row["notes_auto"]:
            print(f"Notes (auto): {row['notes_auto']}")
        if row["interests_auto"]:
            print(f"Interests (auto): {row['interests_auto']}")
        if row["relationship_tone"]:
            print(f"Tone (auto): {row['relationship_tone']}")

        # Optional: enrich auto notes (opt-in)
        if getattr(args, "enrich", False):
            execute = bool(getattr(args, "execute", False))
            force = bool(getattr(args, "force", False))
            mah = getattr(args, "min_age_hours", 72)
            min_age_hours = 72 if mah is None else int(mah)

            skip, last = _should_skip_enrich(conn, did=did, min_age_hours=min_age_hours, force=force)
            if skip:
                print(f"\n(enrich skipped: last auto update {last}; use --force to override)")
                return 0

            recent_dms = [
                dict(r)
                for r in conn.execute(
                    "SELECT sent_at, direction, text FROM dm_messages WHERE actor_did=? ORDER BY sent_at DESC LIMIT 10",
                    (did,),
                ).fetchall()
            ]
            recent_inter = [
                dict(r)
                for r in conn.execute(
                    "SELECT date, type, our_text, their_text FROM interactions WHERE actor_did=? ORDER BY date DESC, id DESC LIMIT 10",
                    (did,),
                ).fetchall()
            ]

            data = _llm_enrich_person(
                handle=str(row["handle"] or ""),
                display_name=str(row["display_name"] or ""),
                tags=[str(t) for t in tags],
                notes_manual=str(row["notes_manual"] or ""),
                recent_dms=recent_dms,
                recent_interactions=recent_inter,
            )

            notes_auto = str(data.get("notes_auto") or "").strip()
            interests_auto = str(data.get("interests_auto") or "").strip()
            tone_auto = str(data.get("relationship_tone") or "").strip()

            print("\n🤖 Enrich preview:")
            if notes_auto:
                print(f"  notes_auto: {notes_auto}")
            if interests_auto:
                print(f"  interests_auto: {interests_auto}")
            if tone_auto:
                print(f"  relationship_tone: {tone_auto}")

            if execute:
                if notes_auto:
                    _save_auto_snapshot(conn, did=did, kind="notes", content=notes_auto)
                if interests_auto:
                    _save_auto_snapshot(conn, did=did, kind="interests", content=interests_auto)
                if tone_auto:
                    _save_auto_snapshot(conn, did=did, kind="tone", content=tone_auto)
                print("  ✓ Saved to DB")
            else:
                print("  (dry-run) re-run with --execute to save")

            return 0

        print("\n📜 Recent interactions:")
        for r in conn.execute(
            "SELECT date, type, our_text, their_text FROM interactions WHERE actor_did=? ORDER BY date DESC, id DESC LIMIT 5",
            (did,),
        ).fetchall():
            print(f"  [{r['date']}] {r['type']}")
            if r["their_text"]:
                t = str(r["their_text"])[:80]
                print(f"    They: \"{t}{'...' if len(str(r['their_text'])) > 80 else ''}\"")
            if r["our_text"]:
                t = str(r["our_text"])[:80]
                print(f"    Us:   \"{t}{'...' if len(str(r['our_text'])) > 80 else ''}\"")

        return 0

    # --- List mode
    limit = int(getattr(args, "limit", 20) or 20)

    # Fetch active actors + computed counts.
    rows = conn.execute(
        "SELECT did, handle, display_name FROM actors WHERE did IN (SELECT actor_did FROM interactions UNION SELECT actor_did FROM dm_messages)"
    ).fetchall()

    people = []
    for r in rows:
        st = _actor_stats(conn, str(r["did"]))
        if st["total"] <= 0:
            continue
        tags = [t["tag"] for t in conn.execute("SELECT tag FROM actor_tags WHERE did=? ORDER BY tag", (r["did"],)).fetchall()]
        people.append(
            {
                "did": r["did"],
                "handle": r["handle"],
                "display_name": r["display_name"],
                "total": st["total"],
                "last": st["last"],
                "tags": tags,
            }
        )

    people.sort(key=lambda x: x.get("last") or "", reverse=True)

    if getattr(args, "regulars", False):
        thresh = get_regular_threshold()
        people = [p for p in people if int(p["total"]) >= thresh]
        title = f"🔄 Regular Interlocutors ({thresh}+ interactions)"
    else:
        title = "👥 All Known Interlocutors"

    if not people:
        print("No interlocutors tracked yet.")
        return 0

    people = people[:limit]

    print(f"{title} ({len(people)} shown)\n")
    for p in people:
        badge = "🔄" if int(p["total"]) >= get_regular_threshold() else "  "
        tags_str = f" [{', '.join(p['tags'])}]" if p["tags"] else ""
        last = p.get("last") or ""
        print(f"{badge} @{p['handle']}: {p['total']} interactions (last: {last}){tags_str}")

    return 0


def main():
    parser = argparse.ArgumentParser(description="View interaction history")
    parser.add_argument("handle", nargs="?", help="Handle/DID to look up")
    parser.add_argument("--regulars", action="store_true", help="Show regulars only")
    parser.add_argument("--stats", action="store_true", help="Show statistics")
    parser.add_argument("--limit", type=int, default=20, help="Max users to show")
    parser.add_argument("--set-note", dest="set_note", help="Set a manual note for this person")
    parser.add_argument("--add-tag", dest="add_tag", action="append", help="Add a tag (repeatable)")
    parser.add_argument("--remove-tag", dest="remove_tag", action="append", help="Remove a tag (repeatable)")

    # Auto-enrich (opt-in)
    parser.add_argument("--enrich", action="store_true", help="Generate/update auto notes (dry-run by default)")
    parser.add_argument("--execute", action="store_true", help="Persist enrich output to DB")
    parser.add_argument("--force", action="store_true", help="Ignore enrich cooldown")
    parser.add_argument("--min-age-hours", type=int, default=72, help="Min hours between enrich runs (default: 72)")
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
