"""Rules for humanitarian numbers.

The whole module exists to enforce a handful of refusals:

* no value without a unit, a measured period, a producer and a link;
* no zero (or any value) invented when a fetch fails or data is missing;
* no old value shown as if it were current: past `max_age_days` the card says
  "no recent verified data" instead;
* no change figure unless the two periods are genuinely comparable;
* no line drawn through points with different definitions or coverage;
* no averaging of sources: the primary producer's value is shown, others are
  listed next to it, each under its own name.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import utcnow
from .models import NUMBER_TYPES, Metric, MetricObservation


class ObservationRejected(ValueError):
    """Raised instead of storing a number that cannot be shown honestly."""


REQUIRED_TEXT = ("unit_ar", "unit_en", "area_ar", "area_en", "population_ar", "population_en",
                 "producer", "source_url", "coverage_key")


def validate_observation(data: dict) -> None:
    missing = [k for k in REQUIRED_TEXT if not str(data.get(k) or "").strip()]
    for k in ("value", "period_start", "period_end", "published_at", "number_type"):
        if data.get(k) is None:
            missing.append(k)
    if missing:
        raise ObservationRejected(f"missing required fields: {', '.join(sorted(missing))}")
    if data["number_type"] not in NUMBER_TYPES:
        raise ObservationRejected(f"number_type must be one of {', '.join(NUMBER_TYPES)}")
    try:
        value = float(data["value"])
    except (TypeError, ValueError):
        raise ObservationRejected("value must be a number") from None
    if value != value or value < 0:  # NaN or negative
        raise ObservationRejected("value must be a non-negative number")
    low, high = data.get("value_low"), data.get("value_high")
    if (low is None) != (high is None):
        raise ObservationRejected("a range needs both value_low and value_high")
    if low is not None and not (float(low) <= value <= float(high)):
        raise ObservationRejected("value must lie within value_low..value_high")
    if not str(data["source_url"]).startswith(("https://", "http://")):
        raise ObservationRejected("source_url must be an http(s) link to the original")
    if data["period_end"] < data["period_start"]:
        raise ObservationRejected("period_end is before period_start")
    if data["published_at"] < data["period_start"]:
        raise ObservationRejected("published_at is before the measured period began")
    if data["published_at"] > date.today() + timedelta(days=1):
        raise ObservationRejected("published_at is in the future")


def add_observation(session: Session, metric: Metric, data: dict, *, entered_by: str,
                    auto_approve: bool | None = None, supersedes: MetricObservation | None = None,
                    correction_note: str | None = None, is_demo: bool = False) -> MetricObservation:
    """Validate and append a new version. Never edits an existing row."""
    payload = {
        "unit_ar": metric.unit_ar, "unit_en": metric.unit_en,
        "area_ar": metric.area_ar, "area_en": metric.area_en,
        "population_ar": metric.population_ar, "population_en": metric.population_en,
        "number_type": metric.default_number_type, "producer": metric.primary_producer,
        **{k: v for k, v in data.items() if v is not None},
    }
    validate_observation(payload)
    if supersedes is not None and supersedes.metric_pk != metric.id:
        raise ObservationRejected("a correction must belong to the same metric")
    next_version = (session.scalar(select(func.max(MetricObservation.version))
                                   .where(MetricObservation.metric_pk == metric.id)) or 0) + 1
    approve = (not metric.requires_review) if auto_approve is None else auto_approve
    obs = MetricObservation(
        metric_pk=metric.id, version=next_version,
        value=float(payload["value"]),
        value_low=payload.get("value_low"), value_high=payload.get("value_high"),
        unit_ar=payload["unit_ar"], unit_en=payload["unit_en"],
        area_ar=payload["area_ar"], area_en=payload["area_en"],
        population_ar=payload["population_ar"], population_en=payload["population_en"],
        period_start=payload["period_start"], period_end=payload["period_end"],
        period_label=payload.get("period_label"), published_at=payload["published_at"],
        number_type=payload["number_type"], producer=payload["producer"],
        source_url=payload["source_url"], methodology_note=payload.get("methodology_note"),
        coverage_note=payload.get("coverage_note"), coverage_key=payload["coverage_key"],
        definition_version=payload.get("definition_version", metric.definition_version),
        review_status="approved" if approve else "pending",
        reviewed_by=entered_by if approve else None,
        reviewed_at=utcnow() if approve else None,
        supersedes_id=supersedes.id if supersedes else None,
        correction_note=correction_note, entered_by=entered_by, is_demo=is_demo,
    )
    session.add(obs)
    session.flush()
    return obs


def _superseded_ids(observations: list[MetricObservation]) -> set[int]:
    """Ids replaced by an approved correction. A pending correction replaces nothing yet."""
    return {o.supersedes_id for o in observations
            if o.supersedes_id and o.review_status == "approved"}


def visible_history(metric: Metric) -> list[MetricObservation]:
    """Approved, not superseded, oldest period first."""
    obs = [o for o in metric.observations if o.review_status == "approved"]
    gone = _superseded_ids(obs)
    return sorted((o for o in obs if o.id not in gone),
                  key=lambda o: (o.period_end, o.published_at, o.version))


def _is_primary(metric: Metric, obs: MetricObservation) -> bool:
    if obs.is_demo:  # demo rows carry a "demo data" producer on purpose
        return True
    return obs.producer.strip().lower() == metric.primary_producer.strip().lower()


def _same_definition(a: MetricObservation, b: MetricObservation) -> bool:
    return (a.definition_version == b.definition_version and a.coverage_key == b.coverage_key
            and a.unit_en == b.unit_en and a.producer.strip().lower() == b.producer.strip().lower())


def _period_days(o: MetricObservation) -> int:
    return (o.period_end - o.period_start).days


def comparable(prev: MetricObservation, cur: MetricObservation) -> tuple[bool, str]:
    if not _same_definition(prev, cur):
        return False, "definition_or_coverage_differs"
    if prev.number_type != cur.number_type:
        return False, "number_type_differs"
    if prev.period_end >= cur.period_start and _period_days(cur) > 0:
        return False, "periods_overlap"
    if prev.period_end >= cur.period_end:
        return False, "not_later"
    a, b = _period_days(prev), _period_days(cur)
    # Snapshots (0-day periods) compare with snapshots; spans must be within
    # 10% of each other's length (a 30-day month vs a 31-day month is fine).
    if (a == 0) != (b == 0) or (a and abs(a - b) > max(1, 0.1 * max(a, b))):
        return False, "period_lengths_differ"
    return True, "ok"


@dataclass
class MetricState:
    status: str  # current | stale | no_data
    current: MetricObservation | None
    previous: MetricObservation | None
    change_reason: str | None
    series: list[MetricObservation]
    alternatives: list[MetricObservation]
    age_days: int | None


def metric_state(metric: Metric, today: date | None = None) -> MetricState:
    today = today or datetime.now(timezone.utc).date()
    history = visible_history(metric)
    primary = [o for o in history if _is_primary(metric, o)]
    alternatives = [o for o in history if not _is_primary(metric, o)]
    if not primary:
        return MetricState("no_data", None, None, None, [], alternatives, None)

    current = primary[-1]
    age = (today - current.period_end).days
    status = "stale" if age > metric.max_age_days else "current"

    previous, reason = None, "no_earlier_value"
    earlier = [o for o in primary[:-1]]
    if earlier:
        ok, reason = comparable(earlier[-1], current)
        previous = earlier[-1] if ok else None

    snapshot = _period_days(current) == 0
    series = [o for o in primary if _same_definition(o, current)
              and o.number_type == current.number_type
              and (_period_days(o) == 0) == snapshot]
    if len(series) < 2:
        series = []
    return MetricState(status, current, previous, None if previous else reason, series,
                       alternatives, age)
