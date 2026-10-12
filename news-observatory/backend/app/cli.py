"""Command line: python -m app.cli <command>

  init              create tables and seed definitions
  ingest-news       run the news job once
  ingest-metrics    run the metrics job once
  worker            run both jobs on their schedules (the worker container)
  demo [--clear]    load (or remove) clearly-labelled fake demo content
"""
from __future__ import annotations

import json
import sys

from .db import SessionLocal, init_db
from .seed import seed


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    command = argv[0]
    init_db()
    with SessionLocal() as session:
        seed(session, update_definitions="--update-definitions" in argv)
        if command == "init":
            print("ok")
        elif command == "ingest-news":
            from .ingest import ingest_news
            print(json.dumps(ingest_news(session), ensure_ascii=False, indent=2))
        elif command == "ingest-metrics":
            from .ingest import ingest_metrics
            print(json.dumps(ingest_metrics(session), ensure_ascii=False, indent=2))
        elif command == "demo":
            from .demo import clear_demo, load_demo
            if "--clear" in argv:
                clear_demo(session)
                print("demo content removed")
            else:
                load_demo(session)
                print("demo content loaded (fake, labelled)")
        elif command == "worker":
            from .scheduler import run_forever
            run_forever()
        else:
            print(f"unknown command: {command}\n{__doc__}")
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
