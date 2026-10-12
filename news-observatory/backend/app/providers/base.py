"""What every provider adapter shares.

An adapter turns one provider's response into NormalizedArticle (or
MetricReading) records and nothing else. Swapping a provider means writing one
adapter; ingestion, storage and the API do not change.

Failure is always an exception, never an empty-but-successful result, so a
dead provider cannot quietly show up as "no news" or as a zero.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from ..config import get_settings


class ProviderError(Exception):
    status = "error"


class QuotaExceeded(ProviderError):
    status = "quota"


class AuthFailed(ProviderError):
    status = "auth"


class NotConfigured(ProviderError):
    status = "skipped"


@dataclass
class NormalizedArticle:
    url: str
    title: str
    publisher_name: str
    published_at: datetime
    provider: str
    language: str | None = None
    description: str | None = None
    publisher_url: str | None = None
    publisher_country: str | None = None
    image_url: str | None = None
    content_type: str = "news"
    # Topics the feed itself guarantees (a sports feed is sports), added to
    # whatever the classifier finds.
    topics: list[str] = field(default_factory=list)
    # Countries the provider itself names for the story (ReliefWeb does).
    places: list[str] = field(default_factory=list)
    author: str | None = None


@dataclass
class MetricReading:
    """One value as a provider reports it, before validation."""
    value: float
    period_start: date
    period_end: date
    published_at: date
    source_url: str
    coverage_key: str
    period_label: str | None = None
    number_type: str | None = None
    producer: str | None = None
    coverage_note: str | None = None
    methodology_note: str | None = None


@dataclass
class FetchResult:
    items: list = field(default_factory=list)
    quota_remaining: str | None = None
    latency_ms: int = 0


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    iso = value.strip().replace("Z", "+00:00")
    if " " in iso and "T" not in iso:
        iso = iso.replace(" ", "T", 1)
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        try:
            dt = parsedate_to_datetime(value.strip())
        except (TypeError, ValueError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class HttpClient:
    """httpx with bounded retries. 429 and 401/403 are not retried."""

    def __init__(self, transport: httpx.BaseTransport | None = None, retries: int = 2,
                 backoff: float = 1.0):
        self.retries = retries
        self.backoff = backoff
        self._client = httpx.Client(
            timeout=get_settings().http_timeout_seconds, transport=transport,
            # Identify honestly, in the form feed readers use; never as a browser.
            headers={"User-Agent": "Mozilla/5.0 (compatible; AlBushraNews/1.0; news feed reader)",
                     "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, "
                               "application/json;q=0.9, text/html;q=0.8, */*;q=0.5"},
            follow_redirects=True)

    def request(self, method: str, url: str, **kwargs) -> tuple[httpx.Response, int]:
        attempt = 0
        started = time.monotonic()
        while True:
            try:
                response = self._client.request(method, url, **kwargs)
            except httpx.TransportError as exc:
                if attempt >= self.retries:
                    raise ProviderError(f"network error: {exc.__class__.__name__}") from exc
            else:
                if response.status_code == 429:
                    raise QuotaExceeded("provider rate limit or quota exhausted (HTTP 429)")
                if response.status_code in (401, 403):
                    raise AuthFailed(f"provider refused credentials (HTTP {response.status_code})")
                if response.status_code < 500:
                    if response.status_code >= 400:
                        raise ProviderError(_error_text(response))
                    return response, int((time.monotonic() - started) * 1000)
                if attempt >= self.retries:
                    raise ProviderError(_error_text(response))
            attempt += 1
            time.sleep(self.backoff * (2 ** (attempt - 1)))

    def get_json(self, url: str, **kwargs):
        response, latency = self.request("GET", url, **kwargs)
        try:
            return response.json(), response, latency
        except ValueError as exc:
            raise ProviderError("provider returned non-JSON body") from exc


def _error_text(response: httpx.Response) -> str:
    """Status plus the provider's own message, without echoing our query string (keys)."""
    detail = ""
    try:
        body = response.json()
        if isinstance(body, dict):
            detail = str(body.get("message") or body.get("errors") or body.get("error") or "")[:300]
    except ValueError:
        pass
    return f"HTTP {response.status_code}" + (f": {detail}" if detail else "")
