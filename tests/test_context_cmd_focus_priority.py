from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from bsky_cli import context_cmd


def test_explicit_focus_is_emitted_even_if_not_in_top_threads(monkeypatch, capsys):
    monkeypatch.setattr(
        context_cmd,
        "get_session",
        lambda: ("https://pds.invalid", "did:me", "jwt", "echo.0mg.cc"),
    )
    monkeypatch.setattr(context_cmd, "resolve_handle", lambda pds, h: "did:plc:target")

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    monkeypatch.setattr(context_cmd, "open_db", lambda account_handle: conn)
    monkeypatch.setattr(context_cmd, "import_interlocutors_json", lambda conn: 0)

    context_cmd.ensure_schema(conn)
    conn.execute("INSERT INTO actors(did, handle) VALUES (?,?)", ("did:plc:target", "target.example"))

    # Seed an indexed thread that is NOT the focus thread
    other_root = "at://did:plc:o/app.bsky.feed.post/otherroot"
    conn.execute("INSERT OR IGNORE INTO threads(root_uri, last_seen_at) VALUES (?,?)", (other_root, "2026-02-10T10:00:00Z"))
    conn.execute(
        "INSERT OR REPLACE INTO thread_actor_state(root_uri, actor_did, last_interaction_at, last_post_uri, last_us, last_them) VALUES (?,?,?,?,?,?)",
        (other_root, "did:plc:target", "2026-02-10T10:00:00Z", "at://did:plc:o/app.bsky.feed.post/x", "us other", "them other"),
    )
    conn.commit()

    focus_uri = "at://did:plc:target/app.bsky.feed.post/focus"
    focus_root = "at://did:plc:root/app.bsky.feed.post/root"

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
                    "uri": focus_root,
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

    monkeypatch.setattr(context_cmd, "_fetch_dm_context", lambda *a, **k: [])
    monkeypatch.setattr(context_cmd, "_get_post_text", lambda pds, jwt, uri: "root text")

    # threads_limit=1 would normally drop focus root if we only enriched indexed rows
    args = SimpleNamespace(handle="target.example", dm=0, threads=1, json=False, focus=focus_uri)
    rc = context_cmd.run(args)
    assert rc == 0

    out = capsys.readouterr().out
    assert "focus:" in out
    assert "path:" in out
    assert "branches:" in out
