import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from app.ingest import ingest_metrics, ingest_news, store_article
from app.models import Article, FetchLog, Metric, Source
from app.providers.base import NormalizedArticle

from .conftest import ADMIN

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _article(session, title, url, hours=1, **kw):
    return store_article(session, NormalizedArticle(
        url=url, title=title, publisher_name=kw.pop("publisher", "Pub"),
        published_at=datetime.now(timezone.utc) - timedelta(hours=hours), provider="rss", **kw), None)


def test_dashboard_without_data_shows_no_values(client):
    cards = client.get("/api/dashboard?scope=world").json()["cards"]
    assert cards and all(c["current"] is None and c["status"] == "no_data" for c in cards)


def test_sections_follow_story_location_not_language_or_publisher(client, session):
    _article(session, "Climate summit opens in Paris", "https://a.com/1", language="ar",
             publisher_country="SA")
    _article(session, "نزوح جديد في دارفور", "https://a.com/2", language="ar")
    _article(session, "Gaza hospitals short of fuel", "https://a.com/3", language="en",
             publisher_country="GB")
    session.commit()
    arab = {a["title"] for a in client.get("/api/articles?section=arab_world").json()["items"]}
    assert arab == {"نزوح جديد في دارفور", "Gaza hospitals short of fuel"}
    pal = client.get("/api/articles?section=palestine").json()["items"]
    assert [a["title"] for a in pal] == ["Gaza hospitals short of fuel"]
    assert pal[0]["publisher"]["country"] == "GB"


def test_duplicates_are_stored_once_and_clustered(client, session):
    assert _article(session, "UN warns of famine in Sudan - Reuters", "https://r.com/x?utm_source=a")
    assert _article(session, "UN warns of famine in Sudan - Reuters", "http://www.r.com/x") is None
    _article(session, "Sudan: UN warns of famine | AP", "https://ap.org/y", publisher="AP")
    session.commit()
    items = client.get("/api/articles").json()["items"]
    assert len(items) == 1 and items[0]["other_publishers"] == 1


def test_failed_metric_fetch_stores_nothing(client, session, monkeypatch):
    monkeypatch.setenv("DTM_SUBSCRIPTION_KEY", "k")
    from app.providers import humanitarian
    from app.providers.base import ProviderError

    def boom(self, cfg):
        raise ProviderError("HTTP 500")
    monkeypatch.setattr(humanitarian.DtmAdapter, "latest", boom)
    ingest_metrics(session)
    m = session.scalar(select(Metric).where(Metric.metric_id == "sd_idps"))
    assert m.observations == []
    log = session.scalar(select(FetchLog).where(FetchLog.target == "sd_idps"))
    assert log.status == "error"
    card = next(c for c in client.get("/api/dashboard?scope=sudan").json()["cards"]
                if c["metric_id"] == "sd_idps")
    assert card["current"] is None


def test_unconfigured_sources_are_skipped_and_logged(session):
    src = session.scalar(select(Source).where(Source.key == "gnews"))
    src.enabled = src.terms_reviewed = True
    session.commit()
    assert ingest_news(session)["gnews"] == "skipped"


def test_admin_requires_token(client):
    assert client.get("/api/admin/status").status_code == 401
    assert client.get("/api/admin/status", headers=ADMIN).status_code == 200


def test_entry_review_flow_requires_second_person(client):
    body = {"value": 1000, "period_start": "2026-09-01", "period_end": "2026-09-30",
            "published_at": "2026-10-01", "source_url": "https://www.ochaopt.org/x",
            "coverage_key": "gaza:all", "entered_by": "Editor A"}
    r = client.post("/api/admin/metrics/ps_gaza_killed/observations", json=body, headers=ADMIN)
    assert r.status_code == 201 and r.json()["review_status"] == "pending"
    obs_id = r.json()["id"]
    same = client.post(f"/api/admin/observations/{obs_id}/review", headers=ADMIN,
                       json={"decision": "approve", "reviewer": "editor a"})
    assert same.status_code == 422
    ok = client.post(f"/api/admin/observations/{obs_id}/review", headers=ADMIN,
                     json={"decision": "approve", "reviewer": "Editor B"})
    assert ok.json()["review_status"] == "approved"


