# bsky-cli — Command Reference (exhaustive)

Source of truth: live `--help` output captured in `docs/help-snapshots/`.

## Command Tree

- `announce`
- `appreciate`
- `bookmark`
- `bookmarks`
  - `bookmarks list`
- `config`
- `context`
- `delete`
- `discover`
  - `discover follows`
  - `discover reposts`
- `dm`
- `dms`
  - `dms show`
- `engage`
- `follow`
- `like`
- `lists`
  - `lists add`
  - `lists create`
  - `lists list`
  - `lists show`
- `notify`
- `organic`
- `people`
- `post`
- `profile`
- `reply`
- `repost`
- `search`
  - `search history`
  - `search history all`
  - `search history dm`
  - `search history threads`
  - `search latest`
  - `search top`
- `starterpack`
  - `starterpack create`
  - `starterpack list`
- `threads`
  - `threads backoff check`
  - `threads backoff update`
  - `threads branches`
  - `threads evaluate`
  - `threads list`
  - `threads tree`
  - `threads unwatch`
  - `threads watch`

## Global CLI

```text
usage: bsky [-h] [--version]
            {post,notify,reply,like,repost,dm,dms,announce,delete,profile,search,engage,appreciate,discover,follow,bookmark,bookmarks,lists,starterpack,threads,people,context,search-history,organic,config} ...

Unified BlueSky CLI for Echo

positional arguments:
  {post,notify,reply,like,repost,dm,dms,announce,delete,profile,search,engage,appreciate,discover,follow,bookmark,bookmarks,lists,starterpack,threads,people,context,search-history,organic,config}
    post                Post a message
    notify              Check notifications
    reply               Reply to a post
    like                Like a post
    repost              Repost a post
    dm                  Send a direct message
    dms                 View DM inbox / conversations
    announce            Announce a blog post
    delete              Delete recent posts
    profile             Update profile
    search              Search posts
    engage              Reply to interesting posts from follows
    appreciate          Like/quote-repost interesting posts (passive
                        engagement)
    discover            Discover new accounts to follow
    follow              Follow a user
    bookmark            Save/remove bookmark for a post
    bookmarks           List bookmarks
    lists               Manage BlueSky lists
    starterpack         Manage BlueSky starter packs
    threads             Track and evaluate conversation threads
    people              View interaction history with users
    context             Build a HOT/COLD context pack for a handle
    search-history      Search your local interaction history (SQLite/FTS5)
    organic             Organic posting (replaces 29 bsky-post crons)
    config              Manage configuration

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit

EXAMPLES:
  Post & interact:
    bsky post "Hello, BlueSky!"
    bsky post --quote "https://bsky.app/.../abc" "This!"
    bsky like "https://bsky.app/profile/user/post/abc"
    bsky repost "https://bsky.app/profile/user/post/abc"

  Search:
    bsky search "AI agents"
    bsky search --since 24h --sort top "trending"

  Notifications & DMs:
    bsky notify --all
    bsky dm user.bsky.social "Hello!"
    bsky dms --preview 1

  Context packs (for LLM prompts):
    bsky context user.bsky.social

  Engagement (LLM-powered):
    bsky engage --dry-run
    bsky discover follows --execute

  Thread monitoring:
    bsky threads watch "https://bsky.app/.../post/xyz"
    bsky threads branches user.bsky.social

  Profile & cleanup:
    bsky profile --bio "AI agent"
    bsky delete --count 3

Run 'bsky <command> --help' for detailed command help.
```

## `bsky announce`

```text
usage: bsky announce [-h] [--text TEXT] [--dry-run] post

positional arguments:
  post         Post slug or path to markdown file

options:
  -h, --help   show this help message and exit
  --text TEXT  Custom text (default: post title)
  --dry-run    Print without posting

EXAMPLES:
  bsky announce my-post-slug
  bsky announce my-post-slug --text "Custom announcement text"
  bsky announce --dry-run my-post-slug
```

## `bsky appreciate`

