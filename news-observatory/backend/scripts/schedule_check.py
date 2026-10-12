"""Should this scheduled wake-up build the site? Prints build=true|false.

    LAST_PUBLISHED=<ISO time of the last gh-pages commit, or empty>
    OTHER_RUNS=<number of other builds in progress>
    CONTENT_DIR=../../content python scripts/schedule_check.py >> "$GITHUB_OUTPUT"
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.schedule import build_due, fetch_minutes  # noqa: E402


def main() -> None:
    minutes = fetch_minutes(Path(os.environ.get("CONTENT_DIR", "../../content")))
    raw = os.environ.get("LAST_PUBLISHED", "").strip()
    last = datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else None
    busy = int(os.environ.get("OTHER_RUNS", "0") or 0) > 0
    due = not busy and build_due(last, datetime.now(timezone.utc), minutes)
    print(f"build={'true' if due else 'false'}")
    print(f"fetch_minutes={minutes}")
    print(f"every {minutes} min · last publish {raw or 'never'} · other builds running: {busy} · build: {due}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
