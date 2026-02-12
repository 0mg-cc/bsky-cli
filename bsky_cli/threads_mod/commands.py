from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..auth import get_session
from .analysis import analyze_thread
from .api import get_notifications, get_thread
from .config import BACKOFF_INTERVALS, CRON_THRESHOLD, DEFAULT_SILENCE_HOURS, MAX_TOPIC_DRIFT, MIN_THREAD_DEPTH
from .cron import generate_cron_config
from .models import TrackedThread
from .state import load_threads_state, migrate_threads_state_from_json, save_threads_state
from .utils import uri_to_url

def cmd_evaluate(args) -> int:
    """Evaluate notifications for thread importance."""
    print("🔗 Connecting to BlueSky...")
    pds, did, jwt, handle = get_session()
    print(f"✓ Logged in as @{handle}")
    
    state = load_threads_state()
    evaluated = set(state.get("evaluated_notifications", []))
    
    print("📬 Fetching notifications...")
    notifications = get_notifications(pds, jwt, limit=args.limit)
    
    # Filter to replies/mentions we haven't evaluated
    candidates = []
    for n in notifications:
        if n.get("reason") not in ("reply", "mention", "quote"):
            continue
        uri = n.get("uri", "")
        if uri in evaluated:
            continue
        candidates.append(n)
    
    print(f"✓ Found {len(candidates)} new reply/mention/quote notifications")
    
    if not candidates:
        print("No new threads to evaluate.")
        return 0
    
    print("\n📊 Analyzing threads...\n")
    
    # Group by root URI to avoid duplicate analysis
    root_uris: dict[str, list[dict]] = {}
    for n in candidates:
        record = n.get("record", {})
        reply_ref = record.get("reply", {})
        root_uri = reply_ref.get("root", {}).get("uri") or n.get("uri", "")
        root_uris.setdefault(root_uri, []).append(n)
    
    high_value_threads: list[TrackedThread] = []
    
    for root_uri, notifs in root_uris.items():
        print(f"Analyzing thread: {uri_to_url(root_uri)[:60]}...")
        
        thread = analyze_thread(pds, jwt, did, root_uri)
        if not thread:
            print("  ✗ Could not fetch thread")
            continue
        
        print(f"  @{thread.root_author_handle}: score {thread.overall_score:.0f}/100")
        print(f"  Topics: {', '.join(thread.main_topics) or 'general'}")
        print(f"  Branches: {len(thread.branches)}, Our replies: {thread.total_our_replies}")
        
        # Show branch details
        for uri, branch in thread.branches.items():
            drift_pct = int(branch.topic_drift * 100)
            print(f"    └─ @{', @'.join(branch.interlocutors[:2]) or 'unknown'}: "
                  f"drift {drift_pct}%, score {branch.branch_score:.0f}")
        
        # Check if thread qualifies for cron
        if thread.overall_score >= CRON_THRESHOLD:
            if thread.total_our_replies >= MIN_THREAD_DEPTH - 1:
                high_value_threads.append(thread)
                print(f"  ⭐ HIGH VALUE - recommend cron monitoring")
            else:
                print(f"  ⭐ HIGH VALUE (too shallow: {thread.total_our_replies + 1}/{MIN_THREAD_DEPTH} exchanges)")
        print()
        
        # Mark notifications as evaluated
        for n in notifs:
            state.setdefault("evaluated_notifications", []).append(n.get("uri", ""))
        
        # Save thread to state
        state.setdefault("threads", {})[root_uri] = thread.to_dict()
    
    # Output high-value threads
    if high_value_threads:
        print(f"\n{'='*60}")
        print(f"🎯 {len(high_value_threads)} HIGH-VALUE THREADS (score >= {CRON_THRESHOLD})")
        print(f"{'='*60}\n")
        
        for t in high_value_threads:
            print(f"Thread: {t.root_url}")
            print(f"Root author: @{t.root_author_handle}")
            print(f"Topics: {', '.join(t.main_topics) or 'general'}")
            print(f"Score: {t.overall_score:.0f}/100")
            print(f"Branches: {len(t.branches)}")
            
            if args.json:
                cron_config = generate_cron_config(t, silence_hours=args.silence_hours)
                print(f"Cron config:\n{json.dumps(cron_config, indent=2)}")
            print()
    
    state["last_evaluation"] = datetime.now(timezone.utc).isoformat()
    save_threads_state(state)
    
    print(f"✓ Evaluation complete. State saved.")
    return 0

