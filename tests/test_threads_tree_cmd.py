from __future__ import annotations

from types import SimpleNamespace


def test_threads_tree_dispatch_calls_cmd_tree(monkeypatch):
    from bsky_cli.threads_mod import commands

    called = {}

    def _fake_cmd_tree(args):
        called["target"] = args.target
        return 0

    monkeypatch.setattr(commands, "cmd_tree", _fake_cmd_tree, raising=False)

    args = SimpleNamespace(
        threads_command="tree",
        target="https://bsky.app/profile/alice.bsky.social/post/abc123",
        depth=6,
        snippet=90,
        mine_only=False,
    )

    rc = commands.run(args)
    assert rc == 0
    assert called["target"].endswith("/abc123")


def test_cmd_tree_prints_ascii_tree(monkeypatch, capsys):
    from bsky_cli.threads_mod import commands

    monkeypatch.setattr(
        commands,
        "get_session",
        lambda: ("https://pds.example", "did:plc:me", "jwt", "me.bsky.social"),
    )

    fake_thread = {
        "post": {
            "uri": "at://did:plc:root/app.bsky.feed.post/root",
            "author": {"handle": "root.bsky.social", "did": "did:plc:root"},
            "record": {"text": "Root post"},
        },
        "replies": [
            {
                "post": {
                    "uri": "at://did:plc:me/app.bsky.feed.post/r1",
                    "author": {"handle": "me.bsky.social", "did": "did:plc:me"},
                    "record": {"text": "My reply"},
                },
                "replies": [],
            },
            {
                "post": {
                    "uri": "at://did:plc:other/app.bsky.feed.post/r2",
                    "author": {"handle": "other.bsky.social", "did": "did:plc:other"},
                    "record": {"text": "Other reply"},
                },
                "replies": [],
            },
        ],
    }

    monkeypatch.setattr(commands, "get_thread", lambda pds, jwt, uri, depth=6: fake_thread)

    args = SimpleNamespace(
        threads_command="tree",
        target="https://bsky.app/profile/root.bsky.social/post/root",
        depth=6,
        snippet=90,
        mine_only=False,
    )

    rc = commands.cmd_tree(args)
    out = capsys.readouterr().out

    assert rc == 0
    assert "root.bsky.social" in out
    assert "My reply" in out
    assert "Other reply" in out
    assert "└─" in out or "├─" in out
