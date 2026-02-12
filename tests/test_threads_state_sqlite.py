from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def _mk_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _sample_thread(uri: str) -> dict:
    # Minimal TrackedThread dict shape (branches can be empty).
    return {
        "root_uri": uri,
        "root_url": "https://bsky.app/profile/x/post/y",
        "root_author_handle": "alice.bsky.social",
        "root_author_did": "did:plc:alice",
        "main_topics": ["AI"],
        "root_text": "hello",
        "overall_score": 80.0,
        "branches": {},
        "total_our_replies": 1,
        "created_at": "2026-02-10T00:00:00Z",
        "last_activity_at": "2026-02-10T00:00:00Z",
        "engaged_interlocutors": [],
        "our_reply_texts": [],
        "cron_id": None,
        "enabled": True,
        "backoff_level": 0,
        "last_check_at": None,
        "last_new_activity_at": None,
    }


def test_threads_state_persists_in_sqlite(monkeypatch, tmp_path: Path):
    """PR-007: threads_mod state should be stored in SQLite, not JSON."""

    from bsky_cli.threads_mod import state as threads_state
    from bsky_cli.storage.db import ensure_schema

    conn = _mk_conn()
    ensure_schema(conn)

    monkeypatch.setattr(threads_state, "_open_default_db", lambda: conn)

    uri = "at://did:plc:alice/app.bsky.feed.post/123"
    s = {
        "threads": {uri: _sample_thread(uri)},
        "evaluated_notifications": ["n1"],
        "last_evaluation": "2026-02-10T00:00:01Z",
    }

    threads_state.save_threads_state(s)
    loaded = threads_state.load_threads_state()

    assert uri in loaded["threads"]
    assert loaded["threads"][uri]["root_author_handle"] == "alice.bsky.social"
    assert loaded["evaluated_notifications"] == ["n1"]
    assert loaded["last_evaluation"] == "2026-02-10T00:00:01Z"


def test_threads_state_prunes_evaluated_notifications(monkeypatch):
    from bsky_cli.threads_mod import state as threads_state
    from bsky_cli.storage.db import ensure_schema

    conn = _mk_conn()
    ensure_schema(conn)

    monkeypatch.setattr(threads_state, "_open_default_db", lambda: conn)

    s = {
        "threads": {},
        "evaluated_notifications": [f"n{i}" for i in range(600)],
        "last_evaluation": None,
    }

    threads_state.save_threads_state(s)
    loaded = threads_state.load_threads_state()

    assert len(loaded["evaluated_notifications"]) == 500
    assert loaded["evaluated_notifications"][0] == "n100"  # keep tail


def test_migrate_threads_state_from_json(monkeypatch, tmp_path: Path):
    """PR-007: provide a one-shot migration from legacy JSON state."""

    from bsky_cli.threads_mod import state as threads_state
    from bsky_cli.storage.db import ensure_schema

    conn = _mk_conn()
    ensure_schema(conn)

    monkeypatch.setattr(threads_state, "_open_default_db", lambda: conn)

    legacy_path = tmp_path / "legacy.json"
    uri = "at://did:plc:alice/app.bsky.feed.post/123"
    legacy = {
        "threads": {uri: _sample_thread(uri)},
        "evaluated_notifications": ["n1", "n2"],
        "last_evaluation": "2026-02-10T00:00:01Z",
    }
    legacy_path.write_text(json.dumps(legacy))

    threads_state.migrate_threads_state_from_json(legacy_path, archive_json=True)

    loaded = threads_state.load_threads_state()
    assert uri in loaded["threads"]
    assert loaded["evaluated_notifications"] == ["n1", "n2"]

    # archived
    assert not legacy_path.exists()
    archived = list(tmp_path.glob("legacy.json.bak.*"))
    assert archived, "expected legacy json to be archived"


def test_tracked_thread_from_dict_missing_root_uri():
    """TrackedThread.from_dict should return None for legacy entries missing required keys."""
    from bsky_cli.threads_mod.models import TrackedThread
    legacy_entry = {
        "root_url": "https://example.com",
        "branches": {},
        # Missing: root_uri, root_author_handle, etc.
    }
    result = TrackedThread.from_dict(legacy_entry)
    assert result is None
