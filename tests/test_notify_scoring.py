from bsky_cli.notify_scoring import (
    score_author,
    is_probable_bot,
    score_notification_text,
    score_notification,
    decide_actions,
)


def test_is_probable_bot_detects_ai_agent_bio():
    profile = {
        "description": "AI agent and systems gardener.",
        "handle": "clankops.bsky.social",
    }
    assert is_probable_bot(profile) is True


def test_score_author_halves_when_bot():
    profile = {
        "handle": "botty.bsky.social",
        "description": "AI agent.",
        "createdAt": "2024-01-01T00:00:00.000Z",
        "postsCount": 100,
        "followersCount": 100,
        "followsCount": 100,
    }
    raw = score_author(profile, assume_bot=False)
    half = score_author(profile, assume_bot=True)
    assert half == raw * 0.5


def test_score_notification_text_penalizes_pseudoscience_keywords():
    txt = "Autodiagnosis is the original precise method from Arica School. enneagram"
    s = score_notification_text(txt)
    assert s < 5


def test_score_notification_returns_0_100():
    n = {
        "reason": "reply",
        "record": {"text": "Great point — do you have a link?"},
        "author": {"did": "did:plc:123", "handle": "user.bsky.social"},
    }
    profile = {
        "handle": "user.bsky.social",
        "description": "Human.",
        "createdAt": "2023-01-01T00:00:00.000Z",
        "postsCount": 50,
        "followersCount": 50,
        "followsCount": 50,
    }
    out = score_notification(n, profile=profile, relationship_total=5)
    assert 0 <= out["score"] <= 100


def test_decide_actions_thresholds():
    # >= 80 -> reply+like
    acts = decide_actions({"score": 85, "question_clear": True})
    assert acts["like"] is True and acts["reply"] is True

    # 60..79 -> like, optional reply if question
    acts = decide_actions({"score": 65, "question_clear": False})
    assert acts["like"] is True and acts["reply"] is False

    acts = decide_actions({"score": 65, "question_clear": True})
    assert acts["like"] is True and acts["reply"] is True

    # 40..59 -> like only if adds value
    acts = decide_actions({"score": 50, "adds_value": False, "question_clear": True})
    assert acts["like"] is False and acts["reply"] is False
