from __future__ import annotations

from types import SimpleNamespace

import pytest


def test_dms_list_formats_convos_with_sender_handle(monkeypatch, mock_session, capsys):
    # Import inside test so monkeypatch applies cleanly
    from bsky_cli import dm as dm_mod
    from bsky_cli import dms_cmd

    # Fake convo list: one convo, unread=2, member list includes sender DID
    fake_convos = [
        {
            "id": "convo1",
            "unreadCount": 2,
            "members": [
                {"did": "did:plc:jen", "handle": "jenrm.bsky.social", "displayName": "Jennifer RM"},
                {"did": "did:plc:echo", "handle": "echo.0mg.cc", "displayName": "Echo"},
            ],
        }
    ]

    fake_messages = [
        {"sender": {"did": "did:plc:jen"}, "text": "hello", "sentAt": "2026-02-08T23:00:00.000Z"},
    ]

    monkeypatch.setattr(dm_mod, "get_dm_conversations", lambda pds, jwt, limit=20: fake_convos)
    monkeypatch.setattr(dm_mod, "get_dm_messages", lambda pds, jwt, convo_id, limit=20: fake_messages)

    args = SimpleNamespace(json=True, limit=20, preview=1)
    rc = dms_cmd.run(args)
    assert rc == 0

    out = capsys.readouterr().out
    assert "jenrm.bsky.social" in out
    assert "unreadCount" in out


def test_dms_show_includes_full_messages(monkeypatch, mock_session, capsys):
    from bsky_cli import dm as dm_mod
    from bsky_cli import dms_cmd

    fake_convos = [
        {
            "id": "convo1",
            "unreadCount": 1,
            "members": [
                {"did": "did:plc:jen", "handle": "jenrm.bsky.social", "displayName": "Jennifer RM"},
                {"did": "did:plc:echo", "handle": "echo.0mg.cc", "displayName": "Echo"},
            ],
        }
    ]

    fake_messages = [
        {"sender": {"did": "did:plc:jen"}, "text": "hi", "sentAt": "2026-02-08T23:00:00.000Z"},
        {"sender": {"did": "did:plc:echo"}, "text": "hello", "sentAt": "2026-02-08T23:01:00.000Z"},
    ]

    monkeypatch.setattr(dm_mod, "get_dm_conversations", lambda pds, jwt, limit=20: fake_convos)
    monkeypatch.setattr(dm_mod, "get_dm_messages", lambda pds, jwt, convo_id, limit=50: fake_messages)

    args = SimpleNamespace(json=True, handle="jenrm.bsky.social", limit=50)
    rc = dms_cmd.run_show(args)
    assert rc == 0

    out = capsys.readouterr().out
    assert "hi" in out
    assert "hello" in out
