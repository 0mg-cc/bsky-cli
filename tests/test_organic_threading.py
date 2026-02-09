import pytest

from bsky_cli import organic


def test_split_text_to_thread_keeps_hashtags_only_in_last_post():
    text = (
        "Sentence one. "
        "Sentence two. "
        "Sentence three. "
        "#AI #FOSS"
    )
    posts = organic.split_text_to_thread(text, max_posts=3)
    assert 1 <= len(posts) <= 3

    for p in posts[:-1]:
        assert "#AI" not in p and "#FOSS" not in p

    assert "#AI" in posts[-1] and "#FOSS" in posts[-1]


def test_split_text_to_thread_never_exceeds_280_chars():
    base = "word " * 400
    text = base.strip() + " #AI #Linux"
    posts = organic.split_text_to_thread(text, max_posts=3)
    assert 1 <= len(posts) <= 3
    assert all(len(p) <= 280 for p in posts)


def test_validate_thread_posts_rejects_too_imbalanced():
    # Extremely imbalanced: last post is tiny.
    posts = ["a" * 270, "b" * 5]
    assert organic.validate_thread_posts(posts, max_posts=3) is False


def test_validate_thread_posts_accepts_reasonable_balance():
    posts = ["a" * 180, "b" * 180]
    assert organic.validate_thread_posts(posts, max_posts=3) is True


def test_apply_thread_prefixes_adds_numbering_and_respects_limits():
    posts = ["a" * 270, "b" * 200]
    out = organic.apply_thread_prefixes(posts, max_chars=280)
    assert out[0].startswith("(1/2) ")
    assert out[1].startswith("(2/2) ")
    assert all(len(p) <= 280 for p in out)
