import json

from .config import THREADS_STATE_FILE


def load_threads_state() -> dict:
    if THREADS_STATE_FILE.exists():
        return json.loads(THREADS_STATE_FILE.read_text())
    return {"threads": {}, "evaluated_notifications": [], "last_evaluation": None}


def save_threads_state(state: dict):
    THREADS_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["evaluated_notifications"] = state.get("evaluated_notifications", [])[-500:]
    THREADS_STATE_FILE.write_text(json.dumps(state, indent=2))
