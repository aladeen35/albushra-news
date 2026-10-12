"""A small in-process scheduler for the worker container.

Each job runs on its own interval, chosen to stay inside provider quotas, not
on page views. One worker process only: running two would double the calls.
"""
from __future__ import annotations

import logging
import threading
import time

from .config import get_settings
from .db import SessionLocal
from .ingest import ingest_metrics, ingest_news

log = logging.getLogger("observatory.scheduler")


def _loop(name: str, job, minutes: int, stop: threading.Event) -> None:
    while not stop.is_set():
        session = SessionLocal()
        try:
            log.info("%s: %s", name, job(session))
        except Exception:  # keep the loop alive; the failure is in the log
            log.exception("%s failed", name)
            session.rollback()
        finally:
            session.close()
        stop.wait(minutes * 60)


def start(stop: threading.Event | None = None) -> threading.Event:
    settings = get_settings()
    stop = stop or threading.Event()
    for name, job, minutes in (("news", ingest_news, settings.news_interval_minutes),
                               ("metrics", ingest_metrics, settings.metrics_interval_minutes)):
        threading.Thread(target=_loop, args=(name, job, minutes, stop), daemon=True,
                         name=f"ingest-{name}").start()
    return stop


def run_forever() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    stop = start()
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        stop.set()
