from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace


def test_search_history_all_returns_dm_and_interactions(monkeypatch, capsys):
    from bsky_cli import search_history_cmd

    # Patch session
    monkeypatch.setattr(
        search_history_cmd,
        "get_session",
        lambda: ("https://pds.invalid", "did:me", "jwt", "echo.0mg.cc"),
    )

    # Patch DID resolution
    monkeypatch.setattr(search_history_cmd, "resolve_handle", lambda pds, h: "did:plc:target")

    # In-memory DB
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    monkeypatch.setattr(search_history_cmd, "open_db", lambda account_handle: conn)

    search_history_cmd.ensure_schema(conn)

    # Seed DM convo where target is a member
    conn.execute("INSERT OR IGNORE INTO dm_conversations(convo_id, last_message_at) VALUES (?,?)", ("c1", "2026-02-10T00:00:02Z"))
    conn.execute("INSERT OR IGNORE INTO dm_convo_members(convo_id, did) VALUES (?,?)", ("c1", "did:plc:target"))
    conn.execute("INSERT OR IGNORE INTO dm_convo_members(convo_id, did) VALUES (?,?)", ("c1", "did:me"))
    conn.execute(
        "INSERT OR IGNORE INTO dm_messages(convo_id, msg_id, actor_did, direction, sent_at, text) VALUES (?,?,?,?,?,?)",
        ("c1", "m1", "did:plc:target", "in", "2026-02-10T00:00:02Z", "hello from dm"),
    )

    # Seed an interaction
    conn.execute(
        "INSERT INTO interactions(actor_did, date, type, post_uri, our_text, their_text) VALUES (?,?,?,?,?,?)",
        (
            "did:plc:target",
            "2026-02-09",
            "reply_to_them",
            "at://did:plc:target/app.bsky.feed.post/abc",
            "we said hello",
            "they said hi",
        ),
    )

    conn.commit()

    args = SimpleNamespace(
        handle="target.example",
        query="hello",
        scope="all",
        since=None,
        until=None,
        limit=10,
        json=True,
    )

    rc = search_history_cmd.run(args)
    assert rc == 0

    out = capsys.readouterr().out.strip()
    data = json.loads(out)

    kinds = {r["kind"] for r in data["results"]}
    assert "dm" in kinds
    assert "interaction" in kinds

    texts = "\n".join(r["text"] for r in data["results"])
    assert "hello from dm" in texts
    assert "we said hello" in texts


def test_search_history_scope_dm_filters_only_dm(monkeypatch, capsys):
    from bsky_cli import search_history_cmd

    monkeypatch.setattr(
        search_history_cmd,
        "get_session",
        lambda: ("https://pds.invalid", "did:me", "jwt", "echo.0mg.cc"),
    )
    monkeypatch.setattr(search_history_cmd, "resolve_handle", lambda pds, h: "did:plc:target")

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    monkeypatch.setattr(search_history_cmd, "open_db", lambda account_handle: conn)

    search_history_cmd.ensure_schema(conn)

    conn.execute("INSERT OR IGNORE INTO dm_conversations(convo_id, last_message_at) VALUES (?,?)", ("c1", "2026-02-10T00:00:02Z"))
    conn.execute("INSERT OR IGNORE INTO dm_convo_members(convo_id, did) VALUES (?,?)", ("c1", "did:plc:target"))
    conn.execute("INSERT OR IGNORE INTO dm_convo_members(convo_id, did) VALUES (?,?)", ("c1", "did:me"))
    conn.execute(
        "INSERT OR IGNORE INTO dm_messages(convo_id, msg_id, actor_did, direction, sent_at, text) VALUES (?,?,?,?,?,?)",
        ("c1", "m1", "did:plc:target", "in", "2026-02-10T00:00:02Z", "hello from dm"),
    )
    conn.execute(
        "INSERT INTO interactions(actor_did, date, type, post_uri, our_text, their_text) VALUES (?,?,?,?,?,?)",
        (
            "did:plc:target",
            "2026-02-09",
            "reply_to_them",
            "at://did:plc:target/app.bsky.feed.post/abc",
            "we said hello",
            "they said hi",
        ),
    )
    conn.commit()

    args = SimpleNamespace(
        handle="target.example",
        query="hello",
        scope="dm",
        since=None,
        until=None,
        limit=10,
        json=True,
    )

    rc = search_history_cmd.run(args)
    assert rc == 0

    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert data["results"]
    assert all(r["kind"] == "dm" for r in data["results"])
