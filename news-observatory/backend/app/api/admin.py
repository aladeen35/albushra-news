"""Admin API: sources, region lists, scopes, metric definitions, number entry,
review of sensitive numbers, classification corrections and monitoring.

Editors sign in with a username and password (see auth.py); scripts may use
ADMIN_TOKEN. With neither configured, the admin API is off rather than open.
"""
from __future__ import annotations

import hmac
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import check_credentials, issue, locked_out, login_enabled, verify
from ..config import get_settings
from ..db import as_utc, get_session, utcnow
from ..geo import COUNTRIES
from ..ingest import ingest_metrics, ingest_news
from ..metrics import ObservationRejected, add_observation, metric_state
from ..models import (NUMBER_TYPES, TOPICS, Article, ArticleTag, FetchLog, Metric,
                      MetricObservation, RegionList, Scope, Source)
from .public import iso, metric_definition_json, observation_json


def require_admin(authorization: str = Header(default="")) -> str:
    settings = get_settings()
    if not (settings.admin_token or login_enabled()):
        raise HTTPException(503, "admin disabled: set ADMIN_PASSWORD (or ADMIN_TOKEN)")
    supplied = authorization.removeprefix("Bearer ").strip()
    if not supplied:
        raise HTTPException(401, "sign in required")
    if settings.admin_token and hmac.compare_digest(supplied.encode(), settings.admin_token.encode()):
        return "token"
    user = verify(supplied)
    if user is None:
        raise HTTPException(401, "session expired or invalid; sign in again")
    return user


class LoginIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=200)


# Sign-in sits outside the protected router.
auth_router = APIRouter(prefix="/api/auth")


@auth_router.post("/login")
def login(body: LoginIn, request: Request):
    if not login_enabled():
        raise HTTPException(503, "sign-in disabled: ADMIN_PASSWORD is not set on the server")
    ip = request.client.host if request.client else "unknown"
    if locked_out(ip):
        raise HTTPException(429, "too many failed attempts; try again in 15 minutes")
    if not check_credentials(ip, body.username, body.password):
        raise HTTPException(401, "wrong username or password")
    token, expires = issue(body.username.strip())
    return {"token": token, "expires_at": expires, "username": body.username.strip()}


@auth_router.get("/status")
def auth_status():
    return {"login_enabled": login_enabled()}


router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])


@router.get("/me")
def me(user: str = Depends(require_admin)):
    return {"username": user}


# --- monitoring --------------------------------------------------------------

@router.get("/status")
def status(session: Session = Depends(get_session)):
    settings = get_settings()
    since = utcnow() - timedelta(hours=24)
    sources = []
    for s in session.scalars(select(Source).order_by(Source.key)):
        logs = list(session.scalars(select(FetchLog).where(
            FetchLog.target == s.key, FetchLog.started_at >= since)))
        latencies = [l.latency_ms for l in logs if l.latency_ms is not None]
        sources.append({
            "key": s.key, "name": s.name, "provider": s.provider, "enabled": s.enabled,
            "terms_reviewed": s.terms_reviewed, "configured": settings.provider_configured(s.provider),
            "last_success_at": iso(s.last_success_at), "last_failure_at": iso(s.last_failure_at),
            "last_error": s.last_error, "calls_24h": len(logs),
            "errors_24h": sum(1 for l in logs if l.status not in ("ok", "skipped")),
            "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else None,
            "quota_remaining": next((l.quota_remaining for l in sorted(
                logs, key=lambda l: l.id, reverse=True) if l.quota_remaining), None),
            "daily_request_limit": s.daily_request_limit, "is_demo": s.is_demo,
        })
    metrics = []
    for m in session.scalars(select(Metric).order_by(Metric.scope_key, Metric.display_order)):
        st = metric_state(m)
        last_log = session.scalar(select(FetchLog).where(FetchLog.target == m.metric_id)
                                  .order_by(FetchLog.id.desc()).limit(1))
        metrics.append({
            "metric_id": m.metric_id, "scope": m.scope_key, "name": {"ar": m.name_ar, "en": m.name_en},
            "provider": m.provider, "configured": settings.provider_configured(m.provider),
            "status": st.status, "age_days": st.age_days, "max_age_days": m.max_age_days,
            "last_fetch": ({"status": last_log.status, "at": iso(last_log.started_at),
                            "error": last_log.error} if last_log else None),
        })
    pending = session.scalar(select(func.count(MetricObservation.id))
                             .where(MetricObservation.review_status == "pending")) or 0
    recent = list(session.scalars(select(FetchLog).order_by(FetchLog.id.desc()).limit(40)))
    return {
        "sources": sources, "metrics": metrics, "pending_reviews": pending,
        "stale_alerts": [m for m in metrics if m["status"] in ("stale", "no_data") and m["provider"]],
        "articles_total": session.scalar(select(func.count(Article.id))) or 0,
        "articles_24h": session.scalar(select(func.count(Article.id)).where(
            Article.fetched_at >= since)) or 0,
        "recent_calls": [{"target": l.target, "provider": l.provider, "status": l.status,
                          "at": iso(l.started_at), "items": l.items, "new": l.new_items,
                          "latency_ms": l.latency_ms, "error": l.error} for l in recent],
    }


