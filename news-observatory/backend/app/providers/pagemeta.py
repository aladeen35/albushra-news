"""Title, summary, picture and date of a story page, for the admin's add-story form.

Read from the tags publishers add for link previews (Open Graph, Twitter
cards, schema.org JSON-LD), with the page's own <title> and description as
fallbacks. The editor reviews everything before saving.
"""
from __future__ import annotations

import ipaddress
import json
import socket
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .base import HttpClient, ProviderError, parse_datetime

MAX_BYTES = 1_500_000


class _MetaParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title = ""
        self.lang = None
        self.jsonld: list[str] = []
        self._in_title = False
        self._in_jsonld = False
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html" and a.get("lang"):
            self.lang = a["lang"]
        elif tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").strip().lower()
            if key and a.get("content") and key not in self.meta:
                self.meta[key] = a["content"].strip()
        elif tag == "title" and not self.title:
            self._in_title = True
        elif tag == "script" and "ld+json" in a.get("type", ""):
            self._in_jsonld, self._buf = True, []

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._in_jsonld:
            self._in_jsonld = False
            self.jsonld.append("".join(self._buf))

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif self._in_jsonld:
            self._buf.append(data)


def _article_ld(blocks: list[str]) -> dict:
    """The first schema.org NewsArticle/Article object in the page, if any."""
    def walk(node):
        if isinstance(node, list):
            for n in node:
                found = walk(n)
                if found:
                    return found
        elif isinstance(node, dict):
            kind = node.get("@type")
            kinds = kind if isinstance(kind, list) else [kind]
            if any(isinstance(k, str) and k.endswith("Article") for k in kinds):
                return node
            return walk(node.get("@graph"))
        return None
    for block in blocks:
        try:
            found = walk(json.loads(block))
        except ValueError:
            continue
        if found:
            return found
    return {}


def _ld_image(value):
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("url")
    return value if isinstance(value, str) else None


def _ld_name(value):
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("name")
    return value if isinstance(value, str) else None


def parse_page(html: str, url: str) -> dict:
    p = _MetaParser()
    try:
        p.feed(html)
    except Exception:  # broken markup: keep what was read
        pass
    m, ld = p.meta, _article_ld(p.jsonld)

    def first(*values):
        for v in values:
            if isinstance(v, str) and v.strip():
                return unescape(v.strip())
        return None

    image = first(m.get("og:image:secure_url"), m.get("og:image"), m.get("twitter:image"),
                  m.get("twitter:image:src"), _ld_image(ld.get("image")))
    if image:
        image = urljoin(url, image)
        if image.startswith("http://"):
            image = "https://" + image[7:]  # the site is served over https; mixed content is blocked
    published = parse_datetime(first(m.get("article:published_time"), ld.get("datePublished"),
                                     m.get("date"), m.get("pubdate"), m.get("dc.date")) or "")
    lang = first(m.get("og:locale"), p.lang, ld.get("inLanguage")) or ""
    title = first(m.get("og:title"), m.get("twitter:title"), ld.get("headline"), p.title)
    return {
        "url": first(m.get("og:url")) or url,
        "title": title[:400] if title else None,
        "description": (first(m.get("og:description"), m.get("twitter:description"),
                              m.get("description"), ld.get("description")) or "")[:1000] or None,
        "image_url": image if image and image.startswith("https://") else None,
        "publisher_name": first(m.get("og:site_name"), _ld_name(ld.get("publisher")),
                                m.get("application-name")),
        "author": first(m.get("author"), m.get("article:author"), _ld_name(ld.get("author"))),
        "published_at": published.isoformat() if published else None,
        "language": lang[:2].lower() or None,
    }


def _public_host(url: str) -> None:
    """Refuse addresses inside private networks; the server is not a proxy to them."""
    host = urlsplit(url).hostname or ""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise ProviderError(f"cannot resolve {host}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ProviderError("address is not on the public internet")


def fetch_page_meta(url: str, http: HttpClient | None = None, check_host: bool = True) -> dict:
    if not url.startswith(("https://", "http://")):
        raise ProviderError("the link must start with https://")
    if check_host:
        _public_host(url)
    response, _ = (http or HttpClient(retries=0)).request(
        "GET", url, headers={"Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"})
    if "html" not in response.headers.get("content-type", "text/html"):
        raise ProviderError("the link is not a web page")
    html = response.content[:MAX_BYTES].decode(response.encoding or "utf-8", errors="replace")
    return parse_page(html, str(response.url))
