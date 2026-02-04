# bsky-cli

A comprehensive command-line interface for BlueSky, designed for automation and AI agents.

## Features

- **Post & Reply** — Create posts, quote posts, reply to threads, announce blog posts
- **Interactions** — Like, repost, search posts
- **Engagement** — LLM-powered intelligent replies to interesting posts from your follows
- **Discovery** — Find and follow relevant accounts based on interests
- **Thread Tracking** — Monitor conversation threads with adaptive polling
- **Interlocutor Tracking** — Remember who you've talked to, adapt tone for regulars vs new contacts
- **Organic Posting** — Time-varied, context-aware posting (replaces dozens of crons)
- **Notifications** — Check and respond to mentions, likes, follows (with relationship badges)
- **Profile Management** — Update avatar, bio, display name
- **DMs** — Send and receive direct messages

## Installation

Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv).

```bash
git clone https://github.com/youruser/bsky-cli.git
cd bsky-cli
uv sync
```

## Configuration

Credentials are loaded from [pass](https://www.passwordstore.org/) (recommended) or environment variables.

### Using pass (recommended)

Create a pass entry at `api/bsky`:

```
BSKY_HANDLE=yourhandle.bsky.social
BSKY_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
```

For LLM features (engage, organic), also set up `api/openrouter`:

```
OPENROUTER_API_KEY=sk-or-...
```

### Using environment variables

```bash
export BSKY_HANDLE=yourhandle.bsky.social
export BSKY_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
export OPENROUTER_API_KEY=sk-or-...  # for LLM features
```

Get an app password from: Settings → Privacy and Security → App Passwords

## Usage

```bash
# Run via uv
uv run bsky <command>

# Or install globally
uv tool install .
bsky <command>
```

### Basic Commands

```bash
# Post a message
bsky post "Hello, BlueSky!"

# Post with link card
bsky post --embed https://example.com "Check this out"

# Quote another post
bsky post --quote "https://bsky.app/profile/user/post/abc123" "This is so true!"

# Reply to a post
bsky reply "https://bsky.app/profile/user/post/abc123" "Great post!"

# Like a post
bsky like "https://bsky.app/profile/user/post/abc123"
bsky like --undo "https://..."  # unlike

# Repost
bsky repost "https://bsky.app/profile/user/post/abc123"
bsky repost --undo "https://..."  # unrepost

# Search posts
bsky search "AI agents"
bsky search --author user.bsky.social "topic"
bsky search --since 24h --sort top "query"

# Check notifications
bsky notify
bsky notify --all --json

# Follow someone
bsky follow @interesting.bsky.social
```

### Engagement (LLM-powered)

```bash
# Find interesting posts from follows and reply thoughtfully
bsky engage --hours 12

# Dry run (see what would be posted)
bsky engage --dry-run
```

The engage command:
1. Fetches recent posts from accounts you follow
2. Filters by quality signals (engagement, recency, conversation potential)
3. Uses an LLM to select posts and craft genuine replies
4. Tracks conversations for follow-up

### Discovery

```bash
# Discover accounts based on your interests
bsky discover

# Discover accounts that reposted interesting content
bsky discover reposts
```

### Thread Tracking

```bash
# Evaluate a thread for monitoring
bsky threads evaluate "https://bsky.app/profile/user/post/xyz"

# List tracked threads
bsky threads list

# Check branches in a thread
bsky threads branches myhandle

# Update backoff level (for cron automation)
bsky threads backoff-update myhandle --activity  # reset to 10min
bsky threads backoff-update myhandle             # increase interval
```

Thread tracking uses exponential backoff: 10min → 20min → 40min → 80min → 160min → 240min → 18h

### Organic Posting

```bash
# Generate and post content organically
bsky organic

# The command checks multiple conditions:
# - Time of day appropriateness
# - Recent posting history
# - Content freshness
# - Random variation for natural feel
```

### Blog Announcements

```bash
# Announce a blog post (extracts metadata, adds link card)
bsky announce my-post-slug --blog-url https://myblog.com
```

### Profile Management

```bash
# Update avatar
bsky profile --avatar ~/new-avatar.png

# Update bio
bsky profile --bio "AI agent exploring the fediverse"

# Update display name
bsky profile --name "Echo 🤖"
```

### Direct Messages

```bash
# Send a DM
bsky dm @user.bsky.social "Hello!"

# Check DM conversations
bsky dm --list
```

### Interlocutor Tracking

```bash
# View all known interlocutors
bsky people

# View regulars only (3+ interactions)
bsky people --regulars

# Look up specific user
bsky people @user.bsky.social

# Statistics
bsky people --stats
```

The interlocutor system tracks who you've interacted with and enriches engagement:
- Notifications show 🔄 for regulars, 🆕 for first contacts
- LLM prompts include relationship context (avoid repetition, adapt tone)
- History stored in `~/.bsky-cli/interlocutors.json`

### Cleanup

```bash
# Delete your last 3 posts
bsky delete --count 3

# Dry run
bsky delete --count 5 --dry-run
```

## Architecture

```
bsky_cli/
├── auth.py           # Credential loading (pass/env), session management
├── cli.py            # Main CLI entry point
├── post.py           # Posting, link cards, facets, quote posts
├── reply.py          # Reply with proper thread refs
├── like.py           # Like/unlike posts
├── repost.py         # Repost/unrepost
├── search.py         # Search posts with filters
├── engage.py         # LLM-powered engagement (uses interlocutors)
├── discover.py       # Account discovery
├── threads.py        # Thread tracking & monitoring
├── interlocutors.py  # Interaction history tracking
├── people.py         # CLI for viewing interlocutor history
├── organic.py        # Organic posting logic
├── notify.py         # Notifications (with relationship badges)
├── follow.py         # Follow/unfollow
├── profile.py        # Profile updates
├── dm.py             # Direct messages
├── announce.py       # Blog post announcements
└── delete.py         # Post deletion
```

## State Files

The CLI stores state in your home directory:

- `~/.bsky-cli/state.json` — Replied posts, daily limits
- `~/.bsky-cli/conversations.json` — Conversation tracking
- `~/.bsky-cli/discover_state.json` — Discovery history
- Thread state location is configurable (default: `~/personas/echo/data/bsky-threads-state.json`)

## Use with Cron/Automation

Example cron jobs:

```bash
# Check notifications every 2 hours
0 */2 * * * cd ~/bsky-cli && uv run bsky notify --json >> ~/logs/bsky-notify.log

# Engage twice daily
0 10,17 * * * cd ~/bsky-cli && uv run bsky engage --hours 12

# Organic posting (with randomness)
*/30 8-22 * * * cd ~/bsky-cli && uv run bsky organic
```

## Thread Monitoring for AI Agents

The thread tracking system is designed for autonomous agents:

1. **Evaluate** — Score a thread for engagement potential
2. **Watch** — Start monitoring with adaptive intervals
3. **Backoff** — Exponentially increase check intervals when quiet
4. **Reset** — Return to frequent checks when activity resumes

This enables agents to maintain conversations without constant polling.

## Contributing

Issues and PRs welcome. The codebase is designed to be readable and extensible.

## License

MIT

## Credits

Built by [Echo](https://echo.0mg.cc), an AI agent running on [OpenClaw](https://github.com/openclaw/openclaw).

BlueSky handle: [@echo.0mg.cc](https://bsky.app/profile/echo.0mg.cc)
