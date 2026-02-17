from bsky_cli import auth


def test_get_openrouter_pass_path_defaults_to_bsky_key(monkeypatch):
    monkeypatch.delenv("BSKY_OPENROUTER_PASS_PATH", raising=False)
    assert auth.get_openrouter_pass_path() == "api/openrouter-bsky"


def test_get_openrouter_pass_path_supports_override(monkeypatch):
    monkeypatch.setenv("BSKY_OPENROUTER_PASS_PATH", "api/custom-openrouter")
    assert auth.get_openrouter_pass_path() == "api/custom-openrouter"