def test_entry_without_link_is_refused(client):
    body = {"value": 1, "period_start": "2026-09-01", "period_end": "2026-09-30",
            "published_at": "2026-10-01", "source_url": "not a link", "coverage_key": "k",
            "entered_by": "Editor"}
    assert client.post("/api/admin/metrics/ps_gaza_killed/observations", json=body,
                       headers=ADMIN).status_code == 422


def test_source_cannot_be_enabled_before_terms_review(client):
    r = client.patch("/api/admin/sources/gnews", json={"enabled": True}, headers=ADMIN)
    assert r.status_code == 422
    r = client.patch("/api/admin/sources/gnews", json={"enabled": True, "terms_reviewed": True},
                     headers=ADMIN)
    assert r.status_code == 200


def test_region_list_is_editable(client):
    r = client.put("/api/admin/region-lists/arab_world", json={"countries": ["eg", "SA", "XX"]},
                   headers=ADMIN)
    assert r.json()["countries"] == ["EG", "SA", "XX"] and r.json()["not_in_gazetteer"] == ["XX"]
    meta = client.get("/api/meta").json()
    assert next(x for x in meta["region_lists"] if x["key"] == "arab_world")["countries"] == ["EG", "SA", "XX"]


def test_classification_correction(client, session):
    a = _article(session, "Talks in Geneva", "https://g.com/1")
    session.commit()
    r = client.patch(f"/api/admin/articles/{a.id}/classification", headers=ADMIN,
                     json={"event_countries": ["SD"], "topics": ["politics"]})
    assert r.json()["event_countries"] == ["SD"]
    assert client.get(f"/api/articles/{a.id}").json()["article"]["classification_edited"] is True


def test_rate_limit(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "3")
    codes = [client.get("/api/health").status_code for _ in range(5)]
    assert codes[:3] == [200] * 3 and codes[-1] == 429


def test_security_headers_and_spa(client):
    r = client.get("/")
    assert r.status_code == 200 and "<main" in r.text
    assert "script-src 'self'" in r.headers["content-security-policy"]


def test_demo_is_labelled_and_removable(client, session):
    from app.demo import clear_demo, load_demo
    load_demo(session)
    assert client.get("/api/meta").json()["demo"] is True
    cards = client.get("/api/dashboard?scope=world").json()["cards"]
    shown = [c["current"] for c in cards if c["current"]]
    assert shown and all(o["is_demo"] and "Demo" in o["producer"] for o in shown)
    clear_demo(session)
    assert client.get("/api/meta").json()["demo"] is False


def test_translations_have_the_same_keys():
    ar = json.loads((FRONTEND / "i18n/ar.json").read_text(encoding="utf-8"))
    en = json.loads((FRONTEND / "i18n/en.json").read_text(encoding="utf-8"))
    assert ar.keys() == en.keys()
    assert all(v.strip() for v in list(ar.values()) + list(en.values()))


def test_frontend_contains_no_provider_keys_or_innerhtml():
    for path in FRONTEND.rglob("*.js"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"apikey|api[-_]key|gnews\.io|worldnewsapi|newsapi\.org|acleddata", text, re.I), path
        assert not re.search(r"\.(innerHTML|outerHTML)\s*=|insertAdjacentHTML|document\.write", text), path


def test_trusted_feeds_are_seeded_on_but_flagged_for_terms_review(session):
    from app.seed import TRUSTED_FEEDS
    keys = {f["key"] for f in TRUSTED_FEEDS}
    rows = list(session.scalars(select(Source).where(Source.key.in_(keys))))
    assert len(rows) == len(keys) >= 6
    assert all(s.enabled and not s.terms_reviewed and s.allow_images for s in rows)
    assert all(f["url"].startswith("https://") for s in rows for f in s.config["feeds"])


