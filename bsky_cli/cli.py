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

    # reply
    reply_parser = subparsers.add_parser("reply", help="Reply to a post")
    reply_parser.add_argument("post_url", help="URL of the post to reply to")
    reply_parser.add_argument("text", help="Reply text (max 300 chars)")
    reply_parser.add_argument("--dry-run", action="store_true", help="Print without posting")

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
    else:
        parser.print_help()
        return 2

    return run(args)


if __name__ == "__main__":
    sys.exit(main())
