"""Scored notifications triage (policy-driven)."""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .http import requests

from . import interlocutors
from .auth import load_from_pass, get_openrouter_pass_path
from .notify_actions import follow_handle, like_url, reply_to_url, quote_url
from .notify_scoring import decide_actions, score_notification
from .public_truth import truth_section


def fetch_profile(handle: str) -> dict | None:
    handle = handle.lstrip("@")
    try:
        r = requests.get(
            "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile",
            params={"actor": handle},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def _post_url_from_notification(n: dict) -> str | None:
    uri = n.get("uri", "")
    if uri.startswith("at://"):
        m = re.match(r"^at://([^/]+)/app\.bsky\.feed\.post/([^/]+)$", uri)
        if m:
            return f"https://bsky.app/profile/{m.group(1)}/post/{m.group(2)}"
    return None


def _maybe(prob: float) -> bool:
    # Use Mathieu's maybe.sh for stable semantics.
    try:
        r = subprocess.run(["/home/echo/scripts/maybe.sh", str(prob)], check=False)
        return r.returncode == 0
    except Exception:
        return False


def _relationship_follow_probability(total_interactions: int) -> float:
    """Return probabilistic follow chance based on interaction depth."""
    n = int(total_interactions or 0)
    if n > 50:
        return 0.3
    if n > 10:
        return 0.1
    return 0.0


def _is_negative_tone(tone: str | None) -> bool:
    t = (tone or "").strip().lower()
    if not t:
        return False
    negative_markers = [
        "negative", "hostile", "antagon", "toxic", "conflict", "aggressive", "blocked", "avoid",
    ]
    return any(m in t for m in negative_markers)


def _load_relationship_tones() -> dict[str, str]:
    """Best-effort load of actor relationship_tone from local DB."""
    try:
        from .auth import load_from_pass
        from .storage.db import open_db

        env = load_from_pass() or {}
        account_handle = (env.get("BSKY_HANDLE") or env.get("BSKY_EMAIL") or "").strip() or "default"
        try:
            conn = open_db(account_handle)
        except Exception:
            base = Path.home() / ".bsky-cli" / "accounts"
            dbs = sorted(base.glob("*/bsky.db"))
            if len(dbs) != 1:
                return {}
            conn = sqlite3.connect(dbs[0])
            conn.row_factory = sqlite3.Row

        rows = conn.execute(
            "SELECT did, relationship_tone FROM actors WHERE relationship_tone IS NOT NULL AND relationship_tone <> ''"
        ).fetchall()
        return {str(r["did"]): str(r["relationship_tone"]) for r in rows}
    except Exception:
        return {}


def _generate_reply_llm(*, their_text: str, our_text: str | None, history: str, author_handle: str) -> str | None:
    pass_path = get_openrouter_pass_path()
    env = load_from_pass(pass_path)
    if not env or "OPENROUTER_API_KEY" not in env:
        return None

    api_key = env["OPENROUTER_API_KEY"]

    public_truth = truth_section(max_chars=5000)

    prompt = f"""You are Echo (@echo.0mg.cc), an ops agent replying on BlueSky.
{public_truth}

## CONTEXT
Author: @{author_handle}

Their message:
{their_text}

Our prior post (if any):
{our_text or "(unknown)"}

{history}

## RULES
- Write ONE reply.
- <= 280 characters (STRICT)
- English only
- Be helpful and specific; avoid generic praise.
- If they asked a question, answer it.
- No private info.

Return ONLY JSON:
{{"text": "..."}}
"""

    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "google/gemini-3-flash-preview",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
            },
            timeout=60,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = "\n".join(content.split("\n")[1:-1])
        data = json.loads(content)
        text = str(data.get("text", "")).strip()
        if len(text) > 280:
            text = text[:277].rstrip() + "..."
        return text
    except Exception:
        return None