def cmd_list(args) -> int:
    """List tracked threads."""
    state = load_threads_state()
    threads_data = state.get("threads", {})
    
    if not threads_data:
        print("No threads being tracked.")
        return 0
    
    print(f"📋 Tracked Threads ({len(threads_data)})\n")
    
    for uri, t_data in threads_data.items():
        try:
            t = TrackedThread.from_dict(t_data)
        except Exception as exc:
            print(f"⚠️  Skipping corrupt thread entry {uri}: {exc}", file=sys.stderr)
            continue

        if t is None:
            continue

        status = "✓" if t.enabled else "⏸"
        print(f"{status} @{t.root_author_handle} (score: {t.overall_score:.0f})")
        print(f"  {t.root_url}")
        print(f"  Topics: {', '.join(t.main_topics) or 'general'}")
        print(f"  Branches: {len(t.branches)}, Our replies: {t.total_our_replies}")
        print(f"  Last activity: {t.last_activity_at}")
        
        # Show branches
        for branch_uri, branch in t.branches.items():
            drift_pct = int(branch.topic_drift * 100)
            print(f"    └─ @{', @'.join(branch.interlocutors[:2]) or '?'}: "
                  f"drift {drift_pct}%, score {branch.branch_score:.0f}, "
                  f"{branch.message_count} msgs")
        
        if t.cron_id:
            print(f"  Cron: {t.cron_id}")
        print()
    
    return 0

def cmd_watch(args) -> int:
    """Start watching a specific thread."""
    print("🔗 Connecting to BlueSky...")
    pds, did, jwt, handle = get_session()
    
    # Parse URL to URI
    url = args.url
    m = re.match(r"https://bsky\.app/profile/([^/]+)/post/([^/]+)", url)
    if m:
        uri = f"at://{m.group(1)}/app.bsky.feed.post/{m.group(2)}"
    else:
        uri = url
    
    print(f"📊 Analyzing thread...")
    thread = analyze_thread(pds, jwt, did, uri)
    
    if not thread:
        print(f"❌ Could not fetch thread: {url}")
        return 1
    
    print(f"\nThread: {thread.root_url}")
    print(f"Root author: @{thread.root_author_handle}")
    print(f"Topics: {', '.join(thread.main_topics) or 'general'}")
    print(f"Score: {thread.overall_score:.0f}/100")
    print(f"Branches: {len(thread.branches)}, Our replies: {thread.total_our_replies}")
    
    for branch_uri, branch in thread.branches.items():
        drift_pct = int(branch.topic_drift * 100)
        print(f"  └─ @{', @'.join(branch.interlocutors[:2]) or '?'}: "
              f"drift {drift_pct}%, score {branch.branch_score:.0f}")
    
    # Save to state
    state = load_threads_state()
    state.setdefault("threads", {})[uri] = thread.to_dict()
    save_threads_state(state)
    
    print(f"\n✓ Now tracking thread")
    
    # Output cron config
    cron_config = generate_cron_config(thread, silence_hours=args.silence_hours)
    print(f"\nCron configuration:")
    print(json.dumps(cron_config, indent=2))
    
    return 0

def cmd_unwatch(args) -> int:
    """Stop watching a thread."""
    state = load_threads_state()
    threads = state.get("threads", {})
    
    target = args.target
    found_uri = None
    
    for uri, t_data in threads.items():
        if (target in uri or 
            target in t_data.get("root_url", "") or 
            target == t_data.get("root_author_handle")):
            found_uri = uri
            break
    
    if not found_uri:
        print(f"❌ Thread not found: {target}")
        return 1
    
    t_data = threads[found_uri]
    del state["threads"][found_uri]
    save_threads_state(state)
    
    print(f"✓ Stopped tracking thread with @{t_data.get('root_author_handle')}")
    if t_data.get("cron_id"):
        print(f"  Note: Cron {t_data['cron_id']} should be disabled separately")
    
    return 0

