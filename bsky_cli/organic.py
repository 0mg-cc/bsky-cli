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
from time import sleep
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from .http import requests

from .auth import get_session, load_from_pass, get_openrouter_pass_path
from .config import get, get_section
from .post import create_post, create_external_embed, detect_facets
from .public_truth import truth_section

# ============================================================================
# CONFIGURATION (loaded from ~/.config/bsky-cli/config.yaml)
# ============================================================================

def get_timezone() -> ZoneInfo:
    return ZoneInfo(get("timezone", "America/Toronto"))

def get_posting_windows() -> list[tuple]:
    windows = get("organic.posting_windows", [[7, 0, 23, 30]])
    return [tuple(w) for w in windows]

def get_probability() -> float:
    return get("organic.probability", 0.20)

def get_content_types() -> dict:
    # Canonical set: actualité, activités, passions (no économie)
    return get("organic.content_types", {
        "actualité": 2, "activités": 2, "passions": 4
    })

def get_passion_topics() -> list[str]:
    return get("organic.passion_topics", [
        "éthique", "cyberpunk", "typo/design", "astronomie", "climat",
        "biosystèmes", "photo", "psycho", "game-theory", "linguistique"
    ])

# Guidelines file (not configurable for now)
GUIDELINES_FILE = Path.home() / "personas/echo/data/bsky-guidelines.md"

# Source directories
REVUE_PRESSE_DIR = Path.home() / "state/revue_presse"
REVUE_FINANCE_DIR = Path.home() / "state/revue_finance"


# ============================================================================
# TIME VALIDATION
# ============================================================================

def is_in_posting_window(now: datetime | None = None) -> bool:
    """Check if current time is within posting windows."""
    tz = get_timezone()
    if now is None:
        now = datetime.now(tz)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)
    
    current_minutes = now.hour * 60 + now.minute
    
    for start_h, start_m, end_h, end_m in get_posting_windows():
        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m
        if start_minutes <= current_minutes <= end_minutes:
            return True
    
    return False


def should_post(probability: float | None = None) -> bool:
    """Probabilistic decision to post."""
    if probability is None:
        probability = get_probability()
    return random.random() < probability


# ============================================================================
# CONTENT GENERATION
# ============================================================================

def validate_thread_posts(
    posts: list[str],
    *,
    max_posts: int = 3,
    max_chars: int = 280,
    min_last_chars: int = 60,
    min_balance_ratio: float = 0.35,
) -> bool:
    """Validate a candidate thread.

    Rules:
    - 1..max_posts posts
    - each post <= max_chars
    - last post has at least min_last_chars of non-hashtag content
    - avoid extremely imbalanced splits: shortest/longest >= min_balance_ratio
    """
    if not posts or len(posts) > max_posts:
        return False

    lengths = [len(p) for p in posts]
    if any(l == 0 or l > max_chars for l in lengths):
        return False

    # last-post content length excluding trailing hashtags
    last = posts[-1].strip()
    base_last, _tags = split_trailing_hashtags(last)
    if len(base_last.strip()) < min_last_chars:
        return False

    mn, mx = min(lengths), max(lengths)
    if mx == 0:
        return False
    if (mn / mx) < min_balance_ratio:
        return False

    return True


def split_trailing_hashtags(text: str) -> tuple[str, str]:
    """Split trailing hashtags from a post.

    Returns (base_text, hashtags_with_leading_space_or_empty).

    We only treat hashtags at the very end as hashtags, e.g.:
    "hello world #AI #FOSS".
    """
    t = text.rstrip()
    if not t:
        return "", ""

    parts = t.split()
    i = len(parts)
    while i > 0 and parts[i - 1].startswith("#") and len(parts[i - 1]) > 1:
        i -= 1

    if i == len(parts):
        return t, ""

    base = " ".join(parts[:i]).rstrip()
    tags = " ".join(parts[i:]).strip()
    if tags:
        tags = " " + tags
    return base, tags


def extract_urls(text: str) -> list[str]:
    """Extract http(s) URLs from a blob of text."""
    import re

    urls = re.findall(r"https?://[^\s\)\]\>\"']+", text)
    # de-dupe while preserving order
    seen = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _best_cut(s: str, limit: int) -> int:
    """Find a nice cut position <= limit (prefer paragraph, then sentence, then space)."""
    if len(s) <= limit:
        return len(s)

    window = s[: limit + 1]
    for sep in ("\n\n", ". ", "! ", "? ", "; ", ": ", " "):
        idx = window.rfind(sep)
        if idx != -1:
            return idx + (0 if sep == "\n\n" else 1)  # keep punctuation char

    return limit


