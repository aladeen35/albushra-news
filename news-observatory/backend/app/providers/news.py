"""News adapters: GNews, World News API, NewsAPI.org and RSS/Atom.

Parameter names follow each provider's published documentation at the time of
writing. Providers change them; verify against the live docs before enabling a
source in production (see docs in the README).

Note on `country` parameters: GNews and World News API filter by the country
where the *publisher* is based. Whatever we pass there is stored as
publisher_country, never as the place the story is about.
"""
from __future__ import annotations

import html
import re
from datetime import datetime

import defusedxml.ElementTree as ET

from .base import (FetchResult, HttpClient, NormalizedArticle, NotConfigured, ProviderError,
                   parse_datetime)
from ..config import get_settings


def _clean(text: str | None, limit: int = 600) -> str | None:
    if not text:
        return None
    text = " ".join(str(text).split())
    return text[:limit] if text else None


class GNewsAdapter:
    provider = "gnews"
    base_url = "https://gnews.io/api/v4"

    def __init__(self, http: HttpClient | None = None, api_key: str | None = None):
        self.http = http or HttpClient()
        self.api_key = api_key if api_key is not None else get_settings().gnews_api_key

    def search(self, query: str, lang: str, country: str | None = None,
               since: datetime | None = None, max_items: int = 10) -> FetchResult:
        if not self.api_key:
            raise NotConfigured("GNEWS_API_KEY is not set")
        params = {"q": query, "lang": lang, "max": max_items, "sortby": "publishedAt",
                  "apikey": self.api_key}
        if country:
            params["country"] = country.lower()
        if since:
            params["from"] = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        return self._run("search", params, country, lang)

    def headlines(self, lang: str, category: str = "world", country: str | None = None,
                  max_items: int = 10) -> FetchResult:
        if not self.api_key:
            raise NotConfigured("GNEWS_API_KEY is not set")
        params = {"lang": lang, "category": category, "max": max_items, "apikey": self.api_key}
        if country:
            params["country"] = country.lower()
        return self._run("top-headlines", params, country, lang)

    def _run(self, endpoint: str, params: dict, country: str | None, lang: str) -> FetchResult:
        body, response, latency = self.http.get_json(f"{self.base_url}/{endpoint}", params=params)
        if not isinstance(body, dict) or "articles" not in body:
            raise ProviderError(f"unexpected GNews response: {str(body.get('errors', body))[:200]}"
                                if isinstance(body, dict) else "unexpected GNews response")
        items = []
        for a in body["articles"]:
            published = parse_datetime(a.get("publishedAt"))
            if not (a.get("url") and a.get("title") and published):
                continue
            source = a.get("source") or {}
            items.append(NormalizedArticle(
                url=a["url"], title=_clean(a["title"], 400), description=_clean(a.get("description")),
                publisher_name=source.get("name") or "", publisher_url=source.get("url"),
                publisher_country=(source.get("country") or country or None),
                published_at=published, provider=self.provider, language=a.get("lang") or lang,
                image_url=a.get("image")))
        return FetchResult(items, response.headers.get("x-ratelimit-remaining"), latency)


class WorldNewsAdapter:
    provider = "worldnews"
    base_url = "https://api.worldnewsapi.com"

    def __init__(self, http: HttpClient | None = None, api_key: str | None = None):
        self.http = http or HttpClient()
        self.api_key = api_key if api_key is not None else get_settings().worldnews_api_key

    def search(self, query: str | None, lang: str, country: str | None = None,
               since: datetime | None = None, max_items: int = 20) -> FetchResult:
        if not self.api_key:
            raise NotConfigured("WORLDNEWS_API_KEY is not set")
        params = {"language": lang, "number": max_items, "sort": "publish-time",
                  "sort-direction": "DESC"}
        if query:
            params["text"] = query
        if country:
            params["source-country"] = country.lower()
        if since:
            params["earliest-publish-date"] = since.strftime("%Y-%m-%d %H:%M:%S")
        body, response, latency = self.http.get_json(
            f"{self.base_url}/search-news", params=params, headers={"x-api-key": self.api_key})
        if not isinstance(body, dict) or "news" not in body:
            raise ProviderError("unexpected World News API response")
        items = []
        for a in body["news"]:
            published = parse_datetime(a.get("publish_date"))
            if not (a.get("url") and a.get("title") and published):
                continue
            items.append(NormalizedArticle(
                url=a["url"], title=_clean(a["title"], 400),
                description=_clean(a.get("summary")),
                publisher_name=_host(a["url"]), publisher_country=a.get("source_country") or country,
                published_at=published, provider=self.provider,
                language=a.get("language") or lang, image_url=a.get("image")))
        return FetchResult(items, response.headers.get("x-api-quota-left"), latency)


