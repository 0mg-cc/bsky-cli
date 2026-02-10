from __future__ import annotations

import pytest

from bsky_cli.post import detect_facets


def test_detect_facets_strips_trailing_dot_for_mentions(monkeypatch):
    import bsky_cli.auth as auth

    def _resolve(pds: str, handle: str) -> str:
        assert handle == "alice.bsky.social"
        return "did:plc:alice"

    monkeypatch.setattr(auth, "resolve_handle", _resolve)

    text = "hi @alice.bsky.social."
    facets = detect_facets(text, pds="https://pds.invalid")
    assert facets

    mention = [f for f in facets if f["features"][0]["$type"].endswith("#mention")][0]

    byte_start = mention["index"]["byteStart"]
    byte_end = mention["index"]["byteEnd"]

    assert text.encode("utf-8")[byte_start:byte_end].decode("utf-8") == "@alice.bsky.social"