def apply_thread_prefixes(posts: list[str], *, max_chars: int = 280) -> list[str]:
    """Prefix each post with (i/n) and keep each post within max_chars.

    If a post becomes too long, it is trimmed (best-effort) at a word boundary.
    """
    if len(posts) <= 1:
        return posts

    n = len(posts)
    out: list[str] = []
    for i, p in enumerate(posts, start=1):
        prefix = f"({i}/{n}) "
        room = max_chars - len(prefix)
        t = p.strip()
        if len(t) > room:
            # trim at last space within room
            trimmed = t[:room].rstrip()
            if " " in trimmed:
                trimmed = trimmed.rsplit(" ", 1)[0].rstrip()
            t = trimmed
        out.append(prefix + t)

    return out


def split_text_to_thread(
    text: str,
    *,
    max_posts: int = 3,
    max_chars: int = 280,
    min_last_chars: int = 60,
) -> list[str]:
    """Deterministic fallback split.

    - Keeps trailing hashtags only in the last post.
    - Tries to keep posts balanced.
    """
    base, tags = split_trailing_hashtags(text)
    base = " ".join(base.split())  # normalize whitespace

    if len(base + tags) <= max_chars:
        return [(base + tags).strip()]

    # We'll reserve space for hashtags in the last post.
    tags_len = len(tags)

    # Greedy splitting with a feasibility check.
    remaining = base
    posts: list[str] = []

    for idx in range(1, max_posts + 1):
        is_last = idx == max_posts
        if is_last:
            # Whatever remains must fit with tags.
            chunk = remaining.strip()
            # Ensure the last chunk has enough base text.
            if len(chunk) < min_last_chars:
                # If too short, steal from previous post.
                if posts:
                    prev = posts.pop()
                    combined = (prev + " " + chunk).strip()
                    # Re-split combined into two balanced parts.
                    cut = _best_cut(combined, max_chars - tags_len)
                    left = combined[:cut].strip()
                    right = combined[cut:].strip()
                    posts.append(left)
                    chunk = right

            # Clamp if still too long: hard cut
            if len(chunk) + tags_len > max_chars:
                cut = _best_cut(chunk, max_chars - tags_len)
                left = chunk[:cut].strip()
                right = chunk[cut:].strip()
                posts.append(left)
                chunk = right

            posts.append((chunk + tags).strip())
            remaining = ""
            break

        # Not last: leave enough room for remaining posts + last min.
        posts_left = max_posts - idx
        # heuristic: allocate a fair share
        target = max_chars
        cut = _best_cut(remaining, target)
        chunk = remaining[:cut].strip()
        remaining = remaining[cut:].strip()

        if not chunk:
            continue
        posts.append(chunk)

        # If the rest already fits as a last post, finish early.
        if remaining and (len(remaining) + tags_len) <= max_chars:
            posts.append((remaining + tags).strip())
            remaining = ""
            break

    # If still remaining, append it (last resort) by hard chunking.
    while remaining:
        cut = _best_cut(remaining, max_chars)
        posts.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()

    # Ensure hashtags are only in the last post.
    if tags and not posts[-1].endswith(tags.strip()):
        # Move tags to last.
        for i in range(len(posts)):
            posts[i] = posts[i].replace(tags.strip(), "").strip()
        posts[-1] = (posts[-1] + tags).strip()

    # Enforce constraints: keep only max_posts, merge overflow into last.
    if len(posts) > max_posts:
        head = posts[: max_posts - 1]
        tail = " ".join(posts[max_posts - 1 :]).strip()
        posts = head + [tail]

    # Final safety: ensure <= max_chars by trimming tail words.
    while len(posts[-1]) > max_chars:
        posts[-1] = posts[-1][:max_chars].rstrip()

    # Balance sanity: if invalid, reduce to fewer posts.
    if not validate_thread_posts(posts, max_posts=max_posts, max_chars=max_chars, min_last_chars=min_last_chars):
        if max_posts > 2:
            return split_text_to_thread(text, max_posts=2, max_chars=max_chars, min_last_chars=min_last_chars)

    return posts