@router.post("/jobs/{job}")
def run_job(job: str, session: Session = Depends(get_session)):
    if job == "ingest-news":
        return ingest_news(session)
    if job == "ingest-metrics":
        return ingest_metrics(session)
    raise HTTPException(404, "unknown job")


# --- sources -----------------------------------------------------------------

class SourceIn(BaseModel):
    key: str | None = Field(None, pattern=r"^[a-z0-9_\-]{2,64}$")
    name: str | None = None
    url: str | None = None
    kind: str | None = Field(None, pattern=r"^(news_api|rss|humanitarian|data)$")
    provider: str | None = Field(None, pattern=r"^(gnews|worldnews|newsapi|rss|wordpress|gdelt|reliefweb|manual)$")
    languages: list[str] | None = None
    country: str | None = Field(None, pattern=r"^[A-Z]{2}$")
    terms_url: str | None = None
    license_note: str | None = None
    attribution: str | None = None
    allow_description: bool | None = None
    allow_images: bool | None = None
    allow_full_text: bool | None = None
    reliability: float | None = Field(None, ge=0, le=1)
    enabled: bool | None = None
    terms_reviewed: bool | None = None
    daily_request_limit: int | None = Field(None, ge=1)
    config: dict | None = None


def _source_json(s: Source) -> dict:
    return {c: getattr(s, c) for c in (
        "id", "key", "name", "url", "kind", "provider", "languages", "country", "terms_url",
        "license_note", "attribution", "allow_description", "allow_images", "allow_full_text",
        "reliability", "enabled", "terms_reviewed", "daily_request_limit", "config", "is_demo")}


@router.get("/sources")
def list_sources(session: Session = Depends(get_session)):
    return [_source_json(s) for s in session.scalars(select(Source).order_by(Source.key))]


def _apply_source(s: Source, body: SourceIn) -> None:
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(s, k, v)
    # Switching a source on needs a terms review. Seeded feeds that are already
    # on stay editable; the status page flags their pending review.
    if data.get("enabled") and not s.terms_reviewed:
        raise HTTPException(422, "review the source's terms (terms_reviewed=true) before enabling it")


@router.post("/sources", status_code=201)
def create_source(body: SourceIn, session: Session = Depends(get_session)):
    for f in ("key", "name", "url", "kind", "provider"):
        if not getattr(body, f):
            raise HTTPException(422, f"{f} is required")
    if session.scalar(select(Source).where(Source.key == body.key)):
        raise HTTPException(409, "source key exists")
    s = Source(languages=[], regions=[], config={})
    _apply_source(s, body)
    session.add(s)
    session.commit()
    return _source_json(s)


