"""GDELT DOC 2.0 API: global news search, free and open, no key.

GDELT asks for at most one request every five seconds and answers 429
otherwise, so the adapter spaces its own calls. Results cover a rolling
three-month window. `seendate` is when GDELT first saw the article, which is
close to, but not the same as, the publisher's own time; we store it as the
publication time and say so in the source's licence note.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from .base import FetchResult, HttpClient, NormalizedArticle, ProviderError, QuotaExceeded
from ..geo import COUNTRIES

BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
MIN_INTERVAL = 5.5  # seconds between calls, per GDELT's published limit
LANGUAGES = {"ar": "arabic", "en": "english"}
_LANG_BACK = {"arabic": "ar", "english": "en"}

# GDELT names countries in English (FIPS-based). Map them to ISO codes.
_COUNTRY_BY_NAME = {v[0].lower(): k for k, v in COUNTRIES.items()}
_COUNTRY_BY_NAME.update({"west bank": "PS", "gaza strip": "PS", "occupied palestinian territory": "PS",
                         "turkey": "TR", "united arab emirates": "AE", "democratic republic of the congo": "CD",
                         "burma": "MM", "ivory coast": "CI", "cote d'ivoire": "CI"})


def _seen(value: str | None) -> datetime | None:
    try:
        return datetime.strptime(value or "", "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class GdeltAdapter:
    provider = "gdelt"
    _last_call = 0.0

    def __init__(self, http: HttpClient | None = None):
        self.http = http or HttpClient()

    def _wait_turn(self) -> None:
        wait = GdeltAdapter._last_call + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        GdeltAdapter._last_call = time.monotonic()

    def search(self, query: str, lang: str | None, timespan: str = "1d", max_items: int = 50,
               publisher_name: str | None = None, publisher_country: str | None = None) -> FetchResult:
        q = f"{query} sourcelang:{LANGUAGES.get(lang, lang)}" if lang else query
        params = {"query": q, "mode": "artlist", "format": "json", "maxrecords": max_items,
                  "sort": "datedesc", "timespan": timespan}
        self._wait_turn()
        try:
            body, response, latency = self.http.get_json(BASE_URL, params=params)
        except QuotaExceeded:
            # GDELT counts by address; shared hosts can trip it. Wait, try once more.
            time.sleep(MIN_INTERVAL * 2)
            self._wait_turn()
            body, response, latency = self.http.get_json(BASE_URL, params=params)
        if not isinstance(body, dict):
            raise ProviderError("unexpected GDELT response")
        items = []
        for a in body.get("articles", []):
            published = _seen(a.get("seendate"))
            if not (a.get("url") and a.get("title") and published):
                continue
            image = a.get("socialimage") or None
            items.append(NormalizedArticle(
                url=a["url"], title=" ".join(a["title"].split())[:400],
                publisher_name=publisher_name or a.get("domain") or "", publisher_url=f"https://{a['domain']}" if a.get("domain") else None,
                publisher_country=publisher_country or _COUNTRY_BY_NAME.get((a.get("sourcecountry") or "").lower()),
                published_at=published, provider=self.provider,
                language=_LANG_BACK.get((a.get("language") or "").lower(), lang),
                image_url=image if image and image.startswith("https://") else None))
        return FetchResult(items, None, latency)
