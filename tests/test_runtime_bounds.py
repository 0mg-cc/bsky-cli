from types import SimpleNamespace

from bsky_cli import engage, appreciate, discover


def _fake_session():
    return ("https://pds.example", "did:plc:me", "jwt", "me.bsky.social")


def test_engage_respects_max_runtime_seconds(monkeypatch, capsys):
    monkeypatch.setattr(engage, "get_session", _fake_session)
    monkeypatch.setattr(engage, "load_state", lambda: {"replied_posts": [], "replied_accounts_today": []})
    monkeypatch.setattr(engage, "load_conversations", lambda: {})

    rc = engage.run(SimpleNamespace(dry_run=True, hours=12, max_runtime_seconds=0))

    assert rc != 0
    out = capsys.readouterr().out
    assert "Timed out" in out
    assert "phase: collect" in out


def test_appreciate_respects_max_runtime_seconds(monkeypatch, capsys):
    monkeypatch.setattr(appreciate, "get_session", _fake_session)
    monkeypatch.setattr(appreciate, "load_state", lambda: {"liked_posts": [], "quoted_posts": []})

    rc = appreciate.run(SimpleNamespace(dry_run=True, hours=12, max=5, max_runtime_seconds=0))

    assert rc != 0
    out = capsys.readouterr().out
    assert "Timed out" in out
    assert "phase: collect" in out


def test_discover_respects_max_runtime_seconds(monkeypatch, capsys):
    monkeypatch.setattr(discover, "get_session", _fake_session)
    monkeypatch.setattr(discover, "load_state", lambda: {})

    rc = discover.run(SimpleNamespace(mode="follows", dry_run=True, max=10, max_runtime_seconds=0))

    assert rc != 0
    out = capsys.readouterr().out
    assert "Timed out" in out
    assert "phase: collect" in out


def test_engage_prints_phase_progression(monkeypatch, capsys):
    monkeypatch.setattr(engage, "get_session", _fake_session)
    monkeypatch.setattr(engage, "load_state", lambda: {"replied_posts": [], "replied_accounts_today": []})
    monkeypatch.setattr(engage, "load_conversations", lambda: {})
    monkeypatch.setattr(engage, "create_default_pipeline", lambda did: SimpleNamespace(process=lambda posts, state: posts))
    monkeypatch.setattr(engage, "get_follows", lambda pds, jwt, did: [])
    monkeypatch.setattr(engage, "get_replies_to_our_posts", lambda *a, **k: [])

    rc = engage.run(SimpleNamespace(dry_run=True, hours=12, max_runtime_seconds=30))

    assert rc == 0
    out = capsys.readouterr().out
    assert "Phase: collect" in out


def test_discover_times_out_during_mode_execution(monkeypatch, capsys):
    class FakeGuard:
        def __init__(self, _seconds):
            self.calls = 0

        def check(self, phase):
            self.calls += 1
            if self.calls >= 5:
                print(f"⏱️ Timed out after 30s during phase: {phase}")
                return True
            return False

    monkeypatch.setattr(discover, "RuntimeGuard", FakeGuard)
    monkeypatch.setattr(discover, "get_session", _fake_session)
    monkeypatch.setattr(
        discover,
        "load_state",
        lambda: {"follows_scanned": {}, "repost_authors": {}, "already_followed": []},
    )
    monkeypatch.setattr(
        discover,
        "get_follows",
        lambda _pds, _jwt, _actor, **_kwargs: [{"did": "did:plc:a", "handle": "a.test"}],
    )
    monkeypatch.setattr(discover.random, "sample", lambda seq, n: list(seq)[:n])

    rc = discover.run(SimpleNamespace(mode="follows", dry_run=True, max=10, max_runtime_seconds=30))

    assert rc == discover.TIMEOUT_EXIT_CODE
    out = capsys.readouterr().out
    assert "Timed out" in out