@router.patch("/sources/{key}")
def update_source(key: str, body: SourceIn, session: Session = Depends(get_session)):
    s = session.scalar(select(Source).where(Source.key == key))
    if not s:
        raise HTTPException(404, "unknown source")
    _apply_source(s, body)
    session.commit()
    return _source_json(s)


# --- region lists and scopes ----------------------------------------------

class RegionIn(BaseModel):
    countries: list[str]
    definition_ar: str | None = None
    definition_en: str | None = None
    reference_url: str | None = None


def _check_codes(codes: list[str]) -> list[str]:
    codes = sorted({c.strip().upper() for c in codes if c.strip()})
    bad = [c for c in codes if len(c) != 2 or not c.isalpha()]
    if bad:
        raise HTTPException(422, f"not ISO 3166-1 alpha-2 codes: {', '.join(bad)}")
    return codes


@router.put("/region-lists/{key}")
def update_region(key: str, body: RegionIn, session: Session = Depends(get_session)):
    r = session.scalar(select(RegionList).where(RegionList.key == key))
    if not r:
        raise HTTPException(404, "unknown region list")
    r.countries = _check_codes(body.countries)
    for f in ("definition_ar", "definition_en", "reference_url"):
        if getattr(body, f) is not None:
            setattr(r, f, getattr(body, f))
    session.commit()
    unknown = [c for c in r.countries if c not in COUNTRIES]
    return {"key": r.key, "countries": r.countries, "not_in_gazetteer": unknown}


class ScopeIn(BaseModel):
    key: str | None = Field(None, pattern=r"^[a-z0-9_\-]{2,64}$")
    name_ar: str | None = None
    name_en: str | None = None
    countries: list[str] | None = None
    queries: dict[str, list[str]] | None = None
    sort_order: int | None = None
    enabled: bool | None = None


def _scope_json(s: Scope) -> dict:
    return {c: getattr(s, c) for c in ("key", "name_ar", "name_en", "countries", "queries",
                                       "sort_order", "enabled")}


@router.get("/scopes")
def list_scopes(session: Session = Depends(get_session)):
    return [_scope_json(s) for s in session.scalars(select(Scope).order_by(Scope.sort_order))]


@router.post("/scopes", status_code=201)
def create_scope(body: ScopeIn, session: Session = Depends(get_session)):
    if not (body.key and body.name_ar and body.name_en):
        raise HTTPException(422, "key, name_ar and name_en are required")
    if session.scalar(select(Scope).where(Scope.key == body.key)):
        raise HTTPException(409, "scope key exists")
    s = Scope(key=body.key, name_ar=body.name_ar, name_en=body.name_en,
              countries=_check_codes(body.countries or []), queries=body.queries or {},
              sort_order=body.sort_order or 100, enabled=body.enabled is not False)
    session.add(s)
    session.commit()
    return _scope_json(s)


@router.patch("/scopes/{key}")
def update_scope(key: str, body: ScopeIn, session: Session = Depends(get_session)):
    s = session.scalar(select(Scope).where(Scope.key == key))
    if not s:
        raise HTTPException(404, "unknown scope")
    data = body.model_dump(exclude_unset=True, exclude={"key"})
    if "countries" in data:
        data["countries"] = _check_codes(data["countries"] or [])
    for k, v in data.items():
        setattr(s, k, v)
    session.commit()
    return _scope_json(s)


# --- metric definitions ------------------------------------------------------

class MetricIn(BaseModel):
    metric_id: str | None = Field(None, pattern=r"^[a-z0-9_]{2,64}$")
    scope_key: str | None = None
    name_ar: str | None = None
    name_en: str | None = None
    unit_ar: str | None = None
    unit_en: str | None = None
    area_ar: str | None = None
    area_en: str | None = None
    population_ar: str | None = None
    population_en: str | None = None
    default_number_type: str | None = None
    primary_producer: str | None = None
    primary_source_url: str | None = None
    methodology_ar: str | None = None
    methodology_en: str | None = None
    uncertainty_ar: str | None = None
    uncertainty_en: str | None = None
    max_age_days: int | None = Field(None, ge=1, le=3650)
    requires_review: bool | None = None
    provider: str | None = Field(None, pattern=r"^(dtm|acled|hapi|manual)$")
    provider_config: dict | None = None
    display_order: int | None = None
    enabled: bool | None = None
    # Set when the meaning of the number changes (new definition, coverage):
    # bumps definition_version so old and new values are never compared.
    definition_changed: bool = False


