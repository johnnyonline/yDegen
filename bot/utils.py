import json
from typing import Any, cast

STATE_FILE = "bot_state.json"


def load_state() -> dict[str, Any]:
    try:
        with open(STATE_FILE) as f:
            return cast(dict[str, Any], json.load(f))
    except FileNotFoundError:
        return {}


def save_state(state: dict[str, Any]) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def format_duration(seconds: int) -> str:
    """Format seconds into a human-readable duration string."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins}m {secs}s" if secs else f"{mins}m"
    elif seconds < 86400:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}h {mins}m" if mins else f"{hours}h"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{days}d {hours}h" if hours else f"{days}d"


def format_time_ago(seconds: int) -> str:
    """Format seconds into a human-readable time ago string."""
    return f"{format_duration(seconds)} ago"
