from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace


def test_search_history_escapes_punctuated_literals(monkeypatch, capsys):
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
        ("c1", "m1", "did:plc:target", "in", "2026-02-10T00:00:02Z", "see did:plc:target and https://example.com"),
    )

    # Ensure history FTS gets populated by triggers in this in-memory DB
    conn.execute(
        "INSERT INTO interactions(actor_did, date, type, post_uri, our_text, their_text) VALUES (?,?,?,?,?,?)",
        ("did:plc:target", "2026-02-09", "reply_to_them", "at://x/app.bsky.feed.post/1", "", ""),
    )
    conn.commit()

    args = SimpleNamespace(
        handle="target.example",
        query="did:plc:target https://example.com",
        scope="dm",
        since=None,
        until=None,
        limit=10,
        json=True,
    )

    rc = search_history_cmd.run(args)
    assert rc == 0

    data = json.loads(capsys.readouterr().out)
    assert data["results"]
    assert any("did:plc:target" in r["text"] for r in data["results"])

def test_search_history_preserves_prefix_and_unary_not_operators():
    """Regression: escaping should preserve common FTS operators like foo* and -foo."""

    from bsky_cli.search_history_cmd import _fts_escape_query

    assert _fts_escape_query("foo*") == "foo*"
    assert _fts_escape_query("-foo") == "-foo"
    # Punctuated tokens should be quoted (avoid FTS parse errors)
    assert _fts_escape_query("did:plc:abc") == '"did:plc:abc"'
