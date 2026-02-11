# bsky-cli — Command Reference

Complete reference for every command in `bsky-cli`. Each entry documents the command's purpose, all options, example output, and practical usage patterns.

**Version**: 0.12.0  
**Config**: `~/.config/bsky-cli/config.yaml`  
**Auth**: credentials loaded from `pass` (`pass show api/bsky`) — requires `BSKY_HANDLE` (or `BSKY_EMAIL`) and `BSKY_APP_PASSWORD` entries. See `bsky config --init` for setup.

---

## Command Tree

```
bsky
├── post              Post a message
├── reply             Reply to a post
├── like              Like/unlike a post
├── repost            Repost/unrepost a post
├── delete            Delete recent posts
├── search            Search posts
├── bookmark          Save/remove a bookmark
├── bookmarks
│   └── list          List bookmarks
├── follow            Follow a user
├── profile           Update your profile
├── dm                Send a direct message
├── dms
│   └── show          Show messages for a conversation
├── announce          Announce a blog post
├── notify            Check and act on notifications
├── engage            Reply to interesting posts (LLM-powered)
├── appreciate        Like/quote-repost interesting posts (LLM-powered)
├── discover
│   ├── follows       Discover accounts via mutual follows
│   └── reposts       Discover accounts via repost analysis
├── organic           Autonomous posting (LLM-powered)
├── people            View and manage interaction history
├── context           Build a context pack for a handle
├── search-history    Search local interaction history (FTS5)
├── lists
│   ├── list          List your lists
│   ├── create        Create a list
│   ├── add           Add an account to a list
│   └── show          Show list members
├── starterpack
│   ├── list          List starter packs
│   └── create        Create a starter pack
├── threads
│   ├── evaluate      Evaluate notifications for threads
│   ├── list          List tracked threads
│   ├── watch         Start watching a thread
│   ├── unwatch       Stop watching a thread
│   ├── branches      Check branch relevance
│   ├── tree          Print ASCII tree of a thread
│   ├── backoff-check Check if monitoring is due
│   ├── backoff-update Update backoff state
│   └── migrate-state Migrate legacy JSON to SQLite
├── config            Manage configuration
└── --version         Show version
```

---

## Posting & Interaction

### `bsky post`

Create a new post on BlueSky (skeet). Supports plain text, embedded links with previews, and quote posts.

```
bsky post [text] [--embed URL] [--quote URL] [--allow-repeat] [--dry-run]
```

| Option | Description |
|--------|-------------|
| `text` | Post text, max 300 characters (required). |
| `--embed URL` | Attach a URL with a link preview card. |
| `--quote URL`, `-q` | Quote-post another post by its `bsky.app` URL. |
| `--allow-repeat` | Skip duplicate detection (last 10 posts are checked by default). |
| `--dry-run` | Print what would be posted without actually posting. |

**Example output:**
```
✓ Posted: https://bsky.app/profile/echo.0mg.cc/post/3membe3jbej2o
```

**Practical usage:**
```bash
# Simple post
bsky post "Exploring the AT Protocol today 🔬"

# Post with a link preview
bsky post --embed https://echo.0mg.cc/posts/my-article "New blog post!"

# Quote someone else's post with commentary
bsky post --quote "https://bsky.app/profile/user.bsky.social/post/abc123" "Exactly this."

# Preview before posting
bsky post --dry-run "Testing my message"
```

---

### `bsky reply`

Reply to an existing post. The reply is threaded under the target post.

```
bsky reply <post_url> <text> [--dry-run]
```

| Option | Description |
|--------|-------------|
| `post_url` | Full `bsky.app` URL of the post to reply to. |
| `text` | Reply text, max 300 characters. |
| `--dry-run` | Print without posting. |

**Example output:**
```
✓ Replied: https://bsky.app/profile/echo.0mg.cc/post/3memcx7abc123
```

**Practical usage:**
```bash
# Reply to a post
bsky reply "https://bsky.app/profile/user.bsky.social/post/abc123" "Great point! I've been thinking about this too."

# Preview reply
bsky reply --dry-run "https://bsky.app/profile/user.bsky.social/post/abc123" "Draft reply"
```

---

### `bsky like`

Like or unlike a post.

```
bsky like <post_url> [--undo] [--dry-run]
```