def test_seeded_feed_stays_editable_but_enabling_still_needs_review(client):
    assert client.patch("/api/admin/sources/bbc", json={"allow_description": False},
                        headers=ADMIN).status_code == 200
    client.patch("/api/admin/sources/bbc", json={"enabled": False}, headers=ADMIN)
    assert client.patch("/api/admin/sources/bbc", json={"enabled": True},
                        headers=ADMIN).status_code == 422


def test_news_every_20_minutes_figures_hourly_by_default(client, monkeypatch):
    monkeypatch.delenv("NEWS_INTERVAL_MINUTES", raising=False)
    monkeypatch.delenv("METRICS_INTERVAL_MINUTES", raising=False)
    assert client.get("/api/meta").json()["refresh_minutes"] == {"news": 20, "metrics": 60}


def test_news_job_reads_feeds_and_one_bad_feed_does_not_stop_the_rest(session, monkeypatch):
    from app.providers import news
    from app.providers.base import FetchResult, ProviderError

    def fake_fetch(self, url, publisher, language=None, country=None, content_type="news",
                   topics=None):
        if "bbci" in url and language == "en":
            raise ProviderError("HTTP 500")
        return FetchResult([NormalizedArticle(
            url=f"{url}#1", title=f"{publisher} السودان", publisher_name=publisher,
            published_at=datetime.now(timezone.utc), provider="rss", language=language,
            publisher_country=country, content_type=content_type)])
    monkeypatch.setattr(news.RssAdapter, "fetch", fake_fetch)
    summary = ingest_news(session)
    assert summary["bbc"] == {"new": 1, "errors": 1}
    assert summary["reliefweb"]["new"] == 1
    report = session.scalar(select(Article).where(Article.publisher_name == "ReliefWeb (OCHA)"))
    assert report.content_type == "humanitarian_report" and report.tag_values("event_country") == ["SD"]
    assert ingest_news(session)["bbc"]["new"] == 0  # the next hour does not duplicate


def test_saudi_arab_sudanese_and_sports_sources_are_seeded(client):
    by_key = {s["key"]: s for s in client.get("/api/sources").json()}
    for key, group in (("spa", "saudi"), ("alarabiya", "saudi"), ("aawsat", "saudi"),
                       ("aljazeera_ar", "arab"), ("skynewsarabia", "arab"),
                       ("suna", "sudan"), ("sudantribune", "sudan"), ("dabanga", "sudan"),
                       ("bbc_sport", "sports"), ("arriyadiyah", "sports")):
        assert by_key[key]["group"] == group and by_key[key]["enabled"], key
    assert by_key["bbc_sport"]["topics"] == ["sports"]
    assert by_key["suna"]["country"] == "SD" and by_key["spa"]["country"] == "SA"


def test_moved_feed_is_found_through_the_site_and_remembered(session, monkeypatch):
    from app.ingest import _fetch_feed
    from app.providers import news
    from app.providers.base import FetchResult, ProviderError

    def fake_fetch(self, url, *a, **k):
        if url.endswith("/old"):
            raise ProviderError("HTTP 404")
        return FetchResult([])
    monkeypatch.setattr(news.RssAdapter, "fetch", fake_fetch)
    monkeypatch.setattr("app.ingest.discover_feeds", lambda http, site: ["https://suna-sd.net/new"])
    src = session.scalar(select(Source).where(Source.key == "suna"))
    src.config = {**src.config, "feeds": [{"url": "https://suna-sd.net/old", "language": "ar",
                                           "site": "https://suna-sd.net"}]}
    session.commit()
    _fetch_feed(src, 0, src.config["feeds"][0])
    session.commit()
    session.refresh(src)
    assert src.config["feeds"][0]["url"] == "https://suna-sd.net/new"
    assert src.config["feeds"][0]["previous_url"] == "https://suna-sd.net/old"


def test_sports_page_and_sudan_page(client, session):
    sport = store_article(session, NormalizedArticle(
        url="https://s.com/1", title="الهلال يفوز", publisher_name="الرياضية", topics=["sports"],
        published_at=datetime.now(timezone.utc), provider="rss", language="ar"), None)
    _article(session, "اشتباكات في الفاشر", "https://n.com/2")
    session.commit()
    assert [a["id"] for a in client.get("/api/articles?section=sports").json()["items"]] == [sport.id]
    assert [a["title"] for a in client.get("/api/articles?section=sudan").json()["items"]] == ["اشتباكات في الفاشر"]


