"""Notification scoring + action decisions.

Goal: score each notification based on author quality, relationship history,
content quality, and context. Then decide which actions to take.

This module is intentionally heuristic and configurable.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone


DEFAULT_PSEUDOSCIENCE_PATTERNS = [
    r"\barica\b",
    r"\benneagram\b",
    r"\bautodiagnosis\b",
    r"\bmbti\b",
    r"\bhexaco\b",
]


def _age_days(created_at: str | None) -> int | None:
    if not created_at:
        return None
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return None


def is_probable_bot(profile: dict) -> bool:
    """Heuristic bot detector.

    We deliberately treat 'legit' bots as bots too; caller may decide penalties.
    """
    desc = (profile.get("description") or "").lower()
    handle = (profile.get("handle") or "").lower()
    name = (profile.get("displayName") or "").lower()

    bot_markers = [
        "ai agent",
        "bot",
        "automated",
        "auto-post",
        "autopost",
        "llm",
    ]

    if any(m in desc for m in bot_markers):
        return True

    if handle.endswith("bot") or handle.endswith("bot.bsky.social"):
        return True

    if "bot" in name and "robot" in name:
        return True

    return False


def score_author(profile: dict, *, assume_bot: bool | None = None) -> float:
    """Return author_score in [0, 30], applying bot penalty when requested."""
    desc = (profile.get("description") or "").strip()
    posts = int(profile.get("postsCount") or 0)
    followers = int(profile.get("followersCount") or 0)
    follows = int(profile.get("followsCount") or 0)

    age = _age_days(profile.get("createdAt"))

    score = 0.0

    # Bio substance
    if len(desc) >= 40:
        score += 10
    elif len(desc) >= 10:
        score += 6

    # Account age
    if age is not None:
        if age >= 30:
            score += 8
        elif age >= 7:
            score += 5
        elif age >= 2:
            score += 2

    # Some original activity
    if posts >= 50:
        score += 7
    elif posts >= 10:
        score += 4
    elif posts >= 1:
        score += 1

    # Anti spam ratio: following massively with low followers
    if follows > 0 and followers > 0:
        ratio = follows / followers
        if ratio > 50:
            score -= 12
        elif ratio > 15:
            score -= 7
        elif ratio > 8:
            score -= 3

    score = max(0.0, min(30.0, score))

    if assume_bot is None:
        assume_bot = is_probable_bot(profile)

    if assume_bot:
        score *= 0.5

    return score


def score_relationship(total_interactions: int | None) -> float:
    """relationship_score in [0, 25]."""
    if not total_interactions:
        return 0.0
    # log-ish scaling
    return max(0.0, min(25.0, 10.0 * math.log10(total_interactions + 1) + 5.0))


def score_notification_text(text: str) -> float:
    """content_quality_score in [0, 25] with heavy penalties for pseudo-science/proselytism."""
    t = (text or "").strip()
    if not t:
        return 0.0

    low = t.lower()

    # Heavy penalty keywords
    for pat in DEFAULT_PSEUDOSCIENCE_PATTERNS:
        if re.search(pat, low):
            return 0.0

    score = 0.0

    # Length / substance
    if len(t) >= 180:
        score += 10
    elif len(t) >= 80:
        score += 7
    elif len(t) >= 30:
        score += 4

    # Questions tend to be worth engaging
    if "?" in t:
        score += 6

    # Links often reduce quality (except legit citations) — mild penalty per link
    link_count = len(re.findall(r"https?://", t))
    score -= min(6.0, 2.0 * link_count)

    # Spammy caps / shouting
    if sum(1 for c in t if c.isupper()) > 0.6 * max(1, len(t)):
        score -= 6

    return max(0.0, min(25.0, score))


def score_context(reason: str) -> float:
    """context_score in [0, 20]"""
    if reason in {"reply", "mention", "quote"}:
        return 15.0
    if reason == "follow":
        return 8.0
    if reason in {"like", "repost"}:
        return 3.0
    return 0.0


def score_notification(n: dict, *, profile: dict, relationship_total: int | None) -> dict:
    reason = n.get("reason", "")
    text = (n.get("record") or {}).get("text", "") or ""

    author_score = score_author(profile)
    relationship_score = score_relationship(relationship_total)
    content_quality_score = score_notification_text(text)
    context_score = score_context(reason)

    score = author_score + relationship_score + content_quality_score + context_score
    score = max(0.0, min(100.0, score))

    question_clear = "?" in text and len(text) >= 20
    adds_value = content_quality_score >= 12

    return {
        "score": score,
        "author_score": author_score,
        "relationship_score": relationship_score,
        "content_quality_score": content_quality_score,
        "context_score": context_score,
        "question_clear": question_clear,
        "adds_value": adds_value,
        "is_bot": is_probable_bot(profile),
    }


def decide_actions(s: dict) -> dict:
    """Return {like, reply, requote} booleans based on thresholds."""
    score = float(s.get("score") or 0)
    question_clear = bool(s.get("question_clear"))
    adds_value = bool(s.get("adds_value"))

    if score >= 80:
        return {"like": True, "reply": True, "requote": False}

    if 60 <= score < 80:
        return {"like": True, "reply": bool(question_clear), "requote": False}

    if 40 <= score < 60:
        return {"like": bool(adds_value), "reply": False, "requote": False}

    return {"like": False, "reply": False, "requote": False}
