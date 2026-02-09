from bsky_cli import organic


def test_clamp_text_leaves_short_text_unchanged():
    txt = "hello"
    assert organic.clamp_text(txt) == txt


def test_clamp_text_truncates_to_exactly_280_chars():
    txt = "a" * 281
    out = organic.clamp_text(txt)
    assert len(out) == 280
    assert out.endswith("...")
    assert out == ("a" * 277 + "...")
