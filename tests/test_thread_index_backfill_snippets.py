from __future__ import annotations

import sqlite3

from bsky_cli.storage import db as dbmod


def test_thread_actor_state_backfills_missing_snippets_from_older_rows():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    dbmod.ensure_schema(conn)

    conn.execute("INSERT INTO actors(did, handle) VALUES (?,?)", ("did:plc:target", "target.example"))

    root_uri = "at://did:plc:root/app.bsky.feed.post/root"

    # Newest interaction has missing our_text
    dbmod.upsert_thread_actor_state(
        conn,
        root_uri=root_uri,
        actor_did="did:plc:target",
        last_interaction_at="2026-02-10T10:00:00Z",
        last_post_uri="at://did:plc:target/app.bsky.feed.post/new",
        last_us="",
        last_them="new them",
    )

    # Older interaction has our_text, but should only backfill missing fields
    dbmod.upsert_thread_actor_state(
        conn,
        root_uri=root_uri,
        actor_did="did:plc:target",
        last_interaction_at="2026-02-09T10:00:00Z",
        last_post_uri="at://did:plc:target/app.bsky.feed.post/old",
        last_us="old us",
        last_them="",
    )

    row = conn.execute(
        "SELECT last_interaction_at, last_post_uri, last_us, last_them FROM thread_actor_state WHERE root_uri=? AND actor_did=?",
        (root_uri, "did:plc:target"),
    ).fetchone()

    assert row["last_interaction_at"] == "2026-02-10T10:00:00Z"
    # keep newest post uri
    assert row["last_post_uri"].endswith("/new")
    # backfilled from older
    assert row["last_us"] == "old us"
    # kept newest them
    assert row["last_them"] == "new them"