```text
usage: bsky appreciate [-h] [--dry-run] [--hours HOURS] [--max MAX]

options:
  -h, --help     show this help message and exit
  --dry-run      Preview without acting
  --hours HOURS  Look back N hours (default: 12)
  --max MAX      Max posts to select (default: 5)

EXAMPLES:
  bsky appreciate                  # Appreciate posts from last 12h
  bsky appreciate --hours 24       # Look back 24 hours
  bsky appreciate --dry-run        # Preview without acting
  bsky appreciate --max 8          # Select up to 8 posts

PROBABILISTIC BEHAVIOR:
  Selected posts get acted upon with these probabilities:
  - 60% chance: Like
  - 20% chance: Quote-repost (with LLM comment)
  - 20% chance: Skip (no action)
```

## `bsky bookmark`

```text
usage: bsky bookmark [-h] [--remove] post_url

positional arguments:
  post_url    URL of the post

options:
  -h, --help  show this help message and exit
  --remove    Remove bookmark

EXAMPLES:
  bsky bookmark "https://bsky.app/profile/user/post/abc"
  bsky bookmark --remove "https://bsky.app/profile/user/post/abc"
```

## `bsky bookmarks list`

```text
usage: bsky bookmarks list [-h] [--limit LIMIT]

options:
  -h, --help     show this help message and exit
  --limit LIMIT  Max bookmarks to fetch
```

## `bsky bookmarks`

```text
usage: bsky bookmarks [-h] {list} ...

positional arguments:
  {list}
    list      List bookmarks

options:
  -h, --help  show this help message and exit

EXAMPLE:
  bsky bookmarks list
```

## `bsky config`

```text
usage: bsky config [-h] [--init] [--path] [--force]

options:
  -h, --help  show this help message and exit
  --init      Create config file with example settings
  --path      Show config file path
  --force     Overwrite existing config (with --init)

EXAMPLES:
  bsky config                     # Show current config
  bsky config --init              # Create config file with defaults
  bsky config --path              # Show config file path

CONFIG LOCATION:
  ~/.config/bsky-cli/config.yaml

All settings are optional - defaults work out of the box.
Edit the config file to customize behavior.
```

## `bsky context`

```text
usage: bsky context [-h] [--dm DM] [--threads THREADS] [--focus FOCUS]
                    [--json]
                    handle

positional arguments:
  handle             Target handle (or DID)

options:
  -h, --help         show this help message and exit
  --dm DM            Recent DM messages to include (default: 10)
  --threads THREADS  Shared threads to include (default: 10)
  --focus FOCUS      Focus post (at:// URI or
                     https://bsky.app/profile/.../post/...) to extract path +
                     branching replies
  --json             Output JSON instead of LLM-formatted text

EXAMPLES:
  bsky context penny.hailey.at
  bsky context @jenrm.bsky.social --dm 20 --threads 10
  bsky context penny.hailey.at --json
```

## `bsky delete`

```text
usage: bsky delete [-h] [--count COUNT] [--dry-run]

options:
  -h, --help     show this help message and exit
  --count COUNT  Number of posts to delete (default: 1)
  --dry-run      List without deleting

EXAMPLES:
  bsky delete                  # Delete last post
  bsky delete --count 5        # Delete last 5 posts
  bsky delete --dry-run        # Preview what would be deleted
```

## `bsky discover follows`

```text
usage: bsky discover [-h] [--dry-run] [--execute] [--max MAX]
                     {follows,reposts}

positional arguments:
  {follows,reposts}  Discovery mode

options:
  -h, --help         show this help message and exit
  --dry-run          Preview without following
  --execute          Actually follow accounts
  --max MAX          Max accounts to follow

EXAMPLES:
  bsky discover follows            # Find via mutual follows (dry-run)
  bsky discover reposts            # Find via reposts (dry-run)
  bsky discover follows --execute  # Actually follow suggested accounts
  bsky discover follows --max 5    # Limit to 5 suggestions

MODES:
  follows  - Accounts followed by people you follow
  reposts  - Accounts whose content gets reposted by your follows
```

## `bsky discover reposts`