def _generate_quote_comment_llm(*, their_text: str, history: str, author_handle: str) -> str | None:
    """Generate short quote-repost commentary (<= 280)."""
    pass_path = get_openrouter_pass_path()
    env = load_from_pass(pass_path)
    if not env or "OPENROUTER_API_KEY" not in env:
        return None

    api_key = env["OPENROUTER_API_KEY"]

    public_truth = truth_section(max_chars=5000)

    prompt = f"""You are Echo (@echo.0mg.cc), writing a quote-repost comment.
{public_truth}

## CONTEXT
Quoted author: @{author_handle}
Quoted text:
{their_text}

{history}

## RULES
- Write ONE quote-repost comment (not a reply).
- <= 280 characters (STRICT)
- English only
- Add 1 concrete thought (agreement, extension, or a question).
- No generic praise.
- No private info.

Return ONLY JSON:
{{"text": "..."}}
"""

    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "google/gemini-3-flash-preview",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
            },
            timeout=60,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = "\n".join(content.split("\n")[1:-1])
        data = json.loads(content)
        text = str(data.get("text", "")).strip()
        if len(text) > 280:
            text = text[:277].rstrip() + "..."
        return text
    except Exception:
        return None


@dataclass
class Budgets:
    max_replies: int = 10
    max_likes: int = 30
    max_follows: int = 5

    replies: int = 0
    likes: int = 0
    follows: int = 0


