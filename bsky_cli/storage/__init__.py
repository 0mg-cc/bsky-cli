"""SQLite storage layer for bsky-cli (per-account).

This module is introduced to consolidate context/memory into a queryable store.
V1 focuses on:
- per-account DB open + migrations
- importing existing interlocutors.json (anti-regression)

Higher-level features (FTS5, DM ingestion, thread cache) build on top.
"""

from .db import open_db, ensure_schema, import_interlocutors_json  # noqa: F401