def test_for_you_filters_by_chosen_sources_and_topics(client, session):
    bbc = session.scalar(select(Source).where(Source.key == "bbc"))
    spa = session.scalar(select(Source).where(Source.key == "spa"))
    for src, title, url in ((bbc, "Cholera outbreak in camps", "https://b.com/1"),
                            (spa, "قمة اقتصادية في الرياض", "https://spa.gov.sa/2")):
        store_article(session, NormalizedArticle(url=url, title=title, publisher_name=src.name,
                      published_at=datetime.now(timezone.utc), provider="rss"), src)
    session.commit()
    only_spa = client.get("/api/articles?sources=spa").json()["items"]
    assert [a["source_key"] for a in only_spa] == ["spa"]
    health_or_economy = client.get("/api/articles?topic=health,economy").json()["total"]
    assert health_or_economy == 2


def test_every_known_country_has_a_flag():
    from app.geo import COUNTRIES
    missing = [c for c in COUNTRIES if not (FRONTEND / f"assets/flags/{c.lower()}.svg").is_file()]
    assert missing == []


def _wp_transport(monkeypatch, handler):
    import httpx
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request",
                        lambda self, request: handler(request))


def test_inspect_and_add_a_wordpress_site(client, session, monkeypatch):
    import httpx
    from .test_providers import WP_POSTS

    def handler(request):
        if request.url.path == "/wp-json":
            return httpx.Response(200, json={"name": "موقعي", "description": "أخبار",
                                             "home": "https://mysite.sa", "namespaces": ["wp/v2"]},
                                  request=request)
        if request.url.path == "/wp-json/wp/v2/posts":
            return httpx.Response(200, json=WP_POSTS, request=request)
        return httpx.Response(404, request=request)
    _wp_transport(monkeypatch, handler)
    info = client.post("/api/admin/sites/inspect", json={"url": "mysite.sa"}, headers=ADMIN).json()
    assert info["type"] == "wordpress" and info["name"] == "موقعي" and info["language"] == "ar"
    assert info["sample"][0]["url"] == "https://mysite.sa/2026/10/sudan-aid/"

    off = client.post("/api/admin/sites", headers=ADMIN, json={
        "url": info["url"], "type": "wordpress", "name": "موقعي", "language": "ar", "country": "SA",
        "group": "saudi"}).json()
    assert off["enabled"] is False and off["first_fetch"] is None  # terms not confirmed yet
    session.expire_all()
    src = session.scalar(select(Source).where(Source.key == "mysite_sa"))
    session.delete(src)
    session.commit()

    on = client.post("/api/admin/sites", headers=ADMIN, json={
        "url": info["url"], "type": "wordpress", "name": "موقعي", "language": "ar", "country": "SA",
        "group": "saudi", "terms_reviewed": True}).json()
    assert on["enabled"] is True and on["first_fetch"]["new"] == 1
    item = client.get("/api/articles?sources=mysite_sa").json()["items"][0]
    assert item["url"] == "https://mysite.sa/2026/10/sudan-aid/" and item["author"] == "سارة"
    assert item["event_countries"] == ["SD"]


def test_wordpress_falls_back_to_feed_when_api_is_off(session, monkeypatch):
    import httpx
    from app.ingest import _fetch_wordpress
    rss = b"""<?xml version="1.0"?><rss><channel><item><title>t</title><link>https://wp.sa/p/1</link>
    <pubDate>Wed, 01 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>"""
    _wp_transport(monkeypatch, lambda r: httpx.Response(200, content=rss, request=r)
                  if r.url.path == "/feed/" else httpx.Response(404, request=r))
    src = Source(key="wp", name="WP", url="https://wp.sa", kind="rss", provider="wordpress",
                 languages=["ar"], config={})
    assert _fetch_wordpress(src).items[0].url == "https://wp.sa/p/1"