def run_scored(args, pds: str, did: str, jwt: str) -> int:
    from .notify import get_notifications, get_last_seen, save_last_seen

    notifications = get_notifications(pds, jwt, limit=args.limit)

    last_seen = get_last_seen()
    if not args.all and last_seen:
        notifications = [n for n in notifications if n.get("indexedAt", "") > last_seen]

    if args.json and not getattr(args, "score", False) and not getattr(args, "execute", False):
        print(json.dumps({"notifications": notifications}, indent=2))
        return 0

    # Defaults come from CLI flags, then config keys, then hard-coded fallbacks.
    from .config import get

    budgets = Budgets(
        max_replies=int(getattr(args, "max_replies", None) or get("notify.budgets.max_replies", 10)),
        max_likes=int(getattr(args, "max_likes", None) or get("notify.budgets.max_likes", 30)),
        max_follows=int(getattr(args, "max_follows", None) or get("notify.budgets.max_follows", 5)),
    )
    relationship_follow_enabled = bool(get("notify.relationship_follow.enabled", False))

    # Score + decide
    tone_by_did = _load_relationship_tones()
    scored_rows = []
    for n in notifications:
        author = n.get("author", {})
        handle = author.get("handle") or ""
        prof = fetch_profile(handle) or {"handle": handle}

        inter = interlocutors.get_interlocutor(author.get("did", ""))
        rel_total = inter.total_count if inter else 0

        s = score_notification(n, profile=prof, relationship_total=rel_total)
        acts = decide_actions(s)
        url = _post_url_from_notification(n)

        scored_rows.append(
            {
                "notification": n,
                "profile": prof,
                "score": s,
                "actions": acts,
                "url": url,
                "rel_total": rel_total,
                "relationship_tone": tone_by_did.get(author.get("did", ""), ""),
            }
        )

    scored_rows.sort(key=lambda r: r["score"]["score"], reverse=True)

    # Human report
    if (getattr(args, "score", False) or not getattr(args, "execute", False)) and not getattr(args, "quiet", False):
        print(f"=== BlueSky Notifications (scored) — {len(scored_rows)} new ===\n")
        for r in scored_rows:
            n = r["notification"]
            a = (n.get("author") or {})
            reason = n.get("reason")
            text = ((n.get("record") or {}).get("text") or "").replace("\n", " ")
            s = r["score"]
            acts = r["actions"]
            print(
                f"[{reason}] @{a.get('handle')} score={s['score']:.1f} "
                f"(author={s['author_score']:.1f} rel={s['relationship_score']:.1f} "
                f"content={s['content_quality_score']:.1f} ctx={s['context_score']:.1f}) "
                f"-> like={acts['like']} reply={acts['reply']} requote={acts.get('requote', False)}"
            )
            if text:
                print(f"  \"{text[:240]}{'...' if len(text) > 240 else ''}\"")
            if r.get("url"):
                print(f"  {r['url']}")
            print()

    if not getattr(args, "execute", False):
        # Update last seen to avoid re-printing forever
        newest = max((n.get("indexedAt", "") for n in notifications), default="")
        if newest:
            save_last_seen(newest)
        return 0

    # Execute actions
    reached = []
    for r in scored_rows:
        n = r["notification"]
        reason = n.get("reason")

        # follow-back can happen without a post URL
        if reason == "follow":
            s = r["score"]
            prof = r.get("profile") or {}
            if budgets.follows < budgets.max_follows and (s.get("author_score", 0) >= 12):
                follow_handle(prof.get("handle") or (n.get("author") or {}).get("handle") or "")
                budgets.follows += 1
            elif budgets.follows >= budgets.max_follows:
                reached.append("follows")

        # Relationship-based probabilistic follow on reply/repost activity.
        if relationship_follow_enabled and reason in {"reply", "repost"}:
            rel_total = int(r.get("rel_total") or 0)
            rel_tone = r.get("relationship_tone") or ""
            prob = _relationship_follow_probability(rel_total)
            prof = r.get("profile") or {}
            already_following = bool(((prof.get("viewer") or {}).get("following")))
            if prob > 0 and not _is_negative_tone(rel_tone) and not already_following:
                if budgets.follows < budgets.max_follows:
                    if _maybe(prob):
                        follow_handle(prof.get("handle") or (n.get("author") or {}).get("handle") or "")
                        budgets.follows += 1
                else:
                    reached.append("follows")

        url = r.get("url")
        if not url:
            continue

        acts = r["actions"]
        s = r["score"]

        # Like
        if acts.get("like") and budgets.likes < budgets.max_likes:
            like_url(url)
            budgets.likes += 1
        elif acts.get("like") and budgets.likes >= budgets.max_likes:
            reached.append("likes")

        # Requote (quote-repost) — only when content quality is high
        if acts.get("requote") and float(s.get("content_quality_score") or 0) >= 20:
            if budgets.replies >= budgets.max_replies:
                reached.append("replies")
            elif _maybe(0.5):
                author = n.get("author", {})
                their_text = (n.get("record") or {}).get("text", "") or ""
                hist = interlocutors.format_context_for_llm(author.get("did", ""), max_interactions=2)
                comment = _generate_quote_comment_llm(
                    their_text=their_text,
                    history=hist,
                    author_handle=author.get("handle", ""),
                )
                if comment:
                    # quote-repost + like already handled above
                    quote_url(url, comment)
                    budgets.replies += 1

        # (duplicate follow handling removed)

        # replies are gated behind allow_replies
        if acts.get("reply") and getattr(args, "allow_replies", False):
            if budgets.replies < budgets.max_replies:
                author = n.get("author", {})
                their_text = (n.get("record") or {}).get("text", "") or ""
                # best-effort get history context
                hist = interlocutors.format_context_for_llm(author.get("did", ""), max_interactions=3)
                reply = _generate_reply_llm(
                    their_text=their_text,
                    our_text=None,
                    history=hist,
                    author_handle=author.get("handle", ""),
                )
                if reply:
                    reply_to_url(url, reply)
                    budgets.replies += 1
            else:
                reached.append("replies")

    if reached:
        reached = sorted(set(reached))
        print(f"⚠️  Budgets reached: {', '.join(reached)}")

    if not getattr(args, "quiet", False):
        print(
            f"=== Actions executed ===\n"
            f"likes: {budgets.likes}/{budgets.max_likes}\n"
            f"replies(+quotes): {budgets.replies}/{budgets.max_replies}\n"
            f"follows: {budgets.follows}/{budgets.max_follows}\n"
        )

    newest = max((n.get("indexedAt", "") for n in notifications), default="")
    if newest:
        save_last_seen(newest)

    return 0
