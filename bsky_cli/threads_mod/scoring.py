from datetime import datetime, timezone

from .config import RELEVANT_TOPICS
from .models import Branch, InterlocutorProfile


def score_interlocutor(profile: InterlocutorProfile) -> tuple[float, list[str]]:
    score = 0.0
    reasons = []

    if profile.followers_count >= 10000:
        score += 15
        reasons.append(f"high followers ({profile.followers_count})")
    elif profile.followers_count >= 1000:
        score += 10
        reasons.append(f"good followers ({profile.followers_count})")
    elif profile.followers_count >= 100:
        score += 5
        reasons.append(f"modest followers ({profile.followers_count})")

    if profile.follows_count > 0:
        ratio = profile.followers_count / profile.follows_count
        if ratio >= 5:
            score += 10
            reasons.append(f"high authority ratio ({ratio:.1f})")
        elif ratio >= 2:
            score += 5
            reasons.append(f"good authority ratio ({ratio:.1f})")

    if profile.posts_count >= 1000:
        score += 5
        reasons.append("very active poster")
    elif profile.posts_count >= 100:
        score += 3
        reasons.append("active poster")

    bio_lower = profile.description.lower()
    topic_matches = sum(1 for t in RELEVANT_TOPICS if t.lower() in bio_lower)
    if topic_matches >= 3:
        score += 10
        reasons.append(f"highly relevant bio ({topic_matches} topics)")
    elif topic_matches >= 1:
        score += 5
        reasons.append(f"relevant bio ({topic_matches} topics)")

    return min(score, 40), reasons


def score_topic_relevance(text: str) -> tuple[float, list[str]]:
    from .topics import extract_topics

    matches = extract_topics(text)
    if len(matches) >= 4:
        return 30, [f"highly relevant: {', '.join(matches[:5])}"]
    if len(matches) >= 2:
        return 20, [f"relevant: {', '.join(matches)}"]
    if len(matches) >= 1:
        return 10, [f"some relevance: {matches[0]}"]
    return 0, ["no obvious topic match"]


def score_thread_dynamics(total_replies: int, our_replies: int, branch_count: int) -> tuple[float, list[str]]:
    score = 0.0
    reasons = []

    if our_replies >= 3:
        score += 15
        reasons.append(f"heavily invested ({our_replies} replies)")
    elif our_replies >= 1:
        score += 8
        reasons.append(f"invested ({our_replies} replies)")

    if branch_count >= 3:
        score += 10
        reasons.append(f"multi-branch conversation ({branch_count} branches)")
    elif branch_count >= 2:
        score += 5
        reasons.append(f"branching conversation ({branch_count} branches)")

    if 3 <= total_replies <= 30:
        score += 5
        reasons.append("active but not crowded")
    elif total_replies > 30:
        reasons.append("crowded thread")
        score -= 5

    return max(0, min(score, 30)), reasons


def score_branch(
    branch: Branch,
    main_topics: list[str],
    profiles: dict[str, InterlocutorProfile],
    engaged_interlocutors: set[str] | None = None,
) -> float:
    score = 0.0

    already_engaged = False
    if engaged_interlocutors:
        already_engaged = bool(set(branch.interlocutor_dids) & engaged_interlocutors)

    if already_engaged:
        score += 40
    else:
        score += 40 * (1 - branch.topic_drift)

    interlocutor_scores = []
    for did in branch.interlocutor_dids:
        if did in profiles:
            int_score, _ = score_interlocutor(profiles[did])
            interlocutor_scores.append(int_score)
    if interlocutor_scores:
        score += (sum(interlocutor_scores) / len(interlocutor_scores)) * 0.75

    if branch.message_count >= 5:
        score += 20
    elif branch.message_count >= 3:
        score += 15
    elif branch.message_count >= 2:
        score += 10

    try:
        last = datetime.fromisoformat(branch.last_activity_at.replace("Z", "+00:00"))
        age_hours = (datetime.now(timezone.utc) - last).total_seconds() / 3600
        if age_hours < 1:
            score += 10
        elif age_hours < 6:
            score += 5
    except Exception:
        pass

    return min(score, 100)
