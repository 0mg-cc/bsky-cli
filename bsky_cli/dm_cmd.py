"""DM command for BlueSky CLI."""
from __future__ import annotations

from __future__ import annotations

import re

from .dm import send_dm_to_handle


def _normalize_dm_text(text: str) -> str:
    """Normalize DM text for BlueSky chat clients.

    In practice, many clients render newlines inconsistently. Default behavior:
    - trim
    - collapse multi-line input into a single line using " — " separators

    Use `bsky dm --raw` to bypass this normalization.
    """

    text = (text or "").strip()
    if not text:
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Split and join non-empty lines.
    parts = [p.strip() for p in text.split("\n")]
    parts = [p for p in parts if p]

    # If it's effectively single-line already, keep as-is.
    if len(parts) <= 1:
        return parts[0]

    out = " — ".join(parts)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out


def run(args) -> int:
    text = args.text
    if not getattr(args, "raw", False):
        text = _normalize_dm_text(text)

    if args.dry_run:
        print(f"[dry-run] DM to @{args.handle}: {text}")
        return 0

    send_dm_to_handle(args.handle, text)
    print(f"✓ Sent DM to @{args.handle}")
    return 0
