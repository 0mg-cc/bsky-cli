from __future__ import annotations


def test_send_dm_includes_facets_when_detected(monkeypatch):
    from bsky_cli import dm as dm_mod

    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json

        class R:
            def raise_for_status(self):
                return None

            def json(self):
                return {"ok": True}

        return R()

    monkeypatch.setattr(
        dm_mod,
        "detect_facets",
        lambda text, pds=None: [
            {
                "index": {"byteStart": 3, "byteEnd": 22},
                "features": [
                    {"$type": "app.bsky.richtext.facet#link", "uri": "https://example.com"}
                ],
            }
        ],
    )
    monkeypatch.setattr(dm_mod.requests, "post", fake_post)

    dm_mod.send_dm("https://pds", "jwt", "convo1", "hi https://example.com")

    msg = captured["json"]["message"]
    assert msg["text"].startswith("hi")
    assert "facets" in msg


def test_send_dm_omits_facets_when_none(monkeypatch):
    from bsky_cli import dm as dm_mod

    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json

        class R:
            def raise_for_status(self):
                return None

            def json(self):
                return {"ok": True}

        return R()

    monkeypatch.setattr(dm_mod, "detect_facets", lambda text, pds=None: [])
    monkeypatch.setattr(dm_mod.requests, "post", fake_post)

    dm_mod.send_dm("https://pds", "jwt", "convo1", "hello")

    msg = captured["json"]["message"]
    assert msg == {"text": "hello"}
