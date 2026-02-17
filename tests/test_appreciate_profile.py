from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from bsky_cli import appreciate


def _fake_session():
    return ("https://pds.test", "did:plc:me", "jwt", "echo.test")


def test_appreciate_profile_writes_jsonl(monkeypatch, tmp_path):
    out = tmp_path / "profile.jsonl"

    monkeypatch.setattr(appreciate, "get_session", _fake_session)
    monkeypatch.setattr(appreciate, "load_state", lambda: {"liked_posts": [], "quoted_posts": []})
    monkeypatch.setattr(appreciate, "get_follows", lambda *a, **k: [{"did": "did:plc:a", "handle": "a.test"}])
    monkeypatch.setattr(appreciate, "get_author_feed", lambda *a, **k: [])
    monkeypatch.setattr(appreciate, "filter_recent_posts", lambda *a, **k: [])

    rc = appreciate.run(
        SimpleNamespace(
            dry_run=True,
            hours=12,
            max=5,
            max_runtime_seconds=1800,
            profile=True,
            profile_output=str(out),
        )
    )

    assert rc == 0
    assert out.exists(), "profile mode should always write a JSONL trace"

    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows, "profile file should contain at least one event"
    assert any(r.get("event") == "run_summary" for r in rows)


def test_appreciate_profile_logs_collect_calls(monkeypatch, tmp_path):
    out = tmp_path / "profile.jsonl"

    monkeypatch.setattr(appreciate, "get_session", _fake_session)
    monkeypatch.setattr(appreciate, "load_state", lambda: {"liked_posts": [], "quoted_posts": []})
    monkeypatch.setattr(appreciate, "get_follows", lambda *a, **k: [{"did": "did:plc:a", "handle": "a.test"}])
    monkeypatch.setattr(appreciate, "filter_recent_posts", lambda *a, **k: [])

    def fake_feed(*_a, **_k):
        return []

    monkeypatch.setattr(appreciate, "get_author_feed", fake_feed)

    rc = appreciate.run(
        SimpleNamespace(
            dry_run=True,
            hours=12,
            max=5,
            max_runtime_seconds=1800,
            profile=True,
            profile_output=str(out),
        )
    )

    assert rc == 0
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line.strip()]
    collect_events = [r for r in rows if r.get("event") == "collect_author_feed"]
    assert collect_events, "collect phase should log per-author feed timings in profile mode"
