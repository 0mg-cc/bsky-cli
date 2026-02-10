from __future__ import annotations

import json

from bsky_cli import appreciate


class FakeResp:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def test_select_posts_with_llm_parses_json_in_code_fence(monkeypatch):
    # Arrange: minimal candidate list
    posts = [
        {
            "uri": "at://x/app.bsky.feed.post/1",
            "cid": "c1",
            "author": {"handle": "a.example"},
            "text": "hello world",
            "created_at": "2026-02-10T00:00:00Z",
            "like_count": 0,
            "repost_count": 0,
            "reply_count": 0,
        }
    ]

    state = {"liked_posts": [], "quoted_posts": []}

    # Stub pass/env + http
    monkeypatch.setattr(appreciate, "load_from_pass", lambda path: {"OPENROUTER_API_KEY": "k", "OPENROUTER_MODEL": "m"})

    content = "```json\n{\"selections\":[{\"index\":0,\"action\":\"like\",\"reason\":\"ok\"}]}\n```"

    def _post(*a, **k):
        return FakeResp(
            200,
            {"choices": [{"message": {"content": content}}]},
        )

    monkeypatch.setattr(appreciate.requests, "post", _post)

    # Act
    sels = appreciate.select_posts_with_llm(posts, state, max_select=1)

    # Assert
    assert len(sels) == 1
    assert sels[0]["uri"].endswith("/1")
    assert sels[0]["action"] == "like"


def test_select_posts_with_llm_handles_empty_content(monkeypatch, capsys):
    posts = [
        {
            "uri": "at://x/app.bsky.feed.post/1",
            "cid": "c1",
            "author": {"handle": "a.example"},
            "text": "hello world",
            "created_at": "2026-02-10T00:00:00Z",
            "like_count": 0,
            "repost_count": 0,
            "reply_count": 0,
        }
    ]
    state = {"liked_posts": [], "quoted_posts": []}

    monkeypatch.setattr(appreciate, "load_from_pass", lambda path: {"OPENROUTER_API_KEY": "k", "OPENROUTER_MODEL": "m"})

    def _post(*a, **k):
        return FakeResp(200, {"choices": [{"message": {"content": ""}}]})

    monkeypatch.setattr(appreciate.requests, "post", _post)

    sels = appreciate.select_posts_with_llm(posts, state, max_select=1)
    assert sels == []
    out = capsys.readouterr().out
    assert "LLM selection failed" in out or "LLM error" in out
