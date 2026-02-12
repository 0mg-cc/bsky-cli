import bsky_cli.followup_notifications as fup
from bsky_cli import post as post_mod
from bsky_cli import reply as reply_mod


def test_schedule_notification_followups_spawns_expected_delays(monkeypatch):
    calls = []

    class DummyPopen:
        def __init__(self, cmd, **kwargs):
            calls.append((cmd, kwargs))

    monkeypatch.setattr(fup.subprocess, "Popen", DummyPopen)

    fup.schedule_notification_followups()

    assert len(calls) == 4
    joined = "\n".join(c[0][2] for c in calls)
    assert "sleep 120" in joined
    assert "sleep 300" in joined
    assert "sleep 600" in joined
    assert "sleep 900" in joined


def test_post_run_triggers_followup_notifications(monkeypatch):
    triggered = {"n": 0}

    monkeypatch.setattr(post_mod, "detect_facets", lambda *a, **k: None)
    monkeypatch.setattr(post_mod, "get_session", lambda: ("https://pds.example", "did:plc:me", "jwt", None))
    monkeypatch.setattr(post_mod, "create_post", lambda *a, **k: {"uri": "at://did:plc:me/app.bsky.feed.post/abc"})
    monkeypatch.setattr(post_mod, "schedule_notification_followups", lambda: triggered.__setitem__("n", triggered["n"] + 1))

    args = type("A", (), {
        "text": "hello",
        "embed": None,
        "quote": None,
        "allow_repeat": True,
        "dry_run": False,
    })()

    rc = post_mod.run(args)
    assert rc == 0
    assert triggered["n"] == 1


def test_reply_run_triggers_followup_notifications(monkeypatch):
    triggered = {"n": 0}

    monkeypatch.setattr(reply_mod, "get_session", lambda: ("https://pds.example", "did:plc:me", "jwt", None))
    monkeypatch.setattr(reply_mod, "resolve_handle", lambda pds, h: "did:plc:target")
    monkeypatch.setattr(reply_mod, "get_post", lambda *a, **k: {
        "uri": "at://did:plc:target/app.bsky.feed.post/xyz",
        "cid": "cid123",
        "value": {},
    })
    monkeypatch.setattr(reply_mod, "create_reply", lambda *a, **k: {"uri": "at://did:plc:me/app.bsky.feed.post/reply1"})
    monkeypatch.setattr(reply_mod, "schedule_notification_followups", lambda: triggered.__setitem__("n", triggered["n"] + 1))

    args = type("A", (), {
        "post_url": "https://bsky.app/profile/penny.hailey.at/post/abc123",
        "text": "thanks!",
        "dry_run": False,
    })()

    rc = reply_mod.run(args)
    assert rc == 0
    assert triggered["n"] == 1
