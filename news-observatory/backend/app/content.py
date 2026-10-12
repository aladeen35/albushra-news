"""Editorial content kept as JSON files in the repository.

On GitHub Pages there is no server to take admin input, so the admin page
commits its changes to a `content/` folder through GitHub's API, and each
hourly build applies them here. The repository's history is the audit log:
every change is a commit with its author.

Files (all optional; a missing file means "nothing"):

  sites.json      [{url, name, type: rss|wordpress, feed_url?, language,
                    country?, group?, topic?, added_by}]
  articles.json   [{title, url, description?, publisher_name, publisher_country?,
                    language, published_at, event_countries?, topics?,
                    content_type?, image_url?, entered_by}]
  figures.json    [{metric_id, value, period_start, period_end, published_at,
                    source_url, coverage_key, number_type?, producer?,
                    period_label?, entered_by}]
  approvals.json  [{metric_id, period_end, value, decision: approve|reject,
                    reviewer}]
  hidden.json     [{url, by}]
  sources.json    {source_key: {"enabled": bool}}

The same rules as the admin API apply: bad entries are skipped and reported,
never half-applied; a figure is approved only by someone other than the
person who entered it.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import utcnow
from .dedupe import canonical_url
from .ingest import store_article
from .metrics import ObservationRejected, add_observation
from .models import TOPICS, Article, ArticleTag, Metric, MetricObservation, Source
from .providers.base import NormalizedArticle, parse_datetime


def _load(folder: Path, name: str, default):
    path = folder / name
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"{name} is not valid JSON: {exc}") from None


def _day(value) -> date:
    return date.fromisoformat(str(value)[:10])


def apply_sources(session: Session, folder: Path, report: dict) -> None:
    """Sites added by editors, and sources switched on or off."""
    for i, site in enumerate(_load(folder, "sites.json", [])):
        try:
            url = str(site["url"]).strip().rstrip("/")
            if not url.startswith("https://"):
                raise ValueError("url must start with https://")
            kind = site.get("type", "rss")
            if kind not in ("rss", "wordpress"):
                raise ValueError("type must be rss or wordpress")
            host = urlsplit(url).netloc.lower().removeprefix("www.")
            key = re.sub(r"[^a-z0-9]+", "_", host).strip("_")[:60]
            if session.scalar(select(Source).where(Source.key == key)):
                continue
            feed = {"url": site.get("feed_url") or url + "/feed/", "language": site.get("language", "ar"),
                    "site": url}
            if site.get("topic") in TOPICS:
                feed["topic"] = site["topic"]
            session.add(Source(
                key=key, name=str(site.get("name") or host)[:200], url=url,
                kind="rss" if kind == "rss" else "news_api", provider=kind,
                languages=[feed["language"]], regions=[], country=site.get("country") or None,
                terms_url=url, reliability=0.6, allow_description=True, allow_images=False,
                terms_reviewed=True, enabled=True,
                license_note=f"Added by {site.get('added_by', 'an editor')} through the admin page.",
                config={"group": site.get("group", "arab"), "feeds": [feed],
                        **({"feed_url": site["feed_url"]} if site.get("feed_url") else {})}))
            report["sites"] += 1
        except (KeyError, ValueError, TypeError) as exc:
            report["skipped"].append(f"sites.json #{i + 1}: {exc}")
    for key, change in _load(folder, "sources.json", {}).items():
        source = session.scalar(select(Source).where(Source.key == key))
        if source is not None and isinstance(change, dict) and "enabled" in change:
            source.enabled = bool(change["enabled"])
    session.commit()


def apply_articles(session: Session, folder: Path, report: dict) -> None:
    for i, item in enumerate(_load(folder, "articles.json", [])):
        try:
            url = str(item["url"]).strip()
            if not url.startswith(("https://", "http://")):
                raise ValueError("url must be a link to the original story")
            published = parse_datetime(str(item["published_at"]))
            if published is None or published > utcnow():
                raise ValueError("published_at is missing or in the future")
            topics = [t for t in item.get("topics") or [] if t in TOPICS]
            article = store_article(session, NormalizedArticle(
                url=url, title=str(item["title"]).strip()[:400],
                description=(str(item.get("description") or "").strip() or None),
                publisher_name=str(item["publisher_name"]).strip()[:300],
                publisher_country=item.get("publisher_country") or None,
                published_at=published, provider="manual", language=item.get("language", "ar"),
                content_type=item.get("content_type") or "news",
                image_url=item.get("image_url") if str(item.get("image_url") or "").startswith("https://") else None,
                topics=topics), None)
            if article is None:
                continue
            article.entered_by = str(item.get("entered_by") or "editor")[:200]
            countries = item.get("event_countries")
            if countries:
                article.tags = [t for t in article.tags if t.kind != "event_country"]
                session.flush()
                article.tags.extend(ArticleTag(kind="event_country", value=str(c).upper()[:2])
                                    for c in sorted(set(countries)))
                article.classification_edited = True
            report["articles"] += 1
        except (KeyError, ValueError, TypeError) as exc:
            report["skipped"].append(f"articles.json #{i + 1}: {exc}")
    session.commit()


def apply_hidden(session: Session, folder: Path, report: dict) -> None:
    for item in _load(folder, "hidden.json", []):
        canon = canonical_url(str(item.get("url", "")))
        article = session.scalar(select(Article).where(Article.canonical_url == canon))
        if article is not None:
            session.delete(article)
            report["hidden"] += 1
    session.commit()


def apply_figures_and_approvals(session: Session, folder: Path, report: dict) -> None:
    for i, item in enumerate(_load(folder, "figures.json", [])):
        try:
            metric = session.scalar(select(Metric).where(Metric.metric_id == item["metric_id"]))
            if metric is None:
                raise ValueError(f"unknown metric {item['metric_id']}")
            add_observation(session, metric, {
                "value": float(item["value"]), "period_start": _day(item["period_start"]),
                "period_end": _day(item["period_end"]), "published_at": _day(item["published_at"]),
                "source_url": item["source_url"], "coverage_key": item["coverage_key"],
                "number_type": item.get("number_type"), "producer": item.get("producer"),
                "period_label": item.get("period_label")}, entered_by=str(item["entered_by"]),
                auto_approve=False)
            report["figures"] += 1
        except (KeyError, ValueError, TypeError, ObservationRejected) as exc:
            report["skipped"].append(f"figures.json #{i + 1}: {exc}")
    session.commit()
    for i, item in enumerate(_load(folder, "approvals.json", [])):
        try:
            metric = session.scalar(select(Metric).where(Metric.metric_id == item["metric_id"]))
            if metric is None:
                raise ValueError(f"unknown metric {item['metric_id']}")
            obs = session.scalar(select(MetricObservation).where(
                MetricObservation.metric_pk == metric.id,
                MetricObservation.period_end == _day(item["period_end"]),
                MetricObservation.value == float(item["value"]),
                MetricObservation.review_status == "pending"))
            if obs is None:
                continue  # already decided, or the figure is not in this build
            reviewer = str(item["reviewer"]).strip()
            decision = item.get("decision", "approve")
            if decision == "approve" and reviewer.lower() == obs.entered_by.strip().lower():
                raise ValueError("the person who entered a figure cannot approve it")
            obs.review_status = "approved" if decision == "approve" else "rejected"
            obs.reviewed_by = reviewer
            obs.reviewed_at = utcnow()
            report["reviews"] += 1
        except (KeyError, ValueError, TypeError) as exc:
            report["skipped"].append(f"approvals.json #{i + 1}: {exc}")
    session.commit()


def new_report() -> dict:
    return {"sites": 0, "articles": 0, "hidden": 0, "figures": 0, "reviews": 0, "skipped": []}
