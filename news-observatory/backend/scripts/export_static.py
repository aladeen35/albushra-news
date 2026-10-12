"""Export a read-only snapshot of the site for static hosting (GitHub Pages,
a shared preview link, any file server).

Writes the JSON the frontend's static mode reads, then copies the frontend
next to it, so the output folder is a complete site:

    python scripts/export_static.py <out_dir>
    python scripts/export_static.py data <data_dir>          # snapshot only
    python scripts/export_static.py site <data_dir> <out>    # site from a snapshot

The snapshot shows exactly what the live site would show at that moment:
only approved figures, the same sections, search and filters (done in the
browser). Editing needs the real server, so the admin page says so.
"""
from __future__ import annotations

import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.api import public  # noqa: E402
from app.db import SessionLocal, init_db, utcnow  # noqa: E402
from app.main import FRONTEND  # noqa: E402
from app.models import Article, Metric, Scope  # noqa: E402

MAX_ARTICLES = 1500


def _write(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))


def export_data(data: str) -> int:
    """Write the JSON snapshot the static frontend reads. Returns the article count."""
    init_db()
    if os.path.isdir(data):
        shutil.rmtree(data)
    with SessionLocal() as s:
        meta = public.meta(s)
        meta["static"] = {"generated_at": public.iso(utcnow())}
        _write(f"{data}/meta.json", meta)
        for scope in s.scalars(select(Scope).where(Scope.enabled)):
            _write(f"{data}/dashboard-{scope.key}.json", public.dashboard(scope.key, s))
        for m in s.scalars(select(Metric).where(Metric.enabled)):
            _write(f"{data}/metrics/{m.metric_id}.json", public.metric_detail(m.metric_id, s))
        rows = list(s.scalars(select(Article).order_by(Article.published_at.desc()).limit(MAX_ARTICLES)))
        articles = []
        for a in rows:
            item = public.article_json(a)
            item["reliability"] = a.source.reliability if a.source else 0.5
            articles.append(item)
        _write(f"{data}/articles.json", articles)
        _write(f"{data}/sources.json", public.sources(s))
    return len(articles)


def build_site(data: str, out: str) -> None:
    """Frontend + a data folder = a complete static site in `out`."""
    if os.path.isdir(out):
        shutil.rmtree(out)
    shutil.copytree(FRONTEND, out)
    shutil.copytree(data, os.path.join(out, "data"))
    # Mark the copy as static: the frontend then answers /api from data/.
    index = os.path.join(out, "index.html")
    with open(index, encoding="utf-8") as fh:
        html = fh.read()
    html = html.replace('<meta charset="utf-8">',
                        '<meta charset="utf-8">\n  <meta name="albushra-static" content="data/">', 1)
    # Relative asset paths, so the site works under any sub-path (e.g. /repo-name/).
    html = html.replace('href="/', 'href="').replace('src="/', 'src="')
    with open(index, "w", encoding="utf-8") as fh:
        fh.write(html)
    with open(os.path.join(out, ".nojekyll"), "w") as fh:
        fh.write("")


if __name__ == "__main__":
    # export_static.py data <dir>          -> JSON snapshot only
    # export_static.py site <data> <out>   -> build a site from a snapshot
    # export_static.py <out>               -> both, in one go
    args = sys.argv[1:]
    if args[:1] == ["data"]:
        print({"articles": export_data(args[1])})
    elif args[:1] == ["site"]:
        build_site(args[1], args[2])
        print({"site": args[2]})
    else:
        out = args[0] if args else "static-site"
        n = export_data(out + "-data")
        build_site(out + "-data", out)
        shutil.rmtree(out + "-data")
        print({"articles": n, "site": out})
