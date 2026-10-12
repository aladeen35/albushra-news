"""Public read API. Everything the frontend shows comes from here."""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..classify import normalize_ar
from ..config import get_settings
from ..db import as_utc, get_session, utcnow
from ..demo import demo_active
from ..geo import COUNTRIES
from ..metrics import metric_state
from ..models import (CONTENT_TYPES, TOPICS, Article, ArticleTag, FetchLog, Metric,
                      MetricObservation, RegionList, Scope, Source)

router = APIRouter(prefix="/api")

SECTIONS = ("world", "palestine", "sudan", "sports", "arab_world", "islamic_world")

# Published in /api/meta and on the "how we show numbers" page.
RANKING = {"recency": 0.55, "breadth": 0.25, "reliability": 0.20, "half_life_hours": 12}


def iso(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return as_utc(value).isoformat().replace("+00:00", "Z")
    return value.isoformat()


# --- serialisers -----------------------------------------------------------

def observation_json(o: MetricObservation) -> dict:
    return {
        "id": o.id, "version": o.version, "value": o.value,
        "value_low": o.value_low, "value_high": o.value_high,
        "unit": {"ar": o.unit_ar, "en": o.unit_en},
        "area": {"ar": o.area_ar, "en": o.area_en},
        "population": {"ar": o.population_ar, "en": o.population_en},
        "period_start": iso(o.period_start), "period_end": iso(o.period_end),
        "period_label": o.period_label, "published_at": iso(o.published_at),
        "fetched_at": iso(o.fetched_at), "number_type": o.number_type, "producer": o.producer,
        "source_url": o.source_url, "methodology_note": o.methodology_note,
        "coverage_note": o.coverage_note, "coverage_key": o.coverage_key,
        "definition_version": o.definition_version, "review_status": o.review_status,
        "supersedes_id": o.supersedes_id, "correction_note": o.correction_note,
        "is_demo": o.is_demo,
    }


def metric_definition_json(m: Metric) -> dict:
    return {
        "metric_id": m.metric_id, "scope": m.scope_key,
        "name": {"ar": m.name_ar, "en": m.name_en},
        "unit": {"ar": m.unit_ar, "en": m.unit_en},
        "area": {"ar": m.area_ar, "en": m.area_en},
        "population": {"ar": m.population_ar, "en": m.population_en},
        "default_number_type": m.default_number_type,
        "primary_producer": m.primary_producer, "primary_source_url": m.primary_source_url,
        "methodology": {"ar": m.methodology_ar, "en": m.methodology_en},
        "uncertainty": ({"ar": m.uncertainty_ar, "en": m.uncertainty_en}
                        if m.uncertainty_ar or m.uncertainty_en else None),
        "max_age_days": m.max_age_days, "definition_version": m.definition_version,
        "provider": m.provider,
    }


def metric_card_json(m: Metric) -> dict:
    state = metric_state(m)
    card = metric_definition_json(m)
    card.update({
        "status": state.status,
        "age_days": state.age_days,
        # A stale value is withheld from the card; the detail page shows it
        # in its history, dated, as the last known value.
        "current": observation_json(state.current) if state.status == "current" else None,
        "last_known": observation_json(state.current) if state.status == "stale" else None,
        "change": None, "change_unavailable_reason": state.change_reason,
        "alternatives": len(state.alternatives),
    })
    if state.status == "current" and state.previous is not None:
        card["change"] = {"delta": state.current.value - state.previous.value,
                          "previous": observation_json(state.previous)}
    return card


def article_json(a: Article, siblings: int = 0) -> dict:
    return {
        "id": a.id, "title": a.title, "description": a.description, "url": a.url,
        "publisher": {"name": a.publisher_name, "url": a.publisher_url,
                      "country": a.publisher_country},
        "language": a.language, "published_at": iso(a.published_at),
        "fetched_at": iso(a.fetched_at), "content_type": a.content_type,
        "event_countries": a.tag_values("event_country"), "topics": a.tag_values("topic"),
        "source_key": a.source.key if a.source else None,
        "author": a.author, "added_by_editor": bool(a.entered_by),
        "image_url": a.image_url, "cluster_id": a.cluster_id, "other_publishers": siblings,
        "provider": a.provider, "classification_edited": a.classification_edited,
        "is_demo": a.is_demo,
    }


# --- helpers ---------------------------------------------------------------

def region_countries(session: Session, key: str) -> list[str]:
    region = session.scalar(select(RegionList).where(RegionList.key == key))
    return list(region.countries) if region else []


def _has_tag(kind: str, values: list[str]):
    return Article.id.in_(select(ArticleTag.article_id).where(
        ArticleTag.kind == kind, ArticleTag.value.in_(values)))


def _section_filter(session: Session, section: str | None):
    if not section or section == "world":
        return None
    if section == "palestine":
        return _has_tag("event_country", ["PS"])
    if section == "sports":  # a topic page, not a place
        return _has_tag("topic", ["sports"])
    if section in ("arab_world", "islamic_world"):
        return _has_tag("event_country", region_countries(session, section) or ["--"])
    scope = session.scalar(select(Scope).where(Scope.key == section))
    if scope and scope.countries:
        return _has_tag("event_country", list(scope.countries))
    raise HTTPException(404, "unknown section")


def _score(a: Article, breadth: int, now: datetime) -> float:
    hours = max(0.0, (now - as_utc(a.published_at)).total_seconds() / 3600)
    recency = 0.5 ** (hours / RANKING["half_life_hours"])
    reliability = a.source.reliability if a.source else 0.5
    return (RANKING["recency"] * recency + RANKING["breadth"] * min(1.0, (breadth - 1) / 4)
            + RANKING["reliability"] * reliability)


def query_articles(session: Session, *, section=None, q=None, lang=None, country=None,
                   topic=None, source=None, source_keys=None, publisher_country=None,
                   content_type=None,
                   since=None, until=None, sort="relevance", page=1, per_page=20):
    stmt = select(Article)
    conditions = []
    section_cond = _section_filter(session, section)
    if section_cond is not None:
        conditions.append(section_cond)
    if q:
        needle = q.strip()
        variants = {needle, normalize_ar(needle)}
        conditions.append(or_(*[Article.title.ilike(f"%{v}%") for v in variants],
                              *[Article.description.ilike(f"%{v}%") for v in variants]))
    if lang:
        conditions.append(Article.language == lang)
    if country:
        conditions.append(_has_tag("event_country", [country.upper()]))
    if publisher_country:
        conditions.append(Article.publisher_country == publisher_country.upper())
    if topic:  # comma list: any of these topics
        conditions.append(_has_tag("topic", [t for t in topic.split(",") if t]))
    if source:
        conditions.append(Article.publisher_name == source)
    if source_keys:  # a reader's chosen sources
        conditions.append(Article.source_id.in_(
            select(Source.id).where(Source.key.in_([k for k in source_keys.split(",") if k]))))
    if content_type:
        conditions.append(Article.content_type == content_type)
    if since:
        conditions.append(Article.published_at >= since)
    if until:
        conditions.append(Article.published_at <= until)
    if conditions:
        stmt = stmt.where(*conditions)
    # Newest 500 matches, collapsed by cluster, then ranked in Python: the
    # ranking formula is published and simple enough not to need SQL.
    rows = list(session.scalars(stmt.order_by(Article.published_at.desc()).limit(500)))
    clusters: dict[int, list[Article]] = {}
    for a in rows:
        clusters.setdefault(a.cluster_id or a.id, []).append(a)
    now = utcnow()
    leads = []
    for members in clusters.values():
        lead = max(members, key=lambda a: (a.source.reliability if a.source else 0.5,
                                           as_utc(a.published_at)))
        publishers = {m.publisher_name for m in members}
        leads.append((lead, len(publishers) - 1, _score(lead, len(publishers), now)))
    if sort == "newest":
        leads.sort(key=lambda t: as_utc(t[0].published_at), reverse=True)
    else:
        leads.sort(key=lambda t: t[2], reverse=True)
    total = len(leads)
    start = (page - 1) * per_page
    return {"items": [article_json(a, n) for a, n, _ in leads[start:start + per_page]],
            "total": total, "page": page, "pages": max(1, math.ceil(total / per_page)),
            "truncated": len(rows) == 500}


def _last_updated(session: Session):
    last = session.scalar(select(func.max(FetchLog.started_at)).where(FetchLog.status == "ok"))
    last_article = session.scalar(select(func.max(Article.fetched_at)))
    candidates = [as_utc(x) for x in (last, last_article) if x]
    return iso(max(candidates)) if candidates else None


# --- routes ----------------------------------------------------------------

@router.get("/health")
def health(session: Session = Depends(get_session)):
    session.execute(select(1))
    return {"ok": True}


@router.get("/meta")
def meta(session: Session = Depends(get_session)):
    settings = get_settings()
    regions = list(session.scalars(select(RegionList)))
    scopes = list(session.scalars(select(Scope).where(Scope.enabled).order_by(Scope.sort_order)))
    return {
        "scopes": [{"key": s.key, "name": {"ar": s.name_ar, "en": s.name_en},
                    "countries": s.countries} for s in scopes],
        "sections": list(SECTIONS),
        "region_lists": [{"key": r.key, "name": {"ar": r.name_ar, "en": r.name_en},
                          "definition": {"ar": r.definition_ar, "en": r.definition_en},
                          "reference_url": r.reference_url, "countries": r.countries,
                          "updated_at": iso(r.updated_at)} for r in regions],
        "topics": list(TOPICS), "content_types": list(CONTENT_TYPES), "languages": ["ar", "en"],
        "countries": {code: {"en": v[0], "ar": v[1]} for code, v in COUNTRIES.items()},
        "ranking": RANKING,
        "providers": {p: settings.provider_configured(p)
                      for p in ("gnews", "worldnews", "newsapi", "dtm", "acled")},
        "last_updated": _last_updated(session),
        "refresh_minutes": {"news": settings.news_interval_minutes,
                            "metrics": settings.metrics_interval_minutes},
        "demo": demo_active(session),
    }


@router.get("/dashboard")
def dashboard(scope: str = "world", session: Session = Depends(get_session)):
    scopes = {s.key: s for s in session.scalars(select(Scope).where(Scope.enabled))}
    if scope not in scopes:
        raise HTTPException(404, "unknown scope")
    stmt = select(Metric).where(Metric.enabled)
    if scope != "world":  # "world" gathers every crisis's cards, grouped
        stmt = stmt.where(Metric.scope_key == scope)
    metrics = list(session.scalars(stmt.order_by(Metric.display_order)))
    order = {k: s.sort_order for k, s in scopes.items()}
    metrics.sort(key=lambda m: (order.get(m.scope_key, 999), m.display_order))
    return {"scope": scope, "generated_at": iso(utcnow()),
            "last_updated": _last_updated(session),
            "cards": [metric_card_json(m) for m in metrics if m.scope_key in scopes]}


@router.get("/metrics/{metric_id}")
def metric_detail(metric_id: str, session: Session = Depends(get_session)):
    m = session.scalar(select(Metric).where(Metric.metric_id == metric_id, Metric.enabled))
    if not m:
        raise HTTPException(404, "unknown metric")
    state = metric_state(m)
    approved = [o for o in m.observations if o.review_status == "approved"]
    superseded = {o.supersedes_id for o in approved if o.supersedes_id}
    return {
        "card": metric_card_json(m),
        "series": [observation_json(o) for o in state.series],
        "alternatives": [observation_json(o) for o in state.alternatives],
        "history": [dict(observation_json(o), superseded=o.id in superseded)
                    for o in sorted(approved, key=lambda o: o.version, reverse=True)],
    }


def _parse_dt(value: str | None):
    if not value:
        return None
    try:
        return as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        raise HTTPException(422, f"invalid date: {value}") from None


@router.get("/articles")
def articles(section: str | None = None, q: str | None = Query(None, max_length=200),
             lang: str | None = None, country: str | None = None, topic: str | None = None,
             source: str | None = None, sources: str | None = Query(None, max_length=1000),
             publisher_country: str | None = None, content_type: str | None = None, since: str | None = None,
             until: str | None = None, hours: int | None = Query(None, ge=1, le=24 * 90),
             sort: str = "relevance", page: int = Query(1, ge=1, le=100),
             per_page: int = Query(20, ge=1, le=50), session: Session = Depends(get_session)):
    since_dt = _parse_dt(since) or (utcnow() - timedelta(hours=hours) if hours else None)
    return query_articles(session, section=section, q=q, lang=lang, country=country,
                          topic=topic, source=source, source_keys=sources,
                          publisher_country=publisher_country,
                          content_type=content_type, since=since_dt, until=_parse_dt(until),
                          sort=sort, page=page, per_page=per_page)


@router.get("/articles/{article_id}")
def article_detail(article_id: int, session: Session = Depends(get_session)):
    a = session.get(Article, article_id)
    if not a:
        raise HTTPException(404, "unknown article")
    cluster = list(session.scalars(select(Article).where(
        Article.cluster_id == (a.cluster_id or a.id), Article.id != a.id)
        .order_by(Article.published_at.desc()).limit(20)))
    related = []
    countries = a.tag_values("event_country")
    if countries:
        related = list(session.scalars(
            select(Article).where(_has_tag("event_country", countries), Article.id != a.id,
                                  Article.cluster_id != (a.cluster_id or a.id))
            .order_by(Article.published_at.desc()).limit(6)))
    source = a.source
    return {
        "article": article_json(a, len({c.publisher_name for c in cluster} - {a.publisher_name})),
        "same_story": [article_json(c) for c in cluster],
        "related": [article_json(r) for r in related],
        "source": ({"name": source.name, "url": source.url, "license_note": source.license_note,
                    "attribution": source.attribution, "terms_url": source.terms_url}
                   if source else None),
    }


@router.get("/search")
def search(q: str = Query(..., min_length=2, max_length=200), lang: str | None = None,
           session: Session = Depends(get_session)):
    needle = q.strip().lower()
    norm = normalize_ar(needle)
    metrics = [metric_definition_json(m) for m in session.scalars(select(Metric).where(Metric.enabled))
               if needle in m.name_en.lower() or norm in normalize_ar(m.name_ar)]
    sources = [{"key": s.key, "name": s.name, "url": s.url, "kind": s.kind}
               for s in session.scalars(select(Source).where(Source.is_demo.is_(False)))
               if needle in s.name.lower()]
    news = query_articles(session, q=q, lang=lang, content_type="news", per_page=10)
    reports = query_articles(session, q=q, lang=lang, content_type="humanitarian_report",
                             per_page=10)
    return {"q": q, "articles": news, "reports": reports, "metrics": metrics, "sources": sources}


@router.get("/sources")
def sources(session: Session = Depends(get_session)):
    out = []
    for s in session.scalars(select(Source).where(Source.is_demo.is_(False)).order_by(Source.name)):
        feeds = (s.config or {}).get("feeds", [])
        out.append({"key": s.key, "name": s.name, "url": s.url, "kind": s.kind,
                    "languages": s.languages, "country": s.country,
                    "group": (s.config or {}).get("group") or (
                        "humanitarian" if s.kind == "humanitarian" else "international"),
                    "topics": sorted({f["topic"] for f in feeds if f.get("topic")}),
                    "terms_url": s.terms_url, "license_note": s.license_note,
                    "reliability": s.reliability, "enabled": s.enabled})
    return out
