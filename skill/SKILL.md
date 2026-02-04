# bsky-cli Skill

CLI for BlueSky automation. Use for posting, engagement, thread tracking, and discovery.

## Installation

```bash
cd ~/projects/bsky-cli
uv sync
```

## Credentials

Load from pass:
```bash
source ~/scripts/pass-env.sh api/bsky
```

Required in `api/bsky`:
```
BSKY_HANDLE=yourhandle.bsky.social
BSKY_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
```

For LLM features, also need `api/openrouter` with `OPENROUTER_API_KEY`.

## Commands

### Post
```bash
uv run bsky post "Hello world"
uv run bsky post --embed https://example.com "Check this out"
```

### Reply
```bash
uv run bsky reply "https://bsky.app/profile/user/post/xyz" "Great point!"
```

### Notifications
```bash
uv run bsky notify              # New notifications
uv run bsky notify --all        # All recent
uv run bsky notify --json       # JSON output
```

### Engage (LLM-powered)
```bash
uv run bsky engage --hours 12   # Find interesting posts, reply thoughtfully
uv run bsky engage --dry-run    # Preview without posting
```

### Discover
```bash
uv run bsky discover            # Find accounts to follow
uv run bsky discover reposts    # From repost activity
```

### Follow
```bash
uv run bsky follow @handle.bsky.social
```

### Threads
```bash
uv run bsky threads list                    # List tracked threads
uv run bsky threads evaluate <url>          # Score a thread
uv run bsky threads branches <handle>       # Check branch activity
uv run bsky threads backoff-update <handle> # Increase interval (no activity)
uv run bsky threads backoff-update <handle> --activity  # Reset to 10min
```

### Organic
```bash
uv run bsky organic   # Time-varied posting with randomness
```

### Announce (blog posts)
```bash
uv run bsky announce my-post-slug   # Announce with link card
```

### Profile
```bash
uv run bsky profile --bio "New bio"
uv run bsky profile --avatar ~/avatar.png
uv run bsky profile --name "Display Name"
```

### Delete
```bash
uv run bsky delete --count 3      # Delete last 3 posts
uv run bsky delete --dry-run      # Preview
```

### DM
```bash
uv run bsky dm @user "Hello!"
uv run bsky dm --list
```

## Thread Monitoring

For cron-based thread monitoring, use persistent crons with update (not delete-after-run):

```bash
# Check thread, then update interval
uv run bsky threads branches echo.0mg.cc

# If activity found:
cron update --jobId <id> --patch '{"schedule":{"kind":"every","everyMs":600000}}'

# If no activity, double interval:
cron update --jobId <id> --patch '{"schedule":{"kind":"every","everyMs":1200000}}'
```

Backoff sequence: 10min → 20 → 40 → 80 → 160 → 240min → 18h → disable

## State Files

- `~/.bsky-cli/state.json` — Replied posts, daily limits
- `~/.bsky-cli/conversations.json` — Conversation tracking
- `~/personas/echo/data/bsky-threads-state.json` — Thread tracking

## Source

- **GitHub**: https://github.com/echo931/bsky-cli
- **Docs**: https://echo.0mg.cc/posts/bsky-cli-open-source/
