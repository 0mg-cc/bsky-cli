from types import SimpleNamespace
from unittest.mock import patch, MagicMock

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
    monkeypatch.setattr(engage, "get_follows", lambda pds, jwt, did, **_kw: [])
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


# --- State persistence on timeout regression tests ---


class _PhaseTimeoutGuard:
    """Guard that allows all phases through except times out on 2nd 'act' check.

    This simulates: pre-loop act check passes, first in-loop act check → timeout.
    Engage/appreciate pre-dispatch: collect(1) score(1) decide(1) act(1) = 4 checks,
    then in-loop act check → timeout.
    """
    def __init__(self, _seconds=None):
        self._act_calls = 0

    def check(self, phase):
        if phase == "act":
            self._act_calls += 1
            if self._act_calls >= 2:
                print(f"⏱️ Timed out after 30s during phase: {phase}")
                return True
        return False


def _make_fake_post():
    from dataclasses import dataclass, field as df
    return engage.Post(
        uri="at://did:plc:a/app.bsky.feed.post/1",
        cid="cid1",
        text="hello world",
        author_did="did:plc:a",
        author_handle="a.test",
        created_at="2026-02-11T12:00:00Z",
    )


def test_engage_saves_state_on_act_timeout(monkeypatch, capsys):
    """PR #16 review: engage must persist state when timeout fires during act phase."""
    saved = {"state": False, "convos": False}

    def fake_save_state(s):
        saved["state"] = True

    def fake_save_conversations(c):
        saved["convos"] = True

    fake_post = _make_fake_post()

    monkeypatch.setattr(engage, "get_session", _fake_session)
    monkeypatch.setattr(engage, "load_state", lambda: {"replied_posts": [], "replied_accounts_today": []})
    monkeypatch.setattr(engage, "load_conversations", lambda: {})
    monkeypatch.setattr(engage, "create_default_pipeline", lambda did: SimpleNamespace(process=lambda posts, state: posts))
    # Provide one follow so the collect loop runs
    monkeypatch.setattr(engage, "get_follows", lambda pds, jwt, did, **_kw: [{"did": "did:plc:a", "handle": "a.test"}])
    monkeypatch.setattr(engage, "get_author_feed", lambda pds, jwt, actor, limit=10: [])
    monkeypatch.setattr(engage, "filter_recent_posts", lambda feed, hours=12: [fake_post])
    monkeypatch.setattr(engage, "get_replies_to_our_posts", lambda *a, **k: [])
    monkeypatch.setattr(
        engage,
        "select_posts_with_llm",
        lambda candidates, state, dry_run=False: [
            {"uri": fake_post.uri, "cid": fake_post.cid, "author_handle": "a.test",
             "author_did": "did:plc:a", "reply": "nice!", "reason": "test"}
        ],
    )
    monkeypatch.setattr(engage, "save_state", fake_save_state)
    monkeypatch.setattr(engage, "save_conversations", fake_save_conversations)
    monkeypatch.setattr(engage, "RuntimeGuard", _PhaseTimeoutGuard)

    rc = engage.run(SimpleNamespace(dry_run=False, hours=12, max_runtime_seconds=30))

    assert rc == engage.TIMEOUT_EXIT_CODE
    assert saved["state"], "engage must save state on timeout"
    assert saved["convos"], "engage must save conversations on timeout"
    assert "partial state saved" in capsys.readouterr().out.lower()


def test_appreciate_saves_state_on_act_timeout(monkeypatch, capsys):
    """PR #16 review: appreciate must persist state when timeout fires during act phase."""
    saved = {"state": False}

    def fake_save_state(s):
        saved["state"] = True

    monkeypatch.setattr(appreciate, "get_session", _fake_session)
    monkeypatch.setattr(appreciate, "load_state", lambda: {"liked_posts": [], "quoted_posts": []})
    # Provide one follow + feed data so collect phase succeeds
    monkeypatch.setattr(appreciate, "get_follows", lambda pds, jwt, did, **_kw: [{"did": "did:plc:a", "handle": "a.test"}])
    monkeypatch.setattr(appreciate, "get_author_feed", lambda pds, jwt, did, limit=30: [])
    monkeypatch.setattr(appreciate, "filter_recent_posts", lambda feed, hours=12: [
        {"uri": "at://did:plc:a/app.bsky.feed.post/1", "cid": "cid1",
         "text": "hello", "author": {"handle": "a.test", "did": "did:plc:a"}},
    ])
    monkeypatch.setattr(
        appreciate,
        "select_posts_with_llm",
        lambda posts, state, max_select=5, dry_run=False: [
            {"uri": "at://did:plc:a/app.bsky.feed.post/1", "cid": "cid1",
             "author_handle": "a.test", "action": "like", "reason": "test", "text": "hello"}
        ],
    )
    monkeypatch.setattr(appreciate, "save_state", fake_save_state)
    monkeypatch.setattr(appreciate, "RuntimeGuard", _PhaseTimeoutGuard)

    rc = appreciate.run(SimpleNamespace(dry_run=False, hours=12, max=5, max_runtime_seconds=30))

    assert rc == appreciate.TIMEOUT_EXIT_CODE
    assert saved["state"], "appreciate must save state on timeout"
    assert "partial state saved" in capsys.readouterr().out.lower()