def test_inspect_reports_when_nothing_is_found(client, monkeypatch):
    import httpx
    _wp_transport(monkeypatch, lambda r: httpx.Response(404, request=r))
    r = client.post("/api/admin/sites/inspect", json={"url": "https://nothing.sa"}, headers=ADMIN)
    assert r.status_code == 422 and "no WordPress API or news feed" in r.json()["detail"]


def test_add_story_by_hand(client):
    body = {"title": "افتتاح مستشفى جديد في الخرطوم", "url": "https://paper.sd/a/1",
            "publisher_name": "صحيفة", "language": "ar", "published_at": "2026-10-10T08:00:00Z",
            "entered_by": "محرر"}
    r = client.post("/api/admin/articles", json=body, headers=ADMIN)
    assert r.status_code == 201 and r.json()["event_countries"] == ["SD"]  # tagged automatically
    assert client.post("/api/admin/articles", json=body, headers=ADMIN).status_code == 409
    a = client.get(f"/api/articles/{r.json()['id']}").json()["article"]
    assert a["added_by_editor"] and a["url"] == "https://paper.sd/a/1"
    assert client.get("/api/admin/articles", headers=ADMIN).json()[0]["entered_by"] == "محرر"

    tagged = client.post("/api/admin/articles", headers=ADMIN, json={
        **body, "url": "https://paper.sd/a/2", "event_countries": ["SA"], "topics": ["sports"]}).json()
    assert tagged["event_countries"] == ["SA"] and tagged["topics"] == ["sports"]
    assert client.delete(f"/api/admin/articles/{tagged['id']}", headers=ADMIN).status_code == 204
    assert client.get(f"/api/articles/{tagged['id']}").status_code == 404


def test_add_story_refuses_bad_input(client):
    base = {"title": "عنوان صالح للخبر", "url": "https://p.sa/1", "publisher_name": "ص",
            "language": "ar", "published_at": "2026-10-10T08:00:00Z", "entered_by": "محرر"}
    assert client.post("/api/admin/articles", json={**base, "url": "javascript:alert(1)"},
                       headers=ADMIN).status_code == 422
    assert client.post("/api/admin/articles", json={**base, "published_at": "2099-01-01T00:00:00Z"},
                       headers=ADMIN).status_code == 422
    assert client.post("/api/admin/articles", json=base).status_code == 401


def test_new_columns_are_added_to_an_older_database(tmp_path):
    import sqlalchemy as sa
    from app import db
    url = f"sqlite:///{tmp_path}/old.db"
    eng = sa.create_engine(url)
    with eng.begin() as c:
        c.execute(sa.text("CREATE TABLE articles (id INTEGER PRIMARY KEY, title TEXT)"))
    db.configure(url)
    db.init_db()
    cols = {c["name"] for c in sa.inspect(db.engine).get_columns("articles")}
    assert {"entered_by", "author"} <= cols


def test_new_api_sources_and_hapi_metrics_are_seeded(client, session):
    by_key = {s["key"]: s for s in client.get("/api/sources").json()}
    assert by_key["gdelt"]["enabled"] and by_key["reliefweb_api"]["group"] == "humanitarian"
    ids = {c["metric_id"] for c in client.get("/api/dashboard?scope=world").json()["cards"]}
    assert {"sd_people_in_need", "ps_people_in_need"} <= ids
    sd = session.scalar(select(Metric).where(Metric.metric_id == "sd_idps"))
    assert sd.provider_config["hapi"]["endpoint"] == "affected-people/idps"


def test_reliefweb_is_skipped_until_an_appname_is_approved(session):
    src = session.scalar(select(Source).where(Source.key == "reliefweb_api"))
    assert src.enabled
    assert ingest_news(session, only="reliefweb_api")["reliefweb_api"] == "skipped"


