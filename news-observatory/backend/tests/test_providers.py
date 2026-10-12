import json
from datetime import date

import httpx
import pytest

from app.providers.base import AuthFailed, HttpClient, NotConfigured, ProviderError, QuotaExceeded
from app.providers.humanitarian import AcledAdapter, DtmAdapter
from app.providers.news import GNewsAdapter, NewsApiAdapter, RssAdapter, WorldNewsAdapter


def client(handler):
    return HttpClient(transport=httpx.MockTransport(handler), backoff=0)


def test_gnews_normalises_and_keeps_publisher_country():
    seen = {}

    def handler(request):
        seen.update(dict(request.url.params))
        return httpx.Response(200, json={"articles": [
            {"title": "Sudan talks", "description": "d", "url": "https://a.com/1",
             "publishedAt": "2026-10-01T10:00:00Z", "source": {"name": "A", "url": "https://a.com"}},
            {"title": "no date", "url": "https://a.com/2"}]})
    res = GNewsAdapter(client(handler), api_key="k").search("Sudan", "ar", country="eg")
    assert seen["lang"] == "ar" and seen["country"] == "eg"
    assert len(res.items) == 1
    assert res.items[0].publisher_country == "eg"  # publisher's country, not the story's


def test_quota_and_auth_are_distinct_failures():
    with pytest.raises(QuotaExceeded):
        GNewsAdapter(client(lambda r: httpx.Response(429)), api_key="k").search("x", "en")
    with pytest.raises(AuthFailed):
        GNewsAdapter(client(lambda r: httpx.Response(401)), api_key="k").search("x", "en")


def test_server_errors_retry_then_fail():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503)
    with pytest.raises(ProviderError):
        GNewsAdapter(client(handler), api_key="k").search("x", "en")
    assert len(calls) == 3


def test_missing_key_is_not_configured():
    with pytest.raises(NotConfigured):
        GNewsAdapter(client(lambda r: httpx.Response(200)), api_key="").search("x", "en")


def test_newsapi_refuses_without_production_plan():
    with pytest.raises(NotConfigured):
        NewsApiAdapter(client(lambda r: httpx.Response(200)), api_key="k",
                       production_plan=False).search("x", "en")


def test_worldnews_sends_key_in_header():
    def handler(request):
        assert request.headers["x-api-key"] == "k" and "api-key" not in request.url.params
        assert request.url.params["source-country"] == "ps"
        return httpx.Response(200, json={"news": [{"title": "t", "url": "https://b.ps/x",
                                                   "publish_date": "2026-10-01 08:00:00",
                                                   "language": "ar", "source_country": "ps"}]})
    res = WorldNewsAdapter(client(handler), api_key="k").search(None, "ar", country="ps")
    assert res.items[0].publisher_name == "b.ps"