def test_discover_saves_state_on_timeout(monkeypatch, capsys):
    """PR #16 review: discover must persist state when DiscoverRuntimeTimeout fires."""
    saved = {"state": False}

    def fake_save_state(s):
        saved["state"] = True

    class DiscoverTimeoutGuard:
        """Pass the 4 pre-dispatch checks in run(), then timeout inside discover_follows."""
        def __init__(self, _seconds=None):
            self.calls = 0

        def check(self, phase):
            self.calls += 1
            # run() pre-dispatch: collect(1) score(2) decide(3) act(4)
            # discover_follows internal: collect(5) → OK, collect(6) → timeout
            if self.calls >= 6:
                print(f"⏱️ Timed out after 30s during phase: {phase}")
                return True
            return False

    monkeypatch.setattr(discover, "RuntimeGuard", DiscoverTimeoutGuard)
    monkeypatch.setattr(discover, "get_session", _fake_session)
    monkeypatch.setattr(
        discover,
        "load_state",
        lambda: {"follows_scanned": {}, "repost_authors": {}, "already_followed": []},
    )
    monkeypatch.setattr(
        discover,
        "get_follows",
        lambda _pds, _jwt, _actor, **_kwargs: [
            {"did": "did:plc:a", "handle": "a.test"},
            {"did": "did:plc:b", "handle": "b.test"},
        ],
    )
    monkeypatch.setattr(discover.random, "sample", lambda seq, n: list(seq)[:n])
    monkeypatch.setattr(discover, "save_state", fake_save_state)

    rc = discover.run(SimpleNamespace(mode="follows", dry_run=False, max=10, max_runtime_seconds=30))

    assert rc == discover.TIMEOUT_EXIT_CODE
    assert saved["state"], "discover must save state on timeout"
    assert "partial state saved" in capsys.readouterr().out.lower()


def test_engage_get_follows_respects_guard(monkeypatch, capsys):
    """Issue #25: get_follows in engage.py must check guard between pagination pages."""
    from bsky_cli.runtime_guard import RuntimeGuard

    # Guard that times out immediately
    guard = RuntimeGuard(0)

    # Mock requests so the actual HTTP call never happens
    import types
    call_count = {"n": 0}

    def fake_get(url, **kwargs):
        call_count["n"] += 1
        resp = types.SimpleNamespace()
        resp.status_code = 200
        resp.raise_for_status = lambda: None
        resp.json = lambda: {"follows": [{"did": f"did:plc:{call_count['n']}", "handle": f"u{call_count['n']}.test"}], "cursor": "next"}
        return resp

    monkeypatch.setattr(engage.requests, "get", fake_get)

    result = engage.get_follows("https://pds.test", "jwt", "did:plc:me", guard=guard)

    # Should return early (empty or partial) because guard fires on first check
    assert len(result) <= 1  # at most 1 page before guard fires
    out = capsys.readouterr().out
    assert "Timed out" in out


def test_appreciate_get_follows_respects_guard(monkeypatch, capsys):
    """Issue #25: get_follows in appreciate.py must check guard between pagination pages."""
    from bsky_cli.runtime_guard import RuntimeGuard

    guard = RuntimeGuard(0)

    import types
    call_count = {"n": 0}

    def fake_get(url, **kwargs):
        call_count["n"] += 1
        resp = types.SimpleNamespace()
        resp.status_code = 200
        resp.raise_for_status = lambda: None
        resp.json = lambda: {"follows": [{"did": f"did:plc:{call_count['n']}", "handle": f"u{call_count['n']}.test"}], "cursor": "next"}
        return resp

    monkeypatch.setattr(appreciate.requests, "get", fake_get)

    result = appreciate.get_follows("https://pds.test", "jwt", "did:plc:me", guard=guard)

    assert len(result) <= 1
    out = capsys.readouterr().out
    assert "Timed out" in out


