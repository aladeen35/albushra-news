"""HDX: HAPI for ready-made humanitarian indicators, CKAN for finding datasets.

HAPI (https://hapi.humdata.org/api/v2) serves standardised tables, such as
IDPs (from IOM DTM), people in need (from humanitarian needs overviews),
refugees, food security and conflict events, for the countries it covers.
Every call carries an app identifier (base64 of "app name:email"), which
names the caller but is not a secret.

Endpoints, filters and field names follow HAPI's published reference. They
are set per metric in provider_config, so a change on HDX's side is a config
edit. Check the data-availability table (https://data.humdata.org/hapi) for
what exists for each country before enabling a metric.

CKAN (https://data.humdata.org/api/3) is a catalogue: it finds datasets and
their licences, but each dataset is a file to process. The admin uses it to
locate a source for a figure; it does not feed the dashboard directly.
"""
from __future__ import annotations

from datetime import date

from .base import FetchResult, HttpClient, MetricReading, NotConfigured, ProviderError, parse_datetime
from ..config import get_settings

HAPI_BASE = "https://hapi.humdata.org/api/v2"
CKAN_BASE = "https://data.humdata.org/api/3/action"


def _day(value) -> date | None:
    dt = parse_datetime(str(value)) if value else None
    return dt.date() if dt else None


class HapiAdapter:
    provider = "hapi"

    def __init__(self, http: HttpClient | None = None, app_identifier: str | None = None):
        self.http = http or HttpClient()
        self.app_identifier = (app_identifier if app_identifier is not None
                               else get_settings().hdx_identifier)

    def latest(self, config: dict) -> FetchResult:
        """The latest period's value for one indicator.

        config: endpoint ("affected-people/idps"), params (server filters),
        match (row filters applied here, exact equality), value_field,
        aggregate ("single" | "sum"), producer, source_url, coverage_key.

        "sum" adds rows only when they share the latest reference period and
        the same HDX resource, i.e. one dataset's admin-level breakdown of one
        period. Anything else is refused rather than added up.
        """
        if not self.app_identifier:
            raise NotConfigured("HDX_APP_IDENTIFIER (or HDX_APP_NAME + HDX_APP_EMAIL) is not set")
        endpoint = config["endpoint"].strip("/")
        page_size = 10000
        params = {"output_format": "json", "limit": page_size, "offset": 0,
                  "app_identifier": self.app_identifier, **(config.get("params") or {})}
        # Read every page: a truncated result could hide the latest period and
        # make an older value look current.
        rows, latency = [], 0
        for _ in range(30):
            body, _, ms = self.http.get_json(f"{HAPI_BASE}/{endpoint}", params=params)
            latency += ms
            page = body.get("data") if isinstance(body, dict) else None
            if page is None:
                raise ProviderError("unexpected HAPI response shape")
            rows.extend(page)
            if len(page) < page_size:
                break
            params["offset"] += page_size
        else:
            raise ProviderError("HAPI result too large to read completely; narrow `params`")
        value_field = config.get("value_field", "population")
        match = config.get("match") or {}
        def matches(row: dict) -> bool:
            # A list in `match` means "any of these values".
            return all(str(row.get(k)) in ([str(x) for x in v] if isinstance(v, list) else [str(v)])
                       for k, v in match.items())
        rows = [r for r in rows if r.get(value_field) is not None and matches(r)]
        dated = [(_day(r.get("reference_period_end")), r) for r in rows]
        dated = [(d, r) for d, r in dated if d]
        if not dated:
            raise ProviderError(f"HAPI returned no usable rows for {endpoint} with {params | match}")
        latest = max(d for d, _ in dated)
        latest_rows = [r for d, r in dated if d == latest]
        aggregate = config.get("aggregate", "single")
        if aggregate == "single":
            if len(latest_rows) != 1:
                sample = [{k: r.get(k) for k in ("admin_level", "category", "population_group", "gender",
                                                 "age_range", value_field) if k in r} for r in latest_rows[:6]]
                raise ProviderError(f"ambiguous: {len(latest_rows)} HAPI rows for {latest}; "
                                    f"narrow `match`/`params` or use aggregate=sum: {sample}")
            value = float(latest_rows[0][value_field])
        elif aggregate == "sum":
            resources = {r.get("resource_hdx_id") for r in latest_rows}
            if len(resources) != 1:
                raise ProviderError(f"refusing to add rows from {len(resources)} different datasets")
            # Rows from different operations (e.g. a monthly and an overview
            # series of the same displacement) can overlap. Add across
            # operations only when the config names which ones belong together.
            operations = {r.get("operation") for r in latest_rows}
            allowed = config.get("operations")
            if allowed:
                latest_rows = [r for r in latest_rows if r.get("operation") in allowed]
                if not latest_rows:
                    raise ProviderError(f"none of the configured operations {allowed} report for {latest}")
            elif len(operations) > 1:
                breakdown = {op: sum(float(r[value_field]) for r in latest_rows if r.get("operation") == op)
                             for op in operations}
                raise ProviderError(f"refusing to add {len(operations)} operations for {latest} "
                                    f"(set provider_config.operations): {breakdown}")
            value = float(sum(float(r[value_field]) for r in latest_rows))
        else:
            raise ProviderError(f"unknown aggregate: {aggregate}")
        first = latest_rows[0]
        start = _day(first.get("reference_period_start")) or latest
        stub = first.get("dataset_hdx_stub")
        label = " · ".join(str(x) for x in (first.get("operation"), first.get("reporting_round") and
                                             f"round {first['reporting_round']}") if x) or None
        reading = MetricReading(
            value=value, period_start=min(start, latest), period_end=latest,
            # HAPI does not give the source's own publication date; the end of
            # the reference period is the stand-in (or today, for a period such
            # as a plan year that has not ended yet), and is labelled so.
            published_at=min(latest, date.today()), period_label=label,
            source_url=(f"https://data.humdata.org/dataset/{stub}" if stub
                        else config.get("source_url", "https://data.humdata.org/hapi")),
            coverage_key=config.get("coverage_key", f"hapi:{endpoint}:{sorted(params.items())}:{sorted(match.items())}"),
            producer=config.get("producer"),
            coverage_note=f"{len(latest_rows)} row(s) from HDX HAPI ({endpoint})",
            methodology_note="Retrieved through HDX HAPI; publication date shown is the end of the "
                             "reference period.")
        return FetchResult([reading], None, latency)


def ckan_search(http: HttpClient, query: str, country_iso3: str | None = None, rows: int = 10) -> list[dict]:
    """Datasets on HDX matching a query, with their licence and freshness."""
    params = {"q": query, "rows": rows, "sort": "metadata_modified desc"}
    if country_iso3:
        params["fq"] = f"groups:{country_iso3.lower()}"
    body, _, _ = http.get_json(f"{CKAN_BASE}/package_search", params=params)
    if not isinstance(body, dict) or not body.get("success"):
        raise ProviderError("HDX catalogue search failed")
    out = []
    for d in body["result"].get("results", []):
        out.append({"title": d.get("title"), "name": d.get("name"),
                    "url": f"https://data.humdata.org/dataset/{d.get('name')}",
                    "organization": (d.get("organization") or {}).get("title"),
                    "license": d.get("license_title"), "updated": d.get("metadata_modified"),
                    "date_range": d.get("dataset_date"),
                    "formats": sorted({r.get("format") for r in d.get("resources", []) if r.get("format")})})
    return out
