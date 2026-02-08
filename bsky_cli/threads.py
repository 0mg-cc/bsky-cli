"""Thread tracking and evaluation for BlueSky engagement.

Compatibility facade: public imports stay available from bsky_cli.threads
while internals are progressively split into bsky_cli.threads_mod.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from .auth import get_session, load_from_pass
from .threads_mod import (
    BACKOFF_INTERVALS,
    CRON_THRESHOLD,
    DEFAULT_SILENCE_HOURS,
    MAX_TOPIC_DRIFT,
    MIN_THREAD_DEPTH,
    RELEVANT_TOPICS,
    Branch,
    InterlocutorProfile,
    TrackedThread,
    calculate_topic_drift,
    extract_topics,
    generate_cron_config,
    get_notifications,
    get_profile,
    get_thread,
    load_threads_state,
    save_threads_state,
    score_branch,
    score_interlocutor,
    score_thread_dynamics,
    score_topic_relevance,
    uri_to_url,
)

def analyze_thread(pds: str, jwt: str, our_did: str, root_uri: str) -> TrackedThread | None:
    """
    Fully analyze a thread, extracting all branches we're involved in.
    """
    thread = get_thread(pds, jwt, root_uri, depth=20)
    if not thread:
        return None
    
    root_post = thread.get("post", {})
    root_record = root_post.get("record", {})
    root_text = root_record.get("text", "")
    root_author = root_post.get("author", {})
    
    main_topics = extract_topics(root_text)
    branches: dict[str, Branch] = {}
    our_reply_uris: list[str] = []
    our_reply_texts: list[str] = []  # For consistency checking
    all_interlocutor_dids: set[str] = set()
    engaged_interlocutors: set[str] = set()  # People we've replied to
    latest_activity = root_record.get("createdAt", "")
    
    def walk_thread(node: dict, parent_is_ours: bool = False, branch_key: str | None = None, parent_author_did: str | None = None):
        """Recursively walk thread to find our replies and track branches."""
        nonlocal latest_activity
        
        post = node.get("post", {})
        record = post.get("record", {})
        author = post.get("author", {})
        uri = post.get("uri", "")
        created = record.get("createdAt", "")
        text = record.get("text", "")
        author_did = author.get("did", "")
        author_handle = author.get("handle", "")
        is_ours = author_did == our_did
        
        if created and created > latest_activity:
            latest_activity = created
        
        # If this is our reply, it starts or continues a branch
        if is_ours:
            our_reply_uris.append(uri)
            our_reply_texts.append(text)  # Track our text for consistency
            # Track who we're engaging with
            if parent_author_did and parent_author_did != our_did:
                engaged_interlocutors.add(parent_author_did)
            if uri not in branches:
                branches[uri] = Branch(
                    our_reply_uri=uri,
                    our_reply_url=uri_to_url(uri),
                    interlocutors=[],
                    interlocutor_dids=[],
                    last_activity_at=created,
                    message_count=1,
                    topic_drift=0.0,
                    branch_score=0.0
                )
            branch_key = uri
        elif branch_key and branch_key in branches:
            # This is a reply to one of our branches
            branch = branches[branch_key]
            if author_handle and author_handle not in branch.interlocutors:
                branch.interlocutors.append(author_handle)
            if author_did and author_did not in branch.interlocutor_dids:
                branch.interlocutor_dids.append(author_did)
                all_interlocutor_dids.add(author_did)
            branch.message_count += 1
            if created > branch.last_activity_at:
                branch.last_activity_at = created
            # Accumulate text for topic drift calculation
            if not hasattr(branch, '_accumulated_text'):
                branch._accumulated_text = ""
            branch._accumulated_text += " " + text
        
        # Recurse into replies
        for reply in node.get("replies", []):
            walk_thread(reply, parent_is_ours=is_ours, branch_key=branch_key, parent_author_did=author_did)
    
    walk_thread(thread)
    
    # Calculate topic drift for each branch
    for branch in branches.values():
        branch_text = getattr(branch, '_accumulated_text', "")
        branch.topic_drift = calculate_topic_drift(root_text, branch_text)
        # Clean up temp attribute
        if hasattr(branch, '_accumulated_text'):
            delattr(branch, '_accumulated_text')
    
    # Fetch interlocutor profiles for scoring
    profiles: dict[str, InterlocutorProfile] = {}
    for did in all_interlocutor_dids:
        profile = get_profile(pds, jwt, did)
        if profile:
            profiles[did] = profile
    
    # Score branches (pass engaged_interlocutors to relax drift for ongoing conversations)
    for branch in branches.values():
        branch.branch_score = score_branch(branch, main_topics, profiles, engaged_interlocutors)
    
    # Calculate overall thread score
    total_replies = root_post.get("replyCount", 0)
    
    # Get root author profile for scoring
    root_profile = get_profile(pds, jwt, root_author.get("did", ""))
    interlocutor_score = 0
    if root_profile:
        interlocutor_score, _ = score_interlocutor(root_profile)
    
    topic_score, _ = score_topic_relevance(root_text)
    dynamics_score, _ = score_thread_dynamics(total_replies, len(our_reply_uris), len(branches))
    
    overall_score = interlocutor_score + topic_score + dynamics_score
    
    return TrackedThread(
        root_uri=root_uri,
        root_url=uri_to_url(root_uri),
        root_author_handle=root_author.get("handle", "unknown"),
        root_author_did=root_author.get("did", ""),
        main_topics=main_topics,
        root_text=root_text[:500],
        overall_score=overall_score,
        branches=branches,
        total_our_replies=len(our_reply_uris),
        created_at=root_record.get("createdAt", ""),
        last_activity_at=latest_activity,
        engaged_interlocutors=list(engaged_interlocutors),
        our_reply_texts=our_reply_texts[-10:]  # Keep last 10 for consistency checking
    )


# ============================================================================
# CRON GENERATION
# ============================================================================

def generate_cron_config(
    thread: TrackedThread,
    interval_minutes: int = 10,
    silence_hours: int = DEFAULT_SILENCE_HOURS,
    telegram_to: str = "843819294",
    key_facts: str = ""
) -> dict:
    """Generate OpenClaw cron configuration for thread monitoring."""
    
    # List active branches
    branch_info = []
    for uri, branch in thread.branches.items():
        if branch.branch_score >= 40:  # Only mention worthwhile branches
            is_engaged = bool(set(branch.interlocutor_dids) & set(thread.engaged_interlocutors))
            drift_status = "engaged" if is_engaged else ("on-topic" if branch.topic_drift < 0.3 else "drifting" if branch.topic_drift < 0.7 else "off-topic")
            branch_info.append(f"  - @{', @'.join(branch.interlocutors[:3])} ({drift_status}, score {branch.branch_score:.0f})")
    
    branches_text = "\n".join(branch_info) if branch_info else "  (no active branches yet)"
    
    # Include recent replies for consistency checking
    consistency_text = ""
    if thread.our_reply_texts:
        recent = thread.our_reply_texts[-3:]
        consistency_text = "\n**OUR RECENT REPLIES (check consistency):**\n" + "\n".join(
            f"  - \"{t[:80]}{'...' if len(t) > 80 else ''}\"" for t in recent
        )
    
    message = f"""Check BlueSky notifications for the thread at {thread.root_url}

