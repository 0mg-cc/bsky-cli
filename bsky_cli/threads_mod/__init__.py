"""Modular components for thread tracking."""

from .api import get_notifications, get_profile, get_thread
from .config import (
    BACKOFF_INTERVALS,
    CRON_THRESHOLD,
    DEFAULT_SILENCE_HOURS,
    MAX_TOPIC_DRIFT,
    MIN_THREAD_DEPTH,
    RELEVANT_TOPICS,
    THREADS_STATE_FILE,
)
from .cron import generate_cron_config
from .models import Branch, InterlocutorProfile, TrackedThread
from .scoring import score_branch, score_interlocutor, score_thread_dynamics, score_topic_relevance
from .state import load_threads_state, save_threads_state
from .topics import calculate_topic_drift, extract_topics
from .utils import uri_to_url

__all__ = [
    "THREADS_STATE_FILE",
    "RELEVANT_TOPICS",
    "CRON_THRESHOLD",
    "MIN_THREAD_DEPTH",
    "MAX_TOPIC_DRIFT",
    "DEFAULT_SILENCE_HOURS",
    "BACKOFF_INTERVALS",
    "Branch",
    "TrackedThread",
    "InterlocutorProfile",
    "load_threads_state",
    "save_threads_state",
    "get_profile",
    "get_thread",
    "get_notifications",
    "uri_to_url",
    "extract_topics",
    "calculate_topic_drift",
    "score_interlocutor",
    "score_topic_relevance",
    "score_thread_dynamics",
    "score_branch",
    "generate_cron_config",
]
