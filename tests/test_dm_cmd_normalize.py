from __future__ import annotations

from types import SimpleNamespace


def test_dm_cmd_normalizes_newlines_by_default(monkeypatch, capsys):
    from bsky_cli import dm_cmd

    captured = {}

    def fake_send(handle: str, text: str):
        captured["handle"] = handle
        captured["text"] = text
        return {"ok": True}

    monkeypatch.setattr(dm_cmd, "send_dm_to_handle", fake_send)

    args = SimpleNamespace(handle="penny.hailey.at", text="a\n\n  b\n c  ", dry_run=False, raw=False)
    rc = dm_cmd.run(args)
    assert rc == 0

    assert captured["handle"] == "penny.hailey.at"
    assert captured["text"] == "a — b — c"

    out = capsys.readouterr().out
    assert "✓ Sent DM" in out


def test_dm_cmd_raw_preserves_text(monkeypatch):
    from bsky_cli import dm_cmd

    captured = {}

    def fake_send(handle: str, text: str):
        captured["text"] = text
        return {"ok": True}

    monkeypatch.setattr(dm_cmd, "send_dm_to_handle", fake_send)

    args = SimpleNamespace(handle="penny.hailey.at", text="a\n\nb", dry_run=False, raw=True)
    dm_cmd.run(args)

    assert captured["text"] == "a\n\nb"
