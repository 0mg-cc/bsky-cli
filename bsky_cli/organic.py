"""Organic posting command for BlueSky.

This module centralizes the logic for organic posts that was previously
spread across 29 separate cron jobs. It handles:
- Time window validation (8h-22h30 America/Toronto)
- Probabilistic posting (default 20%)
- Content type selection (actualité, économie, activités, passions)
- Source selection based on type
- Posting with optional embeds

Issue: https://git.2027a.net/echo/bsky-cli/issues/1
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from .auth import get_session, load_from_pass
from .post import create_post, create_external_embed, detect_facets

# ============================================================================
# CONFIGURATION
# ============================================================================

TIMEZONE = ZoneInfo("America/Toronto")

# Posting windows (hour ranges in Toronto time)
POSTING_WINDOWS = [
    (8, 0, 22, 30),  # 8:00 AM to 10:30 PM
]

# Default probability of posting when called
DEFAULT_PROBABILITY = 0.20

# Content types with weights (more weight = more likely)
CONTENT_TYPES = {
    "actualité": 2,      # News commentary
    "économie": 1,       # Finance/markets
    "activités": 2,      # What I'm working on
    "passions": 4,       # Interests/topics (most common)
}

# Passion topics for double shuffle
PASSION_TOPICS = [
    "éthique", "cyberpunk", "typo/design", "astronomie", "climat",
    "biosystèmes", "photo", "psycho", "game-theory", "linguistique"
]

# Guidelines file
GUIDELINES_FILE = Path.home() / "personas/echo/data/bsky-guidelines.md"

# Source directories
REVUE_PRESSE_DIR = Path.home() / "state/revue_presse"
REVUE_FINANCE_DIR = Path.home() / "state/revue_finance"


# ============================================================================
# TIME VALIDATION
# ============================================================================

def is_in_posting_window(now: datetime | None = None) -> bool:
    """Check if current time is within posting windows."""
    if now is None:
        now = datetime.now(TIMEZONE)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=TIMEZONE)
    else:
        now = now.astimezone(TIMEZONE)
    
    current_minutes = now.hour * 60 + now.minute
    
    for start_h, start_m, end_h, end_m in POSTING_WINDOWS:
        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m
        if start_minutes <= current_minutes <= end_minutes:
            return True
    
    return False


def should_post(probability: float = DEFAULT_PROBABILITY) -> bool:
    """Probabilistic decision to post."""
    return random.random() < probability


# ============================================================================
# CONTENT GENERATION
# ============================================================================

def select_content_type() -> str:
    """Weighted random selection of content type."""
    types = list(CONTENT_TYPES.keys())
    weights = list(CONTENT_TYPES.values())
    return random.choices(types, weights=weights, k=1)[0]


def get_source_for_type(content_type: str) -> dict:
    """Get source material based on content type.
    
    Returns dict with:
    - source_type: str
    - source_path: Path or None
    - topic: str or None (for passions)
    - requires_embed: bool
    """
    if content_type == "actualité":
        return {
            "source_type": "revue_presse",
            "source_path": REVUE_PRESSE_DIR,
            "topic": None,
            "requires_embed": True,
        }
    elif content_type == "économie":
        return {
            "source_type": "revue_finance",
            "source_path": REVUE_FINANCE_DIR,
            "topic": None,
            "requires_embed": True,
        }
    elif content_type == "activités":
        return {
            "source_type": "sessions",
            "source_path": None,
            "topic": None,
            "requires_embed": False,
        }
    elif content_type == "passions":
        topic = random.choice(PASSION_TOPICS)
        return {
            "source_type": "passion",
            "source_path": None,
            "topic": topic,
            "requires_embed": False,
        }
    else:
        raise ValueError(f"Unknown content type: {content_type}")


def load_guidelines() -> str:
    """Load posting guidelines."""
    if GUIDELINES_FILE.exists():
        return GUIDELINES_FILE.read_text()
    return ""


def generate_post_with_llm(content_type: str, source: dict, guidelines: str) -> dict | None:
    """Use LLM to generate post content.
    
    Returns dict with:
    - text: str (max 280 chars)
    - embed_url: str or None
    - reason: str (for logging)
    """
    env = load_from_pass("api/openrouter")
    if not env or "OPENROUTER_API_KEY" not in env:
        print("❌ Missing OPENROUTER_API_KEY")
        return None
    
    api_key = env["OPENROUTER_API_KEY"]
    
    # Build context based on source type
    context = ""
    if source["source_type"] == "revue_presse" and source["source_path"]:
        # Read latest revue
        revue_files = sorted(source["source_path"].glob("*.md"), reverse=True)
        if revue_files:
            context = revue_files[0].read_text()[:3000]
    elif source["source_type"] == "revue_finance" and source["source_path"]:
        revue_files = sorted(source["source_path"].glob("*.md"), reverse=True)
        if revue_files:
            context = revue_files[0].read_text()[:3000]
    elif source["source_type"] == "passion":
        context = f"Topic to explore: {source['topic']}"
    elif source["source_type"] == "sessions":
        context = "Share something about current work/projects (NO SECRETS, no private info)"
    
    prompt = f"""You are Echo, an AI ops agent posting on BlueSky (@echo.0mg.cc).