class NewsApiAdapter:
    provider = "newsapi"
    base_url = "https://newsapi.org/v2"

    def __init__(self, http: HttpClient | None = None, api_key: str | None = None,
                 production_plan: bool | None = None):
        settings = get_settings()
        self.http = http or HttpClient()
        self.api_key = api_key if api_key is not None else settings.newsapi_key
        self.production_plan = (settings.newsapi_production_plan if production_plan is None
                                else production_plan)

    def search(self, query: str, lang: str, country: str | None = None,
               since: datetime | None = None, max_items: int = 20) -> FetchResult:
        if not self.api_key:
            raise NotConfigured("NEWSAPI_KEY is not set")
        if not self.production_plan:
            # The Developer plan is for development only and may not back a
            # published app. Refuse rather than breach the terms.
            raise NotConfigured("NewsAPI requires NEWSAPI_PRODUCTION_PLAN=true (paid plan)")
        params = {"q": query, "language": lang, "pageSize": max_items, "sortBy": "publishedAt"}
        if since:
            params["from"] = since.strftime("%Y-%m-%dT%H:%M:%S")
        body, response, latency = self.http.get_json(
            f"{self.base_url}/everything", params=params, headers={"X-Api-Key": self.api_key})
        if not isinstance(body, dict) or body.get("status") != "ok":
            raise ProviderError(f"NewsAPI error: {body.get('code') if isinstance(body, dict) else ''}")
        items = []
        for a in body.get("articles", []):
            published = parse_datetime(a.get("publishedAt"))
            if not (a.get("url") and a.get("title") and published) or a["title"] == "[Removed]":
                continue
            items.append(NormalizedArticle(
                url=a["url"], title=_clean(a["title"], 400), description=_clean(a.get("description")),
                publisher_name=(a.get("source") or {}).get("name") or _host(a["url"]),
                published_at=published, provider=self.provider, language=lang,
                image_url=a.get("urlToImage")))
        return FetchResult(items, None, latency)


_ATOM = "{http://www.w3.org/2005/Atom}"
_RSS1 = "{http://purl.org/rss/1.0/}"
_RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF"
_DC_DATE = "{http://purl.org/dc/elements/1.1/}date"


class RssAdapter:
    """RSS 2.0 and Atom feeds published officially by a publisher or agency."""
    provider = "rss"

    def __init__(self, http: HttpClient | None = None):
        self.http = http or HttpClient()

    def fetch(self, feed_url: str, publisher_name: str, language: str | None = None,
              publisher_country: str | None = None, content_type: str = "news",
              topics: list[str] | None = None) -> FetchResult:
        response, latency = self.http.request("GET", feed_url)
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise ProviderError(f"feed is not valid XML: {exc}") from exc
        except Exception as exc:  # defusedxml refuses entity tricks
            raise ProviderError(f"feed rejected: {exc.__class__.__name__}") from exc
        items = []
        if root.tag == f"{_ATOM}feed":
            lang = language or root.get("{http://www.w3.org/XML/1998/namespace}lang")
            for entry in root.findall(f"{_ATOM}entry"):
                link = next((l.get("href") for l in entry.findall(f"{_ATOM}link")
                             if l.get("rel", "alternate") == "alternate"), None)
                published = parse_datetime(entry.findtext(f"{_ATOM}published")
                                           or entry.findtext(f"{_ATOM}updated"))
                title = _clean(entry.findtext(f"{_ATOM}title"), 400)
                if link and title and published:
                    items.append(NormalizedArticle(
                        url=link, title=title,
                        description=_clean(_strip_tags(entry.findtext(f"{_ATOM}summary"))),
                        publisher_name=publisher_name, publisher_country=publisher_country,
                        published_at=published, provider=self.provider, language=lang,
                        content_type=content_type, topics=list(topics or []),
                        image_url=_image(entry)))
        elif root.tag == _RDF:  # RSS 1.0 (DW and others)
            lang = language or (root.findtext(f"{_RSS1}channel/{{http://purl.org/dc/elements/1.1/}}language")
                                or "")[:2] or None
            for item in root.findall(f"{_RSS1}item"):
                link = (item.findtext(f"{_RSS1}link") or "").strip()
                published = parse_datetime(item.findtext(_DC_DATE))
                title = _clean(item.findtext(f"{_RSS1}title"), 400)
                if link and title and published:
                    items.append(NormalizedArticle(
                        url=link, title=title,
                        description=_clean(_strip_tags(item.findtext(f"{_RSS1}description"))),
                        publisher_name=publisher_name, publisher_country=publisher_country,
                        published_at=published, provider=self.provider, language=lang,
                        content_type=content_type, topics=list(topics or []),
                        image_url=_image(item)))
        else:
            channel = root.find("channel")
            if channel is None:
                raise ProviderError("feed is not RSS 2.0, RSS 1.0 (RDF) or Atom")
            lang = language or (channel.findtext("language") or "")[:2] or None
            for item in channel.findall("item"):
                link = (item.findtext("link") or "").strip()
                published = parse_datetime(item.findtext("pubDate")
                                           or item.findtext("{http://purl.org/dc/elements/1.1/}date"))
                title = _clean(item.findtext("title"), 400)
                if link and title and published:
                    items.append(NormalizedArticle(
                        url=link, title=title,
                        description=_clean(_strip_tags(item.findtext("description"))),
                        publisher_name=publisher_name, publisher_country=publisher_country,
                        published_at=published, provider=self.provider, language=lang,
                        content_type=content_type, topics=list(topics or []),
                        image_url=_image(item)))
        return FetchResult(items, None, latency)


