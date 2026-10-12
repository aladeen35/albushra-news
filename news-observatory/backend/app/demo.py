"""Demo content for trying the interface without provider keys.

Everything here is fake and labelled as such at every level: the publisher is
"Demo publisher", links go to example.org, observations carry is_demo=True and
the producer "Demo data — not real", and the UI shows a banner plus a badge on
every card. Values are deliberately round so nobody mistakes them for a toll.

`python -m app.cli demo --clear` removes all of it.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .db import utcnow
from .ingest import store_article
from .metrics import add_observation
from .models import Article, Metric, MetricObservation, Source
from .providers.base import NormalizedArticle

DEMO_PRODUCER = "Demo data — not real / بيانات تجريبية"
DEMO_URL = "https://example.org/demo"

ARTICLES = [
    ("ar", "[تجريبي] الأمم المتحدة تحذر من تفاقم أزمة النزوح في دارفور", "SD", "society", 1),
    ("en", "[Demo] Aid convoys reach El Fasher after weeks of delay", "SD", "society", 2),
    ("ar", "[تجريبي] اجتماع وزاري عربي في القاهرة لبحث الأوضاع في غزة", "EG", "politics", 3),
    ("en", "[Demo] Gaza: hospitals report fuel shortages", "PS", "health", 4),
    ("ar", "[تجريبي] الضفة الغربية: هدم منازل في محافظة نابلس", "PS", "conflict", 5),
    ("en", "[Demo] Floods hit northern Pakistan, thousands displaced", "PK", "environment", 6),
    ("ar", "[تجريبي] قمة اقتصادية في الرياض تناقش أسعار النفط", "SA", "economy", 8),
    ("en", "[Demo] Indonesia launches national AI research programme", "ID", "technology", 9),
    ("en", "[Demo] Climate talks resume in Geneva", None, "environment", 11),
    ("ar", "[تجريبي] المغرب يتأهل إلى نصف نهائي البطولة القارية لكرة القدم", "MA", "sports", 12),
    ("en", "[Demo] Sudan: cholera cases rise in displacement camps", "SD", "health", 14),
    ("ar", "[تجريبي] تقرير إنساني: احتياجات متزايدة في السودان", "SD", "society", 16),
]

# (metric_id, [(days_ago_period_end, value)], number_type override, review)
SERIES = [
    ("sd_idps", [(160, 1_200_000), (100, 1_250_000), (40, 1_300_000)], None, "approved"),
    ("sd_acled_events_30d", [(10, 100)], None, "approved"),
    ("ps_gaza_killed", [(5, 1_000)], None, "approved"),
    ("ps_gaza_injured", [(5, 2_000)], None, "approved"),
    ("ps_wb_killed", [(120, 100)], None, "approved"),  # past max age: shows the stale state
    ("ps_gaza_idps", [(3, 500_000)], None, "pending"),  # waits in the review queue
]


def load_demo(session: Session) -> None:
    clear_demo(session)
    source = Source(key="demo", name="Demo publisher", url=DEMO_URL, kind="news_api",
                    provider="manual", languages=["ar", "en"], is_demo=True, enabled=False,
                    allow_description=True, reliability=0.5,
                    license_note="Fake content for interface testing.")
    session.add(source)
    session.flush()
    now = utcnow()
    for i, (lang, title, _country, _topic, hours) in enumerate(ARTICLES):
        content_type = "humanitarian_report" if "تقرير إنساني" in title else "news"
        store_article(session, NormalizedArticle(
            url=f"{DEMO_URL}/article-{i}", title=title, publisher_name="Demo publisher",
            description=("نص وصفي تجريبي لا يمثل خبرًا حقيقيًا." if lang == "ar"
                         else "Placeholder description; not a real story."),
            published_at=now - timedelta(hours=hours), provider="manual", language=lang,
            publisher_country=None, content_type=content_type), source)
    today = date.today()
    for metric_id, points, number_type, review in SERIES:
        metric = session.scalar(select(Metric).where(Metric.metric_id == metric_id))
        if not metric:
            continue
        for days_ago, value in points:
            end = today - timedelta(days=days_ago)
            snapshot = metric.provider == "dtm" or "idps" in metric_id
            start = end if snapshot else end - timedelta(days=29)
            add_observation(session, metric, {
                "value": value, "period_start": start, "period_end": end,
                "published_at": end, "producer": DEMO_PRODUCER, "source_url": DEMO_URL,
                "coverage_key": f"demo:{metric_id}", "number_type": number_type,
                "period_label": "DEMO", "coverage_note": "Demo data for interface testing.",
            }, entered_by="demo", auto_approve=(review == "approved"), is_demo=True)
    session.commit()


def clear_demo(session: Session) -> None:
    session.execute(delete(MetricObservation).where(MetricObservation.is_demo))
    for article in session.scalars(select(Article).where(Article.is_demo)):
        session.delete(article)
    session.execute(delete(Source).where(Source.is_demo))
    session.commit()


def demo_active(session: Session) -> bool:
    return session.scalar(select(Source.id).where(Source.is_demo).limit(1)) is not None