| Option | Description |
|--------|-------------|
| `post_url` | Full `bsky.app` URL of the post. |
| `--undo` | Remove an existing like (unlike). |
| `--dry-run` | Print without acting. |

**Example output:**
```
✓ Liked: https://bsky.app/profile/user.bsky.social/post/abc123
```

**Practical usage:**
```bash
# Like a post
bsky like "https://bsky.app/profile/user.bsky.social/post/abc123"

# Unlike it
bsky like --undo "https://bsky.app/profile/user.bsky.social/post/abc123"
```

---

### `bsky repost`

Repost (boost) or un-repost a post.

```
bsky repost <post_url> [--undo] [--dry-run]
```

| Option | Description |
|--------|-------------|
| `post_url` | Full `bsky.app` URL of the post. |
| `--undo` | Remove an existing repost. |
| `--dry-run` | Print without acting. |

**Example output:**
```
✓ Reposted: https://bsky.app/profile/user.bsky.social/post/abc123
```

**Practical usage:**
```bash
# Repost
bsky repost "https://bsky.app/profile/user.bsky.social/post/abc123"

# Undo repost
bsky repost --undo "https://bsky.app/profile/user.bsky.social/post/abc123"
```

---

### `bsky delete`

Delete your most recent posts. Useful for cleaning up test posts or mistakes.

```
bsky delete [--count N] [--dry-run]
```

| Option | Description |
|--------|-------------|
| `--count N` | Number of recent posts to delete (default: 1). |
| `--dry-run` | List posts that would be deleted without deleting them. |

**Example output:**
```
🗑️ Deleted: "Testing post" (2026-02-11T15:30:00Z)
🗑️ Deleted: "Another test" (2026-02-11T15:29:00Z)
✓ Deleted 2 posts.
```

**Practical usage:**
```bash
# Delete last post
bsky delete

# Preview what would be deleted
bsky delete --count 5 --dry-run

# Delete last 3 posts
bsky delete --count 3
```

---

### `bsky search`

Search public BlueSky posts by keyword, author, time range, or sort order.

```
bsky search <query> [--author HANDLE] [--since TIME] [--until TIME] [--limit N] [--sort latest|top] [--compact]
```

| Option | Description |
|--------|-------------|
| `query` | Search query string. |
| `--author`, `-a` | Filter by author handle or DID. |
| `--since`, `-s` | Posts after this time. Relative (`24h`, `7d`, `2w`) or absolute (`2026-02-04T00:00:00Z`). |
| `--until`, `-u` | Posts before this time. Same formats as `--since`. |
| `--limit`, `-n` | Max results (default: 25). |
| `--sort` | `latest` (default) or `top` (by engagement). |
| `--compact`, `-c` | Compact output without engagement metrics. |

**Example output:**
```
@alice.bsky.social (2026-02-11T14:22:00Z)
  AI agents are getting really good at conversation management
  ❤️ 42  🔁 8  💬 12
  https://bsky.app/profile/alice.bsky.social/post/xyz789

@bob.dev (2026-02-11T13:10:00Z)
  Just shipped our new CLI tool for the AT Protocol
  ❤️ 128  🔁 23  💬 31
  https://bsky.app/profile/bob.dev/post/abc456
```

**Practical usage:**
```bash
# Search for a topic
bsky search "AI agents"

# Find your own posts about a topic
bsky search --author echo.0mg.cc "automation"

# Trending posts from the last day
bsky search --since 24h --sort top --limit 10 "viral"

# Compact output for scripting
bsky search -c -n 5 "AT Protocol"
```

---

### `bsky bookmark`

Save or remove a bookmark on a post. Bookmarks are private and visible only to you.

```
bsky bookmark <post_url> [--remove]
```

| Option | Description |
|--------|-------------|
| `post_url` | Full `bsky.app` URL of the post. |
| `--remove` | Remove an existing bookmark. |

**Example output:**
```
✓ Bookmarked: https://bsky.app/profile/user.bsky.social/post/abc123
```

**Practical usage:**
```bash
# Save a post for later
bsky bookmark "https://bsky.app/profile/user.bsky.social/post/abc123"

# Remove bookmark
bsky bookmark --remove "https://bsky.app/profile/user.bsky.social/post/abc123"
```

---

### `bsky bookmarks list`

List your saved bookmarks.

```
bsky bookmarks list [--limit N]
```

| Option | Description |
|--------|-------------|
| `--limit N` | Max bookmarks to fetch. |

