from __future__ import annotations

from types import SimpleNamespace

from bsky_cli import notify_scored


def _args(**overrides):
    base = {
        "all": False,
        "limit": 50,
        "json": False,
        "score": True,
        "execute": False,
        "quiet": True,
        "max_replies": None,
        "max_likes": None,
        "max_follows": None,
        "allow_replies": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_run_scored_updates_server_seen_even_when_no_local_new(monkeypatch):
    # Raw feed has items, but local cursor filters them all out.
    monkeypatch.setattr(
        "bsky_cli.notify.get_notifications",
        lambda pds, jwt, limit=50: [
            {"indexedAt": "2026-02-17T11:00:00Z", "reason": "like", "author": {"handle": "a"}},
        ],
    )
    monkeypatch.setattr("bsky_cli.notify.get_last_seen", lambda: "2026-02-17T12:00:00Z")

    seen_updates = []
    monkeypatch.setattr("bsky_cli.notify.update_seen", lambda pds, jwt, seen_at: seen_updates.append(seen_at))

    saved = []
    monkeypatch.setattr("bsky_cli.notify.save_last_seen", lambda ts: saved.append(ts))

    rc = notify_scored.run_scored(_args(execute=False), "https://pds", "did:me", "jwt")

    assert rc == 0
    assert seen_updates, "run_scored should always sync server seen marker when notifications exist"
    assert saved == [], "local cursor should not move when there are no locally-new notifications"


def test_run_scored_execute_updates_local_and_server_seen(monkeypatch):
    monkeypatch.setattr(
        "bsky_cli.notify.get_notifications",
        lambda pds, jwt, limit=50: [
            {"indexedAt": "2026-02-17T13:00:00Z", "reason": "like", "author": {"handle": "a"}},
        ],
    )
    monkeypatch.setattr("bsky_cli.notify.get_last_seen", lambda: "2026-02-17T12:00:00Z")

    monkeypatch.setattr(notify_scored, "fetch_profile", lambda handle: {"handle": handle})

    seen_updates = []
    monkeypatch.setattr("bsky_cli.notify.update_seen", lambda pds, jwt, seen_at: seen_updates.append(seen_at))

    saved = []
    monkeypatch.setattr("bsky_cli.notify.save_last_seen", lambda ts: saved.append(ts))

    rc = notify_scored.run_scored(_args(execute=True, score=False), "https://pds", "did:me", "jwt")

    assert rc == 0
    assert saved == ["2026-02-17T13:00:00Z"]
    assert seen_updates, "server seen marker should be updated after execute runs"
