from __future__ import annotations

from types import SimpleNamespace


def test_threads_migrate_state_command_calls_migration(monkeypatch, tmp_path):
    from bsky_cli.threads_mod import commands

    called = {}

    def _fake_migrate(path, archive_json=False, dry_run=False):
        called["path"] = path
        called["archive_json"] = archive_json
        called["dry_run"] = dry_run
        return {"migrated": True}

    monkeypatch.setattr(commands, "migrate_threads_state_from_json", _fake_migrate)

    legacy = tmp_path / "legacy.json"
    legacy.write_text("{}")

    args = SimpleNamespace(
        threads_command="migrate-state",
        from_json=str(legacy),
        archive_json=True,
        dry_run=True,
    )

    rc = commands.run(args)
    assert rc == 0

    assert called["path"] == legacy
    assert called["archive_json"] is True
    assert called["dry_run"] is True
