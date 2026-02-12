"""Schedule adaptive follow-up notification polls after write actions.

Behavior:
- Start checks at +2/+5/+10/+15 minutes.
- If a *new reply* is found during a check, restart the sequence from +2.
- Intended to keep near-real-time responsiveness right after posting/replying.
"""
from __future__ import annotations

import json
import subprocess
import time
from typing import Iterable


DEFAULT_DELAYS = (120, 300, 600, 900)  # +2 / +5 / +10 / +15 min


def _run(cmd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-lc", cmd],
        capture_output=True,
        text=True,
        check=False,
    )


def _fetch_notifications(limit: int = 60) -> list[dict]:
    cmd = (
        "cd /home/echo/projects/bsky-cli && "
        f"uv run bsky notify --json --limit {int(limit)} --no-dm"
    )
    cp = _run(cmd)
    if cp.returncode != 0:
        return []
    try:
        data = json.loads(cp.stdout or "{}")
        return data.get("notifications", []) if isinstance(data, dict) else []
    except Exception:
        return []


def _run_notify_execute() -> None:
    cmd = (
        "cd /home/echo/projects/bsky-cli && "
        "uv run bsky notify --execute --quiet --allow-replies "
        "--max-replies 10 --max-likes 30 --max-follows 5 --limit 60 --no-dm"
    )
    _run(cmd)


def _reply_uris(notifs: Iterable[dict]) -> set[str]:
    out: set[str] = set()
    for n in notifs:
        if (n.get("reason") or "") == "reply":
            uri = n.get("uri")
            if uri:
                out.add(uri)
    return out


def run_followup_worker(
    delays_seconds: tuple[int, ...] = DEFAULT_DELAYS,
    *,
    max_restarts: int = 3,
) -> None:
    """Run adaptive follow-up checks in-process (blocking)."""
    seen_replies: set[str] = set()
    restart_count = 0
    idx = 0

    while idx < len(delays_seconds):
        time.sleep(int(delays_seconds[idx]))

        before = _fetch_notifications(limit=60)
        current_replies = _reply_uris(before)
        new_reply_found = any(uri not in seen_replies for uri in current_replies)
        seen_replies |= current_replies

        _run_notify_execute()

        if new_reply_found and restart_count < max_restarts:
            restart_count += 1
            idx = 0  # restart from +2
            continue

        idx += 1


def schedule_notification_followups(delays_seconds: tuple[int, ...] = DEFAULT_DELAYS) -> None:
    """Spawn a detached adaptive follow-up worker (best-effort)."""
    delays = ",".join(str(int(d)) for d in delays_seconds)
    py = (
        "from bsky_cli.followup_notifications import run_followup_worker;"
        f"run_followup_worker(({delays},))"
    )
    try:
        subprocess.Popen(
            ["bash", "-lc", f"cd /home/echo/projects/bsky-cli && uv run python -c '{py}' >/dev/null 2>&1"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        pass