REQUIRED_METRIC = ("metric_id", "scope_key", "name_ar", "name_en", "unit_ar", "unit_en", "area_ar",
                   "area_en", "population_ar", "population_en", "default_number_type",
                   "primary_producer", "primary_source_url", "methodology_ar", "methodology_en")


@router.get("/metrics")
def list_metrics(session: Session = Depends(get_session)):
    out = []
    for m in session.scalars(select(Metric).order_by(Metric.scope_key, Metric.display_order)):
        d = metric_definition_json(m)
        d.update(requires_review=m.requires_review, enabled=m.enabled,
                 provider_config=m.provider_config, display_order=m.display_order)
        out.append(d)
    return out


def _check_metric(m: Metric, session: Session) -> None:
    if m.default_number_type not in NUMBER_TYPES:
        raise HTTPException(422, f"default_number_type must be one of {', '.join(NUMBER_TYPES)}")
    if not session.scalar(select(Scope.id).where(Scope.key == m.scope_key)):
        raise HTTPException(422, "unknown scope_key")
    if not str(m.primary_source_url).startswith(("https://", "http://")):
        raise HTTPException(422, "primary_source_url must be an http(s) link")


@router.post("/metrics", status_code=201)
def create_metric(body: MetricIn, session: Session = Depends(get_session)):
    data = body.model_dump(exclude_unset=True, exclude={"definition_changed"})
    missing = [f for f in REQUIRED_METRIC if not data.get(f)]
    if missing:
        raise HTTPException(422, f"missing: {', '.join(missing)}")
    if session.scalar(select(Metric).where(Metric.metric_id == data["metric_id"])):
        raise HTTPException(409, "metric_id exists")
    m = Metric(**data)
    _check_metric(m, session)
    session.add(m)
    session.commit()
    return metric_definition_json(m)


@router.patch("/metrics/{metric_id}")
def update_metric(metric_id: str, body: MetricIn, session: Session = Depends(get_session)):
    m = session.scalar(select(Metric).where(Metric.metric_id == metric_id))
    if not m:
        raise HTTPException(404, "unknown metric")
    for k, v in body.model_dump(exclude_unset=True, exclude={"metric_id", "definition_changed"}).items():
        setattr(m, k, v)
    if body.definition_changed:
        m.definition_version += 1
    _check_metric(m, session)
    session.commit()
    return metric_definition_json(m)


# --- observations: entry, review, correction ---------------------------------

class ObservationIn(BaseModel):
    value: float
    value_low: float | None = None
    value_high: float | None = None
    period_start: date
    period_end: date
    published_at: date
    period_label: str | None = None
    number_type: str | None = None
    producer: str | None = None
    source_url: str
    coverage_key: str
    coverage_note: str | None = None
    methodology_note: str | None = None
    unit_ar: str | None = None
    unit_en: str | None = None
    area_ar: str | None = None
    area_en: str | None = None
    population_ar: str | None = None
    population_en: str | None = None
    entered_by: str = Field(..., min_length=2, max_length=200)
    correction_note: str | None = None


def _metric(session: Session, metric_id: str) -> Metric:
    m = session.scalar(select(Metric).where(Metric.metric_id == metric_id))
    if not m:
        raise HTTPException(404, "unknown metric")
    return m


