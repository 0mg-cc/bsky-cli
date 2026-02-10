from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from bsky_cli import context_cmd


def test_context_run_keeps_db_dm_context_if_live_fetch_fails(monkeypatch, capsys):
    """Regression: live fallback should never break a working DB-backed HOT context."""

    monkeypatch.setattr(
        context_cmd,
        "get_session",
        lambda: ("https://pds.invalid", "did:me", "jwt", "echo.0mg.cc"),
    )
    monkeypatch.setattr(context_cmd, "resolve_handle", lambda pds, h: "did:plc:target")

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    monkeypatch.setattr(context_cmd, "open_db", lambda account_handle: conn)
    monkeypatch.setattr(context_cmd, "import_interlocutors_json", lambda conn: 0)

    context_cmd.ensure_schema(conn)
    conn.execute("INSERT INTO actors(did, handle) VALUES (?,?)", ("did:plc:target", "target.example"))

    # Seed DB with 1 DM
    conn.execute("INSERT OR IGNORE INTO dm_conversations(convo_id, last_message_at) VALUES (?,?)", ("c1", "2026-02-10T00:00:00Z"))
    conn.execute("INSERT OR IGNORE INTO dm_convo_members(convo_id, did) VALUES (?,?)", ("c1", "did:plc:target"))
    conn.execute("INSERT OR IGNORE INTO dm_convo_members(convo_id, did) VALUES (?,?)", ("c1", "did:me"))
    conn.execute(
        "INSERT OR IGNORE INTO dm_messages(convo_id, msg_id, actor_did, direction, sent_at, text) VALUES (?,?,?,?,?,?)",
        ("c1", "m1", "did:plc:target", "in", "2026-02-10T00:00:00Z", "db msg"),
    )
    conn.commit()

    def _live(*a, **k):
        raise RuntimeError("offline")

    monkeypatch.setattr(context_cmd, "_fetch_dm_context", _live)

    # No threads needed
    monkeypatch.setattr(context_cmd, "_get_root_uri_for_post_uri", lambda *a, **k: "at://root")
    monkeypatch.setattr(context_cmd, "_get_post_text", lambda *a, **k: "root")

    args = SimpleNamespace(handle="target.example", dm=5, threads=0, json=False)

    rc = context_cmd.run(args)
    assert rc == 0

    out = capsys.readouterr().out
    assert "db msg" in out
