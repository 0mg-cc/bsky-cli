from __future__ import annotations

import json

from bsky_cli import organic


class _Resp:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise organic.requests.HTTPError(f"{self.status_code} error")

    def json(self):
        return self._payload


def _minimal_source():
    return {"source_type": "sessions", "source_path": None, "topic": None, "requires_embed": False}


def test_generate_post_with_llm_retries_on_429_then_succeeds(monkeypatch):
    monkeypatch.setattr(organic, "load_from_pass", lambda _p: {"OPENROUTER_API_KEY": "k"})
    monkeypatch.setattr(organic, "get", lambda *_a, **_k: 2)

    calls = {"n": 0}

    def _post(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _Resp(429, {"error": "rate limited"})
        return _Resp(200, {"choices": [{"message": {"content": '{"text":"hello"}'}}]})

    monkeypatch.setattr(organic.requests, "post", _post)
    monkeypatch.setattr(organic, "sleep", lambda _s: None)

    out = organic.generate_post_with_llm("activités", _minimal_source(), "guidelines")

    assert out == {"text": "hello"}
    assert calls["n"] == 2


def test_generate_post_with_llm_returns_none_after_429_retries(monkeypatch):
    monkeypatch.setattr(organic, "load_from_pass", lambda _p: {"OPENROUTER_API_KEY": "k"})
    monkeypatch.setattr(organic, "get", lambda *_a, **_k: 2)

    calls = {"n": 0}

    def _post(*args, **kwargs):
        calls["n"] += 1
        return _Resp(429, {"error": "rate limited"})

    monkeypatch.setattr(organic.requests, "post", _post)
    monkeypatch.setattr(organic, "sleep", lambda _s: None)

    out = organic.generate_post_with_llm("activités", _minimal_source(), "guidelines")

    assert out is None
    assert calls["n"] == 3


def test_generate_post_with_llm_no_retry_on_permanent_error(monkeypatch):
    """Permanent errors like 401/400 should NOT be retried (PR #17 review fix)."""
    monkeypatch.setattr(organic, "load_from_pass", lambda _p: {"OPENROUTER_API_KEY": "k"})
    monkeypatch.setattr(organic, "get", lambda *_a, **_k: 2)

    calls = {"n": 0}

    def _post(*args, **kwargs):
        calls["n"] += 1
        return _Resp(401, {"error": "unauthorized"})

    monkeypatch.setattr(organic.requests, "post", _post)
    monkeypatch.setattr(organic, "sleep", lambda _s: None)

    out = organic.generate_post_with_llm("activités", _minimal_source(), "guidelines")

    assert out is None
    # Should fail on first attempt without retrying
    assert calls["n"] == 1, "Permanent errors must not trigger retries"


def test_generate_post_with_llm_retries_on_connection_error(monkeypatch):
    """Transient network errors should be retried."""
    monkeypatch.setattr(organic, "load_from_pass", lambda _p: {"OPENROUTER_API_KEY": "k"})
    monkeypatch.setattr(organic, "get", lambda *_a, **_k: 2)

    calls = {"n": 0}

    def _post(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise organic.requests.ConnectionError("connection reset")
        return _Resp(200, {"choices": [{"message": {"content": '{"text":"recovered"}'}}]})

    monkeypatch.setattr(organic.requests, "post", _post)
    monkeypatch.setattr(organic, "sleep", lambda _s: None)

    out = organic.generate_post_with_llm("activités", _minimal_source(), "guidelines")

    assert out == {"text": "recovered"}
    assert calls["n"] == 2


def test_generate_post_with_llm_no_retry_on_json_parse_error(monkeypatch):
    """JSON parse errors (malformed LLM output) should NOT be retried."""
    monkeypatch.setattr(organic, "load_from_pass", lambda _p: {"OPENROUTER_API_KEY": "k"})
    monkeypatch.setattr(organic, "get", lambda *_a, **_k: 2)

    calls = {"n": 0}

    def _post(*args, **kwargs):
        calls["n"] += 1
        return _Resp(200, {"choices": [{"message": {"content": "not valid json at all"}}]})

    monkeypatch.setattr(organic.requests, "post", _post)
    monkeypatch.setattr(organic, "sleep", lambda _s: None)

    out = organic.generate_post_with_llm("activités", _minimal_source(), "guidelines")

    assert out is None
    assert calls["n"] == 1, "JSON parse errors must not trigger retries"