## GUIDELINES
{guidelines}

## TASK
Write an organic post about: {content_type}
{f"Topic: {source['topic']}" if source.get('topic') else ""}

## CONTEXT
{context if context else "(Generate from your knowledge/interests)"}

## RULES
- Max 280 characters (STRICT)
- English only
- Include 1-2 relevant hashtags (e.g. #AI #Linux #FOSS #automation)
- {"MUST include a source URL for embed" if source['requires_embed'] else "No embed required"}
- Be genuine, not generic
- Questions drive engagement
- Show > Tell

## OUTPUT FORMAT
Return ONLY a JSON object:
{{
  "text": "your post text (max 280 chars)",
  "embed_url": "https://..." or null,
  "reason": "why this post"
}}

Return ONLY valid JSON, no markdown."""

    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "google/gemini-3-flash-preview",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.8
            },
            timeout=60
        )
        r.raise_for_status()
        
        content = r.json()["choices"][0]["message"]["content"]
        content = content.strip()
        if content.startswith("```"):
            content = "\n".join(content.split("\n")[1:-1])
        
        return json.loads(content)
    except Exception as e:
        print(f"❌ LLM error: {e}")
        return None


# ============================================================================
# MAIN COMMAND
# ============================================================================

def run(args) -> int:
    """Execute organic post command."""
    probability = getattr(args, 'probability', DEFAULT_PROBABILITY)
    dry_run = getattr(args, 'dry_run', False)
    force = getattr(args, 'force', False)
    
    now = datetime.now(TIMEZONE)
    print(f"🕐 Current time: {now.strftime('%Y-%m-%d %H:%M')} ({TIMEZONE})")
    
    # Check posting window (unless forced)
    if not force and not is_in_posting_window(now):
        print(f"⏸️  Outside posting window (8:00-22:30 Toronto)")
        return 0
    
    # Probabilistic check (unless forced)
    if not force and not should_post(probability):
        print(f"🎲 Probability check failed ({probability*100:.0f}%)")
        return 0
    
    print(f"✓ Posting check passed")
    
    # Select content type
    content_type = select_content_type()
    print(f"📝 Content type: {content_type}")
    
    # Get source
    source = get_source_for_type(content_type)
    print(f"📚 Source: {source['source_type']}" + 
          (f" ({source['topic']})" if source.get('topic') else ""))
    
    # Load guidelines
    guidelines = load_guidelines()
    
    # Generate post
    print("🤖 Generating post...")
    post_data = generate_post_with_llm(content_type, source, guidelines)
    
    if not post_data:
        print("❌ Failed to generate post")
        return 1
    
    text = post_data.get("text", "")
    embed_url = post_data.get("embed_url")
    reason = post_data.get("reason", "")
    
    # Validate
    if len(text) > 300:
        print(f"⚠️  Text too long ({len(text)} chars), truncating...")
        text = text[:297] + "..."
    
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Post content:")
    print(f"  Text: {text}")
    print(f"  Embed: {embed_url or '(none)'}")
    print(f"  Reason: {reason}")
    print(f"  Length: {len(text)} chars")
    
    if dry_run:
        print("\n✓ Dry run complete")
        return 0
    
    # Post
    print("\n🔗 Connecting to BlueSky...")
    pds, did, jwt, handle = get_session()
    print(f"✓ Logged in as @{handle}")
    
    # Fetch embed if URL provided
    embed = None
    if embed_url:
        print(f"🔗 Fetching embed for {embed_url}...")
        embed = create_external_embed(pds, jwt, embed_url)
        if embed:
            print(f"✓ Embed ready: {embed.get('external', {}).get('title', '')[:50]}")
        else:
            print("⚠️  Could not fetch embed, posting without")
    
    # Detect facets (makes hashtags and URLs clickable)
    facets = detect_facets(text)
    
    # Create post
    result = create_post(pds, jwt, did, text, facets=facets, embed=embed)
    
    if result:
        print(f"\n✓ Posted successfully!")
        print(f"  URI: {result.get('uri', '')}")
        return 0
    else:
        print("\n❌ Failed to post")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Organic BlueSky posting (replaces 29 crons)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  # Normal run (respects time window + probability)
  bsky organic
  
  # Dry run
  bsky organic --dry-run
  
  # Force post regardless of time/probability
  bsky organic --force
  
  # Custom probability
  bsky organic --probability 0.5

BEHAVIOR:
  1. Check if within posting window (8:00-22:30 Toronto)
  2. Roll probability (default 20%)
  3. Select content type (weighted: passions > actualité/activités > économie)
  4. Generate post with LLM using guidelines
  5. Post to BlueSky
  
  This replaces 29 separate cron jobs with one command.
  See: https://git.2027a.net/echo/bsky-cli/issues/1
"""
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without posting")
    parser.add_argument("--force", action="store_true", help="Ignore time window and probability")
    parser.add_argument("--probability", type=float, default=DEFAULT_PROBABILITY,
                        help=f"Posting probability (default: {DEFAULT_PROBABILITY})")
    
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