**THREAD INFO:**
- Root author: @{thread.root_author_handle}
- Topics: {', '.join(thread.main_topics) or 'general'}
- Our replies: {thread.total_our_replies}
- Branches:
{branches_text}
{consistency_text}

{f"**KEY FACTS:**{chr(10)}{key_facts}{chr(10)}" if key_facts else ""}
**INSTRUCTIONS:**
1. Run `~/scripts/bsky threads branches {thread.root_author_handle}` to see branch status
2. For engaged interlocutors (people we've already replied to): ALWAYS respond regardless of topic drift
3. For new interlocutors: skip if drift > 70% or score < 40
4. **CHECK CONSISTENCY**: Read our recent replies above. Don't contradict yourself!
5. Read ~/personas/echo/data/bsky-guidelines.md for tone/style
6. Craft thoughtful replies (max 300 chars)
7. STAY FACTUAL - don't make claims you're unsure about
8. Post replies and report what you did

If no new activity, just say 'No new replies in {thread.root_author_handle} thread.'

If no replies for {silence_hours}+ hours, disable this cron as the conversation has likely concluded."""

    return {
        "name": f"bsky-thread-{thread.root_author_handle[:20]}",
        "schedule": {
            "kind": "every",
            "everyMs": interval_minutes * 60 * 1000
        },
        "payload": {
            "kind": "agentTurn",
            "message": message,
            "deliver": True,
            "channel": "telegram",
            "to": telegram_to
        },
        "sessionTarget": "isolated",
        "enabled": True
    }


# ============================================================================
# COMMANDS
# ============================================================================

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
        t = TrackedThread.from_dict(t_data)
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
    elif args.threads_command == "backoff-check":
        return cmd_backoff_check(args)
    elif args.threads_command == "backoff-update":
        return cmd_backoff_update(args)
    else:
        print("Unknown threads command")
        return 2