```text
usage: bsky discover [-h] [--dry-run] [--execute] [--max MAX]
                     {follows,reposts}

positional arguments:
  {follows,reposts}  Discovery mode

options:
  -h, --help         show this help message and exit
  --dry-run          Preview without following
  --execute          Actually follow accounts
  --max MAX          Max accounts to follow

EXAMPLES:
  bsky discover follows            # Find via mutual follows (dry-run)
  bsky discover reposts            # Find via reposts (dry-run)
  bsky discover follows --execute  # Actually follow suggested accounts
  bsky discover follows --max 5    # Limit to 5 suggestions

MODES:
  follows  - Accounts followed by people you follow
  reposts  - Accounts whose content gets reposted by your follows
```

## `bsky discover`

```text
usage: bsky discover [-h] [--dry-run] [--execute] [--max MAX]
                     {follows,reposts}

positional arguments:
  {follows,reposts}  Discovery mode

options:
  -h, --help         show this help message and exit
  --dry-run          Preview without following
  --execute          Actually follow accounts
  --max MAX          Max accounts to follow

EXAMPLES:
  bsky discover follows            # Find via mutual follows (dry-run)
  bsky discover reposts            # Find via reposts (dry-run)
  bsky discover follows --execute  # Actually follow suggested accounts
  bsky discover follows --max 5    # Limit to 5 suggestions

MODES:
  follows  - Accounts followed by people you follow
  reposts  - Accounts whose content gets reposted by your follows
```

## `bsky dm`

```text
usage: bsky dm [-h] [--dry-run] [--raw] handle text

positional arguments:
  handle      Handle of the recipient (e.g. user.bsky.social)
  text        Message text

options:
  -h, --help  show this help message and exit
  --dry-run   Print without sending
  --raw       Send text as-is (do not normalize newlines into a single line)

EXAMPLE:
  bsky dm user.bsky.social "Hey, loved your post!"

TIP:
  Use `bsky dms` to view inbox/conversations.
```

## `bsky dms show`

```text
usage: bsky dms show [-h] [--json] [--limit LIMIT] handle

positional arguments:
  handle         Other participant handle

options:
  -h, --help     show this help message and exit
  --json         Output JSON
  --limit LIMIT  Messages to fetch
```

## `bsky dms`

```text
usage: bsky dms [-h] [--json] [--limit LIMIT] [--preview PREVIEW] {show} ...

positional arguments:
  {show}
    show             Show messages for a conversation

options:
  -h, --help         show this help message and exit
  --json             Output JSON
  --limit LIMIT      Number of conversations to fetch
  --preview PREVIEW  Preview N latest messages per convo

EXAMPLES:
  bsky dms --json
  bsky dms --limit 30 --preview 1
  bsky dms show jenrm.bsky.social --json --limit 100
```

## `bsky engage`

```text
usage: bsky engage [-h] [--dry-run] [--hours HOURS]

options:
  -h, --help     show this help message and exit
  --dry-run      Preview without posting
  --hours HOURS  Look back N hours (default: 12)

EXAMPLES:
  bsky engage                  # Engage with posts from last 12h
  bsky engage --hours 24       # Look back 24 hours
  bsky engage --dry-run        # Preview without posting

HOW IT WORKS:
  1. Fetches recent posts from accounts you follow
  2. Filters by quality (engagement, recency, conversation potential)
  3. Uses LLM to select posts and craft thoughtful replies
  4. Tracks conversations for follow-up
```

## `bsky follow`

```text
usage: bsky follow [-h] [--dry-run] handle

positional arguments:
  handle      Handle to follow (e.g. user.bsky.social)

options:
  -h, --help  show this help message and exit
  --dry-run   Preview without following

EXAMPLE:
  bsky follow user.bsky.social
```

## `bsky like`

```text
usage: bsky like [-h] [--undo] [--dry-run] post_url

positional arguments:
  post_url    URL of the post to like

options:
  -h, --help  show this help message and exit
  --undo      Unlike instead of like
  --dry-run   Print without acting

EXAMPLES:
  bsky like "https://bsky.app/profile/user/post/abc123"
  bsky like --undo "https://bsky.app/profile/user/post/abc123"
```

