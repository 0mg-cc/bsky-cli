"""Announce command for BlueSky CLI."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from .auth import get_session
from .post import create_post, detect_facets, create_external_embed

BLOG_DIR = Path.home() / "projects" / "echo-blog"
BLOG_URL = "https://echo.0mg.cc"
MANDATORY_HASHTAGS = ["#Clawdbot", "#Moltbot"]


def extract_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter from markdown."""
    match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return {}
    
    fm = {}
    for line in match.group(1).split('\n'):
        if ':' in line:
            key, val = line.split(':', 1)
            key = key.strip()
            val = val.strip()
            
            if val.startswith('[') and val.endswith(']'):
                items = val[1:-1].split(',')
                fm[key] = [item.strip().strip('"\'') for item in items if item.strip()]
            elif val.startswith('"') and val.endswith('"'):
                fm[key] = val[1:-1]
            else:
                fm[key] = val
    return fm


def find_post(slug_or_path: str) -> Path | None:
    """Find post file from slug or path."""
    p = Path(slug_or_path).expanduser()
    if p.exists():
        return p
    
    posts_dir = BLOG_DIR / "content" / "posts"
    
    exact = posts_dir / f"{slug_or_path}.md"
    if exact.exists():
        return exact
    
    idx = posts_dir / slug_or_path / "index.md"
    if idx.exists():
        return idx
    
    return None


def format_hashtags(tags: list[str], max_tags: int = 3) -> str:
    """Convert tags to hashtags, limit count, append mandatory ones."""
    hashtags = []
    for tag in tags[:max_tags]:
        clean = re.sub(r'[^a-zA-Z0-9]', '', tag.title().replace('-', ' ').replace('_', ' '))
        if clean:
            hashtags.append(f"#{clean}")
    hashtags.extend(MANDATORY_HASHTAGS)
    return ' '.join(hashtags)


def run(args) -> int:
    """Execute announce command."""
    post_file = find_post(args.post)
    if not post_file:
        print(f"Error: Post not found: {args.post}", file=sys.stderr)
        return 1
    
    content = post_file.read_text()
    fm = extract_frontmatter(content)
    
    title = fm.get('title', '')
    tags = fm.get('tags', [])
    
    if not title:
        print("Error: No title in frontmatter", file=sys.stderr)
        return 1
    
    # Build slug from file path
    if post_file.name == "index.md":
        slug = post_file.parent.name
    else:
        slug = post_file.stem
    
    url = f"{BLOG_URL}/posts/{slug}/"
    
    # Build post text
    text = args.text or title
    if tags:
        hashtags = format_hashtags(tags)
        text = f"{text}\n\n{hashtags}"
    
    # Check length
    if len(text) > 300:
        hashtags = format_hashtags(tags)
        max_title = 300 - len(hashtags) - 4
        text = f"{title[:max_title]}...\n\n{hashtags}"
    
    print(f"Title: {title}")
    print(f"URL: {url}")
    print(f"Tags: {', '.join(tags) if tags else '(none)'}")
    print(f"Text ({len(text)} chars):\n---\n{text}\n---")
    
    if args.dry_run:
        print("\nDRY RUN: would post above text with embed")
        return 0
    
    pds, did, jwt, _ = get_session()
    
    facets = detect_facets(text)
    embed = create_external_embed(pds, jwt, url)
    
    res = create_post(pds, jwt, did, text, facets=facets, embed=embed)
    
    uri = res.get("uri", "")
    m = re.match(r"^at://([^/]+)/app\.bsky\.feed\.post/([^/]+)$", uri)
    if m:
        print(f"\n✅ Posted: https://bsky.app/profile/{m.group(1)}/post/{m.group(2)}")
    else:
        print(res)
    return 0
