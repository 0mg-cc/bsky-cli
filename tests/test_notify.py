from types import SimpleNamespace

from bsky_cli import notify


def _args(**overrides):
    base = {
        "score": False,
        "execute": False,
        "limit": 50,
        "no_dm": True,
        "json": False,
        "all": False,
        "mark_read": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_notify_header_uses_new_when_filtered(monkeypatch, capsys):
    monkeypatch.setattr(notify, "get_session", lambda: ("https://pds", "did:me", "jwt", "me.bsky.social"))
    monkeypatch.setattr(
        notify,
        "get_notifications",
        lambda pds, jwt, limit=50: [
            {"reason": "like", "indexedAt": "2026-02-11T10:00:00Z", "author": {"handle": "a"}},
            {"reason": "like", "indexedAt": "2026-02-11T09:00:00Z", "author": {"handle": "b"}},
        ],
    )
    monkeypatch.setattr(notify, "get_last_seen", lambda: "2026-02-11T09:30:00Z")
    monkeypatch.setattr(notify, "save_last_seen", lambda ts: None)

    rc = notify.run(_args(all=False))

    out = capsys.readouterr().out
    assert rc == 0
    assert "=== BlueSky Notifications (1 new) ===" in out


def test_notify_header_uses_all_wording_with_all_flag(monkeypatch, capsys):
    monkeypatch.setattr(notify, "get_session", lambda: ("https://pds", "did:me", "jwt", "me.bsky.social"))
    monkeypatch.setattr(
        notify,
        "get_notifications",
        lambda pds, jwt, limit=50: [
            {"reason": "like", "indexedAt": "2026-02-11T10:00:00Z", "author": {"handle": "a"}},
            {"reason": "repost", "indexedAt": "2026-02-11T09:00:00Z", "author": {"handle": "b"}},
        ],
    )
    monkeypatch.setattr(notify, "get_last_seen", lambda: "2026-02-11T09:30:00Z")
    monkeypatch.setattr(notify, "save_last_seen", lambda ts: None)

    rc = notify.run(_args(all=True))

    out = capsys.readouterr().out
    assert rc == 0
    assert "=== BlueSky Notifications (2 notifications, all recent) ===" in out
