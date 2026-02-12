"""Schedule short follow-up notification polls after write actions."""
from __future__ import annotations

import subprocess


def schedule_notification_followups(delays_seconds: tuple[int, ...] = (120, 300, 600, 900)) -> None:
    """Spawn detached checks at +2/+5/+10/+15 minutes (default).

    Best-effort fire-and-forget. Failures are intentionally swallowed.
    """
    base_cmd = (
        "cd /home/echo/projects/bsky-cli && "
        "uv run bsky notify --execute --quiet --allow-replies "
        "--max-replies 10 --max-likes 30 --max-follows 5 --limit 60 --no-dm"
    )

    for delay in delays_seconds:
        try:
            shell_cmd = f"sleep {int(delay)}; {base_cmd} >/dev/null 2>&1"
            subprocess.Popen(
                ["bash", "-lc", shell_cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            # Non-blocking helper: never fail caller on scheduling error
            pass
