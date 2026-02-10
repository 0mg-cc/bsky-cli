from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from bsky_cli import context_cmd


def test_context_cmd_does_not_persist_post_uri_as_root_when_root_lookup_fails(monkeypatch):
    # Session
    monkeypatch.setattr(
        context_cmd,
        "get_session",
        lambda: ("https://pds.invalid", "did:me", "jwt", "echo.0mg.cc"),
    )

    monkeypatch.setattr(context_cmd, "resolve_handle", lambda pds, h: "did:plc:target")

    # In-memory DB
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    monkeypatch.setattr(context_cmd, "open_db", lambda account_handle: conn)
    monkeypatch.setattr(context_cmd, "import_interlocutors_json", lambda conn: 0)

    context_cmd.ensure_schema(conn)

    conn.execute("INSERT INTO actors(did, handle) VALUES (?,?)", ("did:plc:target", "target.example"))
    # One interaction with a post uri
    post_uri = "at://did:plc:target/app.bsky.feed.post/abc"
    conn.execute(
        "INSERT INTO interactions(actor_did, date, type, post_uri, our_text, their_text) VALUES (?,?,?,?,?,?)",
        ("did:plc:target", "2026-02-10", "reply_to_them", post_uri, "us", "them"),
    )
    conn.commit()

    # Make root lookup fail
    def _fail(*a, **k):
        raise RuntimeError("network")

    monkeypatch.setattr(context_cmd, "_get_root_uri_for_post_uri", _fail)

    # Avoid other network
    monkeypatch.setattr(context_cmd, "_fetch_dm_context", lambda *a, **k: [])
    monkeypatch.setattr(context_cmd, "_get_post_text", lambda *a, **k: "")

    args = SimpleNamespace(handle="target.example", dm=0, threads=1, json=True)

    rc = context_cmd.run(args)
    assert rc == 0

    # Should not have inserted a bogus root==post_uri
    n = conn.execute("SELECT COUNT(1) AS n FROM thread_actor_state WHERE root_uri=?", (post_uri,)).fetchone()["n"]
    assert int(n) == 0