@router.post("/metrics/{metric_id}/observations", status_code=201)
def create_observation(metric_id: str, body: ObservationIn, session: Session = Depends(get_session)):
    m = _metric(session, metric_id)
    data = body.model_dump(exclude={"entered_by", "correction_note"})
    try:
        # Editor entries still go through review when the metric requires it:
        # a second person approves sensitive numbers.
        obs = add_observation(session, m, data, entered_by=body.entered_by)
    except ObservationRejected as exc:
        raise HTTPException(422, str(exc)) from None
    session.commit()
    return observation_json(obs)


@router.post("/observations/{obs_id}/correct", status_code=201)
def correct_observation(obs_id: int, body: ObservationIn, session: Session = Depends(get_session)):
    old = session.get(MetricObservation, obs_id)
    if not old:
        raise HTTPException(404, "unknown observation")
    if not body.correction_note:
        raise HTTPException(422, "a correction needs a correction_note saying what changed and why")
    data = body.model_dump(exclude={"entered_by", "correction_note"})
    try:
        obs = add_observation(session, old.metric, data, entered_by=body.entered_by,
                              supersedes=old, correction_note=body.correction_note)
    except ObservationRejected as exc:
        raise HTTPException(422, str(exc)) from None
    session.commit()
    return observation_json(obs)


class ReviewIn(BaseModel):
    decision: str = Field(..., pattern=r"^(approve|reject)$")
    reviewer: str = Field(..., min_length=2, max_length=200)
    note: str | None = None


@router.get("/reviews")
def pending_reviews(session: Session = Depends(get_session)):
    rows = session.scalars(select(MetricObservation).where(
        MetricObservation.review_status == "pending").order_by(MetricObservation.id))
    return [dict(observation_json(o), metric=metric_definition_json(o.metric),
                 entered_by=o.entered_by) for o in rows]


@router.post("/observations/{obs_id}/review")
def review_observation(obs_id: int, body: ReviewIn, session: Session = Depends(get_session)):
    o = session.get(MetricObservation, obs_id)
    if not o:
        raise HTTPException(404, "unknown observation")
    if o.review_status != "pending":
        raise HTTPException(409, f"observation is already {o.review_status}")
    if body.decision == "approve" and body.reviewer.strip().lower() == o.entered_by.strip().lower():
        raise HTTPException(422, "the person who entered a number cannot approve it")
    o.review_status = "approved" if body.decision == "approve" else "rejected"
    o.reviewed_by = body.reviewer
    o.reviewed_at = utcnow()
    o.review_note = body.note
    session.commit()
    return observation_json(o)


# --- article classification -----------------------------------------------

class ClassificationIn(BaseModel):
    event_countries: list[str] | None = None
    topics: list[str] | None = None
    content_type: str | None = Field(None, pattern=r"^(news|humanitarian_report|data_update)$")


@router.patch("/articles/{article_id}/classification")
def correct_classification(article_id: int, body: ClassificationIn,
                           session: Session = Depends(get_session)):
    a = session.get(Article, article_id)
    if not a:
        raise HTTPException(404, "unknown article")
    replace: dict[str, list[str]] = {}
    if body.event_countries is not None:
        replace["event_country"] = _check_codes(body.event_countries)
    if body.topics is not None:
        bad = [t for t in body.topics if t not in TOPICS]
        if bad:
            raise HTTPException(422, f"unknown topics: {', '.join(bad)}")
        replace["topic"] = sorted(set(body.topics))
    if replace:
        # Delete first and flush, so re-adding an unchanged tag cannot collide
        # with the unique constraint inside one flush.
        a.tags = [t for t in a.tags if t.kind not in replace]
        session.flush()
        for kind, values in replace.items():
            a.tags.extend(ArticleTag(kind=kind, value=v) for v in values)
    if body.content_type:
        a.content_type = body.content_type
    a.classification_edited = True
    session.commit()
    return {"id": a.id, "event_countries": a.tag_values("event_country"),
            "topics": a.tag_values("topic"), "content_type": a.content_type,
            "published_at": iso(as_utc(a.published_at))}


# --- filling the add-story form from the story's own page ----------------------

class PreviewIn(BaseModel):
    url: str = Field(..., min_length=10, max_length=1000)


