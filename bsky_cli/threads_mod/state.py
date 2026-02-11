from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ..auth import load_from_pass
from ..storage.db import ensure_schema, open_db
from .config import THREADS_STATE_FILE


def _now_suffix() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _open_default_db() -> sqlite3.Connection:
    """Open per-account SQLite without requiring a network session."""
    env = load_from_pass() or {}
    account_handle = (env.get("BSKY_HANDLE") or env.get("BSKY_EMAIL") or "").strip() or "default"

    # Prefer the standard per-account path
    try:
        conn = open_db(account_handle)
        ensure_schema(conn)
        return conn
    except Exception:
        pass

    # Fallback: if exactly one DB exists, use it.
    base = Path.home() / ".bsky-cli" / "accounts"
    dbs = sorted(base.glob("*/bsky.db"))
    if len(dbs) == 1:
        conn = sqlite3.connect(dbs[0])
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=5000;")
        ensure_schema(conn)
        return conn

    if len(dbs) > 1:
        raise SystemExit(
            "Multiple BlueSky accounts found in ~/.bsky-cli/accounts; configure BSKY_HANDLE in pass to select one"
        )

    # No DB on disk; create default
    conn = open_db(account_handle)
    ensure_schema(conn)
    return conn


def load_threads_state() -> dict:
    """Load threads_mod state from SQLite.

    Legacy JSON is only handled via the explicit migration helper.
    """
    conn = _open_default_db()

    threads: dict[str, dict] = {}
    for r in conn.execute("SELECT root_uri, thread_json FROM threads_mod_threads").fetchall():
        try:
            threads[str(r["root_uri"])] = json.loads(str(r["thread_json"]))
        except Exception:
            continue

    evaluated = [
        str(r["notif_uri"])
        for r in conn.execute(
            "SELECT notif_uri FROM threads_mod_evaluated_notifications ORDER BY rowid"
        ).fetchall()
    ]

    row = conn.execute(
        "SELECT value FROM threads_mod_meta WHERE key='last_evaluation'"
    ).fetchone()
    last_eval = str(row["value"]) if row and row["value"] is not None else None

    return {
        "threads": threads,
        "evaluated_notifications": evaluated,
        "last_evaluation": last_eval,
    }


def save_threads_state(state: dict):
    """Persist threads_mod state to SQLite."""
    conn = _open_default_db()

    threads = state.get("threads", {}) or {}
    evaluated = (state.get("evaluated_notifications", []) or [])[-500:]
    last_eval = state.get("last_evaluation")

    with conn:
        # Meta
        if last_eval:
            conn.execute(
                "INSERT INTO threads_mod_meta(key, value) VALUES ('last_evaluation', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(last_eval),),
            )
        else:
            conn.execute("DELETE FROM threads_mod_meta WHERE key='last_evaluation'")

        # Threads upsert
        for uri, t_data in threads.items():
            conn.execute(
                "INSERT INTO threads_mod_threads(root_uri, thread_json, updated_at) VALUES (?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now')) "
                "ON CONFLICT(root_uri) DO UPDATE SET thread_json=excluded.thread_json, updated_at=excluded.updated_at",
                (str(uri), json.dumps(t_data)),
            )

        # Remove deleted threads
        if threads:
            placeholders = ",".join(["?"] * len(threads))
            conn.execute(
                f"DELETE FROM threads_mod_threads WHERE root_uri NOT IN ({placeholders})",
                tuple(map(str, threads.keys())),
            )
        else:
            conn.execute("DELETE FROM threads_mod_threads")

        # Evaluated notifications: store exact pruned list (preserve order via rowid)
        conn.execute("DELETE FROM threads_mod_evaluated_notifications")
        for u in evaluated:
            conn.execute(
                "INSERT INTO threads_mod_evaluated_notifications(notif_uri) VALUES (?)",
                (str(u),),
            )


def migrate_threads_state_from_json(
    path: Path | None = None,
    *,
    archive_json: bool = False,
    dry_run: bool = False,
) -> dict:
    """One-shot migration from legacy JSON into SQLite.

    Returns a small summary dict.
    """

    src = Path(path) if path is not None else THREADS_STATE_FILE
    if not src.exists():
        return {"migrated": False, "reason": "missing", "path": str(src)}

    legacy = json.loads(src.read_text())

    state = {
        "threads": legacy.get("threads", {}) or {},
        "evaluated_notifications": legacy.get("evaluated_notifications", []) or [],
        "last_evaluation": legacy.get("last_evaluation"),
    }

    if dry_run:
        return {
            "migrated": False,
            "dry_run": True,
            "threads": len(state["threads"]),
            "evaluated": len(state["evaluated_notifications"]),
            "path": str(src),
        }

    save_threads_state(state)

    archived_to = None
    if archive_json:
        dst = src.with_name(src.name + f".bak.{_now_suffix()}")
        src.rename(dst)
        archived_to = str(dst)

    return {
        "migrated": True,
        "threads": len(state["threads"]),
        "evaluated": len(state["evaluated_notifications"]),
        "archived_to": archived_to,
    }
