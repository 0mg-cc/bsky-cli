from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from bsky_cli import context_cmd


def test_format_context_pack_includes_hot_and_cold_sections():
    txt = context_cmd._format_context_pack(
        {
            "hot": {"dms": [{"senderHandle": "alice.example", "text": "hello"}]},
            "cold": {
                "actor": {
                    "did": "did:plc:abc",
                    "handle": "alice.example",
                    "first_seen": "2026-02-01",
                    "last_interaction": "2026-02-02",
                    "total_count": 3,
                    "notes_manual": "met at conf",
                    "notes_auto": "",
                    "tags": ["friendly"],
                },
                "threads": [],
            },
        }
    )

    assert "[HOT CONTEXT" in txt
    assert "[COLD CONTEXT" in txt
    assert "@alice.example: hello" in txt
    assert "Actor: @alice.example" in txt
    assert "Tags: friendly" in txt


def test_context_run_smoke(monkeypatch, capsys):
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

    # Avoid importing from real legacy JSON
    monkeypatch.setattr(context_cmd, "import_interlocutors_json", lambda conn: 0)

    # Seed actor + one interaction with post_uri
    context_cmd.ensure_schema(conn)
    conn.execute(
        "INSERT INTO actors(did, handle, first_seen, last_interaction, total_count, notes_manual) VALUES (?,?,?,?,?,?)",
        ("did:plc:target", "target.example", "2026-02-01", "2026-02-02", 1, ""),
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

    # Patch DM fetch to avoid network
    monkeypatch.setattr(
        context_cmd,
        "_fetch_dm_context",
        lambda pds, jwt, account_handle, handle, limit: [
            {
                "sentAt": "2026-02-10T00:00:00Z",
                "senderDid": "did:plc:target",
                "senderHandle": "target.example",
                "text": "hello from dm",
            }
        ],
    )

    # Patch thread root + post text
    monkeypatch.setattr(context_cmd, "_get_root_uri_for_post_uri", lambda pds, jwt, uri: "at://did:plc:target/app.bsky.feed.post/root")
    monkeypatch.setattr(context_cmd, "_get_post_text", lambda pds, jwt, uri: "root post text")

    args = SimpleNamespace(handle="target.example", dm=1, threads=1, json=False)

    rc = context_cmd.run(args)
    assert rc == 0

    out = capsys.readouterr().out
    assert "[HOT CONTEXT" in out
    assert "hello from dm" in out
    assert "root post text" in out


def test_context_run_with_focus_includes_path_and_branches(monkeypatch, capsys):
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

    monkeypatch.setattr(context_cmd, "_fetch_dm_context", lambda *a, **k: [])

    focus_uri = "at://did:plc:target/app.bsky.feed.post/abc"
    root_uri = "at://did:plc:root/app.bsky.feed.post/root"

    # Patch focus resolve + thread fetch
    monkeypatch.setattr(context_cmd, "_resolve_focus_uri", lambda pds, jwt, focus: focus_uri)
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

    # Avoid legacy per-interaction root lookups
    monkeypatch.setattr(context_cmd, "_get_root_uri_for_post_uri", lambda pds, jwt, uri: root_uri)
    monkeypatch.setattr(context_cmd, "_get_post_text", lambda pds, jwt, uri: "root text")

    args = SimpleNamespace(handle="target.example", dm=0, threads=1, json=False, focus=focus_uri)

    rc = context_cmd.run(args)
    assert rc == 0

    out = capsys.readouterr().out
    assert "focus:" in out
    assert "path:" in out
    assert "branches:" in out
    assert "reply one" in out
