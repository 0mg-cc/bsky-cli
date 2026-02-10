from __future__ import annotations


def test_fetch_dm_context_matches_did_targets(monkeypatch):
    from bsky_cli import context_cmd

    # Fake convo list: member has DID+handle
    fake_convos = [
        {
            "id": "convo1",
            "members": [
                {"did": "did:plc:target", "handle": "target.example", "displayName": "Target"},
                {"did": "did:me", "handle": "echo.0mg.cc", "displayName": "Echo"},
            ],
        }
    ]

    fake_messages = [
        {"sender": {"did": "did:plc:target"}, "text": "hi", "sentAt": "2026-02-10T00:00:00Z"},
    ]

    monkeypatch.setattr(context_cmd, "get_dm_conversations", lambda pds, jwt, limit=50: fake_convos)
    monkeypatch.setattr(context_cmd, "get_dm_messages", lambda pds, jwt, convo_id, limit=1: fake_messages)

    out = context_cmd._fetch_dm_context(
        "https://pds",
        "jwt",
        "echo.0mg.cc",
        "did:plc:target",
        1,
    )

    assert out and out[0]["text"] == "hi"