_MEDIA = "{http://search.yahoo.com/mrss/}"
_CONTENT_ENCODED = "{http://purl.org/rss/1.0/modules/content/}encoded"
_IMG_SRC = re.compile(r"""<img\b[^>]*?\bsrc\s*=\s*["'](https://[^"'\s>]+)""", re.I)


def _image(node) -> str | None:
    """Thumbnail a feed offers (media:thumbnail, media:content, enclosure).

    Stored always, shown only when the source's allow_images is on, because
    the right to display a publisher's photo is separate from the feed.
    """
    for el in (node.find(f"{_MEDIA}thumbnail"), node.find(f"{_MEDIA}content"),
               node.find(f"{_MEDIA}group/{_MEDIA}thumbnail"), node.find("enclosure")):
        if el is None:
            continue
        url = el.get("url")
        kind = el.get("type", "image/") or "image/"
        if url and url.startswith("https://") and kind.startswith("image/"):
            return url
    # Many feeds carry the photo only inside the item's HTML.
    for tag in (_CONTENT_ENCODED, "description", f"{_ATOM}content", f"{_ATOM}summary",
                f"{_RSS1}description"):
        match = _IMG_SRC.search(node.findtext(tag) or "")
        if match:
            return html.unescape(match.group(1))
    return None


_ALT_LINK = re.compile(r"<link\b[^>]*>", re.I)
_ATTR = re.compile(r'(\w[\w-]*)\s*=\s*["\']([^"\']*)["\']')


def discover_feeds(http: "HttpClient", site_url: str) -> list[str]:
    """Feed URLs a site advertises with <link rel="alternate" type="...rss|atom...">.

    Used when a configured feed address stops working: publishers move feeds
    far more often than they drop them.
    """
    from urllib.parse import urljoin
    response, _ = http.request("GET", site_url)
    found = []
    for tag in _ALT_LINK.findall(response.text[:300_000]):
        attrs = {k.lower(): v for k, v in _ATTR.findall(tag)}
        if (attrs.get("rel", "").lower() == "alternate" and attrs.get("href")
                and re.search(r"(rss|atom)\+xml", attrs.get("type", ""), re.I)):
            url = urljoin(str(response.url), attrs["href"])
            if url.startswith("https://") and url not in found:
                found.append(url)
    return found


# WordPress appends "The post X appeared first on Site." to feed summaries.
_WP_FOOTER = re.compile(r"(The post .{0,400}? appeared first on .{0,200}?\.?|ظهرت المقالة .{0,400}? أولاً على .{0,200}?\.?)\s*$",
                        re.S)


def _strip_tags(html: str | None) -> str | None:
    if not html:
        return None
    import html as html_lib
    text = html_lib.unescape(re.sub(r"<[^>]+>", " ", html))
    return _WP_FOOTER.sub("", " ".join(text.split())).strip() or None


def _host(url: str) -> str:
    from urllib.parse import urlsplit
    host = urlsplit(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host
