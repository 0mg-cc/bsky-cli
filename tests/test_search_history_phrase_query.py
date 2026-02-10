from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace


def test_search_history_preserves_quoted_phrase(monkeypatch, capsys):
    """Regression: escaping should not break phrase queries like \"foo bar\"."""

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
        ("c1", "m1", "did:plc:target", "in", "2026-02-10T00:00:02Z", "this contains foo bar as a phrase"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO dm_messages(convo_id, msg_id, actor_did, direction, sent_at, text) VALUES (?,?,?,?,?,?)",
        ("c1", "m2", "did:plc:target", "in", "2026-02-10T00:00:03Z", "this contains foo baz bar (not a phrase)"),
    )
    conn.commit()

    args = SimpleNamespace(
        handle="target.example",
        query='"foo bar"',
        scope="dm",
        since=None,
        until=None,
        limit=10,
        json=True,
    )

    rc = search_history_cmd.run(args)
    assert rc == 0

    data = json.loads(capsys.readouterr().out)
    texts = [r["text"] for r in data["results"]]

    assert any("foo bar" in t for t in texts)
    # phrase query should not match the non-phrase variant
    assert all("foo baz bar" not in t for t in texts)
