from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from bsky_cli.storage import db as dbmod


def test_db_path_for_account_is_filesystem_safe(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(dbmod.Path, "home", lambda: tmp_path)

    p = dbmod.db_path_for_account("Foo/Bar Baz")

    # no slashes introduced in the account segment
    assert "Foo" not in str(p)
    assert p.name == "bsky.db"
    assert str(p).startswith(str(tmp_path))
    assert "/accounts/" in str(p)
    assert "foo_bar_baz" in str(p)


def test_ensure_schema_creates_core_tables():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    dbmod.ensure_schema(conn)

    tables = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    assert "schema_migrations" in tables
    assert "actors" in tables
    assert "actor_tags" in tables
    assert "interactions" in tables


def test_import_interlocutors_json_inserts_rows(monkeypatch, tmp_path: Path):
    # Arrange: fake legacy interlocutors.json
    legacy = tmp_path / "interlocutors.json"
    legacy.write_text(
        json.dumps(
            {
                "did:plc:abc": {
                    "did": "did:plc:abc",
                    "handle": "alice.example",
                    "display_name": "Alice",
                    "first_seen": "2026-02-01",
                    "last_interaction": "2026-02-02",
                    "total_count": 2,
                    "notes": "met at conf",
                    "tags": ["friendly", "ai"],
                    "interactions": [
                        {
                            "date": "2026-02-02",
                            "type": "reply_to_them",
                            "post_uri": "at://did:plc:x/app.bsky.feed.post/123",
                            "our_text": "hi",
                            "their_text": "yo",
                        }
                    ],
                }
            }
        )
    )

    monkeypatch.setattr(dbmod, "INTERLOCUTORS_JSON", legacy)

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    dbmod.ensure_schema(conn)

    # Act
    n = dbmod.import_interlocutors_json(conn)

    # Assert
    assert n == 1

    actor = conn.execute("SELECT * FROM actors WHERE did='did:plc:abc'").fetchone()
    assert actor["handle"] == "alice.example"
    assert actor["display_name"] == "Alice"
    assert actor["notes_manual"] == "met at conf"
    assert actor["total_count"] == 2

    tags = {
        r["tag"]
        for r in conn.execute(
            "SELECT tag FROM actor_tags WHERE did='did:plc:abc'"
        ).fetchall()
    }
    assert tags == {"friendly", "ai"}

    inter = conn.execute(
        "SELECT * FROM interactions WHERE actor_did='did:plc:abc'"
    ).fetchall()
    assert len(inter) == 1
    assert inter[0]["type"] == "reply_to_them"
    assert inter[0]["post_uri"].endswith("/123")


def test_import_interlocutors_json_does_not_overwrite_manual_notes_by_default(monkeypatch, tmp_path: Path):
    legacy = tmp_path / "interlocutors.json"
    legacy.write_text(
        json.dumps(
            {
                "did:plc:abc": {
                    "did": "did:plc:abc",
                    "handle": "alice.example",
                    "notes": "NEW NOTES",
                    "tags": [],
                    "interactions": [],
                }
            }
        )
    )
    monkeypatch.setattr(dbmod, "INTERLOCUTORS_JSON", legacy)

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    dbmod.ensure_schema(conn)

    conn.execute(
        "INSERT INTO actors(did, handle, notes_manual) VALUES (?,?,?)",
        ("did:plc:abc", "alice.example", "KEEP"),
    )
    conn.commit()

    dbmod.import_interlocutors_json(conn, overwrite=False)

    actor = conn.execute("SELECT notes_manual FROM actors WHERE did='did:plc:abc'").fetchone()
    assert actor["notes_manual"] == "KEEP"