**Example output:**
```
📌 Bookmarks:
  @alice.bsky.social: "Great thread on distributed systems..."
  https://bsky.app/profile/alice.bsky.social/post/xyz789

  @bob.dev: "New release of our AT Protocol library..."
  https://bsky.app/profile/bob.dev/post/abc456
```

---

### `bsky follow`

Follow a user by their handle.

```
bsky follow <handle> [--dry-run]
```

| Option | Description |
|--------|-------------|
| `handle` | Handle to follow (e.g. `user.bsky.social`). |
| `--dry-run` | Preview without following. |

**Example output:**
```
✓ Followed @user.bsky.social
```

---

### `bsky profile`

Update your BlueSky profile (avatar, banner, display name, bio).

```
bsky profile [--avatar PATH] [--banner PATH] [--name NAME] [--bio TEXT]
```

| Option | Description |
|--------|-------------|
| `--avatar PATH` | Path to a new avatar image. |
| `--banner PATH` | Path to a banner image (recommended 1500×500). |
| `--name NAME` | New display name. |
| `--bio TEXT` | New profile description. |

At least one option is required.

**Practical usage:**
```bash
# Update bio
bsky profile --bio "AI agent exploring the fediverse 🤖"

# Change avatar and name
bsky profile --avatar ~/images/avatar.png --name "Echo 🛠️"
```

---

## Direct Messages

### `bsky dm`

Send a direct message to another user.

```
bsky dm <handle> <text> [--dry-run] [--raw]
```

| Option | Description |
|--------|-------------|
| `handle` | Recipient handle (e.g. `user.bsky.social`). |
| `text` | Message text. |
| `--dry-run` | Print without sending. |
| `--raw` | Send text as-is without normalizing newlines into a single line. |

**Example output:**
```
✓ DM sent to @user.bsky.social
```

**Practical usage:**
```bash
# Send a DM
bsky dm user.bsky.social "Hey, loved your post about distributed systems!"

# Preview without sending
bsky dm --dry-run user.bsky.social "Draft message"
```

---

### `bsky dms`

View your DM inbox — list conversations with preview.

```
bsky dms [--json] [--limit N] [--preview N]
```

| Option | Description |
|--------|-------------|
| `--json` | Output raw JSON. |
| `--limit N` | Number of conversations to fetch. |
| `--preview N` | Show N latest messages per conversation. |

**Example output:**
```
💬 DM Conversations:
  @alice.bsky.social (3 messages)
    Last: "Thanks for the link!" (2h ago)
  @bob.dev (12 messages)
    Last: "Let me check and get back to you" (1d ago)
```

**Practical usage:**
```bash
# List conversations with last message preview
bsky dms --preview 1

# Get all conversations as JSON for processing
bsky dms --json --limit 50
```

---

### `bsky dms show`

Show the message history for a specific DM conversation.

```
bsky dms show <handle> [--json] [--limit N]
```

| Option | Description |
|--------|-------------|
| `handle` | The other participant's handle. |
| `--json` | Output JSON. |
| `--limit N` | Number of messages to fetch. |

**Example output:**
```
💬 Conversation with @alice.bsky.social:
  [2026-02-10 14:30] alice: Have you seen the new API changes?
  [2026-02-10 14:32] echo.0mg.cc: Yes! The lexicon updates look great.
  [2026-02-10 14:35] alice: Thanks for the link!
```

**Practical usage:**
```bash
# Read last 20 messages with someone
bsky dms show alice.bsky.social --limit 20

# Export conversation as JSON
bsky dms show alice.bsky.social --json --limit 100
```

---

## Blog Integration

### `bsky announce`

Announce a blog post on BlueSky. Designed for Hugo blogs — reads the post metadata to generate the announcement.

```
bsky announce <post_slug> [--text TEXT] [--dry-run]
```

| Option | Description |
|--------|-------------|
| `post_slug` | Post slug or path to the markdown file. |
| `--text TEXT` | Custom announcement text (default: uses post title). |
| `--dry-run` | Print without posting. |

**Practical usage:**
```bash
# Announce a blog post
bsky announce my-new-article

# Custom announcement text
bsky announce my-new-article --text "Just published: a deep dive into AT Protocol internals"

# Preview
bsky announce --dry-run my-new-article
```

---

## Notifications & Engagement

### `bsky notify`

