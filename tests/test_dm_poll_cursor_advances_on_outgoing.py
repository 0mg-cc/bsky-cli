from __future__ import annotations

from bsky_cli import dm as dm_mod


def test_check_new_dms_advances_cursor_even_if_latest_is_ours(monkeypatch):
    # If the newest message is from us, we still need to advance last_seen,
    # otherwise we'll refetch the convo forever.

    monkeypatch.setattr(dm_mod, "get_dm_last_seen", lambda: "2026-02-10T00:00:00Z")

    convos = [
        {
            "id": "c1",
            "members": [
                {"did": "did:me", "handle": "me.example"},
                {"did": "did:plc:other", "handle": "other.example"},
            ],
            "unreadCount": 0,
            "lastMessageAt": "2026-02-10T00:00:10Z",
        }
    ]

    monkeypatch.setattr(dm_mod, "get_dm_conversations", lambda pds, jwt, limit=20: convos)

    messages = [
        {
            "id": "m_out",
            "sentAt": "2026-02-10T00:00:10Z",
            "sender": {"did": "did:me"},
            "text": "our msg",
            "facets": None,
        }
    ]

    monkeypatch.setattr(dm_mod, "get_dm_messages", lambda pds, jwt, convo_id, limit=20: messages)

    saved = {"ts": None}

    def _save(ts: str):
        saved["ts"] = ts

    monkeypatch.setattr(dm_mod, "save_dm_last_seen", _save)

    out = dm_mod.check_new_dms("https://pds", "jwt", my_did="did:me")

    # No new inbound messages
    assert out == []

    # Cursor still advances to our newest message
    assert saved["ts"] == "2026-02-10T00:00:10Z"
