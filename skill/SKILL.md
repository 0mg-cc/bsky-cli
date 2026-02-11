# bsky-cli Skill

CLI for BlueSky social network — posting, engagement, discovery, DMs, thread tracking, and more.

**Full reference**: `docs/CLI_REFERENCE.md` (exhaustive, all commands + options)

## Setup

```bash
uv sync   # from the bsky-cli project root
```

## Authentication

Credentials loaded from `pass` (default path: `api/bsky-echo`).  
Required keys: `BSKY_HANDLE`, `BSKY_APP_PASSWORD`.  
LLM features (`engage`, `appreciate`, `organic`, `people --enrich`) also need a `pass` entry at `api/openrouter` with `OPENROUTER_API_KEY`.

## Commands

### Posting & Interaction

```bash
uv run bsky post "Hello!"                              # Post (max 300 chars)
uv run bsky post --embed https://url "Check this out"  # With link preview
uv run bsky post -q "https://bsky.app/..." "Comment"   # Quote post
uv run bsky reply "https://bsky.app/..." "Great post!" # Reply
uv run bsky like "https://bsky.app/..."                # Like
uv run bsky like --undo "https://bsky.app/..."         # Unlike
uv run bsky repost "https://bsky.app/..."              # Repost
uv run bsky bookmark "https://bsky.app/..."            # Bookmark
uv run bsky follow user.bsky.social                    # Follow
uv run bsky delete --count 3                           # Delete last 3 posts
```

Most write commands support `--dry-run` for preview (check `--help` for each).

### Search

```bash
uv run bsky search "AI agents"                             # Basic search
uv run bsky search --author user.bsky.social "topic"       # Filter by author
uv run bsky search --since 24h --sort top --limit 10 "q"   # Time + sort
```

Time formats: `24h`, `7d`, `2w`, or ISO timestamps.

### Notifications

```bash
uv run bsky notify                         # New notifications
uv run bsky notify --all --json            # All, as JSON
uv run bsky notify --score                 # Score and propose actions
# Automated (cron-friendly)
uv run bsky notify --execute --quiet \
  --allow-replies --max-replies 10 \
  --max-likes 30 --max-follows 5 \
  --limit 60 --no-dm
```

### LLM-Powered Features

```bash
# Engage: reply to interesting posts from follows
uv run bsky engage --dry-run
uv run bsky engage --hours 24 --max-runtime-seconds 300

# Appreciate: like/quote-repost quality content (probabilistic)
uv run bsky appreciate --dry-run
uv run bsky appreciate --max 8 --hours 12 --max-runtime-seconds 120

# Organic: autonomous posting (probability-gated)
uv run bsky organic              # 20% chance per call
uv run bsky organic --force      # Bypass probability
uv run bsky organic --dry-run    # Preview

# Discover: find new accounts to follow
uv run bsky discover follows --execute --max 5
uv run bsky discover reposts --execute --max 3
```

### DMs

```bash
uv run bsky dm user.bsky.social "Message"     # Send DM
uv run bsky dms --preview 1                   # List conversations
uv run bsky dms show user.bsky.social         # Read conversation
```

### People & Context

```bash
uv run bsky people                                  # List interlocutors
uv run bsky people --regulars                       # Regulars only (3+)
uv run bsky people user.bsky.social                 # History with someone
uv run bsky people user.bsky.social --set-note "..."  # Add note
uv run bsky people --enrich --execute               # LLM auto-notes

uv run bsky context user.bsky.social                # HOT/COLD context pack
uv run bsky context user.bsky.social --json         # JSON for piping
uv run bsky context user.bsky.social --focus "at://..."  # Focus specific post

uv run bsky search-history user.bsky.social "query"        # FTS5 search
uv run bsky search-history user.bsky.social "q" --scope dm # DMs only
```

### Threads

```bash
uv run bsky threads watch "https://bsky.app/.../post/xyz"  # Watch
uv run bsky threads list                                     # List tracked
uv run bsky threads tree "https://bsky.app/.../post/xyz"    # ASCII tree
uv run bsky threads tree "..." --mine-only --depth 3        # Filter
uv run bsky threads branches user.bsky.social               # Branch relevance
uv run bsky threads unwatch user.bsky.social                # Stop watching
uv run bsky threads evaluate                                 # Score for monitoring
uv run bsky threads backoff-check user.bsky.social          # Check if due
uv run bsky threads backoff-update user.bsky.social         # Increase interval
uv run bsky threads backoff-update user.bsky.social --activity  # Reset (new activity)
uv run bsky threads migrate-state --dry-run                 # Migrate legacy JSON → SQLite
```

Backoff: 10min → 20min → 40min → 80min → 160min → 240min → 18h

### Lists & Starter Packs

```bash
uv run bsky lists list
uv run bsky lists create "Name" --description "..."
uv run bsky lists add "Name" user.bsky.social
uv run bsky lists show "Name"

uv run bsky starterpack list
uv run bsky starterpack create "Name" --list "ListName"
```

### Blog & Profile

```bash
uv run bsky announce my-post-slug                   # Announce blog post
uv run bsky announce my-post-slug --text "Custom"   # Custom text
uv run bsky profile --bio "..." --name "Echo 🛠️"   # Update profile
uv run bsky config                                  # Show config
uv run bsky config --init                           # Create defaults
```

## Runtime Guards

`engage`, `appreciate`, and `discover` support `--max-runtime-seconds N`:
- Saves partial state before exit on timeout
- Exits with code `124`
- Next run resumes from saved state
- Essential for accounts with 200+ follows

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Error |
| `124` | Timeout (`--max-runtime-seconds` exceeded) |

## Cron Patterns

```bash
# Notifications every 15 min
*/15 * * * * uv run bsky notify --execute --quiet --max-likes 30 --no-dm

# Engage twice daily
0 10,17 * * * uv run bsky engage --max-runtime-seconds 300

# Appreciate at noon
30 12 * * * uv run bsky appreciate --max 6 --max-runtime-seconds 120

# Organic (with probability gate)
*/30 8-22 * * * uv run bsky organic

# Discover daily
0 15 * * * uv run bsky discover follows --execute --max 5 --max-runtime-seconds 120
```

## State & Config

- **Config**: `~/.config/bsky-cli/config.yaml` (all settings optional)
- **Per-account DB**: `~/.bsky-cli/accounts/<account>/bsky.db` (context, threads, DMs)
- **State files**: `~/.bsky-cli/state.json`, `discover_state.json`, etc.

## Source

- **GitHub**: https://github.com/echo931/bsky-cli
- **Docs**: `docs/CLI_REFERENCE.md` (exhaustive) · `docs/USAGE_GUIDE.md` (workflows)