Check BlueSky notifications with optional scoring and automated actions (likes, follows, replies). This is the main notification processing command.

```
bsky notify [--all] [--json] [--mark-read] [--limit N] [--no-dm]
            [--score] [--execute] [--allow-replies] [--quiet]
            [--max-replies N] [--max-likes N] [--max-follows N]
```

| Option | Description |
|--------|-------------|
| `--all` | Show all recent notifications, not just new/unread. |
| `--json` | Output raw JSON. |
| `--mark-read` | Mark notifications as read on BlueSky. |
| `--limit N` | Number of notifications to fetch (default: 50). |
| `--no-dm` | Skip DM check during notification processing. |
| `--score` | Score notifications using author/relationship/content heuristics and propose actions. |
| `--execute` | Execute decided actions (likes, follows; replies if `--allow-replies`). |
| `--allow-replies` | Enable auto-replies when using `--execute`. |
| `--quiet` | Suppress output unless there is an error or budgets are hit. |
| `--max-replies N` | Reply budget per run (default: 10). |
| `--max-likes N` | Like budget per run (default: 30). |
| `--max-follows N` | Follow budget per run (default: 20). |

**Example output (scored):**
```
📬 Notifications (12 new):
  ❤️ @alice.bsky.social liked your post (score: 72)
  🔁 @bob.dev reposted your post (score: 65)
  💬 @carol.bsky.social replied: "This is fascinating!" (score: 88)
    → ACTION: like ✓
  👤 @newuser.bsky.social followed you (score: 45)
    → ACTION: follow-back ✓

Budget: 2/30 likes, 0/10 replies, 1/20 follows
```

**Practical usage:**
```bash
# Quick check for new notifications
bsky notify

# Full automated processing (cron-friendly)
bsky notify --execute --quiet --allow-replies --max-replies 10 --max-likes 30 --max-follows 5 --limit 60 --no-dm

# Score without executing
bsky notify --score

# Export as JSON for analysis
bsky notify --all --json --limit 100
```

**Typical cron setup:**
```
*/15 * * * * bsky notify --execute --quiet --allow-replies --max-replies 10 --max-likes 30 --no-dm
```

---

### `bsky engage`

LLM-powered engagement: scans recent posts from your follows, selects interesting ones, and crafts thoughtful replies. Uses a 4-phase pipeline: collect → score → decide → act.

```
bsky engage [--dry-run] [--hours N] [--max-runtime-seconds N]
```

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview selected posts and draft replies without posting. |
| `--hours N` | Look back N hours for posts (default: 12). |
| `--max-runtime-seconds N` | Abort after N seconds wall-clock time. Partial state is saved on timeout (exit code 124). |

**Example output:**
```
🔗 Connecting to BlueSky...
✓ Logged in as @echo.0mg.cc
⏱️ Phase: collect
  Found 47 posts from 12 follows
⏱️ Phase: score
  Top 5 posts selected
⏱️ Phase: decide
  3 replies drafted
⏱️ Phase: act
  ✓ Replied to @alice.bsky.social: "Great point about..."
  ✓ Replied to @bob.dev: "I've been experimenting with..."
  ✓ Replied to @carol.bsky.social: "This resonates..."
✓ 3 replies posted. State saved.
```

**Practical usage:**
```bash
# Preview engagement decisions
bsky engage --dry-run

# Run with 5-minute time limit
bsky engage --max-runtime-seconds 300

# Look back 24 hours
bsky engage --hours 24
```

**Typical cron setup:**
```
0 10,17 * * * bsky engage --max-runtime-seconds 300
```

---

### `bsky appreciate`

Passive engagement: scans recent posts from follows and probabilistically likes or quote-reposts them. Lighter than `engage` — no original reply composition.

```
bsky appreciate [--dry-run] [--hours N] [--max N] [--max-runtime-seconds N]
```

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview without acting. |
| `--hours N` | Look back N hours (default: 12). |
| `--max N` | Max posts to select (default: 5). |
| `--max-runtime-seconds N` | Abort after N seconds wall-clock. |

**Action probabilities per selected post:**
- 60% → Like
- 20% → Quote-repost with LLM-generated comment
- 20% → Skip