def test_dtm_metric_falls_back_to_hapi_without_a_dtm_key(session, monkeypatch):
    from app.providers import hdx
    from app.providers.base import FetchResult, MetricReading
    monkeypatch.setenv("HDX_APP_NAME", "albushra")
    monkeypatch.setenv("HDX_APP_EMAIL", "ops@example.org")
    calls = []

    def fake_latest(self, cfg):
        calls.append(cfg["endpoint"])
        assert self.app_identifier  # derived from name + email
        day = date(2026, 8, 31)
        return FetchResult([MetricReading(value=150, period_start=day, period_end=day, published_at=day,
                                          source_url="https://data.humdata.org/dataset/x",
                                          coverage_key=cfg["coverage_key"], producer=cfg["producer"])])
    monkeypatch.setattr(hdx.HapiAdapter, "latest", fake_latest)
    summary = ingest_metrics(session)
    assert summary["sd_idps"] == {"new": 1}
    assert "affected-people/idps" in calls and "affected-people/humanitarian-needs" in calls
    obs = session.scalar(select(Metric).where(Metric.metric_id == "sd_idps")).observations[0]
    # Still IOM DTM's figure (primary producer), via another channel, and pending review.
    assert obs.producer == "IOM DTM" and obs.entered_by == "provider:hapi" and obs.review_status == "pending"
    assert obs.coverage_key == "hapi:idps:SDN:admin1-sum"


def test_hdx_catalogue_search(client, monkeypatch):
    import httpx

    def handler(request):
        assert request.url.path == "/api/3/action/package_search"
        assert request.url.params["fq"] == "groups:sdn"
        return httpx.Response(200, request=request, json={"success": True, "result": {"results": [
            {"title": "Sudan IDPs", "name": "sudan-idps", "organization": {"title": "IOM"},
             "license_title": "CC BY-IGO", "metadata_modified": "2026-10-01T00:00:00",
             "resources": [{"format": "CSV"}, {"format": "XLSX"}]}]}})
    _wp_transport(monkeypatch, handler)
    rows = client.get("/api/admin/hdx/search?q=idps&country=SDN", headers=ADMIN).json()
    assert rows[0]["license"] == "CC BY-IGO" and rows[0]["url"].endswith("/dataset/sudan-idps")
    assert rows[0]["formats"] == ["CSV", "XLSX"]


