from __future__ import annotations

from bsky_cli import dm as dm_mod


def test_check_new_dms_returns_messages_even_if_unreadcount_zero(monkeypatch):
    # If the user reads a DM quickly, unreadCount can be 0 by the time we poll.
    # We still want to detect it using last_seen cursor.

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
            "id": "m1",
            "sentAt": "2026-02-10T00:00:10Z",
            "sender": {"did": "did:plc:other"},
            "text": "hi",
            "facets": None,
        }
    ]

    monkeypatch.setattr(dm_mod, "get_dm_messages", lambda pds, jwt, convo_id, limit=20: messages)

    # Don't write to disk in tests
    monkeypatch.setattr(dm_mod, "save_dm_last_seen", lambda ts: None)

    out = dm_mod.check_new_dms("https://pds", "jwt", my_did="did:me")

    assert len(out) == 1
    assert out[0]["message_id"] == "m1"
    assert out[0]["text"] == "hi"
