# bsky-cli

A comprehensive command-line interface for BlueSky, built for automation and AI agents.

## Features

| Category | What it does |
|----------|-------------|
| **Post & Reply** | Create posts, quote posts, reply to threads, embed links |
| **Interactions** | Like, repost, bookmark, search, follow |
| **Engagement** | LLM-powered replies to interesting posts from your follows |
| **Appreciation** | Probabilistic likes and quote-reposts of quality content |
| **Discovery** | Find accounts via mutual follows or repost analysis |
| **Thread Tracking** | Monitor conversations with exponential backoff |
| **People** | Track interaction history, notes, tags, LLM-enriched profiles |
| **Context Packs** | Build HOT/COLD context summaries for LLM prompts |
| **Organic Posting** | Time-varied, context-aware autonomous posting |
| **DMs** | Send and browse direct messages |
| **Lists & Starter Packs** | Manage curated lists and onboarding packs |
| **Notifications** | Scored triage with budgeted auto-actions |

## Installation

Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv).

```bash
git clone https://github.com/echo931/bsky-cli.git
cd bsky-cli
uv sync
```

## Authentication

Credentials are loaded from [pass](https://www.passwordstore.org/) (default path: `api/bsky-echo`):

```
BSKY_HANDLE=yourhandle.bsky.social
BSKY_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
```

Get an app password from: [Settings → App Passwords](https://bsky.app/settings/app-passwords)

For LLM features (`engage`, `appreciate`, `organic`, `people --enrich`), create a dedicated pass entry at `api/openrouter-bsky`:

```
OPENROUTER_API_KEY=sk-or-...
```

## Quick Start

```bash
# Post
uv run bsky post "Hello, BlueSky!"

# Search
uv run bsky search "AI agents" --since 24h --sort top

# Check notifications
uv run bsky notify --all

# Send a DM
uv run bsky dm user.bsky.social "Hey!"

# Build context for someone
uv run bsky context user.bsky.social
```

## Command Overview

> **Note**: All examples below assume you're in the `bsky-cli` project directory.  
> Use `uv run bsky ...` or activate the virtualenv first (`source .venv/bin/activate`).

### Posting & Interaction

```bash
bsky post "Hello!"                    # Simple post
bsky post --embed https://url "Text"  # Post with link preview
bsky post -q "https://bsky.app/..." "Comment"  # Quote post

bsky reply "https://bsky.app/..." "Great point!"
bsky like "https://bsky.app/..."
bsky repost "https://bsky.app/..."
bsky delete --count 3 --dry-run       # Preview deletion of last 3 posts
```

### Search

```bash
bsky search "query"                       # Search posts
bsky search --author user.bsky.social "topic"  # Filter by author
bsky search --since 7d --sort top "trending"   # Top posts from last week
```

### Notifications (with scoring & auto-actions)

```bash
bsky notify                     # New notifications
bsky notify --score             # Score and propose actions
bsky notify --execute --quiet --max-likes 30 --max-replies 10 --max-follows 5  # Execute with budgets (cron-friendly)
```

### LLM-Powered Engagement

```bash
# Reply to interesting posts from your follows
bsky engage --dry-run             # Preview
bsky engage --hours 24            # Engage with last 24h of posts
bsky engage --max-runtime-seconds 300  # 5-min time limit

# Passive appreciation (likes + quote-reposts)
bsky appreciate --dry-run
bsky appreciate --max 8 --hours 12

# Autonomous posting (probability-gated)
bsky organic                      # Normal (20% chance per call)
bsky organic --force              # Bypass probability gate
bsky organic --dry-run            # Preview
```

### Discovery

```bash
bsky discover follows --execute --max 5   # Follow suggestions from your network
bsky discover reposts --execute --max 3   # Follow frequently reposted authors
bsky discover follows --max-runtime-seconds 120  # With time limit
```

### Thread Monitoring

```bash
bsky threads watch "https://bsky.app/.../post/xyz"  # Start watching
bsky threads list                                     # List tracked threads
bsky threads tree "https://bsky.app/.../post/xyz"    # Visual ASCII tree

# Thread tree example output:
# 🌳 Thread tree: @alice.bsky.social
# ├── "Distributed identity is the future..."
# │   ├── @bob.dev: "Completely agree..."
# │   │   └── @echo.0mg.cc: "The DID layer is key..."
# │   └── @carol.bsky.social: "What about key rotation?"
# └── (4 total replies, depth 3)

bsky threads branches user.bsky.social    # Check branch relevance
bsky threads unwatch user.bsky.social     # Stop watching
```

Backoff intervals: 10min → 20min → 40min → 80min → 160min → 240min → 18h

### People & Context

```bash
bsky people                               # List known interlocutors
bsky people --regulars                    # Only regulars (3+ interactions)
bsky people user.bsky.social              # History with someone
bsky people user.bsky.social --set-note "Met at conference"
bsky people --enrich --execute            # LLM-generated auto-notes

bsky context user.bsky.social             # HOT/COLD context pack
bsky context user.bsky.social --dm 50     # Include more DM history
bsky context user.bsky.social --json      # JSON output for piping

bsky search-history user.bsky.social "topic"  # FTS5 search of local history
bsky search-history user.bsky.social "meeting" --scope dm
```

### DMs

```bash
bsky dm user.bsky.social "Hello!"     # Send a DM
bsky dms --preview 1                  # List conversations
bsky dms show user.bsky.social        # Read conversation
```

### Lists & Starter Packs

```bash
bsky lists list
bsky lists create "Climate Tech" --description "People working on climate"
bsky lists add "Climate Tech" user.bsky.social
bsky lists show "Climate Tech"

bsky starterpack create "Climate Starter" --list "Climate Tech"
```

### Blog Announcements

```bash
bsky announce my-post-slug
bsky announce my-post-slug --text "Custom announcement text"
```

### Profile & Config

```bash
bsky profile --bio "AI agent" --name "Echo 🛠️"
bsky config          # Show current config
bsky config --init   # Create config with defaults
bsky --version       # Show version
```

## Configuration

Optional YAML config at `~/.config/bsky-cli/config.yaml`:

```yaml
timezone: America/Toronto

topics:
  - AI
  - linux
  - climate

organic:
  probability: 0.20
  posting_windows:
    - [7, 0, 23, 30]

engage:
  hours: 12
  max_per_account: 1

notify:
  budgets:
    max_replies: 10
    max_likes: 30
    max_follows: 5
  relationship_follow:
    enabled: false  # opt-in; default is disabled
```

All settings are optional — sensible defaults work out of the box.

When `notify.relationship_follow.enabled` is true, `notify --execute` can trigger probabilistic follows on `reply`/`repost` interactions:
- >10 prior interactions: `maybe.sh 0.1`
- >50 prior interactions: `maybe.sh 0.3`
- blocked when `relationship_tone` is negative

### Optional: public truth grounding for LLM publishing

For third-party users, this is **opt-in** (disabled by default). When enabled, LLM publishing prompts include a local truth file before generating content.

```yaml
public_truth:
  enabled: true
  path: ~/personas/echo/PUBLIC_ABOUT_ME.md  # optional custom path
```

Used by LLM-powered publishing flows (`organic`, `engage`, `appreciate`, `notify --execute` reply/quote generation).

## Runtime Guards

Commands that scan your follow list (`engage`, `appreciate`, `discover`) support `--max-runtime-seconds` to prevent runaway execution:

- Logs which phase timed out (collect/score/decide/act)
- Saves partial state before exiting (progress preserved)
- Exits with code `124` on timeout
- Next run resumes from saved state

Essential for accounts with many follows (200+).

## Cron Examples

```bash
# Notifications every 15 min
*/15 * * * * cd ~/bsky-cli && uv run bsky notify --execute --quiet --max-likes 30 --no-dm

# Engage twice daily (with time limit)
0 10,17 * * * cd ~/bsky-cli && uv run bsky engage --max-runtime-seconds 300

# Appreciate at noon
30 12 * * * cd ~/bsky-cli && uv run bsky appreciate --max 6 --max-runtime-seconds 120

# Organic posting (with built-in probability gate)
*/30 8-22 * * * cd ~/bsky-cli && uv run bsky organic

# Discover new accounts daily
0 15 * * * cd ~/bsky-cli && uv run bsky discover follows --execute --max 5 --max-runtime-seconds 120
```

## Documentation

- **[CLI Reference](docs/CLI_REFERENCE.md)** — Exhaustive reference for every command and option
- **[Usage Guide](docs/USAGE_GUIDE.md)** — Practical workflows and playbooks

## License

MIT

## Credits

Built by [Echo](https://echo.0mg.cc), an AI agent running on [OpenClaw](https://github.com/openclaw/openclaw).

BlueSky: [@echo.0mg.cc](https://bsky.app/profile/echo.0mg.cc)
