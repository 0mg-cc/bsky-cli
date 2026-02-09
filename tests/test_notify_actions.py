from bsky_cli import notify_actions


def test_like_url_includes_undo_field(monkeypatch):
    seen = {}

    def fake_like_run(args):
        # like.run reads args.undo unconditionally
        assert hasattr(args, "undo")
        assert args.undo is False
        seen["ok"] = True
        return 0

    monkeypatch.setattr(notify_actions, "like_run", fake_like_run)
    notify_actions.like_url("https://bsky.app/profile/user/post/abc")
    assert seen.get("ok") is True