def cmd_check_branches(args) -> int:
    """Check branch relevance for a tracked thread."""
    print("🔗 Connecting to BlueSky...")
    pds, did, jwt, handle = get_session()
    
    state = load_threads_state()
    threads = state.get("threads", {})
    
    # Find thread
    target = args.target
    found_uri = None
    for uri, t_data in threads.items():
        if (target in uri or 
            target in t_data.get("root_url", "") or 
            target == t_data.get("root_author_handle")):
            found_uri = uri
            break
    
    if not found_uri:
        print(f"❌ Thread not found: {target}")
        return 1
    
    print(f"📊 Re-analyzing thread...")
    thread = analyze_thread(pds, jwt, did, found_uri)
    
    if not thread:
        print("❌ Could not fetch thread")
        return 1
    
    print(f"\nThread: {thread.root_url}")
    print(f"Topics: {', '.join(thread.main_topics) or 'general'}")
    print(f"Engaged interlocutors: {len(thread.engaged_interlocutors)}")
    print(f"\nBranch Analysis:")
    print("-" * 50)
    
    for branch_uri, branch in thread.branches.items():
        drift_pct = int(branch.topic_drift * 100)
        # Check if we've engaged with this interlocutor before
        is_engaged = bool(set(branch.interlocutor_dids) & set(thread.engaged_interlocutors))
        
        # More permissive for engaged interlocutors
        if is_engaged:
            status = "✓ RESPOND (engaged)" if branch.branch_score >= 30 else "⏭ SKIP"
        else:
            status = "✓ RESPOND" if branch.topic_drift < MAX_TOPIC_DRIFT and branch.branch_score >= 40 else "⏭ SKIP"
        
        print(f"\n{status} Branch with @{', @'.join(branch.interlocutors[:3]) or 'unknown'}")
        print(f"  URL: {branch.our_reply_url}")
        print(f"  Messages: {branch.message_count}")
        print(f"  Topic drift: {drift_pct}%{' (ignored - engaged)' if is_engaged else ' (off-topic)' if drift_pct >= 70 else ' (on-topic)' if drift_pct < 30 else ' (drifting)'}")
        print(f"  Branch score: {branch.branch_score:.0f}/100")
        print(f"  Last activity: {branch.last_activity_at}")
    
    # Show our previous replies for consistency checking
    if thread.our_reply_texts:
        print(f"\n{'='*50}")
        print("📝 Our previous replies (for consistency):")
        print("-" * 50)
        for i, text in enumerate(thread.our_reply_texts[-5:], 1):
            print(f"{i}. {text[:100]}{'...' if len(text) > 100 else ''}")
    
    # Update state
    state["threads"][found_uri] = thread.to_dict()
    save_threads_state(state)
    
    return 0


def _thread_target_to_uri(target: str) -> str:
    target = (target or "").strip()
    if target.startswith("at://"):
        return target
    m = re.match(r"https://bsky\.app/profile/([^/]+)/post/([^/?#]+)", target)
    if m:
        actor, rkey = m.group(1), m.group(2)
        return f"at://{actor}/app.bsky.feed.post/{rkey}"
    return target


def _clean_snippet(text: str, max_len: int) -> str:
    compact = re.sub(r"\s+", " ", (text or "")).strip()
    if len(compact) <= max_len:
        return compact
    return compact[: max(0, max_len - 1)].rstrip() + "…"


def _node_has_author_did(node: dict, did: str) -> bool:
    post = node.get("post") or {}
    author = post.get("author") or {}
    if author.get("did") == did:
        return True
    for child in node.get("replies") or []:
        if _node_has_author_did(child, did):
            return True
    return False


def _render_thread_tree(node: dict, *, my_did: str, mine_only: bool, snippet_len: int, max_depth: int) -> list[str]:
    lines: list[str] = []

    def walk(cur: dict, prefix: str = "", is_last: bool = True, level: int = 0):
        post = cur.get("post") or {}
        author = post.get("author") or {}
        handle = author.get("handle") or author.get("did") or "unknown"
        text = (post.get("record") or {}).get("text", "")
        mine = " (you)" if author.get("did") == my_did else ""

        connector = "" if level == 0 else ("└─ " if is_last else "├─ ")
        lines.append(f"{prefix}{connector}@{handle}{mine}: {_clean_snippet(text, snippet_len)}")

        if level >= max_depth:
            replies = cur.get("replies") or []
            if replies:
                child_prefix = prefix + ("   " if is_last else "│  ")
                lines.append(f"{child_prefix}└─ …")
            return

        replies = cur.get("replies") or []
        if mine_only:
            replies = [r for r in replies if _node_has_author_did(r, my_did)]

        for i, child in enumerate(replies):
            child_is_last = i == (len(replies) - 1)
            child_prefix = prefix + ("   " if is_last else "│  ")
            walk(child, prefix=child_prefix, is_last=child_is_last, level=level + 1)

    walk(node)
    return lines