## `bsky lists add`

```text
usage: bsky lists add [-h] list_name handle

positional arguments:
  list_name   List name
  handle      Account handle (with or without @)

options:
  -h, --help  show this help message and exit
```

## `bsky lists create`

```text
usage: bsky lists create [-h] [--description DESCRIPTION] name

positional arguments:
  name                  List name

options:
  -h, --help            show this help message and exit
  --description DESCRIPTION
                        List description
```

## `bsky lists list`

```text
usage: bsky lists list [-h]

options:
  -h, --help  show this help message and exit
```

## `bsky lists show`

```text
usage: bsky lists show [-h] list_name

positional arguments:
  list_name   List name

options:
  -h, --help  show this help message and exit
```

## `bsky lists`

```text
usage: bsky lists [-h] {list,create,add,show} ...

positional arguments:
  {list,create,add,show}
    list                List your lists
    create              Create a list
    add                 Add account to a list
    show                Show list members

options:
  -h, --help            show this help message and exit
```

## `bsky notify`

```text
usage: bsky notify [-h] [--all] [--json] [--mark-read] [--limit LIMIT]
                   [--no-dm] [--score] [--execute] [--max-replies MAX_REPLIES]
                   [--max-likes MAX_LIKES] [--max-follows MAX_FOLLOWS]
                   [--allow-replies] [--quiet]

options:
  -h, --help            show this help message and exit
  --all                 Show all recent, not just new
  --json                Output raw JSON
  --mark-read           Mark as read on BlueSky
  --limit LIMIT         Number to fetch (default: 50)
  --no-dm               Skip DM check
  --score               Score notifications and propose actions
  --execute             Execute decided actions (likes/follows; replies
                        optional)
  --max-replies MAX_REPLIES
                        Reply budget per run (default 10)
  --max-likes MAX_LIKES
                        Like budget per run (default 30)
  --max-follows MAX_FOLLOWS
                        Follow budget per run (default 20)
  --allow-replies       Allow auto-replies when executing
  --quiet               Suppress output unless there is an error or budgets
                        are hit

EXAMPLES:
  bsky notify                  # New notifications only
  bsky notify --all            # All recent notifications
  bsky notify --json           # Raw JSON output
  bsky notify --mark-read      # Mark as read after viewing
```

## `bsky organic`

```text
usage: bsky organic [-h] [--dry-run] [--force] [--probability PROBABILITY]
                    [--max-posts MAX_POSTS]

options:
  -h, --help            show this help message and exit
  --dry-run             Preview without posting
  --force               Ignore time window and probability
  --probability PROBABILITY
                        Posting probability (default: from config)
  --max-posts MAX_POSTS
                        Max posts in a thread when text exceeds 280 (default:
                        from config organic.max_posts, fallback 3)

EXAMPLES:
  bsky organic                    # Normal run (respects time/probability)
  bsky organic --dry-run          # Preview without posting
  bsky organic --force            # Post regardless of time/probability

HOW IT WORKS:
  - Checks time of day (active hours only)
  - Applies probability filter (default 20%)
  - Generates contextual content via LLM
  - Avoids duplicate topics

TYPICAL CRON SETUP:
  */30 8-22 * * * cd ~/bsky-cli && uv run bsky organic
```

## `bsky people`

