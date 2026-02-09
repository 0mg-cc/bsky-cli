from .config import RELEVANT_TOPICS


def extract_topics(text: str) -> list[str]:
    text_lower = text.lower()
    return [t for t in RELEVANT_TOPICS if t.lower() in text_lower]


def calculate_topic_drift(root_text: str, branch_text: str) -> float:
    root_topics = set(t.lower() for t in extract_topics(root_text))
    branch_topics = set(t.lower() for t in extract_topics(branch_text))

    if not root_topics:
        return 0.0
    if not branch_topics:
        return 0.5

    overlap = len(root_topics & branch_topics)
    total = len(root_topics | branch_topics)
    if total == 0:
        return 0.5

    similarity = overlap / total
    return 1.0 - similarity
