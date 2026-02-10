from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from bsky_cli.storage import db as dbmod


def test_import_interlocutors_does_not_clear_existing_display_name(monkeypatch, tmp_path: Path):
    legacy = tmp_path / "interlocutors.json"
    legacy.write_text(
        json.dumps(
            {
                "did:plc:abc": {
                    "did": "did:plc:abc",
                    "handle": "alice.example",
                    # display_name is missing/blank in legacy
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
        "INSERT INTO actors(did, handle, display_name) VALUES (?,?,?)",
        ("did:plc:abc", "alice.example", "Alice"),
    )
    conn.commit()

    dbmod.import_interlocutors_json(conn, overwrite=False)

    row = conn.execute("SELECT display_name FROM actors WHERE did='did:plc:abc'").fetchone()
    assert row["display_name"] == "Alice"
