import bsky_cli.public_truth as pt


def test_truth_section_disabled_by_default(monkeypatch):
    monkeypatch.setattr(pt, "get", lambda key, default=None: False if key == "public_truth.enabled" else default)
    monkeypatch.setattr(pt, "load_public_about_me", lambda max_chars=6000: "SHOULD_NOT_LOAD")
    assert pt.truth_section() == ""


def test_truth_section_enabled_returns_content(monkeypatch):
    monkeypatch.setattr(pt, "get", lambda key, default=None: True if key == "public_truth.enabled" else default)
    monkeypatch.setattr(pt, "load_public_about_me", lambda max_chars=6000: "PUBLIC FACTS")
    out = pt.truth_section()
    assert "PUBLIC TRUTH CHECK" in out
    assert "PUBLIC FACTS" in out
