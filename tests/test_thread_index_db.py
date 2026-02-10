from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from bsky_cli import context_cmd
from bsky_cli.storage import db as dbmod


def test_schema_includes_thread_index_tables():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    dbmod.ensure_schema(conn)

    tables = {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }

    assert "threads" in tables
    assert "thread_actor_state" in tables


def test_context_without_focus_uses_recent_thread_position(monkeypatch, capsys):
    # Patch session
    monkeypatch.setattr(
        context_cmd,
        "get_session",
        lambda: ("https://pds.invalid", "did:me", "jwt", "echo.0mg.cc"),
    )

    # Patch DID resolution
    monkeypatch.setattr(context_cmd, "resolve_handle", lambda pds, h: "did:plc:target")

    # In-memory DB
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    monkeypatch.setattr(context_cmd, "open_db", lambda account_handle: conn)
    monkeypatch.setattr(context_cmd, "import_interlocutors_json", lambda conn: 0)

    context_cmd.ensure_schema(conn)

    # Seed actor + interactions with post_uri
    conn.execute(
        "INSERT INTO actors(did, handle) VALUES (?,?)",
        ("did:plc:target", "target.example"),
    )
    conn.execute(
        "INSERT INTO interactions(actor_did, date, type, post_uri, our_text, their_text) VALUES (?,?,?,?,?,?)",
        (
            "did:plc:target",
            "2026-02-02",
            "reply_to_them",
            "at://did:plc:target/app.bsky.feed.post/abc",
            "our msg",
            "their msg",
        ),
    )
    conn.commit()

    root_uri = "at://did:plc:root/app.bsky.feed.post/root"
    focus_uri = "at://did:plc:target/app.bsky.feed.post/abc"

    # Root lookup (so thread grouping works deterministically)
    monkeypatch.setattr(context_cmd, "_get_root_uri_for_post_uri", lambda pds, jwt, uri: root_uri)

    # Avoid live DMs
    monkeypatch.setattr(context_cmd, "_fetch_dm_context", lambda *a, **k: [])

    # Thread fetch for focus-aware excerpt (fallback position)
    monkeypatch.setattr(
        context_cmd,
        "_get_post_thread",
        lambda pds, jwt, uri, depth=10: {
            "post": {
                "uri": focus_uri,
                "author": {"handle": "target.example"},
                "record": {"text": "focus text"},
            },
            "parent": {
                "post": {
                    "uri": root_uri,
                    "author": {"handle": "root.author"},
                    "record": {"text": "root text"},
                },
                "parent": None,
                "replies": [],
            },
            "replies": [
                {
                    "post": {
                        "uri": "at://did:plc:x/app.bsky.feed.post/r1",
                        "author": {"handle": "alice.example"},
                        "record": {"text": "reply one"},
                    },
                    "parent": None,
                    "replies": [],
                }
            ],
        },
    )

    # Root text
    monkeypatch.setattr(context_cmd, "_get_post_text", lambda pds, jwt, uri: "root text")

    args = SimpleNamespace(handle="target.example", dm=0, threads=1, json=False, focus=None)
    rc = context_cmd.run(args)
    assert rc == 0

    out = capsys.readouterr().out
    assert "focus:" in out
    assert "path:" in out
    assert "branches:" in out