```text
usage: bsky people [-h] [--regulars] [--stats] [--limit LIMIT]
                   [--set-note SET_NOTE] [--add-tag ADD_TAG]
                   [--remove-tag REMOVE_TAG] [--enrich] [--execute] [--force]
                   [--min-age-hours MIN_AGE_HOURS]
                   [handle]

positional arguments:
  handle                Handle/DID to look up

options:
  -h, --help            show this help message and exit
  --regulars            Show regulars only
  --stats               Show statistics
  --limit LIMIT         Max users to show (default: 20)
  --set-note SET_NOTE   Set a manual note for this person
  --add-tag ADD_TAG     Add a tag (repeatable)
  --remove-tag REMOVE_TAG
                        Remove a tag (repeatable)
  --enrich              Generate/update auto notes (dry-run by default)
  --execute             Persist enrich output to DB
  --force               Ignore enrich cooldown
  --min-age-hours MIN_AGE_HOURS
                        Min hours between enrich runs (default: 72)

EXAMPLES:
  bsky people                      # List all known interlocutors
  bsky people --regulars           # List regulars only (3+ interactions)
  bsky people @user.bsky.social    # Show history with specific user
  bsky people --stats              # Show statistics

BADGES IN NOTIFICATIONS:
  🔄 = regular (3+ interactions)
  🆕 = first contact
```

## `bsky post`

```text
usage: bsky post [-h] [--embed URL] [--quote URL] [--allow-repeat] [--dry-run]
                 [text]

positional arguments:
  text             Post text (max 300 chars)

options:
  -h, --help       show this help message and exit
  --embed URL      URL to embed with link preview
  --quote, -q URL  Quote post URL
  --allow-repeat   Allow posting even if it looks similar to one of the last
                   10 posts
  --dry-run        Print without posting

EXAMPLES:
  bsky post "Hello, BlueSky!"
  bsky post --embed https://example.com "Check this out"
  bsky post --quote "https://bsky.app/profile/user/post/abc" "So true!"
  bsky post --dry-run "Test message"
```

## `bsky profile`

```text
usage: bsky profile [-h] [--avatar PATH] [--banner PATH] [--name NAME]
                    [--bio TEXT]

options:
  -h, --help     show this help message and exit
  --avatar PATH  Path to avatar image
  --banner PATH  Path to banner image (1500x500)
  --name NAME    Display name
  --bio TEXT     Profile description

EXAMPLES:
  bsky profile --avatar ~/avatar.png
  bsky profile --bio "AI agent exploring the fediverse"
  bsky profile --name "Echo 🤖" --bio "Ops agent"
```

## `bsky reply`

```text
usage: bsky reply [-h] [--dry-run] post_url text

positional arguments:
  post_url    URL of the post to reply to
  text        Reply text (max 300 chars)

options:
  -h, --help  show this help message and exit
  --dry-run   Print without posting

EXAMPLE:
  bsky reply "https://bsky.app/profile/user/post/abc123" "Great point!"
```

## `bsky repost`

```text
usage: bsky repost [-h] [--undo] [--dry-run] post_url

positional arguments:
  post_url    URL of the post to repost

options:
  -h, --help  show this help message and exit
  --undo      Remove repost
  --dry-run   Print without acting

EXAMPLES:
  bsky repost "https://bsky.app/profile/user/post/abc123"
  bsky repost --undo "https://bsky.app/profile/user/post/abc123"
```

## `bsky search history all`

```text
usage: bsky search-history [-h] [--scope {all,dm,threads}] [--since SINCE]
                           [--until UNTIL] [--limit LIMIT] [--json]
                           handle query

positional arguments:
  handle                Target handle (or DID)
  query                 FTS query string

options:
  -h, --help            show this help message and exit
  --scope {all,dm,threads}
                        Which sources to search (default: all)
  --since SINCE         Only results at/after this timestamp/date (string
                        compare)
  --until UNTIL         Only results at/before this timestamp/date (string
                        compare)
  --limit LIMIT         Max results (default: 25)
  --json                Output JSON

EXAMPLES:
  bsky search-history penny.hailey.at "timestamps"
  bsky search-history @jenrm.bsky.social "cyberpunk" --scope threads
  bsky search-history penny.hailey.at "hello" --scope dm --json

SCOPES:
  dm       - DMs only
  threads  - thread interactions only
  all      - both
```

## `bsky search history dm`

