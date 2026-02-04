#!/usr/bin/env python3
"""BlueSky CLI - Unified command-line interface for BlueSky.

Usage:
  bsky post "Hello world!"                      # Post a message
  bsky post --embed https://example.com "text"  # Post with link preview
  bsky notify                                   # Check new notifications
  bsky notify --all                             # Show all recent notifications
  bsky reply <url> "reply text"                 # Reply to a post
  bsky announce <slug>                          # Announce blog post
  bsky delete --count 5                         # Delete recent posts
  bsky profile --name "Echo" --bio "AI agent"   # Update profile
"""

import argparse
import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bsky",
        description="Unified BlueSky CLI for Echo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
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
"""
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # post
    post_parser = subparsers.add_parser(
        "post", help="Post a message",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  bsky post "Hello, BlueSky!"
  bsky post --embed https://example.com "Check this out"
  bsky post --quote "https://bsky.app/profile/user/post/abc" "So true!"
  bsky post --dry-run "Test message"
"""
    )
    post_parser.add_argument("text", nargs="?", help="Post text (max 300 chars)")
    post_parser.add_argument("--embed", metavar="URL", help="URL to embed with link preview")
    post_parser.add_argument("--quote", "-q", metavar="URL", help="Quote post URL")
    post_parser.add_argument("--dry-run", action="store_true", help="Print without posting")

    # notify
    notify_parser = subparsers.add_parser(
        "notify", help="Check notifications",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  bsky notify                  # New notifications only
  bsky notify --all            # All recent notifications
  bsky notify --json           # Raw JSON output
  bsky notify --mark-read      # Mark as read after viewing
"""
    )
    notify_parser.add_argument("--all", action="store_true", help="Show all recent, not just new")
    notify_parser.add_argument("--json", action="store_true", help="Output raw JSON")
    notify_parser.add_argument("--mark-read", action="store_true", help="Mark as read on BlueSky")
    notify_parser.add_argument("--limit", type=int, default=50, help="Number to fetch (default: 50)")
    notify_parser.add_argument("--no-dm", action="store_true", help="Skip DM check")

    # reply
    reply_parser = subparsers.add_parser(
        "reply", help="Reply to a post",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLE:
  bsky reply "https://bsky.app/profile/user/post/abc123" "Great point!"
"""
    )
    reply_parser.add_argument("post_url", help="URL of the post to reply to")
    reply_parser.add_argument("text", help="Reply text (max 300 chars)")
    reply_parser.add_argument("--dry-run", action="store_true", help="Print without posting")

    # like
    like_parser = subparsers.add_parser(
        "like", help="Like a post",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  bsky like "https://bsky.app/profile/user/post/abc123"
  bsky like --undo "https://bsky.app/profile/user/post/abc123"
"""
    )
    like_parser.add_argument("post_url", help="URL of the post to like")
    like_parser.add_argument("--undo", action="store_true", help="Unlike instead of like")
    like_parser.add_argument("--dry-run", action="store_true", help="Print without acting")

    # repost
    repost_parser = subparsers.add_parser(
        "repost", help="Repost a post",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  bsky repost "https://bsky.app/profile/user/post/abc123"
  bsky repost --undo "https://bsky.app/profile/user/post/abc123"
"""
    )
    repost_parser.add_argument("post_url", help="URL of the post to repost")
    repost_parser.add_argument("--undo", action="store_true", help="Remove repost")
    repost_parser.add_argument("--dry-run", action="store_true", help="Print without acting")

    # dm
    dm_parser = subparsers.add_parser(
        "dm", help="Send a direct message",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLE:
  bsky dm user.bsky.social "Hey, loved your post!"
"""
    )
    dm_parser.add_argument("handle", help="Handle of the recipient (e.g. user.bsky.social)")
    dm_parser.add_argument("text", help="Message text")
    dm_parser.add_argument("--dry-run", action="store_true", help="Print without sending")

    # announce
    announce_parser = subparsers.add_parser(
        "announce", help="Announce a blog post",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  bsky announce my-post-slug
  bsky announce my-post-slug --text "Custom announcement text"
  bsky announce --dry-run my-post-slug
"""
    )
    announce_parser.add_argument("post", help="Post slug or path to markdown file")
    announce_parser.add_argument("--text", help="Custom text (default: post title)")
    announce_parser.add_argument("--dry-run", action="store_true", help="Print without posting")

    # delete
    delete_parser = subparsers.add_parser(
        "delete", help="Delete recent posts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  bsky delete                  # Delete last post
  bsky delete --count 5        # Delete last 5 posts
  bsky delete --dry-run        # Preview what would be deleted
"""
    )
    delete_parser.add_argument("--count", type=int, default=1, help="Number of posts to delete (default: 1)")
    delete_parser.add_argument("--dry-run", action="store_true", help="List without deleting")

    # profile
    profile_parser = subparsers.add_parser(
        "profile", help="Update profile",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  bsky profile --avatar ~/avatar.png
  bsky profile --bio "AI agent exploring the fediverse"
  bsky profile --name "Echo 🤖" --bio "Ops agent"
"""
    )
    profile_parser.add_argument("--avatar", metavar="PATH", help="Path to avatar image")
    profile_parser.add_argument("--banner", metavar="PATH", help="Path to banner image (1500x500)")
    profile_parser.add_argument("--name", metavar="NAME", help="Display name")
    profile_parser.add_argument("--bio", metavar="TEXT", help="Profile description")

    # search
    search_parser = subparsers.add_parser(
        "search", help="Search posts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  bsky search "AI agents"
  bsky search --author user.bsky.social "topic"
  bsky search --since 24h "breaking news"
  bsky search --sort top --limit 10 "viral"

TIME FORMATS:
  Relative: 24h, 7d, 2w, 30m
  Absolute: 2026-02-04T00:00:00Z
"""
    )
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--author", "-a", help="Filter by author handle or DID")
    search_parser.add_argument("--since", "-s", help="Posts after this time (e.g. 24h, 7d)")
    search_parser.add_argument("--until", "-u", help="Posts before this time")
    search_parser.add_argument("--limit", "-n", type=int, default=25, help="Max results (default: 25)")
    search_parser.add_argument("--sort", choices=["latest", "top"], default="latest", 
                              help="Sort order (default: latest)")
    search_parser.add_argument("--compact", "-c", action="store_true", help="Compact output (no metrics)")

    # engage
    engage_parser = subparsers.add_parser(
        "engage", help="Reply to interesting posts from follows",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  bsky engage                  # Engage with posts from last 12h
  bsky engage --hours 24       # Look back 24 hours
  bsky engage --dry-run        # Preview without posting

HOW IT WORKS:
  1. Fetches recent posts from accounts you follow
  2. Filters by quality (engagement, recency, conversation potential)
  3. Uses LLM to select posts and craft thoughtful replies
  4. Tracks conversations for follow-up
"""
    )
    engage_parser.add_argument("--dry-run", action="store_true", help="Preview without posting")
    engage_parser.add_argument("--hours", type=int, default=12, help="Look back N hours (default: 12)")

    # discover
    discover_parser = subparsers.add_parser(
        "discover", help="Discover new accounts to follow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  bsky discover follows            # Find via mutual follows (dry-run)
  bsky discover reposts            # Find via reposts (dry-run)
  bsky discover follows --execute  # Actually follow suggested accounts
  bsky discover follows --max 5    # Limit to 5 suggestions

MODES:
  follows  - Accounts followed by people you follow
  reposts  - Accounts whose content gets reposted by your follows
"""
    )
    discover_parser.add_argument("mode", choices=["follows", "reposts"], help="Discovery mode")
    discover_parser.add_argument("--dry-run", action="store_true", default=True, help="Preview without following")
    discover_parser.add_argument("--execute", action="store_true", help="Actually follow accounts")
    discover_parser.add_argument("--max", type=int, default=10, help="Max accounts to follow")

    # follow
    follow_parser = subparsers.add_parser(
        "follow", help="Follow a user",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLE:
  bsky follow user.bsky.social
"""
    )
    follow_parser.add_argument("handle", help="Handle to follow (e.g. user.bsky.social)")
    follow_parser.add_argument("--dry-run", action="store_true", help="Preview without following")

    # threads
    threads_parser = subparsers.add_parser(
        "threads", help="Track and evaluate conversation threads",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
SUBCOMMANDS:
  evaluate      Score notifications for thread importance
  list          List all tracked threads
  watch         Start watching a thread
  unwatch       Stop watching a thread
  branches      Check branch relevance in a thread
  backoff-check Check if monitoring is due (for cron)
  backoff-update Update backoff after check

EXAMPLES:
  bsky threads evaluate
  bsky threads watch "https://bsky.app/profile/user/post/abc"
  bsky threads branches user.bsky.social
  bsky threads backoff-update user --activity

BACKOFF INTERVALS:
  10min → 20min → 40min → 80min → 160min → 240min → 18h (final)
"""
    )
    threads_sub = threads_parser.add_subparsers(dest="threads_command", required=True)
    
    # threads evaluate
    threads_eval = threads_sub.add_parser("evaluate", help="Evaluate notifications for thread importance")
    threads_eval.add_argument("--limit", type=int, default=50, help="Notifications to check (default: 50)")
    threads_eval.add_argument("--json", action="store_true", help="Output cron configs as JSON")
    threads_eval.add_argument("--silence-hours", type=int, default=18, help="Hours of silence before cron disables (default: 18)")
    
    # threads list
    threads_sub.add_parser("list", help="List tracked threads")
    
    # threads watch
    threads_watch = threads_sub.add_parser("watch", help="Start watching a specific thread")
    threads_watch.add_argument("url", help="URL of the thread to watch")
    threads_watch.add_argument("--silence-hours", type=int, default=18, help="Hours of silence before cron disables (default: 18)")
    
    # threads unwatch
    threads_unwatch = threads_sub.add_parser("unwatch", help="Stop watching a thread")
    threads_unwatch.add_argument("target", help="Thread URL, URI, or interlocutor handle")
    
    # threads branches
    threads_branches = threads_sub.add_parser("branches", help="Check branch relevance for a thread")
    threads_branches.add_argument("target", help="Thread URL, URI, or root author handle")
    
    # threads backoff-check
    threads_backoff_check = threads_sub.add_parser("backoff-check", help="Check if thread check is due (for cron)")
    threads_backoff_check.add_argument("target", help="Thread URL, URI, or root author handle")
    
    # threads backoff-update
    threads_backoff_update = threads_sub.add_parser("backoff-update", help="Update backoff state after check")
    threads_backoff_update.add_argument("target", help="Thread URL, URI, or root author handle")
    threads_backoff_update.add_argument("--activity", action="store_true", help="New activity was found (resets backoff)")

    # organic
    organic_parser = subparsers.add_parser(
        "organic", help="Organic posting (replaces 29 bsky-post crons)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
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
"""
    )
    organic_parser.add_argument("--dry-run", action="store_true", help="Preview without posting")
    organic_parser.add_argument("--force", action="store_true", help="Ignore time window and probability")
    organic_parser.add_argument("--probability", type=float, default=0.20, help="Posting probability (default: 0.20)")

    args = parser.parse_args(argv)

    # Import and run the appropriate command
    if args.command == "post":
        from .post import run
    elif args.command == "notify":
        from .notify import run
    elif args.command == "reply":
        from .reply import run
    elif args.command == "like":
        from .like import run
    elif args.command == "repost":
        from .repost import run
    elif args.command == "announce":
        from .announce import run
    elif args.command == "delete":
        from .delete import run
    elif args.command == "profile":
        from .profile import run
    elif args.command == "dm":
        from .dm_cmd import run
    elif args.command == "search":
        from .search import run
    elif args.command == "engage":
        from .engage import run
    elif args.command == "discover":
        if args.execute:
            args.dry_run = False
        from .discover import run
    elif args.command == "follow":
        from .follow import run
    elif args.command == "threads":
        from .threads import run
    elif args.command == "organic":
        from .organic import run
    else:
        parser.print_help()
        return 2

    return run(args)


if __name__ == "__main__":
    sys.exit(main())
