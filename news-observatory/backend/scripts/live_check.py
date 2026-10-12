"""Live check against the real sources, for a machine with internet access.

Seeds a fresh database, runs the news and indicator jobs once, and prints,
per source: calls, errors, stories fetched, and sample headlines with links.
Writes a Markdown report (for the GitHub Actions summary) and exits non-zero
if no real story arrived at all.

    DATABASE_URL=sqlite:///./data/live.db python scripts/live_check.py report.md
"""
from __future__ import annotations

import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, select  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.ingest import ingest_metrics, ingest_news  # noqa: E402
from app.models import Article, FetchLog, Metric, MetricObservation, Source  # noqa: E402
from app.seed import seed  # noqa: E402


def hapi_probe(session) -> list[str]:
    """What HAPI actually returns for each HAPI-backed metric, to tune its filters."""
    from collections import defaultdict

    from app.config import get_settings
    from app.providers.base import HttpClient, ProviderError
    from app.providers.hdx import HAPI_BASE
    out = []
    ident = get_settings().hdx_identifier
    if not ident:
        return ["HDX identifier not set."]
    http = HttpClient(retries=1)
    for m in session.scalars(select(Metric)):
        cfg = m.provider_config or {}
        cfg = cfg.get("hapi") or (cfg if m.provider == "hapi" else None)
        if not cfg:
            continue
        params = {"output_format": "json", "limit": 2000, "app_identifier": ident,
                  **(cfg.get("params") or {})}
        try:
            body, _, _ = http.get_json(f"{HAPI_BASE}/{cfg['endpoint']}", params=params)
        except ProviderError as exc:
            out.append(f"- **{m.metric_id}**: {exc}")
            continue
        rows = body.get("data", []) if isinstance(body, dict) else []
        values = defaultdict(set)
        for r in rows:
            for k, v in r.items():
                if isinstance(v, (str, int)) and len(values[k]) < 12 and len(str(v)) < 60:
                    values[k].add(str(v))
        out.append(f"- **{m.metric_id}** ({cfg['endpoint']} {cfg.get('params')}): {len(rows)} rows")
        ends = sorted({r.get("reference_period_end") for r in rows if r.get("reference_period_end")})
        if ends:
            latest = [r for r in rows if r.get("reference_period_end") == ends[-1]]
            groups = defaultdict(lambda: [0, 0.0])
            for r in latest:
                key = " / ".join(str(r.get(k, "")) for k in ("admin_level", "operation", "sector_name",
                                                             "population_status", "category")
                                 if k in r)
                groups[key][0] += 1
                groups[key][1] += float(r.get(cfg.get("value_field", "population")) or 0)
            out.append(f"  - latest period {ends[-1]}: " + "; ".join(
                f"[{k}] {n} rows = {v:,.0f}" for k, (n, v) in sorted(groups.items())[:25]))
        for k in sorted(values):
            if k in ("sector_name", "sector_code", "population_status", "category", "admin_level",
                     "reference_period_start", "reference_period_end", "operation", "reporting_round",
                     "assessment_type", "population_group", "gender", "age_range", "location_code"):
                out.append(f"  - `{k}`: {', '.join(sorted(values[k]))}")
    return out


def main(report_path: str) -> int:
    init_db()
    lines = ["# البشرى للأخبار — فحص البيانات الحقيقية", ""]
    with SessionLocal() as s:
        seed(s)
        news = ingest_news(s)
        metrics = ingest_metrics(s)
        total = s.scalar(select(func.count(Article.id))) or 0
        lines += [f"**مجموع الأخبار المجلوبة: {total}**", "",
                  "| المصدر | الطلبات | أخطاء | عناصر مستلمة | أخبار جديدة | آخر خطأ |", "|---|---|---|---|---|---|"]
        for src in s.scalars(select(Source).order_by(Source.key)):
            logs = list(s.scalars(select(FetchLog).where(FetchLog.target == src.key)))
            if not logs:
                continue
            statuses = Counter(l.status for l in logs)
            errors = sum(v for k, v in statuses.items() if k not in ("ok",))
            new = sum(l.new_items for l in logs)
            received = sum(l.items for l in logs)
            last_error = next((l.error for l in reversed(logs) if l.error), "") or ""
            lines.append(f"| {src.name} | {len(logs)} | {errors} | {received} | {new} | "
                         f"{last_error[:160].replace('|', '/')} |")
        lines += ["", "## عينات من الأخبار الحقيقية", ""]
        for src in s.scalars(select(Source).order_by(Source.key)):
            sample = list(s.scalars(select(Article).where(Article.source_id == src.id)
                                    .order_by(Article.published_at.desc()).limit(3)))
            if sample:
                lines.append(f"**{src.name}**")
                for a in sample:
                    lines.append(f"- [{a.title}]({a.url}) — {a.published_at:%Y-%m-%d %H:%M} UTC · "
                                 f"{', '.join(a.tag_values('event_country')) or '—'}")
                lines.append("")
        lines += ["## المؤشرات", "", "| المؤشر | النتيجة | التفاصيل |", "|---|---|---|"]
        for m in s.scalars(select(Metric).order_by(Metric.metric_id)):
            obs = s.scalar(select(MetricObservation).where(MetricObservation.metric_pk == m.id)
                           .order_by(MetricObservation.id.desc()).limit(1))
            log = s.scalar(select(FetchLog).where(FetchLog.target == m.metric_id).order_by(FetchLog.id.desc()).limit(1))
            result = metrics.get(m.metric_id, m.provider)
            detail = (f"{obs.value:,.0f} {obs.unit_en} · {obs.period_end} · {obs.producer} (بانتظار المراجعة)"
                      if obs else (log.error[:100] if log and log.error else "يُدخل يدويًا"))
            lines.append(f"| {m.metric_id} | {result} | {detail.replace('|', '/')} |")
        lines += ["", "## فحص حقول HDX HAPI", ""] + hapi_probe(s)
    report = "\n".join(lines) + "\n"
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(report)
    print("news summary:", news)
    return 0 if total > 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "live-report.md"))