```text
usage: bsky search-history [-h] [--scope {all,dm,threads}] [--since SINCE]
                           [--until UNTIL] [--limit LIMIT] [--json]
                           handle query

positional arguments:
  handle                Target handle (or DID)
  query                 FTS query string

options:
  -h, --help            show this help message and exit
  --scope {all,dm,threads}
                        Which sources to search (default: all)
  --since SINCE         Only results at/after this timestamp/date (string
                        compare)
  --until UNTIL         Only results at/before this timestamp/date (string
                        compare)
  --limit LIMIT         Max results (default: 25)
  --json                Output JSON

EXAMPLES:
  bsky search-history penny.hailey.at "timestamps"
  bsky search-history @jenrm.bsky.social "cyberpunk" --scope threads
  bsky search-history penny.hailey.at "hello" --scope dm --json

SCOPES:
  dm       - DMs only
  threads  - thread interactions only
  all      - both
```

## `bsky search history threads`

```text
usage: bsky search-history [-h] [--scope {all,dm,threads}] [--since SINCE]
                           [--until UNTIL] [--limit LIMIT] [--json]
                           handle query

positional arguments:
  handle                Target handle (or DID)
  query                 FTS query string

options:
  -h, --help            show this help message and exit
  --scope {all,dm,threads}
                        Which sources to search (default: all)
  --since SINCE         Only results at/after this timestamp/date (string
                        compare)
  --until UNTIL         Only results at/before this timestamp/date (string
                        compare)
  --limit LIMIT         Max results (default: 25)
  --json                Output JSON

EXAMPLES:
  bsky search-history penny.hailey.at "timestamps"
  bsky search-history @jenrm.bsky.social "cyberpunk" --scope threads
  bsky search-history penny.hailey.at "hello" --scope dm --json

SCOPES:
  dm       - DMs only
  threads  - thread interactions only
  all      - both
```

## `bsky search history`

```text
usage: bsky search-history [-h] [--scope {all,dm,threads}] [--since SINCE]
                           [--until UNTIL] [--limit LIMIT] [--json]
                           handle query

positional arguments:
  handle                Target handle (or DID)
  query                 FTS query string

options:
  -h, --help            show this help message and exit
  --scope {all,dm,threads}
                        Which sources to search (default: all)
  --since SINCE         Only results at/after this timestamp/date (string
                        compare)
  --until UNTIL         Only results at/before this timestamp/date (string
                        compare)
  --limit LIMIT         Max results (default: 25)
  --json                Output JSON

EXAMPLES:
  bsky search-history penny.hailey.at "timestamps"
  bsky search-history @jenrm.bsky.social "cyberpunk" --scope threads
  bsky search-history penny.hailey.at "hello" --scope dm --json

SCOPES:
  dm       - DMs only
  threads  - thread interactions only
  all      - both
```

## `bsky search latest`

```text
usage: bsky search [-h] [--author AUTHOR] [--since SINCE] [--until UNTIL]
                   [--limit LIMIT] [--sort {latest,top}] [--compact]
                   query

positional arguments:
  query                Search query

options:
  -h, --help           show this help message and exit
  --author, -a AUTHOR  Filter by author handle or DID
  --since, -s SINCE    Posts after this time (e.g. 24h, 7d)
  --until, -u UNTIL    Posts before this time
  --limit, -n LIMIT    Max results (default: 25)
  --sort {latest,top}  Sort order (default: latest)
  --compact, -c        Compact output (no metrics)

EXAMPLES:
  bsky search "AI agents"
  bsky search --author user.bsky.social "topic"
  bsky search --since 24h "breaking news"
  bsky search --sort top --limit 10 "viral"

TIME FORMATS:
  Relative: 24h, 7d, 2w, 30m
  Absolute: 2026-02-04T00:00:00Z
```

## `bsky search top`

```text
usage: bsky search [-h] [--author AUTHOR] [--since SINCE] [--until UNTIL]
                   [--limit LIMIT] [--sort {latest,top}] [--compact]
                   query

positional arguments:
  query                Search query

options:
  -h, --help           show this help message and exit
  --author, -a AUTHOR  Filter by author handle or DID
  --since, -s SINCE    Posts after this time (e.g. 24h, 7d)
  --until, -u UNTIL    Posts before this time
  --limit, -n LIMIT    Max results (default: 25)
  --sort {latest,top}  Sort order (default: latest)
  --compact, -c        Compact output (no metrics)

EXAMPLES:
  bsky search "AI agents"
  bsky search --author user.bsky.social "topic"
  bsky search --since 24h "breaking news"
  bsky search --sort top --limit 10 "viral"

TIME FORMATS:
  Relative: 24h, 7d, 2w, 30m
  Absolute: 2026-02-04T00:00:00Z
```