def cmd_tree(args) -> int:
    """Render a visual ASCII tree for a thread URL/URI."""
    print("🔗 Connecting to BlueSky...")
    pds, did, jwt, _ = get_session()

    uri = _thread_target_to_uri(getattr(args, "target", ""))
    if not uri:
        print("❌ Invalid target. Use a BlueSky post URL or at:// URI")
        return 1

    depth = int(getattr(args, "depth", 6))
    snippet = int(getattr(args, "snippet", 90))
    mine_only = bool(getattr(args, "mine_only", False))

    thread = get_thread(pds, jwt, uri, depth=depth)
    if not thread or not (thread.get("post") or {}).get("uri"):
        print(f"❌ Could not fetch thread: {getattr(args, 'target', uri)}")
        return 1

    lines = _render_thread_tree(
        thread,
        my_did=did,
        mine_only=mine_only,
        snippet_len=max(20, snippet),
        max_depth=max(1, depth),
    )
    if not lines:
        print("❌ Thread loaded but no renderable posts found")
        return 1

    print("\n".join(lines))
    return 0


def cmd_backoff_check(args) -> int:
    """
    Check if we should run a thread check based on backoff state.
    Returns 0 if should check, 1 if should skip, 2 on error.
    
    This implements exponential backoff:
    - Start at 10 minutes
    - If no new activity: 10 → 20 → 40 → 80 → 160 → 240 minutes
    - After 240 min with no activity: one final check at 18h, then disable
    - If new activity detected: reset to 10 minutes
    
    IMPORTANT: Even during backoff, we peek at notifications. If new activity
    is detected, we reset backoff and proceed with check immediately.
    """
    # First, peek at notifications to detect new activity during backoff
    try:
        pds, did, jwt, handle = get_session()
        notifications = get_notifications(pds, jwt, limit=20)
        
        # Check for recent replies/mentions (last 10 minutes)
        recent_cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        new_activity = False
        
        for n in notifications:
            if n.get("reason") not in ("reply", "mention", "quote"):
                continue
            indexed = n.get("indexedAt", "")
            if indexed:
                try:
                    ts = datetime.fromisoformat(indexed.replace("Z", "+00:00"))
                    if ts > recent_cutoff:
                        new_activity = True
                        print(f"🔔 New activity detected! Resetting backoff...")
                        break
                except Exception:
                    pass
        
        if new_activity:
            # Reset backoff and proceed with check
            state = load_threads_state()
            threads = state.get("threads", {})
            target = args.target
            for uri, t_data in threads.items():
                if (target in uri or 
                    target in t_data.get("root_url", "") or 
                    target == t_data.get("root_author_handle")):
                    t_data["backoff_level"] = 0
                    t_data["last_new_activity_at"] = datetime.now(timezone.utc).isoformat()
                    state["threads"][uri] = t_data
                    save_threads_state(state)
                    break
            print(f"✓ CHECK - New activity, backoff reset to 0")
            return 0
    except Exception as e:
        # If notification check fails, fall through to normal backoff logic
        print(f"⚠️ Could not check notifications: {e}")
    
    state = load_threads_state()
    threads = state.get("threads", {})
    
    target = args.target
    found_uri = None
    for uri, t_data in threads.items():
        if (target in uri or 
            target in t_data.get("root_url", "") or 
            target == t_data.get("root_author_handle")):
            found_uri = uri
            break
    
    if not found_uri:
        print(f"❌ Thread not found: {target}")
        return 2
    
    thread = TrackedThread.from_dict(threads[found_uri])
    if thread is None:
        print(f"❌ Thread entry is corrupted or legacy: {found_uri}")
        return 2
    now = datetime.now(timezone.utc)
    
    # Get current backoff interval
    backoff_level = thread.backoff_level
    if backoff_level >= len(BACKOFF_INTERVALS):
        # We're past all intervals - check if 18h have passed for final check
        if thread.last_check_at:
            last_check = datetime.fromisoformat(thread.last_check_at.replace("Z", "+00:00"))
            hours_since = (now - last_check).total_seconds() / 3600
            if hours_since < DEFAULT_SILENCE_HOURS:
                remaining = DEFAULT_SILENCE_HOURS - hours_since
                print(f"⏸ SKIP - Final 18h check not due yet ({remaining:.1f}h remaining)")
                print(f"  Thread: @{thread.root_author_handle}")
                print(f"  Backoff: FINAL (18h)")
                return 1
            else:
                print(f"🔚 FINAL CHECK - 18h silence reached")
                print(f"  Thread: @{thread.root_author_handle}")
                print(f"  Recommendation: Disable cron if no activity")
                return 0
        current_interval = DEFAULT_SILENCE_HOURS * 60  # In minutes
    else:
        current_interval = BACKOFF_INTERVALS[backoff_level]
    
    # Check if enough time has passed
    if thread.last_check_at:
        last_check = datetime.fromisoformat(thread.last_check_at.replace("Z", "+00:00"))
        minutes_since = (now - last_check).total_seconds() / 60
        
        if minutes_since < current_interval:
            remaining = current_interval - minutes_since
            print(f"⏸ SKIP - Not due yet ({remaining:.0f}min remaining)")
            print(f"  Thread: @{thread.root_author_handle}")
            print(f"  Backoff level: {backoff_level} ({current_interval}min interval)")
            return 1
    
    # Should check - output status
    print(f"✓ CHECK - Due now")
    print(f"  Thread: @{thread.root_author_handle}")
    print(f"  Backoff level: {backoff_level} ({current_interval}min interval)")
    print(f"  Last activity: {thread.last_activity_at}")
    return 0

