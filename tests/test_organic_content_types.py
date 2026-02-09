import pytest

from bsky_cli.organic import get_source_for_type


@pytest.mark.parametrize(
    "content_type, expected_source_type, expected_requires_embed",
    [
        ("ops_insight", "sessions", False),
        ("agent_life", "sessions", False),
        ("question", "sessions", False),
        ("tech_take", "revue_presse", True),
    ],
)
def test_get_source_for_type_new_schema(content_type, expected_source_type, expected_requires_embed):
    src = get_source_for_type(content_type)
    assert src["source_type"] == expected_source_type
    assert src["requires_embed"] is expected_requires_embed


def test_get_source_for_type_blog_teaser_does_not_crash():
    # Behavior depends on local blog repo + config presence; we mainly assert stability.
    src = get_source_for_type("blog_teaser")
    assert "source_type" in src
    assert "requires_embed" in src