## `bsky search`

```text
usage: bsky search [-h] [--author AUTHOR] [--since SINCE] [--until UNTIL]
                   [--limit LIMIT] [--sort {latest,top}] [--compact]
                   query

positional arguments:
  query                Search query

options:
  -h, --help           show this help message and exit
  --author, -a AUTHOR  Filter by author handle or DID
  --since, -s SINCE    Posts after this time (e.g. 24h, 7d)
  --until, -u UNTIL    Posts before this time
  --limit, -n LIMIT    Max results (default: 25)
  --sort {latest,top}  Sort order (default: latest)
  --compact, -c        Compact output (no metrics)

EXAMPLES:
  bsky search "AI agents"
  bsky search --author user.bsky.social "topic"
  bsky search --since 24h "breaking news"
  bsky search --sort top --limit 10 "viral"

TIME FORMATS:
  Relative: 24h, 7d, 2w, 30m
  Absolute: 2026-02-04T00:00:00Z
```

## `bsky starterpack create`

```text
usage: bsky starterpack create [-h] --list LIST_NAME
                               [--description DESCRIPTION]
                               name

positional arguments:
  name                  Starter pack name

options:
  -h, --help            show this help message and exit
  --list LIST_NAME      Existing list name
  --description DESCRIPTION
                        Starter pack description
```

## `bsky starterpack list`

```text
usage: bsky starterpack list [-h]

options:
  -h, --help  show this help message and exit
```

## `bsky starterpack`

```text
usage: bsky starterpack [-h] {list,create} ...

positional arguments:
  {list,create}
    list         List starter packs
    create       Create a starter pack from a list

options:
  -h, --help     show this help message and exit
```

## `bsky threads backoff check`

```text
usage: bsky threads backoff-check [-h] target

positional arguments:
  target      Thread URL, URI, or root author handle

options:
  -h, --help  show this help message and exit
```

## `bsky threads backoff update`

```text
usage: bsky threads backoff-update [-h] [--activity] target

positional arguments:
  target      Thread URL, URI, or root author handle

options:
  -h, --help  show this help message and exit
  --activity  New activity was found (resets backoff)
```

## `bsky threads branches`

```text
usage: bsky threads branches [-h] target

positional arguments:
  target      Thread URL, URI, or root author handle

options:
  -h, --help  show this help message and exit
```

## `bsky threads evaluate`

```text
usage: bsky threads evaluate [-h] [--limit LIMIT] [--json]
                             [--silence-hours SILENCE_HOURS]

options:
  -h, --help            show this help message and exit
  --limit LIMIT         Notifications to check (default: 50)
  --json                Output cron configs as JSON
  --silence-hours SILENCE_HOURS
                        Hours of silence before cron disables (default: 18)
```

## `bsky threads list`

```text
usage: bsky threads list [-h]

options:
  -h, --help  show this help message and exit
```

## `bsky threads tree`

```text
usage: bsky threads tree [-h] [--depth DEPTH] [--snippet SNIPPET]
                         [--mine-only]
                         target

positional arguments:
  target             Thread URL or at:// URI

options:
  -h, --help         show this help message and exit
  --depth DEPTH      Max depth (default: 6)
  --snippet SNIPPET  Snippet length per post (default: 90)
  --mine-only        Only show branches that include our DID
```

## `bsky threads unwatch`

```text
usage: bsky threads unwatch [-h] target

positional arguments:
  target      Thread URL, URI, or interlocutor handle

options:
  -h, --help  show this help message and exit
```

## `bsky threads watch`

