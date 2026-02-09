from bsky_cli.post import create_post


def test_create_post_includes_reply_fields_when_provided(monkeypatch):
    sent = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        sent["record"] = json["record"]
        class R:
            status_code = 200
            def raise_for_status(self):
                return None
            def json(self):
                return {"uri": "at://x/app.bsky.feed.post/1", "cid": "bafy..."}
        return R()

    # Monkeypatch requests + preflight recent fetch
    import bsky_cli.post as post_mod
    monkeypatch.setattr(post_mod.requests, "post", fake_post)
    monkeypatch.setattr(post_mod, "_fetch_recent_own_posts", lambda *a, **k: [])

    root = {"uri": "at://root", "cid": "cidroot"}
    parent = {"uri": "at://parent", "cid": "cidparent"}

    res = create_post(
        "https://pds",
        "jwt",
        "did:me",
        "hello",
        reply_root=root,
        reply_parent=parent,
    )
    assert res["uri"].startswith("at://")
    rec = sent["record"]
    assert rec["reply"]["root"]["uri"] == "at://root"
    assert rec["reply"]["parent"]["cid"] == "cidparent"