@router.post("/articles/preview")
def preview_article(body: PreviewIn):
    """Title, summary, picture and date from the page, for the editor to review."""
    from ..providers.base import ProviderError
    from ..providers.pagemeta import fetch_page_meta
    try:
        return fetch_page_meta(body.url.strip())
    except ProviderError as exc:
        raise HTTPException(422, f"could not read the page: {exc}") from None


# --- adding a site by its address (WordPress or any site with a feed) -------

class SiteIn(BaseModel):
    url: str = Field(..., min_length=8, max_length=500)


def _normalise_site(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if not url.startswith("https://"):
        url = "https://" + url.split("://", 1)[1]
    return url.rstrip("/")


def _sample(items) -> list[dict]:
    return [{"title": i.title, "url": i.url, "published_at": iso(i.published_at),
             "image_url": i.image_url, "author": i.author}
            for i in sorted(items, key=lambda i: i.published_at, reverse=True)[:5]]


@router.post("/sites/inspect")
def inspect_site(body: SiteIn):
    """Work out how to read a site, and show its latest posts before saving."""
    from ..classify import detect_language
    from ..providers.base import HttpClient, ProviderError
    from ..providers.news import RssAdapter, discover_feeds
    from ..providers.wordpress import WordPressAdapter, probe

    url = _normalise_site(body.url)
    http = HttpClient(retries=0)
    tried = []
    try:
        info = probe(http, url)
        result = WordPressAdapter(http).posts(info["url"].rstrip("/"), info["name"] or url, per_page=5)
        if result.items:
            return {"type": "wordpress", "url": info["url"].rstrip("/"), "name": info["name"],
                    "description": info["description"],
                    "language": detect_language(" ".join(i.title for i in result.items)),
                    "sample": _sample(result.items)}
        tried.append("WordPress API: no posts")
    except ProviderError as exc:
        tried.append(f"WordPress API: {exc}")
    candidates = [url]
    try:
        candidates += discover_feeds(http, url)
    except ProviderError as exc:
        tried.append(f"site page: {exc}")
    candidates.append(url + "/feed/")
    for feed_url in dict.fromkeys(candidates):
        try:
            result = RssAdapter(http).fetch(feed_url, url)
        except ProviderError as exc:
            tried.append(f"{feed_url}: {exc}")
            continue
        if result.items:
            return {"type": "rss", "url": url, "feed_url": feed_url, "name": None, "description": None,
                    "language": detect_language(" ".join(i.title for i in result.items)),
                    "sample": _sample(result.items)}
    raise HTTPException(422, "no WordPress API or news feed found at this address. Tried: "
                        + " | ".join(tried[-4:]))


class SiteCreate(BaseModel):
    url: str = Field(..., min_length=8, max_length=500)
    type: str = Field(..., pattern=r"^(wordpress|rss)$")
    feed_url: str | None = None
    name: str = Field(..., min_length=2, max_length=200)
    language: str = Field("ar", pattern=r"^(ar|en)$")
    country: str | None = Field(None, pattern=r"^[A-Z]{2}$")
    group: str = Field("arab", pattern=r"^(saudi|arab|sudan|sports|international|humanitarian)$")
    topic: str | None = None
    terms_reviewed: bool = False
    allow_images: bool = True


@router.post("/sites", status_code=201)
def create_site(body: SiteCreate, session: Session = Depends(get_session)):
    import re
    from urllib.parse import urlsplit
    url = _normalise_site(body.url)
    if body.topic and body.topic not in TOPICS:
        raise HTTPException(422, "unknown topic")
    host = urlsplit(url).netloc.lower().removeprefix("www.")
    key = re.sub(r"[^a-z0-9]+", "_", host).strip("_")[:60]
    if session.scalar(select(Source).where(Source.key == key)):
        raise HTTPException(409, f"this site is already a source ({key})")
    feed = {"url": body.feed_url or url + "/feed/", "language": body.language, "site": url}
    if body.topic:
        feed["topic"] = body.topic
    s = Source(key=key, name=body.name, url=url, kind="rss" if body.type == "rss" else "news_api",
               provider=body.type, languages=[body.language], regions=[], country=body.country,
               terms_url=url, reliability=0.6, allow_description=True, allow_images=body.allow_images,
               terms_reviewed=body.terms_reviewed, enabled=body.terms_reviewed,
               license_note="Added by an editor from the site's address.",
               config={"group": body.group, "feeds": [feed],
                       **({"feed_url": body.feed_url} if body.feed_url else {})})
    session.add(s)
    session.commit()
    first = ingest_news(session, only=key) if s.enabled else {}
    return {**_source_json(s), "first_fetch": first.get(key)}


# --- adding a story by hand --------------------------------------------------

class ArticleIn(BaseModel):
    title: str = Field(..., min_length=5, max_length=400)
    url: str = Field(..., min_length=10, max_length=1000)
    description: str | None = Field(None, max_length=1000)
    publisher_name: str = Field(..., min_length=2, max_length=300)
    publisher_country: str | None = Field(None, pattern=r"^[A-Z]{2}$")
    language: str = Field(..., pattern=r"^(ar|en)$")
    published_at: datetime
    event_countries: list[str] | None = None
    topics: list[str] | None = None
    content_type: str = Field("news", pattern=r"^(news|humanitarian_report|data_update)$")
    image_url: str | None = None
    entered_by: str = Field(..., min_length=2, max_length=200)


@router.post("/articles", status_code=201)
def create_article(body: ArticleIn, session: Session = Depends(get_session)):
    from ..ingest import store_article
    from ..providers.base import NormalizedArticle
    if not body.url.startswith(("https://", "http://")):
        raise HTTPException(422, "url must be a link to the original story")
    if body.image_url and not body.image_url.startswith("https://"):
        raise HTTPException(422, "image_url must be an https link")
    published = as_utc(body.published_at)
    if published > utcnow() + timedelta(minutes=10):
        raise HTTPException(422, "published_at is in the future")
    article = store_article(session, NormalizedArticle(
        url=body.url, title=body.title.strip(), description=(body.description or "").strip() or None,
        publisher_name=body.publisher_name.strip(), publisher_country=body.publisher_country,
        published_at=published, provider="manual", language=body.language,
        content_type=body.content_type, image_url=body.image_url, topics=body.topics or []), None)
    if article is None:
        raise HTTPException(409, "a story with this link is already stored")
    article.entered_by = body.entered_by.strip()
    if body.event_countries is not None or body.topics is not None:
        correct_classification(article.id, ClassificationIn(
            event_countries=body.event_countries, topics=body.topics), session)
    session.commit()
    return {"id": article.id, "event_countries": article.tag_values("event_country"),
            "topics": article.tag_values("topic")}


@router.get("/articles")
def recent_manual_articles(session: Session = Depends(get_session)):
    rows = session.scalars(select(Article).where(Article.entered_by.is_not(None))
                           .order_by(Article.id.desc()).limit(30))
    return [{"id": a.id, "title": a.title, "url": a.url, "publisher": a.publisher_name,
             "entered_by": a.entered_by, "published_at": iso(a.published_at)} for a in rows]


@router.delete("/articles/{article_id}", status_code=204)
def delete_article(article_id: int, session: Session = Depends(get_session)):
    a = session.get(Article, article_id)
    if not a:
        raise HTTPException(404, "unknown article")
    session.delete(a)
    session.commit()


# --- finding a dataset on HDX (catalogue search, for editors) -------------

@router.get("/hdx/search")
def hdx_search(q: str = Query(..., min_length=2, max_length=200), country: str | None = Query(
        None, pattern=r"^[A-Za-z]{3}$")):
    from ..providers.base import HttpClient, ProviderError
    from ..providers.hdx import ckan_search
    try:
        return ckan_search(HttpClient(retries=0), q, country)
    except ProviderError as exc:
        raise HTTPException(502, f"HDX catalogue unavailable: {exc}") from None