def test_engage_collect_timeout_during_get_follows_pagination(monkeypatch, capsys):
    """Issue #25: engage run() should return TIMEOUT_EXIT_CODE when get_follows
    times out mid-pagination (not just at the top of the collect loop)."""

    class SlowPaginationGuard:
        """Allows a few checks, then times out during get_follows pagination."""
        def __init__(self, _seconds=None):
            self.calls = 0

        def check(self, phase):
            self.calls += 1
            # First check (pre-collect in run()) passes, 2nd check (inside get_follows) passes,
            # 3rd check (post-page inside get_follows) → timeout
            if self.calls >= 3:
                print(f"⏱️ Timed out after 30s during phase: {phase}")
                return True
            return False

    monkeypatch.setattr(engage, "RuntimeGuard", SlowPaginationGuard)
    monkeypatch.setattr(engage, "get_session", _fake_session)
    monkeypatch.setattr(engage, "load_state", lambda: {"replied_posts": [], "replied_accounts_today": []})
    monkeypatch.setattr(engage, "load_conversations", lambda: {})

    import types
    def fake_get(url, **kwargs):
        resp = types.SimpleNamespace()
        resp.status_code = 200
        resp.raise_for_status = lambda: None
        resp.json = lambda: {"follows": [{"did": "did:plc:a", "handle": "a.test"}], "cursor": "next"}
        return resp

    monkeypatch.setattr(engage.requests, "get", fake_get)

    rc = engage.run(SimpleNamespace(dry_run=True, hours=12, max_runtime_seconds=30))

    assert rc == engage.TIMEOUT_EXIT_CODE
    out = capsys.readouterr().out
    assert "Timed out" in out
    assert "partial" in out.lower()


def test_discover_reposts_flushes_state_before_timeout(monkeypatch, capsys):
    """Codex P2 on PR #19: repost_authors must be flushed into state before
    check_runtime can raise, so partial progress is saved on timeout."""
    saved = {"state": None}

    def fake_save_state(s):
        saved["state"] = dict(s)

    class RepostTimeoutGuard:
        """Pass pre-dispatch checks in run(), then timeout on the post-feed
        check_runtime inside discover_reposts (after get_author_feed).
        
        Call sequence with monkeypatched get_follows (no internal guard):
          run() pre-dispatch: collect(1) score(2) decide(3) act(4)
          discover_reposts loop: pre-check(5) → feed → items → flush → post-check(6)
        Trip on call 6 to exercise exactly the post-feed check path.
        """
        def __init__(self, _seconds=None):
            self.calls = 0

        def check(self, phase):
            self.calls += 1
            if self.calls >= 6:
                print(f"⏱️ Timed out after 30s during phase: {phase}")
                return True
            return False

    monkeypatch.setattr(discover, "RuntimeGuard", RepostTimeoutGuard)
    monkeypatch.setattr(discover, "get_session", _fake_session)
    monkeypatch.setattr(
        discover,
        "load_state",
        lambda: {"follows_scanned": {}, "repost_authors": {}, "already_followed": []},
    )
    monkeypatch.setattr(
        discover,
        "get_follows",
        lambda _pds, _jwt, _actor, **_kw: [
            {"did": "did:plc:a", "handle": "a.test"},
        ],
    )
    # Feed with a repost so repost_authors gets populated
    monkeypatch.setattr(
        discover,
        "get_author_feed",
        lambda _pds, _jwt, _actor, **_kw: [
            {
                "reason": {"$type": "app.bsky.feed.defs#reasonRepost"},
                "post": {"author": {"did": "did:plc:reposted", "handle": "rp.test"}},
            }
        ],
    )
    monkeypatch.setattr(discover.random, "sample", lambda seq, n: list(seq)[:n])
    monkeypatch.setattr(discover, "save_state", fake_save_state)

    rc = discover.run(SimpleNamespace(mode="reposts", dry_run=False, max=10, max_runtime_seconds=30))

    assert rc == discover.TIMEOUT_EXIT_CODE
    assert saved["state"] is not None, "state must be saved on timeout"
    assert "did:plc:reposted" in saved["state"].get("repost_authors", {}), \
        "repost_authors accumulated before timeout must be persisted"
