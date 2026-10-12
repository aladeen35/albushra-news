"""How often the GitHub Pages site re-fetches, chosen by an editor.

The editor's choice lives in content/settings.json. The workflow wakes every
5 minutes and builds only when this much time has passed since the last
publish. No third-party imports, so the check runs without installing
anything.
"""
from __future__ import annotations

import json
from pathlib import Path

FETCH_CHOICES = (10, 15, 20, 30, 45, 60, 120, 180, 360)
DEFAULT_FETCH_MINUTES = 20


def fetch_minutes(folder: Path) -> int:
    try:
        data = json.loads((Path(folder) / "settings.json").read_text(encoding="utf-8"))
        value = int(data.get("fetch_minutes", DEFAULT_FETCH_MINUTES))
    except (OSError, ValueError, TypeError, AttributeError):
        return DEFAULT_FETCH_MINUTES
    return value if value in FETCH_CHOICES else DEFAULT_FETCH_MINUTES


def build_due(last_published, now, minutes: int) -> bool:
    """True when a scheduled wake-up should build. A few minutes of slack
    absorb the scheduler's own delays, so "every 20" does not become 25."""
    if last_published is None:
        return True
    return (now - last_published).total_seconds() >= (minutes - 4) * 60
