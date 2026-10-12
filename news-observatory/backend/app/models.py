"""Data model.

Three distinctions run through every table, because the product is wrong
without them:

* an article's language, its publisher's country and the places it is about
  are three separate facts (ArticleTag keeps the last one per country);
* a metric definition is separate from its observations, and observations are
  never updated in place: a correction is a new version that supersedes the
  old one, so a change in value can always be explained;
* a number's type (reported / verified / estimated / projected) is stored with
  the number, never inferred.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String,
                        Text, UniqueConstraint, Index)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, utcnow

NUMBER_TYPES = ("reported", "verified", "estimated", "projected")
REVIEW_STATUSES = ("pending", "approved", "rejected")
CONTENT_TYPES = ("news", "humanitarian_report", "data_update")
TOPICS = ("politics", "conflict", "economy", "society", "environment", "health",
          "technology", "sports")


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(500))
    # news_api | rss | humanitarian | data
    kind: Mapped[str] = mapped_column(String(32))
    # gnews | worldnews | newsapi | rss | wordpress | dtm | acled | manual
    provider: Mapped[str] = mapped_column(String(32))
    languages: Mapped[list] = mapped_column(JSON, default=list)
    regions: Mapped[list] = mapped_column(JSON, default=list)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    terms_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    license_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    attribution: Mapped[str | None] = mapped_column(Text, nullable=True)
    allow_description: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_images: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_full_text: Mapped[bool] = mapped_column(Boolean, default=False)
    # 0..1, published in the ranking policy. Editorial, not computed.
    reliability: Mapped[float] = mapped_column(Float, default=0.5)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    terms_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    daily_request_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_url: Mapped[str] = mapped_column(String(1000), unique=True)
    url: Mapped[str] = mapped_column(String(1000))
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    publisher_name: Mapped[str] = mapped_column(String(300))
    publisher_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    publisher_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(32))
    language: Mapped[str] = mapped_column(String(8))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    content_type: Mapped[str] = mapped_column(String(32), default="news")
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    title_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    cluster_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    classification_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    # Set when an editor added the story by hand.
    entered_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    author: Mapped[str | None] = mapped_column(String(200), nullable=True)

    source: Mapped[Source | None] = relationship()
    tags: Mapped[list["ArticleTag"]] = relationship(
        back_populates="article", cascade="all, delete-orphan", lazy="selectin")

    def tag_values(self, kind: str) -> list[str]:
        return sorted({t.value for t in self.tags if t.kind == kind})


class ArticleTag(Base):
    """`event_country` = a place the story is about; `topic` = subject."""
    __tablename__ = "article_tags"
    __table_args__ = (
        UniqueConstraint("article_id", "kind", "value"),
        Index("ix_article_tags_kind_value", "kind", "value"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))
    value: Mapped[str] = mapped_column(String(64))
    article: Mapped[Article] = relationship(back_populates="tags")


class RegionList(Base):
    """A declared, editable list of countries behind a section."""
    __tablename__ = "region_lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True)
    name_ar: Mapped[str] = mapped_column(String(200))
    name_en: Mapped[str] = mapped_column(String(200))
    definition_ar: Mapped[str] = mapped_column(Text)
    definition_en: Mapped[str] = mapped_column(Text)
    reference_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    countries: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 onupdate=utcnow)


class Scope(Base):
    """A dashboard scope: the world, or one crisis (Palestine, Sudan, ...)."""
    __tablename__ = "scopes"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True)
    name_ar: Mapped[str] = mapped_column(String(200))
    name_en: Mapped[str] = mapped_column(String(200))
    countries: Mapped[list] = mapped_column(JSON, default=list)
    # Search terms the news job runs for this scope, per language.
    queries: Mapped[dict] = mapped_column(JSON, default=dict)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Metric(Base):
    """What a number means. Values live in MetricObservation."""
    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    metric_id: Mapped[str] = mapped_column(String(64), unique=True)
    scope_key: Mapped[str] = mapped_column(String(64), index=True)
    name_ar: Mapped[str] = mapped_column(String(300))
    name_en: Mapped[str] = mapped_column(String(300))
    unit_ar: Mapped[str] = mapped_column(String(100))
    unit_en: Mapped[str] = mapped_column(String(100))
    area_ar: Mapped[str] = mapped_column(String(300))
    area_en: Mapped[str] = mapped_column(String(300))
    population_ar: Mapped[str] = mapped_column(String(300))
    population_en: Mapped[str] = mapped_column(String(300))
    default_number_type: Mapped[str] = mapped_column(String(16))
    primary_producer: Mapped[str] = mapped_column(String(200))
    primary_source_url: Mapped[str] = mapped_column(String(500))
    methodology_ar: Mapped[str] = mapped_column(Text)
    methodology_en: Mapped[str] = mapped_column(Text)
    uncertainty_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    uncertainty_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    # After this many days since the measured period ended, the card says
    # "no recent verified data" instead of showing the value.
    max_age_days: Mapped[int] = mapped_column(Integer, default=60)
    definition_version: Mapped[int] = mapped_column(Integer, default=1)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=True)
    # dtm | acled | manual
    provider: Mapped[str] = mapped_column(String(32), default="manual")
    provider_config: Mapped[dict] = mapped_column(JSON, default=dict)
    display_order: Mapped[int] = mapped_column(Integer, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    observations: Mapped[list["MetricObservation"]] = relationship(
        back_populates="metric", order_by="MetricObservation.version")


class MetricObservation(Base):
    """One published value. Append-only: never updated except review fields."""
    __tablename__ = "metric_observations"
    __table_args__ = (UniqueConstraint("metric_pk", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    metric_pk: Mapped[int] = mapped_column(ForeignKey("metrics.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    value: Mapped[float] = mapped_column(Float)
    value_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit_ar: Mapped[str] = mapped_column(String(100))
    unit_en: Mapped[str] = mapped_column(String(100))
    area_ar: Mapped[str] = mapped_column(String(300))
    area_en: Mapped[str] = mapped_column(String(300))
    population_ar: Mapped[str] = mapped_column(String(300))
    population_en: Mapped[str] = mapped_column(String(300))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    period_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    published_at: Mapped[date] = mapped_column(Date)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    number_type: Mapped[str] = mapped_column(String(16))
    producer: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str] = mapped_column(String(1000))
    methodology_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    coverage_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Two observations are comparable only if this matches (plus definition
    # version, unit and period shape). E.g. "admin0:SDN:all-idps".
    coverage_key: Mapped[str] = mapped_column(String(200))
    definition_version: Mapped[int] = mapped_column(Integer)
    review_status: Mapped[str] = mapped_column(String(16), default="pending")
    reviewed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    supersedes_id: Mapped[int | None] = mapped_column(
        ForeignKey("metric_observations.id"), nullable=True)
    correction_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    entered_by: Mapped[str] = mapped_column(String(200))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    metric: Mapped[Metric] = relationship(back_populates="observations")


class FetchLog(Base):
    """One provider call: what monitoring reads."""
    __tablename__ = "fetch_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    target: Mapped[str] = mapped_column(String(100), index=True)  # source key or metric id
    provider: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # ok | error | quota | auth | skipped
    status: Mapped[str] = mapped_column(String(16))
    items: Mapped[int] = mapped_column(Integer, default=0)
    new_items: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    quota_remaining: Mapped[str | None] = mapped_column(String(64), nullable=True)