def test_admin_sign_in_with_username_and_password(client):
    from app import auth
    auth._failures.clear()
    assert client.get("/api/auth/status").json() == {"login_enabled": True}
    r = client.post("/api/auth/login", json={"username": "Editor", "password": "correct horse"})
    assert r.status_code == 200
    token = r.json()["token"]
    me = client.get("/api/admin/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me == {"username": "Editor"}
    tampered = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
    assert client.get("/api/admin/me", headers={"Authorization": f"Bearer {tampered}"}).status_code == 401
    assert client.get("/api/admin/me").status_code == 401


def test_sign_in_locks_out_after_repeated_failures(client):
    from app import auth
    auth._failures.clear()
    codes = [client.post("/api/auth/login", json={"username": "editor", "password": "nope"}).status_code
             for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429
    # Even the right password waits out the lockout.
    assert client.post("/api/auth/login", json={"username": "editor",
                                                 "password": "correct horse"}).status_code == 429
    auth._failures.clear()


def test_expired_session_is_refused(monkeypatch):
    from app import auth
    token, _ = auth.issue("editor")
    assert auth.verify(token) == "editor"
    monkeypatch.setattr(auth.time, "time", lambda: 10**11)
    assert auth.verify(token) is None


def test_admin_address_opens_the_sign_in_page(client):
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/#/admin"


def test_unreadable_feed_falls_back_to_gdelt_for_that_domain(session, monkeypatch):
    from app.ingest import _fetch_feed
    from app.providers import gdelt, news
    from app.providers.base import AuthFailed, FetchResult
    calls = {}

    def blocked(self, url, *a, **k):
        raise AuthFailed("provider refused credentials (HTTP 403)")

    def fake_search(self, query, lang, timespan="1d", max_items=50, publisher_name=None,
                    publisher_country=None):
        calls.update(query=query, lang=lang, name=publisher_name)
        return FetchResult([NormalizedArticle(url="https://www.spa.gov.sa/n/1", title="خبر من واس",
                                              publisher_name=publisher_name, provider="gdelt",
                                              published_at=datetime.now(timezone.utc))])
    monkeypatch.setattr(news.RssAdapter, "fetch", blocked)
    monkeypatch.setattr("app.ingest.discover_feeds", lambda http, site: [])
    monkeypatch.setattr(gdelt.GdeltAdapter, "search", fake_search)
    spa = session.scalar(select(Source).where(Source.key == "spa"))
    assert spa.config["gdelt_domain"] == "spa.gov.sa"
    result = _fetch_feed(spa, 0, spa.config["feeds"][0])
    assert calls == {"query": "domain:spa.gov.sa", "lang": "ar", "name": spa.name}
    assert result.items[0].publisher_name == "واس — وكالة الأنباء السعودية"


def test_story_seen_again_in_a_humanitarian_feed_becomes_a_humanitarian_update(session):
    item = dict(url="https://news.un.org/en/story/1", title="Aid reaches Sudan", publisher_name="UN News",
                published_at=datetime.now(timezone.utc), provider="rss")
    first = store_article(session, NormalizedArticle(**item), None)
    assert first.content_type == "news"
    assert store_article(session, NormalizedArticle(**item, content_type="humanitarian_report"), None) is None
    assert first.content_type == "humanitarian_report"


def test_static_export_builds_a_complete_read_only_site(session, tmp_path, monkeypatch):
    import importlib.util
    _article(session, "نزوح جديد في دارفور", "https://n.sd/1", language="ar")
    session.commit()
    spec = importlib.util.spec_from_file_location(
        "export_static", Path(__file__).resolve().parents[1] / "scripts" / "export_static.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "SessionLocal", lambda: session.__class__(bind=session.get_bind()))
    monkeypatch.setattr(mod, "init_db", lambda: None)
    assert mod.export_data(str(tmp_path / "data")) == 1
    mod.build_site(str(tmp_path / "data"), str(tmp_path / "site"))
    index = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert 'name="albushra-static"' in index and 'href="/' not in index and 'src="/' not in index
    meta = json.loads((tmp_path / "site" / "data" / "meta.json").read_text(encoding="utf-8"))
    assert meta["static"]["generated_at"]
    for name in ("articles.json", "sources.json", "dashboard-world.json", "dashboard-sudan.json",
                 "metrics/sd_idps.json"):
        assert (tmp_path / "site" / "data" / name).is_file(), name
    assert (tmp_path / "site" / "assets" / "js" / "static.js").is_file()


def test_saudi_page_takes_stories_about_saudi_and_saudi_publishers_local_news(client, session):
    _article(session, "ولي العهد يستقبل وفدًا في الرياض", "https://n.com/sa1")
    local = store_article(session, NormalizedArticle(
        url="https://spa.gov.sa/x", title="افتتاح مشروع جديد", publisher_name="واس", publisher_country="SA",
        published_at=datetime.now(timezone.utc), provider="rss", language="ar"), None)
    _article(session, "اشتباكات في الفاشر", "https://n.com/sd1")
    session.commit()
    titles = {a["title"] for a in client.get("/api/articles?section=saudi").json()["items"]}
    assert titles == {"ولي العهد يستقبل وفدًا في الرياض", local.title}
    assert "saudi" in client.get("/api/meta").json()["sections"]


def test_images_shown_by_default_and_hidden_by_the_source_switch(client, session):
    src = session.scalar(select(Source).where(Source.key == "bbc"))
    store_article(session, NormalizedArticle(
        url="https://bbc.com/a", title="Story with a photo", publisher_name="BBC",
        image_url="https://ichef.bbci.co.uk/p.jpg",
        published_at=datetime.now(timezone.utc), provider="rss", language="en"), src)
    session.commit()
    item = client.get("/api/articles?q=photo").json()["items"][0]
    assert item["image_url"] == "https://ichef.bbci.co.uk/p.jpg"
    src.allow_images = False
    session.commit()
    assert client.get("/api/articles?q=photo").json()["items"][0]["image_url"] is None
