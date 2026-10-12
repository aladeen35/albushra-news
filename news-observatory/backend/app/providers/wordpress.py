"""WordPress sites, read through the site's own REST API.

Any WordPress site serves /wp-json/wp/v2/posts unless a security plugin has
switched it off; then ingestion falls back to the site's RSS feed (/feed/).
The REST API gives more than the feed: categories, the featured image and the
author. Each article's link is the post's own page on the site, so readers
open the full story there.
"""
from __future__ import annotations

import html
import re
from datetime import datetime

from .base import FetchResult, HttpClient, NormalizedArticle, ProviderError, parse_datetime
from ..classify import detect_topics


def _text(rendered: str | None, limit: int = 600) -> str | None:
    if not rendered:
        return None
    text = html.unescape(re.sub(r"<[^>]+>", " ", rendered))
    text = re.sub(r"\[(?:&hellip;|…|\.\.\.)\]", "…", text)
    text = " ".join(text.split())
    return text[:limit] or None


def api_base(site_url: str) -> str:
    return site_url.rstrip("/") + "/wp-json/wp/v2"


class WordPressAdapter:
    provider = "wordpress"

    def __init__(self, http: HttpClient | None = None):
        self.http = http or HttpClient()

    def posts(self, site_url: str, publisher_name: str, language: str | None = None,
              publisher_country: str | None = None, since: datetime | None = None,
              per_page: int = 20, category_ids: list[int] | None = None) -> FetchResult:
        params = {"per_page": per_page, "orderby": "date", "order": "desc", "_embed": "1",
                  "status": "publish"}
        if since:
            params["after"] = since.strftime("%Y-%m-%dT%H:%M:%S")
        if category_ids:
            params["categories"] = ",".join(str(c) for c in category_ids)
        body, response, latency = self.http.get_json(f"{api_base(site_url)}/posts", params=params)
        if not isinstance(body, list):
            raise ProviderError("not a WordPress posts list (REST API off or not WordPress)")
        items = []
        for post in body:
            link = post.get("link")
            title = _text((post.get("title") or {}).get("rendered"), 400)
            published = parse_datetime((post.get("date_gmt") or "") + "Z" if post.get("date_gmt")
                                       else post.get("date"))
            if not (link and title and published):
                continue
            embedded = post.get("_embedded") or {}
            image = None
            media = embedded.get("wp:featuredmedia") or []
            if media and isinstance(media[0], dict):
                url = media[0].get("source_url")
                image = url if url and url.startswith("https://") else None
            authors = embedded.get("author") or []
            author = authors[0].get("name") if authors and isinstance(authors[0], dict) else None
            terms = [t.get("name", "") for group in embedded.get("wp:term") or [] for t in group
                     if isinstance(t, dict) and t.get("taxonomy") == "category"]
            items.append(NormalizedArticle(
                url=link, title=title, description=_text((post.get("excerpt") or {}).get("rendered")),
                publisher_name=publisher_name, publisher_url=site_url,
                publisher_country=publisher_country, published_at=published,
                provider=self.provider, language=language, image_url=image,
                # The site's own categories ("رياضة", "Sports") are a strong hint.
                topics=detect_topics(" ".join(terms)), author=_text(author, 200)))
        return FetchResult(items, response.headers.get("x-wp-total"), latency)


def probe(http: HttpClient, site_url: str) -> dict:
    """Name and language a WordPress site reports about itself, or raise."""
    body, _, _ = http.get_json(site_url.rstrip("/") + "/wp-json")
    if not isinstance(body, dict) or "namespaces" not in body or "wp/v2" not in body["namespaces"]:
        raise ProviderError("no WordPress REST API at this address")
    return {"name": _text(body.get("name"), 200), "description": _text(body.get("description"), 300),
            "url": body.get("home") or body.get("url") or site_url}
