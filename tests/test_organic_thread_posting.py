from bsky_cli import organic


def test_thread_segments_skip_antirepeat(monkeypatch):
    # Force a 2-post thread from LLM

    monkeypatch.setattr(organic, "load_guidelines", lambda: "")
    monkeypatch.setattr(organic, "select_content_type", lambda: "passions")
    monkeypatch.setattr(organic, "get_source_for_type", lambda ct: {"source_type": "sessions", "source_path": None, "topic": None, "requires_embed": False})

    monkeypatch.setattr(
        organic,
        "generate_post_with_llm",
        lambda *a, **k: {"posts": [{"text": "a" * 120}, {"text": "b" * 140 + " #AI"}], "embed_url": None, "reason": ""},
    )

    monkeypatch.setattr(organic, "get_session", lambda: ("https://pds", "did:me", "jwt", "me.bsky.social"))
    monkeypatch.setattr(organic, "create_external_embed", lambda *a, **k: None)

    seen = []

    def fake_create_post(pds, jwt, did, text, *, allow_repeat=False, **kwargs):
        seen.append(allow_repeat)
        # minimal response
        return {"uri": "at://x/app.bsky.feed.post/1", "cid": "cid"}

    monkeypatch.setattr(organic, "create_post", fake_create_post)

    class Args:
        probability = 1.0
        dry_run = False
        force = True
        max_posts = 3

    rc = organic.run(Args())
    assert rc == 0
    # First post: allow_repeat False, subsequent: True
    assert seen == [False, True]
