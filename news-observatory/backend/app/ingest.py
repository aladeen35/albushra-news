"""Ingestion jobs: pull news and metric readings, store them, log every call.

Runs from the worker (scheduler.py) or the CLI, never on page load.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .classify import detect_countries, detect_language, detect_topics
from .config import get_settings
from .db import as_utc, utcnow
from .dedupe import canonical_url, title_fingerprint
from .metrics import ObservationRejected, add_observation
from .models import Article, ArticleTag, FetchLog, Metric, MetricObservation, Scope, Source
from .providers.base import FetchResult, NormalizedArticle, ProviderError
from .providers.humanitarian import AcledAdapter, DtmAdapter
from .providers.gdelt import GdeltAdapter
from .providers.hdx import HapiAdapter
from .providers.reliefweb import ReliefWebAdapter
from .providers.wordpress import WordPressAdapter
from .providers.news import (GNewsAdapter, NewsApiAdapter, RssAdapter, WorldNewsAdapter,
                             discover_feeds)

log = logging.getLogger("observatory.ingest")

CLUSTER_WINDOW = timedelta(hours=48)


def store_article(session: Session, item: NormalizedArticle, source: Source | None) -> Article | None:
    """Insert one article; return None if its URL is already stored."""
    canon = canonical_url(item.url)
    existing = session.scalar(select(Article).where(Article.canonical_url == canon))
    if existing is not None:
        # The same story from a humanitarian feed marks it as a humanitarian
        # update, whichever feed stored it first.
        if item.content_type == "humanitarian_report" and existing.content_type == "news" \
                and not existing.classification_edited:
            existing.content_type = "humanitarian_report"
        return None
    text = f"{item.title} {item.description or ''}"
    fingerprint = title_fingerprint(item.title)
    allow_desc = source.allow_description if source else True
    allow_img = source.allow_images if source else False
    article = Article(
        canonical_url=canon, url=item.url, title=item.title,
        description=item.description if allow_desc else None,
        publisher_name=item.publisher_name or (source.name if source else ""),
        publisher_url=item.publisher_url,
        publisher_country=(item.publisher_country or (source.country if source else None) or None),
        source_id=source.id if source else None, provider=item.provider,
        language=(item.language or detect_language(text))[:8],
        published_at=item.published_at, fetched_at=utcnow(),
        content_type=item.content_type if item.content_type else "news",
        image_url=item.image_url if allow_img else None,
        title_fingerprint=fingerprint, is_demo=bool(source and source.is_demo),
        author=item.author)
    if article.publisher_country:
        article.publisher_country = article.publisher_country.upper()[:2]
    session.add(article)
    session.flush()

    sibling = session.scalar(
        select(Article).where(Article.title_fingerprint == fingerprint, Article.id != article.id,
                              Article.published_at >= item.published_at - CLUSTER_WINDOW,
                              Article.published_at <= item.published_at + CLUSTER_WINDOW)
        .order_by(Article.id).limit(1))
    article.cluster_id = (sibling.cluster_id or sibling.id) if sibling else article.id

    for code in sorted(set(detect_countries(text)) | set(item.places or [])):
        article.tags.append(ArticleTag(kind="event_country", value=code))
    for topic in sorted(set(detect_topics(text)) | set(item.topics or [])):
        article.tags.append(ArticleTag(kind="topic", value=topic))
    return article


def _log(session: Session, target: str, provider: str, status: str, *, items: int = 0,
         new_items: int = 0, error: str | None = None, result: FetchResult | None = None) -> None:
    session.add(FetchLog(target=target, provider=provider, status=status, items=items,
                         new_items=new_items, error=error,
                         latency_ms=result.latency_ms if result else None,
                         quota_remaining=result.quota_remaining if result else None))


def _since(source: Source):
    last = as_utc(source.last_success_at)
    return (last - timedelta(hours=1)) if last else utcnow() - timedelta(days=2)


def _calls_for(source: Source, scopes: list[Scope]):
    """Yield (label, callable) pairs for one source's configured queries."""
    cfg = source.config or {}
    if source.provider == "rss":
        for i, feed in enumerate(cfg.get("feeds", [])):
            yield feed["url"], lambda i=i, f=feed: _fetch_feed(source, i, f)
        return
    if source.provider == "wordpress":
        yield source.url, lambda: _fetch_wordpress(source)
        return
    if source.provider == "reliefweb":
        yield "reports", lambda: ReliefWebAdapter().reports(cfg.get("countries"))
        return
    if source.provider == "gdelt":
        gdelt = GdeltAdapter()
        queries = {lang: list((cfg.get("queries") or {}).get(lang, [])) for lang in ("ar", "en")}
        for scope in scopes:
            for lang in queries:
                queries[lang] += (scope.queries or {}).get(lang, [])
        for lang, terms in queries.items():
            for term in dict.fromkeys(terms):
                phrase = f'"{term}"' if " " in term else term
                yield f"{lang}:{term}", lambda p=phrase, l=lang: gdelt.search(p, l)
        return
    adapter = {"gnews": GNewsAdapter, "worldnews": WorldNewsAdapter,
               "newsapi": NewsApiAdapter}[source.provider]()
    since = _since(source)
    languages = source.languages or ["ar", "en"]
    for scope in scopes:
        for lang in languages:
            for query in (scope.queries or {}).get(lang, []):
                yield (f"{scope.key}:{lang}:{query}",
                       lambda q=query, l=lang: adapter.search(q, l, since=since))
    for h in cfg.get("headlines", []):  # GNews top-headlines
        yield (f"headlines:{h['lang']}:{h.get('category', 'world')}",
               lambda h=h: adapter.headlines(h["lang"], h.get("category", "world"), h.get("country")))
    for extra in cfg.get("country_feeds", []):  # e.g. World News API source-country=ps
        yield (f"country:{extra['country']}:{extra['language']}",
               lambda e=extra: adapter.search(e.get("query"), e["language"],
                                              country=e["country"], since=since))


