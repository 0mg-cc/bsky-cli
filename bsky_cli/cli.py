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
  Post a message:
    bsky post "Hello from the command line!"

  Post with link preview:
    bsky post --embed https://echo.0mg.cc "Check out my blog"

  Check notifications:
    bsky notify
    bsky notify --all --json

  Reply to a post:
    bsky reply "https://bsky.app/profile/user/post/abc123" "Thanks!"

  Announce a blog post:
    bsky announce my-post-slug

  Delete recent posts:
    bsky delete --count 3

  Update profile:
    bsky profile --avatar ~/avatar.png --bio "Ops AI agent"
"""
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # post
    post_parser = subparsers.add_parser("post", help="Post a message")
    post_parser.add_argument("text", nargs="?", help="Post text (max 300 chars)")
    post_parser.add_argument("--embed", metavar="URL", help="URL to embed with link preview")
    post_parser.add_argument("--dry-run", action="store_true", help="Print without posting")

    # notify
    notify_parser = subparsers.add_parser("notify", help="Check notifications")
    notify_parser.add_argument("--all", action="store_true", help="Show all recent, not just new")
    notify_parser.add_argument("--json", action="store_true", help="Output raw JSON")
    notify_parser.add_argument("--mark-read", action="store_true", help="Mark as read on BlueSky")
    notify_parser.add_argument("--limit", type=int, default=50, help="Number to fetch (default: 50)")
    notify_parser.add_argument("--no-dm", action="store_true", help="Skip DM check")

    # reply
    reply_parser = subparsers.add_parser("reply", help="Reply to a post")
    reply_parser.add_argument("post_url", help="URL of the post to reply to")
    reply_parser.add_argument("text", help="Reply text (max 300 chars)")
    reply_parser.add_argument("--dry-run", action="store_true", help="Print without posting")

    # dm
    dm_parser = subparsers.add_parser("dm", help="Send a direct message")
    dm_parser.add_argument("handle", help="Handle of the recipient (e.g. user.bsky.social)")
    dm_parser.add_argument("text", help="Message text")
    dm_parser.add_argument("--dry-run", action="store_true", help="Print without sending")

    # announce
    announce_parser = subparsers.add_parser("announce", help="Announce a blog post")
    announce_parser.add_argument("post", help="Post slug or path to markdown file")
    announce_parser.add_argument("--text", help="Custom text (default: post title)")
    announce_parser.add_argument("--dry-run", action="store_true", help="Print without posting")

    # delete
    delete_parser = subparsers.add_parser("delete", help="Delete recent posts")
    delete_parser.add_argument("--count", type=int, default=1, help="Number of posts to delete (default: 1)")
    delete_parser.add_argument("--dry-run", action="store_true", help="List without deleting")

    # profile
    profile_parser = subparsers.add_parser("profile", help="Update profile")
    profile_parser.add_argument("--avatar", metavar="PATH", help="Path to avatar image")
    profile_parser.add_argument("--banner", metavar="PATH", help="Path to banner image (1500x500)")
    profile_parser.add_argument("--name", metavar="NAME", help="Display name")
    profile_parser.add_argument("--bio", metavar="TEXT", help="Profile description")

    # engage
    engage_parser = subparsers.add_parser("engage", help="Reply to interesting posts from follows")
    engage_parser.add_argument("--dry-run", action="store_true", help="Preview without posting")
    engage_parser.add_argument("--hours", type=int, default=12, help="Look back N hours (default: 12)")

    # discover
    discover_parser = subparsers.add_parser("discover", help="Discover new accounts to follow")
    discover_parser.add_argument("mode", choices=["follows", "reposts"], help="Discovery mode")
    discover_parser.add_argument("--dry-run", action="store_true", default=True, help="Preview without following")
    discover_parser.add_argument("--execute", action="store_true", help="Actually follow accounts")
    discover_parser.add_argument("--max", type=int, default=10, help="Max accounts to follow")

    # follow
    follow_parser = subparsers.add_parser("follow", help="Follow a user")
    follow_parser.add_argument("handle", help="Handle to follow (e.g. user.bsky.social)")
    follow_parser.add_argument("--dry-run", action="store_true", help="Preview without following")

    # threads
    threads_parser = subparsers.add_parser("threads", help="Track and evaluate conversation threads")
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

    args = parser.parse_args(argv)

    # Import and run the appropriate command
    if args.command == "post":
        from .post import run
    elif args.command == "notify":
        from .notify import run
    elif args.command == "reply":
        from .reply import run
    elif args.command == "announce":
        from .announce import run
    elif args.command == "delete":
        from .delete import run
    elif args.command == "profile":
        from .profile import run
    elif args.command == "dm":
        from .dm_cmd import run
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
    else:
        parser.print_help()
        return 2

    return run(args)


if __name__ == "__main__":
    sys.exit(main())
