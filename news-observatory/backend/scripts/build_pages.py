"""The hourly GitHub Pages build: real data + the editors' content, as a static site.

    CONTENT_DIR=../../content python scripts/build_pages.py <out_dir>

Order matters: editors' sites are added before the news is fetched (so they
are fetched too); their stories after (so a feed's copy of the same link
does not win); approvals after the figures they approve exist.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import content  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.ingest import ingest_metrics, ingest_news  # noqa: E402
from app.seed import seed  # noqa: E402

import export_static  # noqa: E402  (same folder)


def main(out: str) -> int:
    folder = Path(os.environ.get("CONTENT_DIR", "../../content")).resolve()
    report = content.new_report()
    init_db()
    with SessionLocal() as s:
        seed(s)
        content.apply_sources(s, folder, report)
        news = ingest_news(s)
        content.apply_articles(s, folder, report)
        content.apply_hidden(s, folder, report)
        ingest_metrics(s)
        content.apply_figures_and_approvals(s, folder, report)
    data = out + "-data"
    count = export_static.export_data(data)
    with open(os.path.join(data, "content-report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False)
    export_static.build_site(data, out)
    import shutil
    shutil.rmtree(data)
    print(json.dumps({"stories": count, "editor_content": report,
                      "sources": {k: v for k, v in news.items()}}, ensure_ascii=False, indent=1))
    return 0 if count else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "site"))
