from bsky_cli import notify_scored


def test_relationship_follow_probability_thresholds():
    assert notify_scored._relationship_follow_probability(0) == 0.0
    assert notify_scored._relationship_follow_probability(10) == 0.0
    assert notify_scored._relationship_follow_probability(11) == 0.1
    assert notify_scored._relationship_follow_probability(50) == 0.1
    assert notify_scored._relationship_follow_probability(51) == 0.3


def test_is_negative_tone_detects_negative_markers():
    assert notify_scored._is_negative_tone("hostile, conflict-heavy") is True
    assert notify_scored._is_negative_tone("friendly, technical") is False


def test_run_scored_can_follow_without_post_url(monkeypatch, capsys):
    # Follow notifications don't have a post URL; we still want follow-back.

    follow_notif = {
        "reason": "follow",
        "indexedAt": "2099-01-01T00:00:00.000Z",
        "author": {"did": "did:plc:abc", "handle": "human.bsky.social"},
        "uri": "at://did:plc:abc/app.bsky.graph.follow/xyz",
        "record": {"$type": "app.bsky.graph.follow"},
    }

    # Patch notify module functions imported inside run_scored.
    import bsky_cli.notify as notify_mod

    monkeypatch.setattr(notify_mod, "get_notifications", lambda *a, **k: [follow_notif])
    monkeypatch.setattr(notify_mod, "get_last_seen", lambda: None)
    monkeypatch.setattr(notify_mod, "save_last_seen", lambda ts: None)

    # Strong profile so follow passes author_score threshold.
    monkeypatch.setattr(
        notify_scored,
        "fetch_profile",
        lambda handle: {
            "handle": handle,
            "description": "I write software.",
            "createdAt": "2023-01-01T00:00:00.000Z",
            "postsCount": 100,
            "followersCount": 100,
            "followsCount": 100,
        },
    )

    calls = {"follow": 0}

    monkeypatch.setattr(notify_scored, "follow_handle", lambda handle: calls.__setitem__("follow", calls["follow"] + 1) or 0)
    monkeypatch.setattr(notify_scored, "like_url", lambda url: 0)

    class A:
        all = False
        json = False
        score = False
        execute = True
        allow_replies = False
        quiet = True
        limit = 50
        max_replies = 10
        max_likes = 30
        max_follows = 5

    rc = notify_scored.run_scored(A(), "https://pds", "did:me", "jwt")
    assert rc == 0
    assert calls["follow"] == 1


def test_run_scored_relationship_follow_disabled_by_default(monkeypatch):
    reply_notif = {
        "reason": "reply",
        "indexedAt": "2099-01-01T00:00:00.000Z",
        "author": {"did": "did:plc:abc", "handle": "human.bsky.social"},
        "uri": "at://did:plc:abc/app.bsky.feed.post/xyz",
        "record": {"$type": "app.bsky.feed.post", "text": "replying to you"},
    }

    import bsky_cli.notify as notify_mod

    monkeypatch.setattr(notify_mod, "get_notifications", lambda *a, **k: [reply_notif])
    monkeypatch.setattr(notify_mod, "get_last_seen", lambda: None)
    monkeypatch.setattr(notify_mod, "save_last_seen", lambda ts: None)

    monkeypatch.setattr(
        notify_scored,
        "fetch_profile",
        lambda handle: {
            "handle": handle,
            "description": "I write software.",
            "createdAt": "2023-01-01T00:00:00.000Z",
            "postsCount": 100,
            "followersCount": 100,
            "followsCount": 100,
            "viewer": {"following": None},
        },
    )

    monkeypatch.setattr(notify_scored, "_load_relationship_tones", lambda: {"did:plc:abc": "friendly"})
    monkeypatch.setattr(notify_scored.interlocutors, "get_interlocutor", lambda did: type("I", (), {"total_count": 11})())
    monkeypatch.setattr(notify_scored, "_maybe", lambda p: True)

    calls = {"follow": 0}
    monkeypatch.setattr(notify_scored, "follow_handle", lambda handle: calls.__setitem__("follow", calls["follow"] + 1) or 0)
    monkeypatch.setattr(notify_scored, "like_url", lambda url: 0)

    class A:
        all = False
        json = False
        score = False
        execute = True
        allow_replies = False
        quiet = True
        limit = 50
        max_replies = 10
        max_likes = 30
        max_follows = 5

    rc = notify_scored.run_scored(A(), "https://pds", "did:me", "jwt")
    assert rc == 0
    assert calls["follow"] == 0


def test_run_scored_relationship_follow_for_reply(monkeypatch):
    reply_notif = {
        "reason": "reply",
        "indexedAt": "2099-01-01T00:00:00.000Z",
        "author": {"did": "did:plc:abc", "handle": "human.bsky.social"},
        "uri": "at://did:plc:abc/app.bsky.feed.post/xyz",
        "record": {"$type": "app.bsky.feed.post", "text": "replying to you"},
    }

    import bsky_cli.notify as notify_mod

    monkeypatch.setattr(notify_mod, "get_notifications", lambda *a, **k: [reply_notif])
    monkeypatch.setattr(notify_mod, "get_last_seen", lambda: None)
    monkeypatch.setattr(notify_mod, "save_last_seen", lambda ts: None)

    monkeypatch.setattr(
        notify_scored,
        "fetch_profile",
        lambda handle: {
            "handle": handle,
            "description": "I write software.",
            "createdAt": "2023-01-01T00:00:00.000Z",
            "postsCount": 100,
            "followersCount": 100,
            "followsCount": 100,
            "viewer": {"following": None},
        },
    )

    # Relationship >10, tone non-negative, maybe() true => follow should trigger
    import bsky_cli.config as config_mod

    _orig_get = config_mod.get
    monkeypatch.setattr(
        config_mod,
        "get",
        lambda key, default=None: True if key == "notify.relationship_follow.enabled" else _orig_get(key, default),
    )
    monkeypatch.setattr(notify_scored, "_load_relationship_tones", lambda: {"did:plc:abc": "friendly"})
    monkeypatch.setattr(notify_scored.interlocutors, "get_interlocutor", lambda did: type("I", (), {"total_count": 11})())
    monkeypatch.setattr(notify_scored, "_maybe", lambda p: True)

    calls = {"follow": 0}
    monkeypatch.setattr(notify_scored, "follow_handle", lambda handle: calls.__setitem__("follow", calls["follow"] + 1) or 0)
    monkeypatch.setattr(notify_scored, "like_url", lambda url: 0)

    class A:
        all = False
        json = False
        score = False
        execute = True
        allow_replies = False
        quiet = True
        limit = 50
        max_replies = 10
        max_likes = 30
        max_follows = 5

    rc = notify_scored.run_scored(A(), "https://pds", "did:me", "jwt")
    assert rc == 0
    assert calls["follow"] == 1