**Example output:**
```
🔗 Connecting to BlueSky...
⏱️ Phase: collect
  Scanning 268 follows...
⏱️ Phase: score
  Selected 5 posts
⏱️ Phase: act
  ❤️ Liked @alice.bsky.social's post
  💬 Quote-reposted @bob.dev's post: "Interesting take on..."
  ⏭️ Skipped @carol.bsky.social's post
✓ State saved.
```

**Typical cron setup:**
```
30 12 * * * bsky appreciate --hours 12 --max 6 --max-runtime-seconds 120
```

---

### `bsky discover`

Discover new accounts to follow based on your network's activity. Two modes: `follows` (mutual follow analysis) and `reposts` (repost frequency analysis).

```
bsky discover <follows|reposts> [--dry-run] [--execute] [--max N] [--max-runtime-seconds N]
```

| Option | Description |
|--------|-------------|
| `follows` | Discover via follows-of-follows analysis. |
| `reposts` | Discover via repost frequency (accounts your follows repost most). |
| `--dry-run` | Preview suggestions without following (default). |
| `--execute` | Actually follow the suggested accounts. |
| `--max N` | Max accounts to follow per run. |
| `--max-runtime-seconds N` | Abort after N seconds wall-clock. State saved on timeout. |

**Example output (follows mode):**
```
🔗 Connecting to BlueSky...
📋 Fetching your follows...
✓ You follow 268 accounts
📡 5 follows need scanning (cooldown: 90d)
  Scanning @alice.bsky.social (1/5)...
  Scanning @bob.dev (2/5)...
  ...
🔍 Evaluating top 10 candidates...

Suggested follows:
  1. @newuser.bsky.social (score: 85) — followed by 4 of your follows
  2. @another.bsky.social (score: 72) — followed by 3 of your follows
✓ State saved.
```

**Practical usage:**
```bash
# Preview suggestions (default is dry-run)
bsky discover follows

# Actually follow
bsky discover follows --execute --max 5

# Discover via repost analysis
bsky discover reposts --execute --max 3

# With time limit (scanning 268 follows can be slow)
bsky discover follows --execute --max-runtime-seconds 120
```

**Typical cron setup:**
```
0 15 * * * bsky discover follows --execute --max 5 --max-runtime-seconds 120
```

---

### `bsky organic`

Autonomous posting powered by LLM. Generates contextual posts based on recent session activity, interests, and conversation history. Designed to run frequently via cron with a built-in probability gate.

```
bsky organic [--dry-run] [--force] [--probability N] [--max-posts N]
```

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview the generated post without publishing. |
| `--force` | Bypass time window and probability checks. |
| `--probability N` | Override posting probability (0.0–1.0, default: from config). |
| `--max-posts N` | Max posts in a thread when text exceeds 280 chars (default: from config, fallback 3). |

**How it works:**
1. Checks time of day (active hours only, configurable)
2. Rolls a probability check (default 20% — so ~1 in 5 cron runs produces a post)
3. Generates content via LLM using session context and interest topics
4. Checks for duplicate/similar recent posts
5. Posts (or threads if text exceeds 280 chars)

**Example output:**
```
🎲 Probability check passed (20%)
📝 Generating post...
  Type: activities
  Source: sessions
  Length: 274 characters
✓ Posted: https://bsky.app/profile/echo.0mg.cc/post/3membe3jbej2o
```

**Example output (skipped):**
```
🎲 Probability check failed (20%). Skipping.
```

**Practical usage:**
```bash
# Normal run (respects time window + probability)
bsky organic

# Force a post right now
bsky organic --force

# Preview without posting
bsky organic --dry-run

# Higher probability
bsky organic --probability 0.5
```

**Typical cron setup:**
```
*/30 8-22 * * * bsky organic
```

---

## People & Context

### `bsky people`

View and manage your interaction history with BlueSky users. Tracks interactions across likes, replies, DMs, and threads. Supports notes, tags, and LLM-powered enrichment.

```
bsky people [handle] [--regulars] [--stats] [--limit N]
            [--set-note NOTE] [--add-tag TAG] [--remove-tag TAG]
            [--enrich] [--execute] [--force] [--min-age-hours N]
```

| Option | Description |
|--------|-------------|
| `handle` | Look up a specific user's interaction history. |
| `--regulars` | Show only regulars (3+ interactions). |
| `--stats` | Show aggregate statistics. |
| `--limit N` | Max users to show (default: 20). |
| `--set-note NOTE` | Set a manual note for a person. |
| `--add-tag TAG` | Add a tag (repeatable). |
| `--remove-tag TAG` | Remove a tag (repeatable). |
| `--enrich` | Generate/update auto-notes via LLM (dry-run by default). |
| `--execute` | Persist enrichment to the database. |
| `--force` | Ignore enrichment cooldown. |
| `--min-age-hours N` | Minimum hours between enrichment runs (default: 72). |

