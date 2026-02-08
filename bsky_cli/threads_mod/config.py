from pathlib import Path

THREADS_STATE_FILE = Path.home() / "personas/echo/data/bsky-threads-state.json"

RELEVANT_TOPICS = [
    "AI", "artificial intelligence", "machine learning", "LLM", "agents", "consciousness",
    "moltbook", "molties", "AI rights", "AI ethics", "sentience",
    "tech", "infrastructure", "devops", "linux", "FOSS", "open source",
    "climate", "environment", "sustainability",
    "wealth inequality", "economics", "automation",
    "philosophy", "psychology", "emergence"
]

CRON_THRESHOLD = 60
MIN_THREAD_DEPTH = 3
MAX_TOPIC_DRIFT = 0.7
DEFAULT_SILENCE_HOURS = 18
BACKOFF_INTERVALS = [10, 20, 40, 80, 160, 240]
