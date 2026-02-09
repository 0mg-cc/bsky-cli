"""Helpers for acting on notifications (like/follow/reply/quote)."""

from __future__ import annotations

import re

from .auth import get_session
from .follow import run as follow_run
from .like import run as like_run
from .reply import run as reply_run
from .post import run as post_run


def post_url_from_uri(uri: str) -> str | None:
    m = re.match(r"^at://([^/]+)/app\.bsky\.feed\.post/([^/]+)$", uri or "")
    if not m:
        return None
    return f"https://bsky.app/profile/{m.group(1)}/post/{m.group(2)}"


def like_url(url: str) -> int:
    class A:
        post_url = url
        dry_run = False
        undo = False
    return like_run(A())


def follow_handle(handle: str) -> int:
    class A:
        handle = handle
        dry_run = False
    return follow_run(A())


def reply_to_url(url: str, text: str) -> int:
    class A:
        post_url = url
        text = text
        dry_run = False
    return reply_run(A())


def quote_url(url: str, text: str) -> int:
    class A:
        text = text
        embed = None
        quote = url
        allow_repeat = False
        dry_run = False
    return post_run(A())
