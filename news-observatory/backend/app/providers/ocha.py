"""Gaza casualty totals from OCHA oPt's weekly Humanitarian Situation Report.

Each report repeats the Ministry of Health's running totals in one sentence:
"…the overall reported casualty toll since the announcement of a ceasefire
agreement on 10 October 2025 to 1,431 fatalities and 5,026 injuries,
according to MoH." The adapter finds the newest report, reads that sentence
and the week it closes, and returns the figure with the report's link. If the
wording changes, nothing is stored and the monitoring tab shows why.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from .base import FetchResult, HttpClient, MetricReading, ProviderError

BASE = "https://www.ochaopt.org"
LIST_PAGES = (f"{BASE}/publications/situation-reports", f"{BASE}/publications", BASE)
_REPORT = re.compile(r'/content/humanitarian-situation-report-(\d{1,2})-([a-z]+)-(\d{4})')
_TOTALS = re.compile(r"since the announcement of a ceasefire agreement on (\d{1,2} [A-Z][a-z]+ \d{4}) "
                     r"to ([\d,]+) fatalities and ([\d,]+) injuries", re.S)
_WEEK = re.compile(r"between (\d{1,2})(?: ([A-Z][a-z]+))? and (\d{1,2}) ([A-Z][a-z]+)")
_MONTHS = {m: i for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july",
                                       "august", "september", "october", "november", "december"), 1)}

_cache: dict[str, tuple[str, str]] = {}  # one download per build, shared by both cards


def _report_date(day: str, month: str, year: str) -> date | None:
    try:
        return date(int(year), _MONTHS[month.lower()], int(day))
    except (KeyError, ValueError):
        return None


def _text(html: str) -> str:
    html = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    return " ".join(re.sub(r"<[^>]+>", " ", html).replace("&nbsp;", " ").split())


def parse_report(text: str, published: date) -> dict | None:
    """The totals and the period they close on, from one report's text."""
    m = _TOTALS.search(text)
    if not m:
        return None
    start = datetime.strptime(m.group(1), "%d %B %Y").date()
    end = published
    week = _WEEK.search(text[max(0, m.start() - 600):m.start()])
    if week:
        month = _MONTHS.get(week.group(4).lower())
        if month:
            year = published.year - (1 if month > published.month else 0)
            end = date(year, month, int(week.group(3)))
    return {"start": start, "end": end, "fatalities": int(m.group(2).replace(",", "")),
            "injuries": int(m.group(3).replace(",", ""))}


class OchaSitrepAdapter:
    provider = "ocha_sitrep"

    def __init__(self, http: HttpClient | None = None):
        self.http = http or HttpClient(retries=1)

    def _latest_reports(self) -> list[tuple[date, str]]:
        found: dict[str, date] = {}
        errors = []
        for page in LIST_PAGES:
            try:
                response, _ = self.http.request("GET", page)
            except ProviderError as exc:
                errors.append(f"{page}: {exc}")
                continue
            for m in _REPORT.finditer(response.text):
                d = _report_date(*m.groups())
                if d:
                    found[BASE + m.group(0)] = d
            if found:
                break
        if not found:
            raise ProviderError("no situation report found on OCHA oPt's site"
                                + (f" ({'; '.join(errors)})" if errors else ""))
        return sorted(((d, u) for u, d in found.items()), reverse=True)

    def latest(self, config: dict) -> FetchResult:
        measure = config.get("measure", "fatalities")
        if "report" not in _cache:
            for published, url in self._latest_reports()[:3]:
                response, _ = self.http.request("GET", url)
                parsed = parse_report(_text(response.text), published)
                if parsed:
                    _cache["report"] = (url, published, parsed)
                    break
            else:
                raise ProviderError("the latest situation reports no longer state the MoH totals "
                                    "in the expected sentence")
        url, published, parsed = _cache["report"]
        return FetchResult([MetricReading(
            value=parsed[measure], period_start=parsed["start"], period_end=parsed["end"],
            published_at=published, source_url=url, number_type="reported", producer="OCHA oPt",
            coverage_key=f"ocha:gaza:moh-since-ceasefire-{parsed['start'].isoformat()}:{measure}",
            period_label=f"منذ إعلان وقف إطلاق النار في {parsed['start'].isoformat()} — بحسب وزارة الصحة في غزة",
            coverage_note="Reported by the Ministry of Health in Gaza, as cited in OCHA's weekly report; "
                          "counted from the ceasefire announcement, not from October 2023.")], None, 0)


def reset_cache() -> None:
    _cache.clear()