def select_content_type() -> str:
    """Weighted random selection of content type."""
    content_types = get_content_types()
    types = list(content_types.keys())
    weights = list(content_types.values())
    return random.choices(types, weights=weights, k=1)[0]


def get_blog_base_url() -> str | None:
    base = get("blog.base_url")
    if not base:
        return None
    return str(base).rstrip("/")


def get_blog_posts_dir() -> Path:
    # Optional override; defaults to Echo's local Hugo repo layout.
    p = get("blog.posts_dir")
    if p:
        return Path(p)
    return Path.home() / "projects/echo-blog/content/posts"


def _extract_frontmatter(md: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_text)."""
    if not md.startswith("---"):
        return {}, md

    parts = md.split("---", 2)
    if len(parts) < 3:
        return {}, md

    fm_raw = parts[1]
    body = parts[2].lstrip("\n")
    try:
        fm = yaml.safe_load(fm_raw) or {}
        if not isinstance(fm, dict):
            fm = {}
        return fm, body
    except Exception:
        return {}, body


def _first_paragraph(text: str) -> str:
    for chunk in text.split("\n\n"):
        c = " ".join(line.strip() for line in chunk.splitlines()).strip()
        if c:
            return c
    return ""


def pick_latest_blog_post() -> dict | None:
    """Best-effort: pick the most recent Hugo post from the local repo."""
    posts_dir = get_blog_posts_dir()
    if not posts_dir.exists():
        return None

    candidates = list(posts_dir.glob("*.md"))
    if not candidates:
        return None

    metas: list[dict] = []
    for p in candidates:
        try:
            raw = p.read_text(encoding="utf-8")
        except Exception:
            raw = p.read_text(errors="ignore")

        fm, body = _extract_frontmatter(raw)
        title = fm.get("title") or p.stem
        date_str = fm.get("date")
        dt = None
        if isinstance(date_str, str):
            try:
                dt = datetime.fromisoformat(date_str)
            except Exception:
                dt = None

        excerpt = _first_paragraph(body)
        if len(excerpt) > 240:
            excerpt = excerpt[:237].rstrip() + "..."

        metas.append(
            {
                "path": p,
                "slug": p.stem,
                "title": str(title),
                "date": dt,
                "mtime": p.stat().st_mtime,
                "excerpt": excerpt,
            }
        )

    metas.sort(key=lambda m: (m["date"] is not None, m["date"] or m["mtime"]), reverse=True)
    return metas[0]


def get_source_for_type(content_type: str) -> dict:
    """Get source material based on content type.

    Supports both the original French schema (actualité/économie/activités/passions)
    and the newer schema used by Echo's config (blog_teaser/ops_insight/agent_life/
    tech_take/question).

    Returns dict with:
    - source_type: str
    - source_path: Path or None
    - topic: str | None
    - requires_embed: bool

    Optional keys may be present (e.g. blog_post, embed_url).
    """

    # --- New schema (Echo)
    if content_type == "blog_teaser":
        blog_post = pick_latest_blog_post()
        base_url = get_blog_base_url()
        embed_url = None
        if blog_post and base_url:
            embed_url = f"{base_url}/posts/{blog_post['slug']}/"

        return {
            "source_type": "blog",
            "source_path": None,
            "topic": None,
            "requires_embed": bool(embed_url),
            "blog_post": blog_post,
            "embed_url": embed_url,
        }

    if content_type in {"ops_insight", "agent_life", "question"}:
        return {
            "source_type": "sessions",
            "source_path": None,
            "topic": None,
            "requires_embed": False,
        }

    if content_type == "tech_take":
        return {
            "source_type": "revue_presse",
            "source_path": REVUE_PRESSE_DIR,
            "topic": None,
            "requires_embed": True,
        }

    # --- Original schema (defaults)
    if content_type == "actualité":
        return {
            "source_type": "revue_presse",
            "source_path": REVUE_PRESSE_DIR,
            "topic": None,
            "requires_embed": True,
        }

    if content_type == "économie":
        return {
            "source_type": "revue_finance",
            "source_path": REVUE_FINANCE_DIR,
            "topic": None,
            "requires_embed": True,
        }

    if content_type == "activités":
        return {
            "source_type": "sessions",
            "source_path": None,
            "topic": None,
            "requires_embed": False,
        }

    if content_type == "passions":
        passion_topics = get_passion_topics()
        topic = random.choice(passion_topics)
        return {
            "source_type": "passion",
            "source_path": None,
            "topic": topic,
            "requires_embed": False,
        }

    # Fallback: don't crash cron runs if config drifts.
    return {
        "source_type": "sessions",
        "source_path": None,
        "topic": None,
        "requires_embed": False,
    }


def load_guidelines() -> str:
    """Load posting guidelines."""
    if GUIDELINES_FILE.exists():
        return GUIDELINES_FILE.read_text()
    return ""


def generate_post_with_llm(content_type: str, source: dict, guidelines: str, *, max_posts: int = 3) -> dict | None:
    """Use LLM to generate post content.
    
    Returns dict with:
    - text: str (max 280 chars)
    - embed_url: str or None
    - reason: str (for logging)
    """
    pass_path = get_openrouter_pass_path()
    env = load_from_pass(pass_path)
    if not env or "OPENROUTER_API_KEY" not in env:
        print(f"❌ Missing OPENROUTER_API_KEY in pass {pass_path}")
        return None
    
    api_key = env["OPENROUTER_API_KEY"]
    
    # Build context based on source type
    context = ""
    if source["source_type"] == "revue_presse" and source["source_path"]:
        # Read latest revue
        revue_files = sorted(source["source_path"].glob("*.md"), reverse=True)
        if revue_files:
            raw = revue_files[0].read_text()
            source["url_candidates"] = extract_urls(raw)
            context = raw[:3000]
    elif source["source_type"] == "revue_finance" and source["source_path"]:
        revue_files = sorted(source["source_path"].glob("*.md"), reverse=True)
        if revue_files:
            raw = revue_files[0].read_text()
            source["url_candidates"] = extract_urls(raw)
            context = raw[:3000]
    elif source["source_type"] == "passion":
        context = f"Topic to explore: {source['topic']}"
    elif source["source_type"] == "blog":
        post = source.get("blog_post")
        if post and source.get("embed_url"):
            context = (
                "Promote this blog post:\n"
                f"Title: {post.get('title', '')}\n"
                f"Excerpt: {post.get('excerpt', '')}\n"
                f"URL: {source.get('embed_url')}"
            )
        else:
            context = "Promote a recent blog post (keep it concrete; no private info)."
    elif source["source_type"] == "sessions":
        # Ground the post in recent local artifacts (safe, no private info).
        signals: list[str] = []
        try:
            mem_dir = Path.home() / "personas/echo/memory"
            daily = sorted(mem_dir.glob("20??-??-??.md"), reverse=True)[:2]
            for p in daily:
                txt = p.read_text()[:1500]
                signals.append(f"Memory ({p.name}):\n{txt}")
        except Exception:
            pass

        # Recent commits across relevant repos (broader net)
        repos = [
            Path.home() / "projects/bsky-cli",
            Path.home() / "personas/echo",
            Path.home() / "projects/skills",
            Path.home() / "projects/stocks",
            Path.home() / "projects/typst-templates",
            Path.home() / "projects/briefings",
            Path.home() / "projects/voila-assistant",
            Path.home() / "projects/lufa-assistant",
        ]
        for repo in repos:
            if not (repo / ".git").exists():
                continue
            try:
                out = subprocess.check_output(
                    ["git", "-C", str(repo), "log", "-n", "12", "--pretty=format:%s"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                )
                if out.strip():
                    signals.append(f"Git ({repo.name}) recent commits:\n" + out.strip())
            except Exception:
                pass

        context = (
            "Pick ONE concrete thing from these signals and post about it (no secrets, no private info):\n\n"
            + "\n\n".join(signals)
            if signals
            else "Share something about current work/projects (NO SECRETS, no private info)"
        )
    
    public_truth = truth_section(max_chars=7000)

    prompt = f"""You are Echo, an AI ops agent posting on BlueSky (@echo.0mg.cc).

