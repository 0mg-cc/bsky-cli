from __future__ import annotations

import sqlite3
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace


def _mk_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_people_enrich_skips_when_recent(monkeypatch, capsys):
    from bsky_cli import people

    conn = _mk_conn()
    people.ensure_schema(conn)

    monkeypatch.setattr(people, "_open_default_db", lambda: (conn, "echo.0mg.cc"))

    conn.execute("INSERT INTO actors(did, handle, display_name) VALUES (?,?,?)", ("did:plc:alice", "alice.bsky.social", "Alice"))
    conn.execute("INSERT INTO dm_conversations(convo_id, last_message_at) VALUES (?,?)", ("c1", "2026-02-10T00:00:00Z"))
    conn.execute("INSERT INTO dm_convo_members(convo_id, did) VALUES (?,?)", ("c1", "did:plc:alice"))
    conn.execute(
        "INSERT INTO dm_messages(convo_id, msg_id, actor_did, direction, sent_at, text) VALUES (?,?,?,?,?,?)",
        ("c1", "m1", "did:plc:alice", "in", "2026-02-10T00:00:00Z", "hello"),
    )

    # Pretend enrich was done 1 hour ago
    recent = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    conn.execute(
        "INSERT INTO actor_auto_notes(did, kind, content, created_at) VALUES (?,?,?,?)",
        ("did:plc:alice", "notes", "old", recent),
    )
    conn.commit()

    # session/network not required for enrich tests

    # Ensure the LLM would blow up if called (so we know skip works)
    monkeypatch.setattr(people, "_llm_enrich_person", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("should not call")))

    args = SimpleNamespace(
        stats=False,
        handle="@alice.bsky.social",
        regulars=False,
        limit=20,
        set_note=None,
        add_tag=None,
        remove_tag=None,
        enrich=True,
        execute=False,
        force=False,
        min_age_hours=72,
    )

    rc = people.run(args)
    assert rc == 0

    out = capsys.readouterr().out
    assert "enrich skipped" in out


def test_people_enrich_min_age_hours_zero_disables_cooldown(monkeypatch, capsys):
    from bsky_cli import people

    conn = _mk_conn()
    people.ensure_schema(conn)

    monkeypatch.setattr(people, "_open_default_db", lambda: (conn, "echo.0mg.cc"))

    conn.execute("INSERT INTO actors(did, handle, display_name) VALUES (?,?,?)", ("did:plc:alice", "alice.bsky.social", "Alice"))

    # Pretend enrich was done 1 hour ago
    recent = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    conn.execute(
        "INSERT INTO actor_auto_notes(did, kind, content, created_at) VALUES (?,?,?,?)",
        ("did:plc:alice", "notes", "old", recent),
    )
    conn.commit()

    # session/network not required for enrich tests

    called = {"n": 0}

    def _fake_llm(**kwargs):
        called["n"] += 1
        return {"notes_auto": "auto notes", "interests_auto": "ai", "relationship_tone": "friendly"}

    monkeypatch.setattr(people, "_llm_enrich_person", _fake_llm)

    args = SimpleNamespace(
        stats=False,
        handle="@alice.bsky.social",
        regulars=False,
        limit=20,
        set_note=None,
        add_tag=None,
        remove_tag=None,
        enrich=True,
        execute=False,
        force=False,
        min_age_hours=0,
    )

    rc = people.run(args)
    assert rc == 0

    out = capsys.readouterr().out
    assert "enrich skipped" not in out
    assert "Enrich preview" in out
    assert called["n"] == 1


def test_people_enrich_cooldown_applies_across_kinds(monkeypatch, capsys):
    from bsky_cli import people

    conn = _mk_conn()
    people.ensure_schema(conn)

    monkeypatch.setattr(people, "_open_default_db", lambda: (conn, "echo.0mg.cc"))

    conn.execute("INSERT INTO actors(did, handle, display_name) VALUES (?,?,?)", ("did:plc:alice", "alice.bsky.social", "Alice"))

    # Pretend last snapshot was interests-only, 1 hour ago
    recent = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    conn.execute(
        "INSERT INTO actor_auto_notes(did, kind, content, created_at) VALUES (?,?,?,?)",
        ("did:plc:alice", "interests", "ai", recent),
    )
    conn.commit()

    monkeypatch.setattr(people, "_llm_enrich_person", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("should not call")))

    args = SimpleNamespace(
        stats=False,
        handle="@alice.bsky.social",
        regulars=False,
        limit=20,
        set_note=None,
        add_tag=None,
        remove_tag=None,
        enrich=True,
        execute=False,
        force=False,
        min_age_hours=72,
    )

    rc = people.run(args)
    assert rc == 0

    out = capsys.readouterr().out
    assert "enrich skipped" in out


