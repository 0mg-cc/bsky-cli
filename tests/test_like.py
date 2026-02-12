from bsky_cli import like


class _Resp:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text

    def json(self):
        return self._json_data


def test_unlike_post_uses_viewer_like_record_when_available(monkeypatch):
    calls = {"delete": None}

    def fake_get(url, **kwargs):
        if url.endswith("/xrpc/app.bsky.feed.getPosts"):
            return _Resp(
                200,
                {
                    "posts": [
                        {
                            "viewer": {
                                "like": "at://did:plc:me/app.bsky.feed.like/3lxyzabc"
                            }
                        }
                    ]
                },
            )
        if url.endswith("/xrpc/app.bsky.feed.getLikes"):
            return _Resp(200, {"likes": []})
        raise AssertionError(f"Unexpected GET {url}")

    def fake_post(url, **kwargs):
        if url.endswith("/xrpc/com.atproto.repo.deleteRecord"):
            calls["delete"] = kwargs.get("json")
            return _Resp(200, {})
        raise AssertionError(f"Unexpected POST {url}")

    monkeypatch.setattr(like.requests, "get", fake_get)
    monkeypatch.setattr(like.requests, "post", fake_post)

    ok = like.unlike_post(
        "https://pds.example",
        "jwt",
        "did:plc:me",
        "at://did:plc:author/app.bsky.feed.post/abc",
    )

    assert ok is True
    assert calls["delete"]["rkey"] == "3lxyzabc"
