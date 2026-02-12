"""Public truth grounding for publishing prompts."""
from __future__ import annotations

from pathlib import Path


def load_public_about_me(max_chars: int = 6000) -> str:
    """Load PUBLIC_ABOUT_ME.md for LLM grounding (best-effort).

    Returns empty string if unavailable.
    """
    candidates = [
        Path.home() / "personas/echo/PUBLIC_ABOUT_ME.md",
        Path.cwd() / "PUBLIC_ABOUT_ME.md",
    ]
    for p in candidates:
        try:
            if p.exists() and p.is_file():
                txt = p.read_text(encoding="utf-8", errors="ignore").strip()
                return txt[: max(500, int(max_chars))]
        except Exception:
            continue
    return ""


def truth_section(max_chars: int = 6000) -> str:
    txt = load_public_about_me(max_chars=max_chars)
    if not txt:
        return ""
    return (
        "\n## PUBLIC TRUTH CHECK (must stay aligned)\n"
        "The following is the public source of truth about Echo. Do not contradict it.\n\n"
        f"{txt}\n"
    )
