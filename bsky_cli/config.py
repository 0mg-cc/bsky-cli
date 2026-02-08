"""Configuration management for bsky-cli.

Loads settings from ~/.config/bsky-cli/config.yaml with sensible defaults.
All settings are optional - defaults work out of the box.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# ============================================================================
# DEFAULTS
# ============================================================================

DEFAULT_CONFIG = {
    # General settings
    "timezone": "America/Toronto",
    
    # Topics of interest (used for engage, appreciate, discover)
    "topics": [
        "tech", "ops", "infrastructure", "devops",
        "AI", "machine learning", "LLM", "agents",
        "linux", "FOSS", "open source",
        "climate", "environment", "sustainability",
        "wealth inequality", "economics", "social justice",
        "consciousness", "philosophy", "psychology",
        "automation", "scripting", "tools"
    ],
    
    # Organic posting settings
    "organic": {
        "probability": 0.20,           # Chance of posting when called
        "posting_windows": [           # Time windows (start_h, start_m, end_h, end_m)
            [7, 0, 23, 30]             # 7:00 AM to 11:30 PM
        ],
        "content_types": {             # Content types with weights
            "actualité": 2,
            "économie": 1,
            "activités": 2,
            "passions": 4,
        },
        "passion_topics": [
            "éthique", "cyberpunk", "typo/design", "astronomie", "climat",
            "biosystèmes", "photo", "psycho", "game-theory", "linguistique"
        ],
    },
    
    # Engagement settings
    "engage": {
        "hours": 12,                   # Look back window
        "max_per_account": 1,          # Max replies per account per session
        "min_text_length": 20,         # Minimum post length to consider
        "max_thread_replies": 50,      # Skip posts with too many replies
        "like_after_reply_prob": 0.4,  # Probability to like after replying
        "max_selections": 4,           # Max posts to engage with per session
    },
    
    # Appreciation settings (passive engagement)
    "appreciate": {
        "prob_like": 0.60,             # Probability to like selected posts
        "prob_quote": 0.20,            # Probability to quote-repost
        "prob_skip": 0.20,             # Probability to skip (score but no action)
    },
    
    # Discovery settings
    "discover": {
        "follows_sample_pct": 0.10,    # % of each follow's follows to sample
        "repost_top_pct": 0.20,        # Top % most reposted authors to consider
        "scan_cooldown_days": 90,      # Days before re-scanning a follow
        "min_posts": 5,                # Minimum posts to consider following
        "min_followers": 10,           # Minimum followers
        "max_following_ratio": 10,     # Max following/followers ratio (anti-bot)
    },
    
    # Interlocutor tracking
    "interlocutors": {
        "friendly_threshold": 3,       # Interactions to be considered "friendly"
        "regular_threshold": 10,       # Interactions to be considered "regular"
        "friendly_boost": 1.5,         # Score multiplier for friendly accounts
        "regular_boost": 2.0,          # Score multiplier for regular accounts
    },

    # API behavior
    "api": {
        "calls_per_minute": 60,        # Client-side request cap for BlueSky API
    },
}

# Config file locations (first found wins)
CONFIG_PATHS = [
    Path.home() / ".config/bsky-cli/config.yaml",
    Path.home() / ".config/bsky-cli/config.yml",
    Path.home() / ".bsky-cli.yaml",
    Path("./bsky-cli.yaml"),
]


# ============================================================================
# CONFIG LOADING
# ============================================================================

_config_cache: dict | None = None


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override into base, returning new dict."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def find_config_file() -> Path | None:
    """Find the first existing config file."""
    for path in CONFIG_PATHS:
        if path.exists():
            return path
    return None


def load_config(reload: bool = False) -> dict:
    """Load configuration with defaults.
    
    Returns merged config: defaults + user overrides.
    Config is cached after first load.
    """
    global _config_cache
    
    if _config_cache is not None and not reload:
        return _config_cache
    
    config = DEFAULT_CONFIG.copy()
    
    config_file = find_config_file()
    if config_file:
        try:
            user_config = yaml.safe_load(config_file.read_text()) or {}
            config = _deep_merge(config, user_config)
        except Exception as e:
            print(f"Warning: Could not load config from {config_file}: {e}")
    
    _config_cache = config
    return config


def get(key: str, default: Any = None) -> Any:
    """Get a config value by dot-separated key.
    
    Example:
        get("organic.probability")  # Returns 0.20
        get("topics")               # Returns list of topics
    """
    config = load_config()
    parts = key.split(".")
    value = config
    for part in parts:
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return default
    return value


def get_section(section: str) -> dict:
    """Get an entire config section."""
    config = load_config()
    return config.get(section, {})


# ============================================================================
# CLI HELPER
# ============================================================================

def init_config(force: bool = False) -> Path:
    """Create example config file in default location."""
    config_path = CONFIG_PATHS[0]
    
    if config_path.exists() and not force:
        raise FileExistsError(f"Config already exists: {config_path}")
    
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    example = """# bsky-cli configuration
# All settings are optional - defaults work out of the box.
# See full documentation: https://github.com/echo931/bsky-cli

# Your timezone (IANA format)
timezone: America/Toronto

# Topics you're interested in (used for engagement scoring)
topics:
  - AI
  - automation
  - linux
  - FOSS
  - climate
  - philosophy

# Organic posting settings
organic:
  probability: 0.20              # Chance of posting (0.0 to 1.0)
  posting_windows:               # When to post [start_h, start_m, end_h, end_m]
    - [7, 0, 23, 30]             # 7:00 AM to 11:30 PM
  passion_topics:                # Topics for "passions" content type
    - AI
    - cyberpunk
    - climate

# Engagement settings (replying to posts)
engage:
  hours: 12                      # Look back window (hours)
  max_per_account: 1             # Max replies per account per session
  like_after_reply_prob: 0.4     # Chance to also like after replying
  max_selections: 4              # Max posts to reply to per session

# Appreciation settings (liking/quoting)
appreciate:
  prob_like: 0.60                # Probability to like
  prob_quote: 0.20               # Probability to quote-repost
  prob_skip: 0.20                # Probability to skip

# Discovery settings (finding new accounts to follow)
discover:
  scan_cooldown_days: 90         # Days before re-scanning an account
  min_posts: 5                   # Minimum posts to consider following
  min_followers: 10              # Minimum followers

# Interlocutor settings (tracking conversation partners)
interlocutors:
  friendly_threshold: 3          # Interactions to be "friendly"
  regular_threshold: 10          # Interactions to be "regular"

# API settings
api:
  calls_per_minute: 60           # Client-side API cap (logs when throttled)
"""
    
    config_path.write_text(example)
    return config_path


def show_config() -> None:
    """Print current configuration."""
    config = load_config()
    config_file = find_config_file()
    
    print("=" * 60)
    print("bsky-cli configuration")
    print("=" * 60)
    
    if config_file:
        print(f"Config file: {config_file}")
    else:
        print("Config file: (using defaults)")
    
    print()
    print(yaml.dump(config, default_flow_style=False, sort_keys=False))
