from .config import DEFAULT_SILENCE_HOURS
from .models import TrackedThread


def generate_cron_config(
    thread: TrackedThread,
    interval_minutes: int = 10,
    silence_hours: int = DEFAULT_SILENCE_HOURS,
    telegram_to: str = "843819294",
    key_facts: str = "",
) -> dict:
    branch_info = []
    for _, branch in thread.branches.items():
        if branch.branch_score >= 40:
            is_engaged = bool(set(branch.interlocutor_dids) & set(thread.engaged_interlocutors))
            drift_status = "engaged" if is_engaged else (
                "on-topic" if branch.topic_drift < 0.3 else "drifting" if branch.topic_drift < 0.7 else "off-topic"
            )
            branch_info.append(f"  - @{', @'.join(branch.interlocutors[:3])} ({drift_status}, score {branch.branch_score:.0f})")

    branches_text = "\n".join(branch_info) if branch_info else "  (no active branches yet)"

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
        "schedule": {"kind": "every", "everyMs": interval_minutes * 60 * 1000},
        "payload": {
            "kind": "agentTurn",
            "message": message,
            "deliver": True,
            "channel": "telegram",
            "to": telegram_to,
        },
        "sessionTarget": "isolated",
        "enabled": True,
    }
