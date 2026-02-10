from __future__ import annotations

from pathlib import Path


def test_check_new_dms_skips_messages_from_self(monkeypatch, tmp_path: Path):
    from bsky_cli import dm as dm_mod

    # isolate state file
    monkeypatch.setattr(dm_mod, "DM_STATE_FILE", tmp_path / "last_seen.txt")

    fake_convos = [
        {
            "id": "convo1",
            "unreadCount": 2,
            "members": [
                {"did": "did:plc:them", "handle": "penny.hailey.at", "displayName": "Penny"},
                {"did": "did:plc:me", "handle": "echo.0mg.cc", "displayName": "Echo"},
            ],
        }
    ]

    fake_messages = [
        {
            "id": "m1",
            "sender": {"did": "did:plc:me"},
            "text": "my own message",
            "sentAt": "2026-02-10T00:00:02.000Z",
        },
        {
            "id": "m2",
            "sender": {"did": "did:plc:them"},
            "text": "their message",
            "facets": [
                {
                    "index": {"byteStart": 0, "byteEnd": 5},
                    "features": [
                        {"$type": "app.bsky.richtext.facet#tag", "tag": "test"}
                    ],
                }
            ],
            "sentAt": "2026-02-10T00:00:03.000Z",
        },
    ]

    monkeypatch.setattr(dm_mod, "get_dm_conversations", lambda pds, jwt, limit=20: fake_convos)
    monkeypatch.setattr(dm_mod, "get_dm_messages", lambda pds, jwt, convo_id, limit=20: fake_messages)

    new = dm_mod.check_new_dms("https://pds", "jwt", my_did="did:plc:me")

    assert len(new) == 1
    assert new[0]["text"] == "their message"
    assert new[0]["message_id"] == "m2"
    assert new[0]["facets"][0]["features"][0]["$type"] == "app.bsky.richtext.facet#tag"