def _remaining_budget(session: Session, source: Source) -> int | None:
    if not source.daily_request_limit:
        return None
    from sqlalchemy import func
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    used = session.scalar(select(func.count(FetchLog.id)).where(
        FetchLog.target == source.key, FetchLog.started_at >= start,
        FetchLog.status.in_(["ok", "error", "quota", "auth"]))) or 0
    return source.daily_request_limit - used


def _fetch_wordpress(source: Source) -> FetchResult:
    """WordPress REST API first; the site's RSS feed if the API is switched off."""
    cfg = source.config or {}
    language = (source.languages or [None])[0]
    try:
        # The latest 20 posts every hour; duplicates are dropped on store. No
        # `after` filter: WordPress reads it in the site's own time zone.
        return WordPressAdapter().posts(source.url, source.name, language, source.country,
                                        category_ids=cfg.get("category_ids"))
    except ProviderError as exc:
        if exc.status != "error":
            raise
        log.info("%s: REST API unavailable (%s), reading the feed", source.key, exc)
        return RssAdapter().fetch(cfg.get("feed_url") or source.url.rstrip("/") + "/feed/",
                                  source.name, language, source.country)


def _fetch_feed(source: Source, index: int, feed: dict) -> FetchResult:
    """Read one feed; if its address fails, look for the feed the site advertises."""
    adapter = RssAdapter()

    def read(url: str) -> FetchResult:
        return adapter.fetch(
            url, source.name, feed.get("language") or (source.languages or [None])[0],
            source.country, feed.get("content_type", "humanitarian_report"
                                     if source.kind == "humanitarian" else "news"),
            [feed["topic"]] if feed.get("topic") else None)

    try:
        return read(feed["url"])
    except ProviderError as first:
        if first.status == "quota":
            raise
        moved = _rediscover(source, index, feed, adapter, read) if feed.get("site") else None
        if moved is not None:
            return moved
        domain = (source.config or {}).get("gdelt_domain")
        if domain:
            # The publisher offers no readable feed, but GDELT indexes its
            # site: read the same publisher's latest stories from there.
            try:
                result = GdeltAdapter().search(f"domain:{domain}", feed.get("language"), timespan="2d",
                                               publisher_name=source.name, publisher_country=source.country)
            except ProviderError as exc:
                raise ProviderError(f"{first}; GDELT fallback for {domain}: {exc}") from None
            for item in result.items:
                item.content_type = feed.get("content_type", "humanitarian_report"
                                             if source.kind == "humanitarian" else "news")
                if feed.get("topic"):
                    item.topics = [feed["topic"]]
            log.info("%s: feed unavailable (%s), %d stories via GDELT domain:%s",
                     source.key, first, len(result.items), domain)
            return result
        raise


def _rediscover(source: Source, index: int, feed: dict, adapter, read) -> FetchResult | None:
    """Look for the feed the site advertises; remember it if it works."""
    try:
        candidates = discover_feeds(adapter.http, feed["site"])
    except ProviderError:
        return None
    for url in candidates:
        if url == feed["url"]:
            continue
        try:
            result = read(url)
        except ProviderError:
            continue
        # Remember the working address (reassign so the JSON column saves).
        feeds = [dict(f) for f in source.config.get("feeds", [])]
        feeds[index] = {**feeds[index], "url": url, "previous_url": feed["url"]}
        source.config = {**source.config, "feeds": feeds}
        log.info("%s: feed moved %s -> %s", source.key, feed["url"], url)
        return result
    return None


