from __future__ import annotations

import sqlite3
from types import SimpleNamespace


def _mk_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_people_stats_uses_sqlite(monkeypatch, capsys):
    """PR-006: bsky people should read stats from the per-account SQLite DB (not interlocutors.json)."""

    from bsky_cli import people

    conn = _mk_conn()

    monkeypatch.setattr(people, "get_session", lambda: ("https://pds.invalid", "did:me", "jwt", "echo.0mg.cc"))
    monkeypatch.setattr(people, "open_db", lambda account_handle: conn)

    people.ensure_schema(conn)

    conn.execute(
        "INSERT INTO actors(did, handle, display_name, first_seen, last_interaction, total_count, notes_manual) VALUES (?,?,?,?,?,?,?)",
        ("did:plc:alice", "alice.bsky.social", "Alice", "2026-02-01", "2026-02-10", 0, ""),
    )
    conn.execute(
        "INSERT INTO interactions(actor_did, date, type, post_uri, our_text, their_text) VALUES (?,?,?,?,?,?)",
        ("did:plc:alice", "2026-02-10", "reply_to_them", None, "hi", "yo"),
    )
    conn.execute("INSERT OR IGNORE INTO dm_conversations(convo_id, last_message_at) VALUES (?,?)", ("c1", "2026-02-10T00:00:02Z"))
    conn.execute("INSERT OR IGNORE INTO dm_convo_members(convo_id, did) VALUES (?,?)", ("c1", "did:plc:alice"))
    conn.execute("INSERT OR IGNORE INTO dm_messages(convo_id, msg_id, actor_did, direction, sent_at, text) VALUES (?,?,?,?,?,?)", (
        "c1",
        "m1",
        "did:plc:alice",
        "in",
        "2026-02-10T00:00:02Z",
        "hello",
    ))
    conn.commit()

    args = SimpleNamespace(
        stats=True,
        handle=None,
        regulars=False,
        limit=20,
        # new PR-006 flags (ignored if not implemented yet)
        enrich=False,
        execute=False,
        set_note=None,
        add_tag=None,
        remove_tag=None,
    )

    rc = people.run(args)
    assert rc == 0

    out = capsys.readouterr().out
    assert "Total users tracked" in out
    assert "1" in out


def test_people_can_set_note_and_tags_in_db(monkeypatch, capsys):
    """PR-006: allow setting manual notes/tags in SQLite via bsky people."""

    from bsky_cli import people

    conn = _mk_conn()

    monkeypatch.setattr(people, "get_session", lambda: ("https://pds.invalid", "did:me", "jwt", "echo.0mg.cc"))
    monkeypatch.setattr(people, "open_db", lambda account_handle: conn)

    people.ensure_schema(conn)

    conn.execute(
        "INSERT INTO actors(did, handle, display_name) VALUES (?,?,?)",
        ("did:plc:alice", "alice.bsky.social", "Alice"),
    )
    conn.commit()

    args = SimpleNamespace(
        stats=False,
        handle="@alice.bsky.social",
        regulars=False,
        limit=20,
        enrich=False,
        execute=False,
        set_note="Met at conference",
        add_tag=["ai"],
        remove_tag=None,
    )

    rc = people.run(args)
    assert rc == 0

    row = conn.execute("SELECT notes_manual FROM actors WHERE did=?", ("did:plc:alice",)).fetchone()
    assert row[0] == "Met at conference"

    tags = [r[0] for r in conn.execute("SELECT tag FROM actor_tags WHERE did=?", ("did:plc:alice",)).fetchall()]
    assert "ai" in tags
