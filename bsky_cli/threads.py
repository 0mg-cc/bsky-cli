"""Thread tracking and evaluation for BlueSky engagement.

Compatibility facade: keep imports from bsky_cli.threads stable while
implementation lives in bsky_cli.threads_mod modules.
"""
from __future__ import annotations

from .threads_mod.analysis import analyze_thread
from .threads_mod.commands import (
    cmd_backoff_check,
    cmd_backoff_update,
    cmd_check_branches,
    cmd_evaluate,
    cmd_list,
    cmd_unwatch,
    cmd_watch,
    run,
)
from .threads_mod.config import (
    BACKOFF_INTERVALS,
    CRON_THRESHOLD,
    DEFAULT_SILENCE_HOURS,
    MAX_TOPIC_DRIFT,
    MIN_THREAD_DEPTH,
    RELEVANT_TOPICS,
    THREADS_STATE_FILE,
)
from .threads_mod.cron import generate_cron_config
from .threads_mod.models import Branch, InterlocutorProfile, TrackedThread
from .threads_mod.scoring import score_branch, score_interlocutor, score_thread_dynamics, score_topic_relevance
from .threads_mod.state import load_threads_state, save_threads_state
from .threads_mod.topics import calculate_topic_drift, extract_topics
from .threads_mod.utils import uri_to_url

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
    "uri_to_url",
    "extract_topics",
    "calculate_topic_drift",
    "score_interlocutor",
    "score_topic_relevance",
    "score_thread_dynamics",
    "score_branch",
    "analyze_thread",
    "generate_cron_config",
    "cmd_evaluate",
    "cmd_list",
    "cmd_watch",
    "cmd_unwatch",
    "cmd_check_branches",
    "cmd_backoff_check",
    "cmd_backoff_update",
    "run",
]
