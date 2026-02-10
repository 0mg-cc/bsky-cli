from __future__ import annotations

import sqlite3
from types import SimpleNamespace


def _mk_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_people_last_activity_uses_newest_of_dm_and_interactions(monkeypatch, capsys):
    """Regression test for Codex inline comment: last activity must be newest of DM vs interactions."""

    from bsky_cli import people

    conn = _mk_conn()
    people.ensure_schema(conn)

    conn.execute("INSERT INTO actors(did, handle, display_name) VALUES (?,?,?)", ("did:plc:alice", "alice.bsky.social", "Alice"))

    # Old DM
    conn.execute("INSERT OR IGNORE INTO dm_conversations(convo_id, last_message_at) VALUES (?,?)", ("c1", "2026-02-01T00:00:00Z"))
    conn.execute("INSERT OR IGNORE INTO dm_convo_members(convo_id, did) VALUES (?,?)", ("c1", "did:plc:alice"))
    conn.execute(
        "INSERT OR IGNORE INTO dm_messages(convo_id, msg_id, actor_did, direction, sent_at, text) VALUES (?,?,?,?,?,?)",
        ("c1", "m1", "did:plc:alice", "in", "2026-02-01T00:00:00Z", "hello"),
    )

    # Newer interaction
    conn.execute(
        "INSERT INTO interactions(actor_did, date, type, post_uri, our_text, their_text) VALUES (?,?,?,?,?,?)",
        ("did:plc:alice", "2026-02-10", "reply_to_them", None, "hi", "yo"),
    )
    conn.commit()

    monkeypatch.setattr(people, "_open_default_db", lambda: (conn, "echo.0mg.cc"))

    args = SimpleNamespace(
        stats=False,
        handle="@alice.bsky.social",
        regulars=False,
        limit=20,
        set_note=None,
        add_tag=None,
        remove_tag=None,
        enrich=False,
        execute=False,
        force=False,
        min_age_hours=72,
    )

    rc = people.run(args)
    assert rc == 0

    out = capsys.readouterr().out
    assert "Last activity: 2026-02-10" in out
