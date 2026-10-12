import json
from datetime import date

from sqlalchemy import select

from app import content
from app.models import Article, Metric, MetricObservation, Source


def _write(folder, name, data):
    (folder / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_missing_folder_means_nothing_to_apply(session, tmp_path):
    report = content.new_report()
    content.apply_sources(session, tmp_path / "none", report)
    content.apply_articles(session, tmp_path / "none", report)
    assert report == content.new_report()


def test_editor_site_and_source_toggle(session, tmp_path):
    _write(tmp_path, "sites.json", [
        {"url": "https://mysite.sa/", "name": "موقعي", "type": "wordpress", "language": "ar",
         "country": "SA", "group": "saudi", "added_by": "محرر"},
        {"url": "http://insecure.sa", "name": "x"}])
    _write(tmp_path, "sources.json", {"bbc": {"enabled": False}})
    report = content.new_report()
    content.apply_sources(session, tmp_path, report)
    src = session.scalar(select(Source).where(Source.key == "mysite_sa"))
    assert src.provider == "wordpress" and src.enabled and src.config["group"] == "saudi"
    assert report["sites"] == 1 and "https://" in report["skipped"][0]
    assert session.scalar(select(Source).where(Source.key == "bbc")).enabled is False


def test_editor_story_and_hiding(session, tmp_path):
    _write(tmp_path, "articles.json", [
        {"title": "افتتاح مستشفى في الخرطوم", "url": "https://paper.sd/1", "publisher_name": "صحيفة",
         "language": "ar", "published_at": "2026-10-10T08:00:00Z", "entered_by": "محرر"},
        {"title": "تجربة", "url": "javascript:x", "publisher_name": "x", "language": "ar",
         "published_at": "2026-10-10T08:00:00Z"},
        {"title": "مستقبل", "url": "https://p.sd/2", "publisher_name": "x", "language": "ar",
         "published_at": "2099-01-01T00:00:00Z"}])
    report = content.new_report()
    content.apply_articles(session, tmp_path, report)
    a = session.scalar(select(Article).where(Article.url == "https://paper.sd/1"))
    assert a.entered_by == "محرر" and a.tag_values("event_country") == ["SD"]
    assert report["articles"] == 1 and len(report["skipped"]) == 2
    _write(tmp_path, "hidden.json", [{"url": "https://paper.sd/1", "by": "محرر"}])
    content.apply_hidden(session, tmp_path, report)
    assert session.scalar(select(Article).where(Article.url == "https://paper.sd/1")) is None


def test_editor_figure_needs_a_second_person(session, tmp_path):
    _write(tmp_path, "figures.json", [{
        "metric_id": "ps_gaza_killed", "value": 1000, "period_start": "2026-09-01",
        "period_end": "2026-09-30", "published_at": "2026-10-01",
        "source_url": "https://www.ochaopt.org/x", "coverage_key": "gaza:all", "entered_by": "سارة"}])
    _write(tmp_path, "approvals.json", [
        {"metric_id": "ps_gaza_killed", "period_end": "2026-09-30", "value": 1000, "reviewer": "سارة"}])
    report = content.new_report()
    content.apply_figures_and_approvals(session, tmp_path, report)
    m = session.scalar(select(Metric).where(Metric.metric_id == "ps_gaza_killed"))
    obs = session.scalar(select(MetricObservation).where(MetricObservation.metric_pk == m.id))
    assert obs.review_status == "pending" and "cannot approve" in report["skipped"][0]
    _write(tmp_path, "approvals.json", [
        {"metric_id": "ps_gaza_killed", "period_end": "2026-09-30", "value": 1000, "reviewer": "أحمد"}])
    content.apply_figures_and_approvals(session, tmp_path, content.new_report())
    approved = session.scalars(select(MetricObservation).where(
        MetricObservation.metric_pk == m.id, MetricObservation.review_status == "approved")).all()
    assert len(approved) == 1 and approved[0].reviewed_by == "أحمد"
    assert approved[0].period_end == date(2026, 9, 30)


def test_invalid_json_is_reported_not_ignored(session, tmp_path):
    (tmp_path / "sites.json").write_text("[{broken", encoding="utf-8")
    import pytest
    with pytest.raises(ValueError, match="sites.json is not valid JSON"):
        content.apply_sources(session, tmp_path, content.new_report())


def test_images_switch_in_sources_json(session, tmp_path):
    _write(tmp_path, "sources.json", {"bbc": {"images": False}})
    content.apply_sources(session, tmp_path, content.new_report())
    src = session.scalar(select(Source).where(Source.key == "bbc"))
    assert src.enabled and not src.allow_images


def test_fetch_interval_setting_and_schedule(tmp_path):
    from datetime import datetime, timedelta, timezone
    assert content.fetch_minutes(tmp_path) == 20
    _write(tmp_path, "settings.json", {"fetch_minutes": 60})
    assert content.fetch_minutes(tmp_path) == 60
    _write(tmp_path, "settings.json", {"fetch_minutes": 1})  # not offered: fall back
    assert content.fetch_minutes(tmp_path) == 20
    now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
    assert content.build_due(None, now, 20)
    assert content.build_due(now - timedelta(minutes=17), now, 20)
    assert not content.build_due(now - timedelta(minutes=10), now, 20)
    assert not content.build_due(now - timedelta(minutes=50), now, 60)
