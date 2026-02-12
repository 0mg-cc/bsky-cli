from __future__ import annotations

from types import SimpleNamespace


def test_cmd_list_skips_corrupt_thread_entries(monkeypatch, capsys):
    from bsky_cli.threads_mod import commands

    state = {
        "threads": {
            "at://broken": {"root_url": "https://bsky.app/profile/x/post/y"},
            "at://ok": {
                "root_uri": "at://ok",
                "root_url": "https://bsky.app/profile/alice/post/ok",
                "root_author_handle": "alice.bsky.social",
                "root_author_did": "did:plc:alice",
                "main_topics": ["ai"],
                "root_text": "hello",
                "overall_score": 55,
                "branches": {},
                "total_our_replies": 1,
                "created_at": "2026-02-12T00:00:00Z",
                "last_activity_at": "2026-02-12T00:10:00Z",
            },
        }
    }

    monkeypatch.setattr(commands, "load_threads_state", lambda: state)

    original_from_dict = commands.TrackedThread.from_dict

    def _maybe_broken(payload):
        if payload is state["threads"]["at://broken"]:
            raise KeyError("root_uri")
        return original_from_dict(payload)

    monkeypatch.setattr(commands.TrackedThread, "from_dict", _maybe_broken)

    rc = commands.cmd_list(SimpleNamespace())
    out = capsys.readouterr().out

    assert rc == 0
    assert "alice.bsky.social" in out
