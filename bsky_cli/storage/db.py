from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Iterable


def _slug_account(account: str) -> str:
    account = (account or "").strip().lstrip("@").lower()
    if not account:
        return "unknown"
    # Keep it filesystem-safe
    return re.sub(r"[^a-z0-9._-]+", "_", account)


def db_path_for_account(account_handle: str) -> Path:
    base = Path.home() / ".bsky-cli" / "accounts" / _slug_account(account_handle)
    return base / "bsky.db"


def open_db(account_handle: str) -> sqlite3.Connection:
    path = db_path_for_account(account_handle)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row

    # Pragmas: safe defaults for a local bot store
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


MIGRATIONS: list[str] = [
    # 1
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
      version INTEGER PRIMARY KEY,
      applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    );

    CREATE TABLE IF NOT EXISTS accounts (
      account_handle TEXT PRIMARY KEY,
      account_did TEXT,
      created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    );

    CREATE TABLE IF NOT EXISTS actors (
      did TEXT PRIMARY KEY,
      handle TEXT,
      display_name TEXT,
      first_seen TEXT,
      last_interaction TEXT,
      total_count INTEGER NOT NULL DEFAULT 0,
      notes_manual TEXT NOT NULL DEFAULT '',
      notes_auto TEXT NOT NULL DEFAULT '',
      interests_auto TEXT NOT NULL DEFAULT '',
      relationship_tone TEXT NOT NULL DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS actor_tags (
      did TEXT NOT NULL,
      tag TEXT NOT NULL,
      PRIMARY KEY (did, tag),
      FOREIGN KEY (did) REFERENCES actors(did) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS interactions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      actor_did TEXT NOT NULL,
      date TEXT NOT NULL,
      type TEXT NOT NULL,
      post_uri TEXT,
      our_text TEXT,
      their_text TEXT,
      FOREIGN KEY (actor_did) REFERENCES actors(did) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_interactions_actor_date ON interactions(actor_did, date);
    """,

    # 2 — DMs
    """
    CREATE TABLE IF NOT EXISTS dm_conversations (
      convo_id TEXT PRIMARY KEY,
      last_message_at TEXT
    );

    CREATE TABLE IF NOT EXISTS dm_convo_members (
      convo_id TEXT NOT NULL,
      did TEXT NOT NULL,
      PRIMARY KEY (convo_id, did)
    );

    CREATE TABLE IF NOT EXISTS dm_messages (
      convo_id TEXT NOT NULL,
      msg_id TEXT NOT NULL,
      actor_did TEXT NOT NULL,
      direction TEXT NOT NULL CHECK(direction IN ('in','out')),
      sent_at TEXT NOT NULL,
      text TEXT NOT NULL,
      facets_json TEXT,
      raw_json TEXT,
      PRIMARY KEY (convo_id, msg_id),
      FOREIGN KEY (actor_did) REFERENCES actors(did) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_dm_messages_actor_time ON dm_messages(actor_did, sent_at);
    CREATE INDEX IF NOT EXISTS idx_dm_messages_convo_time ON dm_messages(convo_id, sent_at);
    CREATE INDEX IF NOT EXISTS idx_dm_members_did ON dm_convo_members(did);
    """,
]


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))")
    cur = conn.execute("SELECT COALESCE(MAX(version), 0) AS v FROM schema_migrations")
    current = int(cur.fetchone()["v"])

    for idx, sql in enumerate(MIGRATIONS, start=1):
        if idx <= current:
            continue
        with conn:
            conn.executescript(sql)
            conn.execute("INSERT INTO schema_migrations(version) VALUES (?)", (idx,))


# -----------------------------------------------------------------------------
# DMs (ingestion)
# -----------------------------------------------------------------------------


def ingest_new_dms(conn: sqlite3.Connection, new_dms: list[dict], *, my_did: str) -> int:
    """Insert DM messages into the DB (idempotent).

    Expects items like those returned by bsky_cli.dm.check_new_dms().
    Returns number of new messages inserted.
    """

    inserted = 0

    def upsert_actor_from_member(m: dict) -> None:
        did = m.get("did")
        if not did:
            return
        handle = m.get("handle")
        display = m.get("displayName") or m.get("display_name")
        conn.execute(
            "INSERT INTO actors(did, handle, display_name) VALUES (?,?,?) "
            "ON CONFLICT(did) DO UPDATE SET handle=COALESCE(excluded.handle, handle), display_name=COALESCE(excluded.display_name, display_name)",
            (did, handle, display),
        )

    for dm in new_dms or []:
        convo_id = dm.get("convo_id")
        msg_id = dm.get("message_id") or dm.get("msg_id") or ""
        sender = dm.get("sender") or {}
        sender_did = sender.get("did") or ""
        sent_at = dm.get("sent_at") or dm.get("sentAt") or ""
        text = dm.get("text") or ""

        if not convo_id or not msg_id or not sender_did or not sent_at:
            continue

        # Keep actor directory fresh + members mapping
        for m in dm.get("members", []) or []:
            upsert_actor_from_member(m)

        direction = "out" if sender_did == my_did else "in"

        facets_json = None
        if dm.get("facets") is not None:
            try:
                facets_json = json.dumps(dm.get("facets"), ensure_ascii=False)
            except Exception:
                facets_json = None

        raw_json = None
        try:
            raw_json = json.dumps(dm, ensure_ascii=False)
        except Exception:
            raw_json = None

        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO dm_conversations(convo_id, last_message_at) VALUES (?,?)",
                (convo_id, sent_at),
            )
            conn.execute(
                "UPDATE dm_conversations SET last_message_at=MAX(COALESCE(last_message_at,''), ?) WHERE convo_id=?",
                (sent_at, convo_id),
            )

            for m in dm.get("members", []) or []:
                did = m.get("did")
                if did:
                    conn.execute(
                        "INSERT OR IGNORE INTO dm_convo_members(convo_id, did) VALUES (?,?)",
                        (convo_id, did),
                    )

            cur = conn.execute(
                "INSERT OR IGNORE INTO dm_messages(convo_id, msg_id, actor_did, direction, sent_at, text, facets_json, raw_json) VALUES (?,?,?,?,?,?,?,?)",
                (convo_id, msg_id, sender_did, direction, sent_at, text, facets_json, raw_json),
            )
            inserted += cur.rowcount

    return inserted


# -----------------------------------------------------------------------------
# Import (anti-regression)
# -----------------------------------------------------------------------------

INTERLOCUTORS_JSON = Path.home() / ".bsky-cli" / "interlocutors.json"


def _iter_interlocutors(path: Path | None = None) -> Iterable[dict]:
    # NOTE: keep default lazy so tests (and callers) can monkeypatch INTERLOCUTORS_JSON
    # without fighting with default-arg evaluation time.
    path = path or INTERLOCUTORS_JSON
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    # Stored as dict keyed by did
    return data.values() if isinstance(data, dict) else data


def import_interlocutors_json(conn: sqlite3.Connection, *, overwrite: bool = False) -> int:
    """Import existing interlocutors.json into SQLite.

    This is meant to avoid regressions during the migration period.
    Returns number of actors imported/updated.
    """

    count = 0

    for inter in _iter_interlocutors():
        did = inter.get("did")
        if not did:
            continue
        handle = inter.get("handle")
        display_name = inter.get("display_name") or inter.get("display_name") or inter.get("displayName") or inter.get("display_name", "")
        first_seen = inter.get("first_seen") or ""
        last_interaction = inter.get("last_interaction") or ""
        total_count = int(inter.get("total_count") or 0)
        notes = inter.get("notes") or ""
        tags = inter.get("tags") or []
        interactions = inter.get("interactions") or []

        # Upsert actor
        existing = conn.execute("SELECT did FROM actors WHERE did=?", (did,)).fetchone()
        if existing and not overwrite:
            # keep manual notes/tags as-is; update basic fields + counts, and append interactions if new
            conn.execute(
                "UPDATE actors SET handle=COALESCE(NULLIF(?,''), handle), display_name=COALESCE(NULLIF(?,''), display_name), first_seen=COALESCE(NULLIF(?,''), first_seen), last_interaction=COALESCE(NULLIF(?,''), last_interaction), total_count=MAX(total_count, ?) WHERE did=?",
                (handle or "", display_name or "", first_seen, last_interaction, total_count, did),
            )
        else:
            conn.execute(
                "INSERT INTO actors(did, handle, display_name, first_seen, last_interaction, total_count, notes_manual) VALUES (?,?,?,?,?,?,?) ON CONFLICT(did) DO UPDATE SET handle=excluded.handle, display_name=excluded.display_name, first_seen=excluded.first_seen, last_interaction=excluded.last_interaction, total_count=excluded.total_count",
                (did, handle, display_name, first_seen, last_interaction, total_count, notes),
            )

        # Tags (best-effort, de-dupe)
        for t in tags:
            if not t:
                continue
            conn.execute("INSERT OR IGNORE INTO actor_tags(did, tag) VALUES (?,?)", (did, str(t)))

        # Interactions (append-only; we keep it simple and allow duplicates during migration)
        for i in interactions:
            date = i.get("date") or ""
            itype = i.get("type") or ""
            if not date or not itype:
                continue
            conn.execute(
                "INSERT INTO interactions(actor_did, date, type, post_uri, our_text, their_text) VALUES (?,?,?,?,?,?)",
                (
                    did,
                    date,
                    itype,
                    i.get("post_uri"),
                    i.get("our_text"),
                    i.get("their_text"),
                ),
            )

        count += 1

    conn.commit()
    return count