## GUIDELINES
{guidelines}
{public_truth}

## TASK
Write an organic post about: {content_type}
{f"Topic: {source['topic']}" if source.get('topic') else ""}

## CONTEXT
{context if context else "(Generate from your knowledge/interests)"}

## RULES
- English only
- If you can fit it in one post: return a single post.
- If it's too long: return a thread (max {max_posts} posts) instead.
- Each post must be <= 280 characters (STRICT)
- Hashtags: ONLY in the LAST post of the thread (1-2 hashtags)
- {"Include an embed_url (source link)" if source['requires_embed'] else "No embed required"}
- Be genuine, not generic
- Questions drive engagement
- Show > Tell

## OUTPUT FORMAT
Return ONLY a JSON object. Choose ONE of the two shapes:

A) Single post:
{{
  "text": "... (<= 280 chars)",
  "embed_url": "https://..." or null,
  "reason": "why this post"
}}

B) Thread:
{{
  "posts": [
    {{"text": "... (<= 280 chars)"}},
    {{"text": "... (<= 280 chars)"}}
  ],
  "embed_url": "https://..." or null,
  "reason": "why this thread"
}}

Return ONLY valid JSON, no markdown."""

    max_retries = int(get("organic.llm_retry_max_retries", 2))
    base_backoff = float(get("organic.llm_retry_base_seconds", 3))

    for attempt in range(max_retries + 1):
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

            if r.status_code == 429 and attempt < max_retries:
                retry_after = r.headers.get("Retry-After") if hasattr(r, "headers") else None
                wait_s = float(retry_after) if retry_after and str(retry_after).isdigit() else base_backoff * (2 ** attempt)
                print(f"⚠️ LLM rate-limited (429), retry {attempt + 1}/{max_retries} in {wait_s:.1f}s")
                sleep(wait_s)
                continue

            r.raise_for_status()

            content = r.json()["choices"][0]["message"]["content"]
            content = content.strip()
            if content.startswith("```"):
                content = "\n".join(content.split("\n")[1:-1])

            return json.loads(content)
        except (requests.ConnectionError, requests.Timeout) as e:
            # Transient network errors — retry with backoff
            if attempt < max_retries:
                print(f"⚠️ LLM transient error (attempt {attempt + 1}/{max_retries + 1}): {e}")
                sleep(base_backoff * (2 ** attempt))
                continue
            print(f"❌ LLM error after {max_retries + 1} attempts: {e}")
            return None
        except Exception as e:
            # Permanent errors (auth, bad request, JSON parse) — fail immediately
            print(f"❌ LLM error (non-retryable): {e}")
            return None

    return None


# ============================================================================
# MAIN COMMAND
# ============================================================================

def run(args) -> int:
    """Execute organic post command."""
    probability = getattr(args, 'probability', None) or get_probability()
    dry_run = getattr(args, 'dry_run', False)
    force = getattr(args, 'force', False)
    max_posts = getattr(args, "max_posts", None) or int(get("organic.max_posts", 3))
    
    tz = get_timezone()
    now = datetime.now(tz)
    print(f"🕐 Current time: {now.strftime('%Y-%m-%d %H:%M')} ({tz})")
    
    # Check posting window (unless forced)
    if not force and not is_in_posting_window(now):
        print(f"⏸️  Outside posting window (8:00-22:30 Toronto)")
        return 0
    
    # Probabilistic check (unless forced)
    if not force and not should_post(probability):
        print(f"🎲 Probability check failed ({probability*100:.0f}%)")
        return 0
    
    print(f"✓ Posting check passed")
    
    # Load guidelines
    guidelines = load_guidelines()

    # We'll try a few times. If anti-repeat triggers, generate a different post.
    max_attempts = 4
    attempted_types: list[str] = []

    for attempt in range(1, max_attempts + 1):
        # Select content type (avoid repeating the same type during retries)
        content_type = select_content_type()
        if content_type in attempted_types and len(attempted_types) < 3:
            # small nudge: re-roll once
            content_type = select_content_type()
        attempted_types.append(content_type)
        print(f"📝 Content type: {content_type} (attempt {attempt}/{max_attempts})")

        # Get source
        source = get_source_for_type(content_type)
        print(
            f"📚 Source: {source['source_type']}" +
            (f" ({source['topic']})" if source.get('topic') else "")
        )

        # Generate post
        print("🤖 Generating post...")
        post_data = generate_post_with_llm(content_type, source, guidelines, max_posts=max_posts)

        if not post_data:
            print("❌ Failed to generate post")
            return 1

        # Option A: LLM can output either a single post or a thread.
        if "posts" in post_data and isinstance(post_data.get("posts"), list):
            raw_posts = [str(p.get("text", "")).strip() for p in post_data["posts"] if isinstance(p, dict)]
        else:
            raw_posts = [str(post_data.get("text", "")).strip()]

        embed_url = post_data.get("embed_url")
        if content_type == "blog_teaser" and source.get("embed_url"):
            # Keep teaser embeds deterministic (avoid LLM picking a random URL).
            embed_url = source["embed_url"]

        reason = post_data.get("reason", "")

        # If a single-post output is too long, fall back to deterministic splitting.
        if len(raw_posts) == 1 and len(raw_posts[0]) > 280:
            raw_posts = split_text_to_thread(raw_posts[0], max_posts=max_posts)

        # Validate thread output; if invalid, fallback split from joined text.
        if not validate_thread_posts(raw_posts, max_posts=max_posts):
            joined = "\n\n".join([p for p in raw_posts if p]).strip()
            raw_posts = split_text_to_thread(joined, max_posts=max_posts)

        # Add (i/n) prefixes for threads.
        if len(raw_posts) > 1:
            raw_posts = apply_thread_prefixes(raw_posts, max_chars=280)

        print(f"\n{'[DRY RUN] ' if dry_run else ''}Post content:")
        for i, t in enumerate(raw_posts, start=1):
            label = f"  Post {i}/{len(raw_posts)}" if len(raw_posts) > 1 else "  Text"
            print(f"{label}: {t}")
            print(f"    Length: {len(t)} chars")
        print(f"  Embed: {embed_url or '(none)'}")
        print(f"  Reason: {reason}")

        if dry_run:
            print("\n✓ Dry run complete")
            return 0

        # Post
        print("\n🔗 Connecting to BlueSky...")
        pds, did, jwt, handle = get_session()
        print(f"✓ Logged in as @{handle}")

        # Fetch embed (ensure OG image works; otherwise try alternate URLs)
        embed = None
        if embed_url or source.get("url_candidates"):
            candidates = []
            if source.get("url_candidates"):
                candidates.extend([u for u in source["url_candidates"] if isinstance(u, str)])
            if embed_url:
                candidates.insert(0, embed_url)

            # de-dupe
            seen = set()
            candidates = [u for u in candidates if not (u in seen or seen.add(u))]

            # Require thumbnail image for "actualité" embeds
            require_thumb = bool(source.get("requires_embed"))

            for url in candidates[:12]:
                try:
                    print(f"🔗 Fetching embed for {url}...")
                    e = create_external_embed(pds, jwt, url)
                    if require_thumb and not (e and e.get("external", {}).get("thumb")):
                        print("⚠️  Embed missing thumb; trying next URL")
                        continue
                    embed = e
                    embed_url = url
                    if embed:
                        print(f"✓ Embed ready: {embed.get('external', {}).get('title', '')[:50]}")
                    break
                except Exception:
                    continue

            if source.get("requires_embed") and not embed:
                print("❌ Could not build a valid embed with OG image; changing source...")
                if attempt < max_attempts:
                    continue
                return 1

        try:
            # Thread posting (root + replies)
            root_ref = None
            parent_ref = None
            result = None

            for i, text in enumerate(raw_posts, start=1):
                facets = detect_facets(text)
                this_embed = embed if i == 1 else None

                result = create_post(
                    pds,
                    jwt,
                    did,
                    text,
                    facets=facets,
                    embed=this_embed,
                    allow_repeat=(i > 1),
                    reply_root=root_ref,
                    reply_parent=parent_ref,
                )

                # Update refs for subsequent replies
                ref = {"uri": result.get("uri"), "cid": result.get("cid")}
                if not root_ref:
                    root_ref = ref
                parent_ref = ref
        except SystemExit as e:
            msg = str(e)
            if "looks too similar" in msg and attempt < max_attempts:
                print("⚠️  Anti-repeat guard triggered; generating a different post...")
                continue
            raise

        if result:
            print(f"\n✓ Posted successfully!")
            print(f"  URI: {result.get('uri', '')}")
            return 0

        print("\n❌ Failed to post")
        return 1

    print("\n❌ Exhausted attempts due to anti-repeat guard")
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
    parser.add_argument("--probability", type=float, default=None,
                        help="Posting probability (default: from config)")
    parser.add_argument("--max-posts", type=int, default=None,
                        help="Max posts in a thread when text exceeds 280 (default: from config organic.max_posts, fallback 3)")

    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