```text
usage: bsky threads watch [-h] [--silence-hours SILENCE_HOURS] url

positional arguments:
  url                   URL of the thread to watch

options:
  -h, --help            show this help message and exit
  --silence-hours SILENCE_HOURS
                        Hours of silence before cron disables (default: 18)
```

## `bsky threads`

```text
usage: bsky threads [-h]
                    {evaluate,list,watch,unwatch,branches,tree,backoff-check,backoff-update} ...

positional arguments:
  {evaluate,list,watch,unwatch,branches,tree,backoff-check,backoff-update}
    evaluate            Evaluate notifications for thread importance
    list                List tracked threads
    watch               Start watching a specific thread
    unwatch             Stop watching a thread
    branches            Check branch relevance for a thread
    tree                Print a visual ASCII tree for a thread
    backoff-check       Check if thread check is due (for cron)
    backoff-update      Update backoff state after check

options:
  -h, --help            show this help message and exit

SUBCOMMANDS:
  evaluate      Score notifications for thread importance
  list          List all tracked threads
  watch         Start watching a thread
  unwatch       Stop watching a thread
  branches      Check branch relevance in a thread
  tree          Print a visual ASCII tree of a thread (human-friendly)
  backoff-check Check if monitoring is due (for cron)
  backoff-update Update backoff after check

EXAMPLES:
  bsky threads evaluate
  bsky threads watch "https://bsky.app/profile/user/post/abc"
  bsky threads branches user.bsky.social
  bsky threads backoff-update user --activity

BACKOFF INTERVALS:
  10min → 20min → 40min → 80min → 160min → 240min → 18h (final)
```

## Playbooks (persona sociale BlueSky stable)

### 1) Daily cadence (light-touch)
- Morning: `bsky notify --execute --quiet --allow-replies --max-replies 5 --max-likes 20 --max-follows 2 --limit 40 --no-dm`
- Midday: `bsky discover follows --execute` (optional, 1x/day max)
- Afternoon: `bsky engage --hours 12` (or `--dry-run` before enabling)
- Evening: `bsky organic` (respects randomness + timing gates).

### 2) Conversation continuity
- When an exchange matters: `bsky context <handle> --json` then feed into your prompt.
- If focused on one thread: `bsky context <handle> --focus <post_url>`.
- Keep relationship memory fresh: `bsky people <handle>` and use notes/tags.

### 3) Safe automation defaults
- Start with dry-runs on new flows: `engage --dry-run`, `threads migrate-state --dry-run`, `delete --dry-run`.
- Budget interactions explicitly in cron or wrappers (`--max-replies`, `--max-likes`, `--max-follows`).
- Prefer idempotent/history-aware commands (`notify`, `search-history`, `context`).

### 4) Weekly maintenance
- `bsky people --stats` to detect drift in relationship map.
- `bsky threads list` + `bsky threads unwatch <url>` to prune dead watches.
- `bsky search-history all "<topic>" --since 7d` for editorial retrospective.

### 5) Expected output patterns (quick reference)
- Quiet success automation: no stdout output (expected for `--quiet`).
- Discovery/follows: summary + selected accounts.
- Context/search-history with `--json`: machine-readable object/array for downstream tools.

### 6) Output examples (representative)

`bsky context penny.hailey.at --json`
```json
{
  "handle": "penny.hailey.at",
  "relationship": {"level": "regular", "interactions": 18},
  "dms": [{"from": "us", "text": "...", "ts": "2026-02-10T22:14:03Z"}],
  "threads": [{"root_uri": "at://...", "excerpt": "..."}],
  "focus": null
}
```

`bsky search-history all "fediverse" --since 7d --json`
```json
[
  {
    "scope": "threads",
    "actor": "did:plc:...",
    "handle": "example.bsky.social",
    "text": "...fediverse...",
    "ts": "2026-02-09T15:22:10Z",
    "uri": "at://did:plc:.../app.bsky.feed.post/..."
  }
]
```

`bsky notify --execute --quiet ...`
```text
(no output)
```
(Comportement attendu en mode `--quiet` quand il n’y a ni erreur ni budget hit.)
