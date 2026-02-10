from __future__ import annotations

import sqlite3

from bsky_cli.storage import db as dbmod


def test_schema_includes_dm_tables_after_migrations():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    dbmod.ensure_schema(conn)

    tables = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    assert "dm_conversations" in tables
    assert "dm_convo_members" in tables
    assert "dm_messages" in tables


def test_ingest_new_dms_inserts_messages_and_members():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    dbmod.ensure_schema(conn)

    new_dms = [
        {
            "convo_id": "c1",
            "members": [
                {"did": "did:plc:them", "handle": "penny.hailey.at", "displayName": "Penny"},
                {"did": "did:plc:me", "handle": "echo.0mg.cc", "displayName": "Echo"},
            ],
            "message_id": "m1",
            "sender": {"did": "did:plc:them"},
            "text": "hi https://example.com",
            "facets": [
                {
                    "index": {"byteStart": 3, "byteEnd": 22},
                    "features": [
                        {"$type": "app.bsky.richtext.facet#link", "uri": "https://example.com"}
                    ],
                }
            ],
            "sent_at": "2026-02-10T00:00:03.000Z",
        }
    ]

    n = dbmod.ingest_new_dms(conn, new_dms, my_did="did:plc:me")
    assert n == 1

    # actors seeded from members
    actor = conn.execute("SELECT did, handle FROM actors WHERE did='did:plc:them'").fetchone()
    assert actor["handle"] == "penny.hailey.at"

    # membership mapping
    mem = conn.execute("SELECT did FROM dm_convo_members WHERE convo_id='c1' ORDER BY did").fetchall()
    assert [m["did"] for m in mem] == ["did:plc:me", "did:plc:them"]

    # message inserted
    msg = conn.execute("SELECT convo_id, msg_id, actor_did, direction, text, facets_json FROM dm_messages").fetchone()
    assert msg["convo_id"] == "c1"
    assert msg["msg_id"] == "m1"
    assert msg["direction"] == "in"
    assert "example.com" in (msg["facets_json"] or "")
