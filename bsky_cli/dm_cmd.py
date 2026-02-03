"""DM command for BlueSky CLI."""
from __future__ import annotations

from .dm import send_dm_to_handle


def run(args) -> int:
    if args.dry_run:
        print(f"[dry-run] DM to @{args.handle}: {args.text}")
        return 0

    send_dm_to_handle(args.handle, args.text)
    print(f"✓ Sent DM to @{args.handle}")
    return 0
