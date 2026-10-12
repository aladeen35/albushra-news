from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.metrics import ObservationRejected, add_observation, metric_state
from app.models import Metric

TODAY = date.today()


def _metric(session, metric_id="sd_idps"):
    return session.scalar(select(Metric).where(Metric.metric_id == metric_id))


def _obs(session, m, days_ago, value, *, span=0, approve=True, **extra):
    end = TODAY - timedelta(days=days_ago)
    data = {"value": value, "period_start": end - timedelta(days=span), "period_end": end,
            "published_at": end, "source_url": "https://dtm.iom.int/sudan",
            "coverage_key": "k", **extra}
    return add_observation(session, m, data, entered_by="ed", auto_approve=approve)


@pytest.mark.parametrize("missing", ["source_url", "coverage_key", "period_end", "published_at"])
def test_refuses_value_without_required_fields(session, missing):
    m = _metric(session)
    data = {"value": 5, "period_start": TODAY, "period_end": TODAY, "published_at": TODAY,
            "source_url": "https://x.org", "coverage_key": "k"}
    data[missing] = None
    with pytest.raises(ObservationRejected):
        add_observation(session, m, data, entered_by="ed")


def test_refuses_bad_values(session):
    m = _metric(session)
    with pytest.raises(ObservationRejected):
        _obs(session, m, 1, -3)
    with pytest.raises(ObservationRejected):
        _obs(session, m, 1, 10, value_low=11, value_high=20)
    with pytest.raises(ObservationRejected):
        _obs(session, m, 1, 10, source_url="javascript:alert(1)")
    with pytest.raises(ObservationRejected):
        _obs(session, m, 1, 10, number_type="guess")


def test_no_data_means_no_value_not_zero(session):
    state = metric_state(_metric(session))
    assert state.status == "no_data" and state.current is None


def test_pending_values_are_not_shown(session):
    m = _metric(session)
    _obs(session, m, 5, 100, approve=False)
    assert metric_state(m).status == "no_data"


def test_stale_after_max_age(session):
    m = _metric(session)
    _obs(session, m, m.max_age_days + 1, 100)
    state = metric_state(m)
    assert state.status == "stale"


def test_change_only_between_comparable_snapshots(session):
    m = _metric(session)
    _obs(session, m, 60, 100)
    _obs(session, m, 10, 150)
    state = metric_state(m)
    assert state.previous.value == 100 and len(state.series) == 2


def test_no_change_across_definition_versions(session):
    m = _metric(session)
    _obs(session, m, 60, 100)
    m.definition_version += 1
    _obs(session, m, 10, 150)
    state = metric_state(m)
    assert state.previous is None
    assert state.change_reason == "definition_or_coverage_differs"
    assert state.series == []  # never draw a line through different definitions


def test_no_change_for_unequal_periods(session):
    m = _metric(session, "sd_acled_events_30d")
    _obs(session, m, 60, 100, span=29)
    _obs(session, m, 10, 150, span=6)
    assert metric_state(m).change_reason == "period_lengths_differ"


def test_other_producers_are_alternatives_not_averaged(session):
    m = _metric(session)
    _obs(session, m, 10, 100)
    _obs(session, m, 9, 900, producer="Other agency")
    state = metric_state(m)
    assert state.current.value == 100
    assert [o.value for o in state.alternatives] == [900]


def test_correction_supersedes_without_overwriting(session):
    m = _metric(session)
    first = _obs(session, m, 10, 100)
    end = first.period_end
    fix = add_observation(session, m, {"value": 120, "period_start": end, "period_end": end,
                                       "published_at": TODAY, "source_url": "https://x.org",
                                       "coverage_key": "k"},
                          entered_by="ed", auto_approve=True, supersedes=first,
                          correction_note="typo")
    session.refresh(m)
    assert first.value == 100  # history intact
    assert metric_state(m).current.id == fix.id
    assert fix.version == first.version + 1
