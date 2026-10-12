"""ReliefWeb API v2: humanitarian reports as JSON.

Needs an application name approved by ReliefWeb (RELIEFWEB_APPNAME) and is
limited to 1,000 calls a day. ReliefWeb carries documents from many
publishers, each with its own rights, so only the title, the publishing
organisation, the date and the link are stored; the report body is not.
"""
from __future__ import annotations

from .base import FetchResult, HttpClient, NormalizedArticle, NotConfigured, ProviderError, parse_datetime
from ..classify import detect_countries
from ..config import get_settings

BASE_URL = "https://api.reliefweb.int/v2/reports"


class ReliefWebAdapter:
    provider = "reliefweb"

    def __init__(self, http: HttpClient | None = None, appname: str | None = None):
        self.http = http or HttpClient()
        self.appname = appname if appname is not None else get_settings().reliefweb_appname

    def reports(self, countries_iso3: list[str] | None = None, limit: int = 30) -> FetchResult:
        if not self.appname:
            raise NotConfigured("RELIEFWEB_APPNAME is not set (ReliefWeb must approve it first)")
        query = {
            "limit": limit, "sort": ["date.created:desc"],
            "fields": {"include": ["title", "url_alias", "url", "date.created", "source.name",
                                   "source.shortname", "language.code", "primary_country.name",
                                   "country.name", "format.name"]},
        }
        if countries_iso3:
            query["filter"] = {"field": "primary_country.iso3", "value": countries_iso3}
        response, latency = self.http.request("POST", BASE_URL, params={"appname": self.appname},
                                              json=query)
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderError("ReliefWeb returned non-JSON body") from exc
        if not isinstance(body, dict) or "data" not in body:
            raise ProviderError("unexpected ReliefWeb response")
        items = []
        for row in body["data"]:
            f = row.get("fields") or {}
            link = f.get("url_alias") or f.get("url") or (f"https://reliefweb.int/node/{row['id']}"
                                                          if row.get("id") else None)
            published = parse_datetime((f.get("date") or {}).get("created"))
            if not (link and f.get("title") and published):
                continue
            sources = f.get("source") or []
            publisher = (sources[0].get("shortname") or sources[0].get("name")) if sources else "ReliefWeb"
            langs = [l.get("code") for l in f.get("language") or [] if l.get("code")]
            primary = f.get("primary_country")
            named = ([primary] if isinstance(primary, dict) else primary or []) or f.get("country") or []
            places = " ".join(c.get("name", "") for c in named if isinstance(c, dict))
            items.append(NormalizedArticle(
                url=link, title=" ".join(f["title"].split())[:400],
                publisher_name=f"{publisher} · ReliefWeb", publisher_url="https://reliefweb.int",
                published_at=published, provider=self.provider,
                language="ar" if "ar" in langs else "en" if "en" in langs else (langs[0] if langs else None),
                content_type="humanitarian_report",
                # ReliefWeb's own country names go through the same gazetteer.
                places=detect_countries(places)))
        return FetchResult(items, response.headers.get("x-ratelimit-remaining"), latency)