def test_rss_and_atom():
    rss = b"""<?xml version="1.0"?><rss><channel><language>ar</language><item><title>t1</title>
    <link>https://p.org/1</link><pubDate>Wed, 01 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>"""
    atom = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><title>t2</title>
    <link href="https://p.org/2"/><updated>2026-10-01T10:00:00Z</updated></entry></feed>"""
    r1 = RssAdapter(client(lambda r: httpx.Response(200, content=rss))).fetch("https://p.org/rss", "P")
    r2 = RssAdapter(client(lambda r: httpx.Response(200, content=atom))).fetch("https://p.org/atom", "P")
    assert r1.items[0].language == "ar" and r2.items[0].url == "https://p.org/2"


def test_rss_rejects_entity_expansion():
    bomb = b"""<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><rss><channel>
    <item><title>&a;</title></item></channel></rss>"""
    with pytest.raises(ProviderError):
        RssAdapter(client(lambda r: httpx.Response(200, content=bomb))).fetch("https://p.org/rss", "P")


def test_dtm_picks_latest_round_and_refuses_ambiguity():
    rows = [{"operation": "Sudan crisis", "numPresentIdpInd": 100, "reportingDate": "2026-05-01", "roundNumber": 1},
            {"operation": "Sudan crisis", "numPresentIdpInd": 120, "reportingDate": "2026-08-01", "roundNumber": 2}]
    res = DtmAdapter(client(lambda r: httpx.Response(200, json={"result": rows})), key="k").latest({})
    assert res.items[0].value == 120 and res.items[0].period_label == "DTM round 2"
    rows.append({"operation": "Other", "numPresentIdpInd": 5, "reportingDate": "2026-08-01"})
    with pytest.raises(ProviderError, match="ambiguous"):
        DtmAdapter(client(lambda r: httpx.Response(200, json={"result": rows})), key="k").latest({})


def test_acled_counts_unique_events_in_window():
    def handler(request):
        if request.url.path.endswith("/oauth/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        assert request.headers["authorization"] == "Bearer tok"
        assert request.url.params["event_date"] == "2026-09-03|2026-10-02"
        return httpx.Response(200, json={"data": [
            {"event_id_cnty": "SDN1", "fatalities": "3", "event_type": "Battles"},
            {"event_id_cnty": "SDN1", "fatalities": "3", "event_type": "Battles"},
            {"event_id_cnty": "SDN2", "fatalities": "0", "event_type": "Protests"}]})
    adapter = AcledAdapter(client(handler), username="u", password="p")
    events = adapter.window({"measure": "events"}, today=date(2026, 10, 9))
    deaths = adapter.window({"measure": "fatalities"}, today=date(2026, 10, 9))
    assert events.items[0].value == 2 and deaths.items[0].value == 3


def test_rss1_rdf_feed_and_html_entities():
    rdf = """<?xml version="1.0"?>
    <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/"
             xmlns:dc="http://purl.org/dc/elements/1.1/">
      <channel><title>DW</title><dc:language>ar</dc:language></channel>
      <item><title>عنوان</title><link>https://dw.com/a</link>
        <description><![CDATA[<p>نص &amp; &quot;وصف&quot;</p>]]></description>
        <dc:date>2026-10-01T10:00:00Z</dc:date></item>
    </rdf:RDF>""".encode()
    res = RssAdapter(client(lambda r: httpx.Response(200, content=rdf))).fetch("https://dw.com/rss", "DW")
    item = res.items[0]
    assert item.language == "ar" and item.url == "https://dw.com/a"
    assert item.description == 'نص & "وصف"'


def test_feed_images_are_read_from_media_and_enclosure():
    rss = b"""<?xml version="1.0"?><rss xmlns:media="http://search.yahoo.com/mrss/"><channel>
    <item><title>a</title><link>https://p.org/1</link><pubDate>Wed, 01 Oct 2026 10:00:00 GMT</pubDate>
      <media:thumbnail url="https://img.p.org/1.jpg"/></item>
    <item><title>b</title><link>https://p.org/2</link><pubDate>Wed, 01 Oct 2026 10:00:00 GMT</pubDate>
      <enclosure url="https://img.p.org/2.png" type="image/png"/></item>
    <item><title>c</title><link>https://p.org/3</link><pubDate>Wed, 01 Oct 2026 10:00:00 GMT</pubDate>
      <enclosure url="https://p.org/3.mp3" type="audio/mpeg"/></item>
    </channel></rss>"""
    res = RssAdapter(client(lambda r: httpx.Response(200, content=rss))).fetch(
        "https://p.org/rss", "P", topics=["sports"])
    assert [i.image_url for i in res.items] == ["https://img.p.org/1.jpg", "https://img.p.org/2.png", None]
    assert all(i.topics == ["sports"] for i in res.items)


def test_discover_feeds_from_site_html():
    from app.providers.news import discover_feeds
    page = """<html><head>
      <link rel="stylesheet" href="/s.css">
      <link rel="alternate" type="application/rss+xml" title="RSS" href="/ar/feed">
      <link type="application/atom+xml" rel="alternate" href="https://cdn.site.sa/atom.xml">
      <link rel="alternate" hreflang="en" href="/en">
    </head></html>"""
    found = discover_feeds(client(lambda r: httpx.Response(200, text=page)), "https://site.sa/ar")
    assert found == ["https://site.sa/ar/feed", "https://cdn.site.sa/atom.xml"]


WP_POSTS = [{
    "link": "https://mysite.sa/2026/10/sudan-aid/", "date_gmt": "2026-10-01T09:00:00",
    "title": {"rendered": "وصول مساعدات إلى الفاشر &#8211; السودان"},
    "excerpt": {"rendered": "<p>قافلة جديدة تصل [&hellip;]</p>"},
    "_embedded": {"author": [{"name": "سارة"}],
                  "wp:featuredmedia": [{"source_url": "https://mysite.sa/wp-content/a.jpg"}],
                  "wp:term": [[{"taxonomy": "category", "name": "رياضة"}], [{"taxonomy": "post_tag", "name": "x"}]]},
}]


def test_wordpress_posts_link_to_the_site_and_carry_extras():
    from app.providers.wordpress import WordPressAdapter

    def handler(request):
        assert request.url.path == "/wp-json/wp/v2/posts" and request.url.params["_embed"] == "1"
        return httpx.Response(200, json=WP_POSTS)
    item = WordPressAdapter(client(handler)).posts("https://mysite.sa", "موقعي", "ar").items[0]
    assert item.url == "https://mysite.sa/2026/10/sudan-aid/"  # opens on the site itself
    assert item.title == "وصول مساعدات إلى الفاشر – السودان"
    assert item.description == "قافلة جديدة تصل …"
    assert item.author == "سارة" and item.image_url.endswith("a.jpg")
    assert item.topics == ["sports"]
    assert item.published_at.isoformat() == "2026-10-01T09:00:00+00:00"


def test_wordpress_without_api_is_an_error_not_an_empty_list():
    from app.providers.wordpress import WordPressAdapter
    with pytest.raises(ProviderError):
        WordPressAdapter(client(lambda r: httpx.Response(200, text="<html>"))).posts("https://x.sa", "x")


def test_gdelt_artlist_and_spacing(monkeypatch):
    from app.providers import gdelt
    waits = []
    monkeypatch.setattr(gdelt.time, "sleep", lambda s: waits.append(s))
    gdelt.GdeltAdapter._last_call = 0.0
    seen = {}

    def handler(request):
        seen.update(dict(request.url.params))
        return httpx.Response(200, json={"articles": [
            {"url": "https://n.sd/a", "title": "خبر  من   الخرطوم", "seendate": "20261012T101500Z",
             "domain": "n.sd", "language": "Arabic", "sourcecountry": "Sudan",
             "socialimage": "https://n.sd/i.jpg"},
            {"url": "https://x.ps/b", "title": "Gaza", "seendate": "20261012T090000Z",
             "domain": "x.ps", "language": "English", "sourcecountry": "Gaza Strip"},
            {"url": "https://bad", "title": "no date", "seendate": ""}]})
    a = gdelt.GdeltAdapter(client(handler))
    first = a.search('"الضفة الغربية"', "ar")
    a.search("Sudan", "en")
    assert seen["mode"] == "artlist" and seen["format"] == "json" and "sourcelang:english" in seen["query"]
    assert [i.publisher_country for i in first.items] == ["SD", "PS"]
    assert first.items[0].title == "خبر من الخرطوم" and first.items[0].language == "ar"
    assert first.items[0].published_at.isoformat() == "2026-10-12T10:15:00+00:00"
    assert waits and waits[-1] > 5  # second call waited for GDELT's 5-second rule


def test_reliefweb_reports_need_an_approved_appname():
    from app.providers.reliefweb import ReliefWebAdapter
    with pytest.raises(NotConfigured):
        ReliefWebAdapter(client(lambda r: httpx.Response(200)), appname="").reports()

    def handler(request):
        assert request.url.params["appname"] == "albushra"
        body = json.loads(request.content)
        assert body["filter"] == {"field": "primary_country.iso3", "value": ["SDN"]}
        return httpx.Response(200, json={"data": [{"id": 9, "fields": {
            "title": "Sudan: Situation Report", "url_alias": "https://reliefweb.int/report/sudan/x",
            "date": {"created": "2026-10-10T08:00:00+00:00"}, "source": [{"shortname": "OCHA"}],
            "language": [{"code": "en"}], "primary_country": {"name": "Sudan"}}}]})
    item = ReliefWebAdapter(client(handler), appname="albushra").reports(["SDN"]).items[0]
    assert item.url == "https://reliefweb.int/report/sudan/x" and item.publisher_name == "OCHA · ReliefWeb"
    assert item.places == ["SD"] and item.content_type == "humanitarian_report" and item.description is None


def _hapi(rows):
    from app.providers.hdx import HapiAdapter

    def handler(request):
        assert request.url.params["app_identifier"] == "aWQ="
        return httpx.Response(200, json={"data": rows})
    return HapiAdapter(client(handler), app_identifier="aWQ=")


def test_hapi_sums_one_dataset_one_period_only():
    rows = [{"admin_level": 1, "population": 100, "reference_period_start": "2026-08-01",
             "reference_period_end": "2026-08-31", "resource_hdx_id": "r1", "dataset_hdx_stub": "sdn-dtm",
             "reporting_round": 20},
            {"admin_level": 1, "population": 50, "reference_period_start": "2026-08-01",
             "reference_period_end": "2026-08-31", "resource_hdx_id": "r1"},
            {"admin_level": 1, "population": 999, "reference_period_start": "2026-05-01",
             "reference_period_end": "2026-05-31", "resource_hdx_id": "r0"}]
    cfg = {"endpoint": "affected-people/idps", "match": {"admin_level": 1}, "aggregate": "sum"}
    r = _hapi(rows).latest(cfg).items[0]
    assert r.value == 150 and str(r.period_end) == "2026-08-31"
    assert r.source_url == "https://data.humdata.org/dataset/sdn-dtm" and r.period_label == "round 20"
    rows[1]["resource_hdx_id"] = "other"
    with pytest.raises(ProviderError, match="different datasets"):
        _hapi(rows).latest(cfg)


def test_hapi_single_refuses_ambiguity_and_empty_matches():
    rows = [{"population": 5, "reference_period_end": "2026-01-01", "sector_name": "Intersectoral"},
            {"population": 6, "reference_period_end": "2026-01-01", "sector_name": "Intersectoral"}]
    with pytest.raises(ProviderError, match="ambiguous"):
        _hapi(rows).latest({"endpoint": "affected-people/humanitarian-needs"})
    with pytest.raises(ProviderError, match="no usable rows"):
        _hapi(rows).latest({"endpoint": "x", "match": {"sector_name": "Health"}})


def test_hapi_never_adds_different_operations_unless_named():
    base = {"admin_level": 1, "reference_period_start": "2026-07-01", "reference_period_end": "2026-07-31",
            "resource_hdx_id": "r1"}
    rows = [{**base, "population": 100, "operation": "Armed Clashes in Sudan"},
            {**base, "population": 100, "operation": "Armed Clashes in Sudan (Overview)"},
            {**base, "population": 30, "operation": "Darfur conflict"}]
    cfg = {"endpoint": "affected-people/idps", "aggregate": "sum"}
    with pytest.raises(ProviderError, match="refusing to add 3 operations"):
        _hapi(rows).latest(cfg)
    named = {**cfg, "operations": ["Armed Clashes in Sudan", "Darfur conflict"]}
    assert _hapi(rows).latest(named).items[0].value == 130


def test_hapi_reads_every_page_before_choosing_the_latest_period():
    from app.providers.hdx import HapiAdapter
    old = [{"population": 1, "reference_period_end": "2024-01-31", "resource_hdx_id": "r"}] * 10000
    new = [{"population": 7, "reference_period_end": "2026-07-31", "resource_hdx_id": "r"}]
    offsets = []

    def handler(request):
        offsets.append(int(request.url.params["offset"]))
        return httpx.Response(200, json={"data": old if offsets[-1] == 0 else new})
    r = HapiAdapter(client(handler), app_identifier="x").latest({"endpoint": "e"}).items[0]
    assert offsets == [0, 10000] and r.value == 7 and str(r.period_end) == "2026-07-31"


def test_hapi_match_accepts_a_list_of_values():
    rows = [{"population": 5, "reference_period_end": "2026-01-01", "category": "total"},
            {"population": 9, "reference_period_end": "2026-01-01", "category": "Adult"}]
    assert _hapi(rows).latest({"endpoint": "e", "match": {"category": ["", "total"]}}).items[0].value == 5


def test_rss_image_from_media_tag_or_item_html():
    rss = b"""<?xml version="1.0"?><rss xmlns:media="http://search.yahoo.com/mrss/"
      xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
      <item><title>a</title><link>https://p.org/a</link><pubDate>Wed, 01 Oct 2026 10:00:00 GMT</pubDate>
        <media:content url="https://p.org/a.jpg" medium="image"/></item>
      <item><title>b</title><link>https://p.org/b</link><pubDate>Wed, 01 Oct 2026 10:00:00 GMT</pubDate>
        <description>&lt;p&gt;&lt;img class="x" src="https://p.org/b.jpg?w=1&amp;h=2"/&gt; text&lt;/p&gt;</description></item>
      <item><title>c</title><link>https://p.org/c</link><pubDate>Wed, 01 Oct 2026 10:00:00 GMT</pubDate>
        <content:encoded><![CDATA[<img src="http://p.org/insecure.jpg">]]></content:encoded></item>
    </channel></rss>"""
    items = RssAdapter(client(lambda r: httpx.Response(200, content=rss))).fetch("https://p.org/rss", "P").items
    assert [i.image_url for i in items] == ["https://p.org/a.jpg", "https://p.org/b.jpg?w=1&h=2", None]
