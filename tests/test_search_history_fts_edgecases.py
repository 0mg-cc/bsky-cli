from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace


def test_fts_escape_does_not_uppercase_lowercase_or():
    """Regression: searching for the word 'or' should not become the OR operator."""

    from bsky_cli.search_history_cmd import _fts_escape_query

    assert _fts_escape_query("or") == "or"
    assert _fts_escape_query("and") == "and"
    assert _fts_escape_query("not") == "not"


def test_fts_escape_preserves_parentheses_grouping_without_extra_spaces():
    from bsky_cli.search_history_cmd import _fts_escape_query

    assert _fts_escape_query("foo AND (bar OR baz)") == "foo AND (bar OR baz)"


def test_search_history_since_date_only_includes_interactions_same_day(monkeypatch, capsys):
    """Regression: --since YYYY-MM-DD should not exclude interaction rows indexed as date-only ts."""

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

    # Seed a same-day interaction. The trigger should index into history_fts with ts='YYYY-MM-DD'.
    conn.execute(
        "INSERT INTO interactions(actor_did, date, type, post_uri, our_text, their_text) VALUES (?,?,?,?,?,?)",
        (
            "did:plc:target",
            "2026-02-10",
            "reply_to_them",
            "at://x/app.bsky.feed.post/1",
            "needle",
            "",
        ),
    )
    conn.commit()

    args = SimpleNamespace(
        handle="target.example",
        query="needle",
        scope="threads",
        since="2026-02-10",
        until=None,
        limit=10,
        json=True,
    )

    rc = search_history_cmd.run(args)
    assert rc == 0

    data = json.loads(capsys.readouterr().out)
    assert data["results"], "expected same-day interaction to be included"