def ingest_news(session: Session, only: str | None = None) -> dict:
    """Run every enabled news source, or just the one keyed `only`."""
    settings = get_settings()
    scopes = list(session.scalars(select(Scope).where(Scope.enabled)))
    summary = {}
    stmt = select(Source).where(Source.enabled, Source.provider.in_(
        ["gnews", "worldnews", "newsapi", "rss", "wordpress", "gdelt", "reliefweb"]))
    if only:
        stmt = stmt.where(Source.key == only)
    for source in list(session.scalars(stmt)):
        if not settings.provider_configured(source.provider):
            _log(session, source.key, source.provider, "skipped", error="provider not configured")
            summary[source.key] = "skipped"
            continue
        new_total, failures = 0, []
        budget = _remaining_budget(session, source)
        for label, call in _calls_for(source, scopes):
            if budget is not None and budget <= 0:
                _log(session, source.key, source.provider, "quota",
                     error=f"daily request limit of {source.daily_request_limit} reached")
                failures.append("daily request limit reached")
                break
            if budget is not None:
                budget -= 1
            try:
                result = call()
            except ProviderError as exc:
                _log(session, source.key, source.provider, exc.status, error=f"{label}: {exc}")
                failures.append(str(exc))
                if exc.status in ("quota", "auth", "skipped"):
                    break  # the next query will fail the same way
                continue
            new = sum(1 for item in result.items if store_article(session, item, source))
            new_total += new
            _log(session, source.key, source.provider, "ok", items=len(result.items),
                 new_items=new, result=result)
        if failures:
            source.last_failure_at = utcnow()
            source.last_error = failures[-1][:500]
        else:
            source.last_success_at = utcnow()
            source.last_error = None
        session.commit()
        summary[source.key] = {"new": new_total, "errors": len(failures)}
    return summary


def _metric_channel(metric: Metric, settings):
    """(provider, fetch) for a metric, or (provider, None) if nothing is configured.

    A DTM metric with a `hapi` block falls back to HDX HAPI, which republishes
    DTM's IDP figures, when no DTM key is set. The producer stays IOM DTM; the
    coverage key differs, so values from the two channels are never compared.
    """
    cfg = metric.provider_config or {}
    if metric.provider == "dtm":
        if settings.provider_configured("dtm"):
            return "dtm", lambda: DtmAdapter().latest(cfg)
        if cfg.get("hapi") and settings.provider_configured("hapi"):
            return "hapi", lambda: HapiAdapter().latest(cfg["hapi"])
        return "dtm", None
    if metric.provider == "acled":
        return "acled", (lambda: AcledAdapter().window(cfg)) if settings.provider_configured("acled") else None
    if metric.provider == "hapi":
        return "hapi", (lambda: HapiAdapter().latest(cfg)) if settings.provider_configured("hapi") else None
    return metric.provider, None


def ingest_metrics(session: Session) -> dict:
    settings = get_settings()
    summary = {}
    for metric in session.scalars(select(Metric).where(Metric.enabled,
                                                       Metric.provider.in_(["dtm", "acled", "hapi"]))):
        provider, fetch = _metric_channel(metric, settings)
        if fetch is None:
            _log(session, metric.metric_id, provider, "skipped", error="provider not configured")
            summary[metric.metric_id] = "skipped"
            continue
        try:
            result = fetch()
        except ProviderError as exc:
            # A failed fetch stores nothing. The card keeps the last approved
            # value, ages it, and eventually says "no recent verified data".
            _log(session, metric.metric_id, provider, exc.status, error=str(exc))
            summary[metric.metric_id] = exc.status
            session.commit()
            continue
        created = 0
        for reading in result.items:
            if _already_have(session, metric, reading):
                continue
            try:
                add_observation(session, metric, {
                    "value": reading.value, "period_start": reading.period_start,
                    "period_end": reading.period_end, "published_at": reading.published_at,
                    "period_label": reading.period_label, "source_url": reading.source_url,
                    "coverage_key": reading.coverage_key, "coverage_note": reading.coverage_note,
                    "number_type": reading.number_type, "producer": reading.producer,
                    "methodology_note": reading.methodology_note,
                }, entered_by=f"provider:{provider}")
                created += 1
            except ObservationRejected as exc:
                _log(session, metric.metric_id, provider, "error", error=f"rejected: {exc}")
        _log(session, metric.metric_id, provider, "ok", items=len(result.items),
             new_items=created, result=result)
        session.commit()
        summary[metric.metric_id] = {"new": created}
    return summary


def _already_have(session: Session, metric: Metric, reading) -> bool:
    return session.scalar(select(MetricObservation.id).where(
        MetricObservation.metric_pk == metric.id,
        MetricObservation.period_start == reading.period_start,
        MetricObservation.period_end == reading.period_end,
        MetricObservation.coverage_key == reading.coverage_key,
        MetricObservation.value == reading.value).limit(1)) is not None