def test_people_enrich_execute_saves_snapshots(monkeypatch, capsys):
    from bsky_cli import people

    conn = _mk_conn()
    people.ensure_schema(conn)

    monkeypatch.setattr(people, "_open_default_db", lambda: (conn, "echo.0mg.cc"))

    conn.execute("INSERT INTO actors(did, handle, display_name) VALUES (?,?,?)", ("did:plc:alice", "alice.bsky.social", "Alice"))
    conn.execute("INSERT INTO dm_conversations(convo_id, last_message_at) VALUES (?,?)", ("c1", "2026-02-10T00:00:00Z"))
    conn.execute("INSERT INTO dm_convo_members(convo_id, did) VALUES (?,?)", ("c1", "did:plc:alice"))
    conn.execute(
        "INSERT INTO dm_messages(convo_id, msg_id, actor_did, direction, sent_at, text) VALUES (?,?,?,?,?,?)",
        ("c1", "m1", "did:plc:alice", "in", "2026-02-10T00:00:00Z", "hello"),
    )
    conn.execute(
        "INSERT INTO interactions(actor_did, date, type, post_uri, our_text, their_text) VALUES (?,?,?,?,?,?)",
        ("did:plc:alice", "2026-02-10", "reply_to_them", None, "hi", "yo"),
    )
    conn.commit()

    # session/network not required for enrich tests

    monkeypatch.setattr(
        people,
        "_llm_enrich_person",
        lambda **kwargs: {
            "notes_auto": "auto notes",
            "interests_auto": "ai, infra",
            "relationship_tone": "friendly, technical",
        },
    )

    args = SimpleNamespace(
        stats=False,
        handle="@alice.bsky.social",
        regulars=False,
        limit=20,
        set_note=None,
        add_tag=None,
        remove_tag=None,
        enrich=True,
        execute=True,
        force=True,
        min_age_hours=72,
    )

    rc = people.run(args)
    assert rc == 0

    out = capsys.readouterr().out
    assert "Saved to DB" in out

    row = conn.execute(
        "SELECT notes_auto, interests_auto, relationship_tone FROM actors WHERE did=?",
        ("did:plc:alice",),
    ).fetchone()
    assert row[0] == "auto notes"
    assert row[1] == "ai, infra"
    assert row[2] == "friendly, technical"

    kinds = [r[0] for r in conn.execute("SELECT kind FROM actor_auto_notes WHERE did=? ORDER BY kind", ("did:plc:alice",)).fetchall()]
    assert kinds == ["interests", "notes", "tone"]


def test_people_enrich_list_mode_supports_max_dry_run(monkeypatch, capsys):
    from bsky_cli import people

    conn = _mk_conn()
    people.ensure_schema(conn)
    monkeypatch.setattr(people, "_open_default_db", lambda: (conn, "echo.0mg.cc"))

    conn.execute("INSERT INTO actors(did, handle, display_name) VALUES (?,?,?)", ("did:plc:alice", "alice.bsky.social", "Alice"))
    conn.execute("INSERT INTO actors(did, handle, display_name) VALUES (?,?,?)", ("did:plc:bob", "bob.bsky.social", "Bob"))
    conn.execute("INSERT INTO interactions(actor_did, date, type, post_uri, our_text, their_text) VALUES (?,?,?,?,?,?)", ("did:plc:alice", "2026-02-10", "reply_to_them", None, "hi", "yo"))
    conn.execute("INSERT INTO interactions(actor_did, date, type, post_uri, our_text, their_text) VALUES (?,?,?,?,?,?)", ("did:plc:bob", "2026-02-09", "reply_to_them", None, "hi", "yo"))
    conn.commit()

    called = {"n": 0}

    def _fake_llm(**kwargs):
        called["n"] += 1
        return {"notes_auto": "note", "interests_auto": "tech", "relationship_tone": "friendly"}

    monkeypatch.setattr(people, "_llm_enrich_person", _fake_llm)

    args = SimpleNamespace(
        stats=False,
        handle=None,
        regulars=False,
        limit=20,
        set_note=None,
        add_tag=None,
        remove_tag=None,
        enrich=True,
        execute=False,
        dry_run=True,
        max=1,
        force=True,
        min_age_hours=72,
        json=False,
    )

    rc = people.run(args)
    assert rc == 0

    out = capsys.readouterr().out
    assert "[DRY RUN] Would enrich 1 people" in out
    assert "@alice.bsky.social" in out
    assert called["n"] == 1
