from __future__ import annotations

import sqlite3


def test_ensure_schema_recreates_missing_tables_even_if_version_marker_is_latest(tmp_path):
    from bsky_cli.storage import db as storage_db

    db_path = tmp_path / "broken.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Simulate a DB that claims all migrations were applied,
    # but is actually missing DM tables (real-world partial/broken state).
    conn.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT)")
    conn.execute(
        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, '2026-01-01T00:00:00Z')",
        (len(storage_db.MIGRATIONS),),
    )
    conn.commit()

    # Sanity check: table is missing before ensure_schema.
    before = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='dm_convo_members'"
    ).fetchone()
    assert before is None

    storage_db.ensure_schema(conn)

    after = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='dm_convo_members'"
    ).fetchone()
    assert after is not None


def test_search_history_run_does_not_crash_on_partially_migrated_db(monkeypatch, tmp_path, capsys):
    from bsky_cli import search_history_cmd
    from bsky_cli.storage import db as storage_db

    db_path = tmp_path / "broken-search.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    conn.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT)")
    conn.execute(
        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, '2026-01-01T00:00:00Z')",
        (len(storage_db.MIGRATIONS),),
    )
    conn.commit()

    monkeypatch.setattr(search_history_cmd, "get_session", lambda: ("https://pds.example", "did:plc:me", "jwt", "me.bsky.social"))
    monkeypatch.setattr(search_history_cmd, "resolve_handle", lambda pds, h: "did:plc:target")
    monkeypatch.setattr(search_history_cmd, "open_db", lambda account: conn)

    class _Args:
        handle = "target.bsky.social"
        query = "hello"
        scope = "all"
        since = None
        until = None
        limit = 10
        json = True

    rc = search_history_cmd.run(_Args())
    out = capsys.readouterr().out

    assert rc == 0
    assert '"results": []' in out