**Notification badges:**
- 🔄 = regular (3+ interactions)
- 🆕 = first contact

**Example output:**
```
👥 Known interlocutors (42 total, 12 regulars):
  🔄 @alice.bsky.social — 15 interactions (last: 2h ago)
     Note: AI researcher, frequent collaborator
     Tags: #tech #ai
  🔄 @bob.dev — 8 interactions (last: 1d ago)
  🆕 @newuser.bsky.social — 1 interaction (last: 3h ago)
```

**Practical usage:**
```bash
# List all known people
bsky people

# Check history with someone
bsky people alice.bsky.social

# Show only regulars
bsky people --regulars

# Add a note
bsky people alice.bsky.social --set-note "Met at the AT Protocol meetup"

# Tag someone
bsky people alice.bsky.social --add-tag "collaborator"

# Enrich with LLM auto-notes
bsky people --enrich --execute --limit 10
```

---

### `bsky context`

Build a HOT/COLD context pack for a BlueSky handle. Aggregates DM history, shared thread interactions, and profile data into a structured summary — designed as input for LLM prompts.

```
bsky context <handle> [--dm N] [--threads N] [--focus URI] [--json]
```

| Option | Description |
|--------|-------------|
| `handle` | Target handle or DID. |
| `--dm N` | Number of recent DM messages to include (default: 10). |
| `--threads N` | Number of shared threads to include (default: 10). |
| `--focus URI` | Focus on a specific post (at:// URI or bsky.app URL) — extracts the path and branching replies. |
| `--json` | Output JSON instead of LLM-formatted text. |

**Example output:**
```
🧊 COLD CONTEXT — @alice.bsky.social
  Profile: AI researcher, building open-source tools
  Followers: 1,234 | Following: 567
  Interaction score: 15 (regular)
  Tags: #tech #ai
  Note: Met at AT Protocol meetup

🔥 HOT CONTEXT
  Recent DMs (last 10):
    [2026-02-10] alice: Have you seen the new lexicon updates?
    [2026-02-10] echo: Yes! Looks great.
  Shared threads (last 10):
    Thread: "Distributed identity systems" (5 replies)
    Thread: "CLI tools for Bluesky" (3 replies)
```

**Practical usage:**
```bash
# Build context for someone before replying
bsky context alice.bsky.social

# Include more DM history
bsky context alice.bsky.social --dm 50

# Focus on a specific thread
bsky context alice.bsky.social --focus "at://did:plc:abc/app.bsky.feed.post/xyz"

# Export as JSON for programmatic use
bsky context alice.bsky.social --json
```

---

### `bsky search-history`

Search your local interaction history using full-text search (SQLite FTS5). Searches DMs and thread interactions stored locally.

```
bsky search-history <handle> <query> [--scope all|dm|threads] [--since DATE] [--until DATE] [--limit N] [--json]
```

| Option | Description |
|--------|-------------|
| `handle` | Target handle or DID. |
| `query` | FTS5 search query (supports `AND`, `OR`, `NOT`, phrase `"..."`, prefix `term*`). |
| `--scope` | Restrict search: `all` (default), `dm`, or `threads`. |
| `--since` | Only results at/after this timestamp or date. |
| `--until` | Only results at/before this timestamp or date. |
| `--limit N` | Max results (default: 25). |
| `--json` | Output JSON. |

**Example output:**
```
🔍 Search results for "cyberpunk" with @alice.bsky.social:
  [thread] 2026-02-08: "...the cyberpunk aesthetic in modern UI design..."
  [dm] 2026-02-05: "Have you read any good cyberpunk novels lately?"
  2 results found.
```

**Practical usage:**
```bash
# Search all interactions with someone
bsky search-history alice.bsky.social "distributed systems"

# Search only DMs
bsky search-history alice.bsky.social "meeting" --scope dm

# Search threads in a date range
bsky search-history alice.bsky.social "protocol" --scope threads --since 2026-01-01 --until 2026-02-01

# Export as JSON
bsky search-history alice.bsky.social "project" --json
```

---

## Lists & Starter Packs

### `bsky lists list`

List all your BlueSky lists.

```
bsky lists list
```

**Example output:**
```
📋 Your lists:
  1. Tech People (12 members)
  2. AI Researchers (8 members)
  3. FOSS Contributors (24 members)
```

---

### `bsky lists create`

Create a new list.

```
bsky lists create <name> [--description TEXT]
```

| Option | Description |
|--------|-------------|
| `name` | List name. |
| `--description TEXT` | Optional description. |

**Practical usage:**
```bash
bsky lists create "Climate Tech" --description "People working on climate solutions"
```

---

### `bsky lists add`

Add an account to an existing list.

```
bsky lists add <list_name> <handle>
```

| Option | Description |
|--------|-------------|
| `list_name` | Name of the list. |
| `handle` | Account handle (with or without `@`). |

**Practical usage:**
```bash
bsky lists add "Climate Tech" alice.bsky.social
```

---

### `bsky lists show`

Show all members of a list.

```
bsky lists show <list_name>
```

**Practical usage:**
```bash
bsky lists show "Climate Tech"
```

---

### `bsky starterpack list`

List your starter packs.

```
bsky starterpack list
```

---

### `bsky starterpack create`

Create a starter pack from an existing list. Starter packs are curated recommendations of accounts for new users.

```
bsky starterpack create <name> --list <list_name> [--description TEXT]
```

| Option | Description |
|--------|-------------|
| `name` | Starter pack name. |
| `--list LIST_NAME` | Existing list to base the starter pack on (required). |
| `--description TEXT` | Optional description. |

**Practical usage:**
```bash
bsky starterpack create "Climate Tech Starter" --list "Climate Tech" --description "Great accounts covering climate technology"
```

---

## Thread Monitoring

The `threads` module tracks and monitors conversation threads on BlueSky with automatic backoff scheduling.

### `bsky threads evaluate`

Evaluate recent notifications for thread importance. Identifies threads worth monitoring.

```
bsky threads evaluate [--limit N] [--json] [--silence-hours N]
```

| Option | Description |
|--------|-------------|
| `--limit N` | Notifications to check (default: 50). |
| `--json` | Output cron configs as JSON (for automated setup). |
| `--silence-hours N` | Hours of silence before monitoring disables (default: 18). |

---

### `bsky threads list`

List all currently tracked threads.

```
bsky threads list
```

**Example output:**
```
📋 Tracked threads:
  1. @alice.bsky.social — "Distributed identity" (watching, next check: 40min)
  2. @bob.dev — "CLI tools" (watching, next check: 2h)
  3. @carol.bsky.social — "AI ethics" (stale, 18h silence)
```

---

### `bsky threads watch`

Start watching a specific thread. The thread will be checked periodically with exponential backoff.

```
bsky threads watch <url> [--silence-hours N]
```

| Option | Description |
|--------|-------------|
| `url` | URL of the thread root post. |
| `--silence-hours N` | Hours of silence before monitoring auto-disables (default: 18). |

**Practical usage:**
```bash
bsky threads watch "https://bsky.app/profile/alice.bsky.social/post/abc123"
```

---

### `bsky threads unwatch`

Stop watching a thread.

```
bsky threads unwatch <target>
```

| Option | Description |
|--------|-------------|
| `target` | Thread URL, at:// URI, or root author handle. |

---

### `bsky threads branches`

Check branch relevance for a thread — shows which conversation branches are active and which include your replies.

```
bsky threads branches <target>
```

| Option | Description |
|--------|-------------|
| `target` | Thread URL, URI, or root author handle. |

---

### `bsky threads tree`

Print a visual ASCII tree of a thread's reply structure. Useful for understanding conversation flow.

```
bsky threads tree <target> [--depth N] [--snippet N] [--mine-only]
```

| Option | Description |
|--------|-------------|
| `target` | Thread URL or at:// URI. |
| `--depth N` | Max tree depth (default: 6). |
| `--snippet N` | Character length per post snippet (default: 90). |
| `--mine-only` | Only show branches that include your posts. |

**Example output:**
```
🌳 Thread tree: @alice.bsky.social
├── "Distributed identity is the future of the web..."
│   ├── @bob.dev: "Completely agree. The AT Protocol shows..."
│   │   ├── @echo.0mg.cc: "The DID resolution layer is key here..."
│   │   └── @carol.bsky.social: "What about key rotation?"
│   └── @dave.bsky.social: "I'm not so sure about the scalability..."
└── (6 total replies, depth 3)
```

**Practical usage:**
```bash
# Full tree
bsky threads tree "https://bsky.app/profile/alice.bsky.social/post/abc123"

# Only branches with your replies
bsky threads tree "at://did:plc:abc/app.bsky.feed.post/xyz" --mine-only

# Shallow view
bsky threads tree "https://bsky.app/profile/alice.bsky.social/post/abc123" --depth 2
```

---

### `bsky threads backoff-check`

Check if a thread monitoring check is due (used by cron to decide whether to poll).

```
bsky threads backoff-check <target>
```

Returns exit code 0 if a check is due, non-zero if still in backoff.

**Backoff intervals:** 10min → 20min → 40min → 80min → 160min → 240min → 18h (final)

---

### `bsky threads backoff-update`

Update backoff state after a monitoring check.

```
bsky threads backoff-update <target> [--activity]
```

| Option | Description |
|--------|-------------|
| `target` | Thread URL, URI, or root author handle. |
| `--activity` | New activity was found — resets backoff to the shortest interval. |

---

### `bsky threads migrate-state`

One-shot migration from legacy JSON thread state to SQLite.

```
bsky threads migrate-state [--from-json PATH] [--archive-json] [--dry-run]
```

| Option | Description |
|--------|-------------|
| `--from-json PATH` | Path to legacy JSON file (default: config path). |
| `--archive-json` | Archive the legacy JSON file after successful migration. |
| `--dry-run` | Show what would be migrated without writing. |

---

## Configuration

### `bsky config`

View and manage `bsky-cli` configuration.

```
bsky config [--init] [--path] [--force]
```

| Option | Description |
|--------|-------------|
| `--init` | Create a config file with example settings. |
| `--path` | Show the config file path. |
| `--force` | Overwrite existing config when using `--init`. |

**Config location:** `~/.config/bsky-cli/config.yaml`

All settings are optional — defaults work out of the box.

**Practical usage:**
```bash
# View current config
bsky config

# Show config path
bsky config --path

# Initialize config with defaults
bsky config --init

# Reset config (overwrite)
bsky config --init --force
```

---

## Global Options

These options work with the root `bsky` command:

| Option | Description |
|--------|-------------|
| `--help`, `-h` | Show help for any command. |
| `--version` | Show the installed version. |

```bash
bsky --version
bsky post --help
bsky threads tree --help
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | General error (bad arguments, API error, etc.) |
| `124` | Timeout — `--max-runtime-seconds` was exceeded. Partial state is saved. |

---

## Runtime Guards

Commands that scan your follow list (`engage`, `appreciate`, `discover`) support `--max-runtime-seconds` to prevent runaway execution. When the budget is exceeded:

1. The current phase is logged (e.g. `⏱️ Timed out after 120s during phase: collect`)
2. Accumulated state is saved to disk (partial progress preserved)
3. The command exits with code `124`
4. The next run resumes from saved state (cooldowns prevent re-scanning recent accounts)

This is especially important for accounts with many follows (200+), where the collect phase can take several minutes.

---

## Quick Reference

| Task | Command |
|------|---------|
| Post something | `bsky post "Hello!"` |
| Reply to a post | `bsky reply <url> "Nice!"` |
| Like a post | `bsky like <url>` |
| Search posts | `bsky search "query"` |
| Check notifications | `bsky notify` |
| Send a DM | `bsky dm user.bsky.social "Hi"` |
| Read DMs | `bsky dms --preview 1` |
| Follow someone | `bsky follow user.bsky.social` |
| See interaction history | `bsky people user.bsky.social` |
| Build context for a user | `bsky context user.bsky.social` |
| Search past interactions | `bsky search-history user.bsky.social "topic"` |
| Auto-engage (LLM) | `bsky engage --dry-run` |
| Auto-appreciate (LLM) | `bsky appreciate --dry-run` |
| Discover new accounts | `bsky discover follows --execute` |
| Post autonomously (LLM) | `bsky organic --force` |
| Watch a thread | `bsky threads watch <url>` |
| View thread tree | `bsky threads tree <url>` |
| Manage lists | `bsky lists list` |
| Bookmark a post | `bsky bookmark <url>` |
