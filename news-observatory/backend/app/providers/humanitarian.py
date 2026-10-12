"""Humanitarian data adapters: IOM DTM and ACLED.

OCHA oPt has no general public API for its casualty and displacement figures
(several tools are restricted to operational partners), so OCHA numbers enter
through the admin form with a link to the report they came from.

Field names below match the providers' published documentation at the time of
writing and are overridable per metric (Metric.provider_config), because they
change. Verify them against the live docs before enabling a metric.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from .base import (AuthFailed, FetchResult, HttpClient, MetricReading, NotConfigured,
                   ProviderError, parse_datetime)
from ..config import get_settings


class DtmAdapter:
    """IOM Displacement Tracking Matrix, country-level (admin 0) IDP figures.

    DTM figures are periodic assessment rounds, not live counts: the reading's
    period is the round's reporting date, and that is what the card shows.
    """
    provider = "dtm"
    base_url = "https://dtmapi.iom.int/v2"

    def __init__(self, http: HttpClient | None = None, key: str | None = None):
        self.http = http or HttpClient()
        self.key = key if key is not None else get_settings().dtm_subscription_key

    def latest(self, config: dict) -> FetchResult:
        if not self.key:
            raise NotConfigured("DTM_SUBSCRIPTION_KEY is not set")
        endpoint = config.get("endpoint", "IdpAdmin0Data")
        params = dict(config.get("params") or {"CountryName": config.get("country", "Sudan")})
        value_field = config.get("value_field", "numPresentIdpInd")
        date_field = config.get("date_field", "reportingDate")
        round_field = config.get("round_field", "roundNumber")
        operation = config.get("operation")
        body, _, latency = self.http.get_json(
            f"{self.base_url}/{endpoint}", params=params,
            headers={"Ocp-Apim-Subscription-Key": self.key})
        rows = body.get("result") if isinstance(body, dict) else body
        if not isinstance(rows, list):
            raise ProviderError("unexpected DTM response shape")
        if operation:
            rows = [r for r in rows if r.get("operation") == operation]
        dated = [(parse_datetime(str(r.get(date_field) or "")), r) for r in rows
                 if r.get(value_field) is not None]
        dated = [(d, r) for d, r in dated if d]
        if not dated:
            raise ProviderError("DTM returned no rows with a value and a reporting date")
        latest_date = max(d for d, _ in dated)
        latest_rows = [r for d, r in dated if d == latest_date]
        if len(latest_rows) > 1:
            # Several operations reporting on the same day: summing them could
            # double-count. Make the operator choose one in provider_config.
            ops = sorted({str(r.get("operation")) for r in latest_rows})
            raise ProviderError(f"ambiguous: {len(latest_rows)} DTM rows for {latest_date.date()} "
                                f"(operations: {', '.join(ops)}); set provider_config.operation")
        row = latest_rows[0]
        day = latest_date.date()
        label = f"DTM round {row.get(round_field)}" if row.get(round_field) is not None else None
        reading = MetricReading(
            value=float(row[value_field]), period_start=day, period_end=day,
            # DTM rows carry the reporting date, not a separate publication
            # date; we use the reporting date and say so in the methodology.
            published_at=day, period_label=label,
            source_url=config.get("source_url", "https://dtm.iom.int/sudan"),
            coverage_key=config.get("coverage_key", f"dtm:{endpoint}:{params}:{value_field}"),
            coverage_note=row.get("operation"))
        return FetchResult([reading], None, latency)


class AcledAdapter:
    """ACLED conflict-event data, aggregated over a trailing window.

    The result is "events recorded by ACLED" or "fatalities reported in
    ACLED-recorded events": event data under ACLED's methodology, not an
    official or complete casualty count. Metric copy must say so.
    """
    provider = "acled"
    token_url = "https://acleddata.com/oauth/token"
    read_url = "https://acleddata.com/api/acled/read"

    def __init__(self, http: HttpClient | None = None, username: str | None = None,
                 password: str | None = None):
        settings = get_settings()
        self.http = http or HttpClient()
        self.username = username if username is not None else settings.acled_username
        self.password = password if password is not None else settings.acled_password
        self._token: str | None = None

    def _authenticate(self) -> str:
        if not (self.username and self.password):
            raise NotConfigured("ACLED_USERNAME / ACLED_PASSWORD are not set")
        response, _ = self.http.request("POST", self.token_url, data={
            "username": self.username, "password": self.password,
            "grant_type": "password", "client_id": "acled"})
        token = response.json().get("access_token")
        if not token:
            raise AuthFailed("ACLED did not return an access token")
        self._token = token
        return token

    def window(self, config: dict, today: date | None = None) -> FetchResult:
        token = self._token or self._authenticate()
        today = today or date.today()
        # ACLED publishes with a lag; end the window `lag_days` back so the
        # last days are not silently undercounted.
        end = today - timedelta(days=int(config.get("lag_days", 7)))
        start = end - timedelta(days=int(config.get("window_days", 30)) - 1)
        measure = config.get("measure", "events")  # events | fatalities
        params = {"_format": "json", "country": config.get("country", "Sudan"),
                  "event_date": f"{start.isoformat()}|{end.isoformat()}",
                  "event_date_where": "BETWEEN", "fields": "event_id_cnty|event_date|event_type|fatalities",
                  "limit": 5000, "page": 1}
        rows, latency = [], 0
        while True:
            body, _, ms = self.http.get_json(self.read_url, params=params,
                                             headers={"Authorization": f"Bearer {token}"})
            latency += ms
            page = body.get("data") if isinstance(body, dict) else None
            if page is None:
                raise ProviderError("unexpected ACLED response shape")
            rows.extend(page)
            if len(page) < params["limit"] or params["page"] >= 50:
                break
            params["page"] += 1
        unique = {r.get("event_id_cnty"): r for r in rows}.values()
        if measure == "fatalities":
            value = sum(int(r.get("fatalities") or 0) for r in unique)
        else:
            value = len(unique)
        reading = MetricReading(
            value=float(value), period_start=start, period_end=end, published_at=today,
            period_label=f"{start.isoformat()} – {end.isoformat()}",
            source_url=config.get("source_url", "https://acleddata.com/data-export-tool/"),
            coverage_key=f"acled:{params['country']}:{measure}:{config.get('window_days', 30)}d",
            coverage_note=_type_breakdown(unique))
        return FetchResult([reading], None, latency)


def _type_breakdown(rows) -> str:
    counts = Counter(r.get("event_type") for r in rows if r.get("event_type"))
    top = ", ".join(f"{k}: {v}" for k, v in counts.most_common(3))
    return f"{len(rows)} events" + (f" ({top})" if top else "")