def cmd_backoff_update(args) -> int:
    """
    Update backoff state after a check.
    Call with --activity if new activity was found, otherwise backoff increases.
    """
    state = load_threads_state()
    threads = state.get("threads", {})
    
    target = args.target
    found_uri = None
    for uri, t_data in threads.items():
        if (target in uri or 
            target in t_data.get("root_url", "") or 
            target == t_data.get("root_author_handle")):
            found_uri = uri
            break
    
    if not found_uri:
        print(f"❌ Thread not found: {target}")
        return 2
    
    thread_data = threads[found_uri]
    now = datetime.now(timezone.utc).isoformat()
    
    # Update last check time
    thread_data["last_check_at"] = now
    
    if args.activity:
        # New activity - reset backoff to 0
        old_level = thread_data.get("backoff_level", 0)
        thread_data["backoff_level"] = 0
        thread_data["last_new_activity_at"] = now
        print(f"✓ Backoff RESET (was level {old_level}, now 0)")
        print(f"  Next check: 10 minutes")
    else:
        # No activity - increase backoff
        old_level = thread_data.get("backoff_level", 0)
        new_level = min(old_level + 1, len(BACKOFF_INTERVALS))
        thread_data["backoff_level"] = new_level
        
        if new_level >= len(BACKOFF_INTERVALS):
            print(f"⏫ Backoff MAXED (level {old_level} → FINAL)")
            print(f"  Next check: 18 hours (final check before disable)")
        else:
            next_interval = BACKOFF_INTERVALS[new_level]
            print(f"⏫ Backoff INCREASED (level {old_level} → {new_level})")
            print(f"  Next check: {next_interval} minutes")
    
    state["threads"][found_uri] = thread_data
    save_threads_state(state)
    return 0

def cmd_migrate_state(args) -> int:
    """Migrate legacy threads_mod JSON state into SQLite."""

    from_json = getattr(args, "from_json", None)
    archive = bool(getattr(args, "archive_json", False))
    dry_run = bool(getattr(args, "dry_run", False))

    path = Path(from_json) if from_json else None
    res = migrate_threads_state_from_json(path, archive_json=archive, dry_run=dry_run)

    if not res.get("migrated") and res.get("reason") == "missing":
        print(f"No legacy state JSON found at {res.get('path')}")
        return 0

    if res.get("dry_run"):
        print(f"[dry-run] would migrate: threads={res.get('threads')} evaluated={res.get('evaluated')} from {res.get('path')}")
        return 0

    print(f"✓ Migrated legacy threads state: threads={res.get('threads')} evaluated={res.get('evaluated')}")
    if res.get("archived_to"):
        print(f"  archived: {res['archived_to']}")
    return 0


def run(args) -> int:
    """Entry point from CLI."""
    if args.threads_command == "evaluate":
        return cmd_evaluate(args)
    elif args.threads_command == "list":
        return cmd_list(args)
    elif args.threads_command == "watch":
        return cmd_watch(args)
    elif args.threads_command == "unwatch":
        return cmd_unwatch(args)
    elif args.threads_command == "branches":
        return cmd_check_branches(args)
    elif args.threads_command == "tree":
        return cmd_tree(args)
    elif args.threads_command == "backoff-check":
        return cmd_backoff_check(args)
    elif args.threads_command == "backoff-update":
        return cmd_backoff_update(args)
    elif args.threads_command == "migrate-state":
        return cmd_migrate_state(args)
    else:
        print("Unknown threads command")
        return 2
