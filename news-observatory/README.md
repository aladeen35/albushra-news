# البشرى للأخبار — Al-Bushra News

**دليل التشغيل بالعربية: [GUIDE-AR.md](GUIDE-AR.md)** (النشر، لوحة الإدارة، تطبيق أندرويد).

A bilingual (Arabic RTL / English LTR) news reader with a humanitarian numbers
dashboard. Every figure on the dashboard carries its unit, area, the period it
measures, the date its source published it, its type (reported, verified,
estimated or projected), its producer and a link to the original.

## Sources and refresh

News and indicators refresh **every hour** (`NEWS_INTERVAL_MINUTES` and
`METRICS_INTERVAL_MINUTES`, both 60 by default). The scheduler runs inside the
API process by default. Under docker-compose it runs in the `worker` container
instead, so the hourly jobs never run twice.

These sources work without API keys and are switched on from the start. Each
is the outlet's or agency's own public RSS feed. Only the headline, a short
summary, the publisher and a link are shown; images (read from the feed) and
full text stay off until enabled per source.

| Group | Sources |
|---|---|
| Saudi | SPA / واس (ar, en), Al Arabiya / العربية (ar, en, sport), Asharq Al-Awsat / الشرق الأوسط, Arab News |
| Arab | Al Jazeera Net / الجزيرة نت, Sky News Arabia / سكاي نيوز عربية (+ sport), Anadolu Arabic / الأناضول |
| Sudan | SUNA / سونا, Sudan Tribune / سودان تربيون (ar, en), Radio Dabanga / راديو دبنقا (ar, en) |
| Sports | Arriyadiyah / الرياضية, Yallakora / يلا كورة, BBC Sport, plus the sport feeds above |
| International | BBC (ar, en), Al Jazeera English, France 24 (ar, en), DW (ar, en), The Guardian, UN News (ar, en) |
| Humanitarian | ReliefWeb (OCHA) |

The feed addresses could not be fetched from the build environment, whose
network blocks news sites. Each feed therefore also names its site. If the
address fails, the hourly job reads the feed the site itself advertises
(`<link rel="alternate">`), switches to it and records the old address.
Admin → Monitoring shows each feed's last success or error. Before a public
launch, confirm each publisher's reuse terms and tick "Terms reviewed".

### News and data APIs

| Service | What it adds | Access | In the app |
|---|---|---|---|
| GDELT DOC 2.0 | Global news search, Arabic and English | Open, no key; one call per 5 s | On. Runs the Palestine, Sudan and Saudi queries hourly |
| GNews | News search | Key. Free plan: 100 calls a day, 12 h delay, non-commercial | Joins when `GNEWS_API_KEY` is set |
| World News API | News by country (`ps`) and language | Key. Free plan: 50 points a day; only 2 Palestinian sources | Complement only |
| NewsAPI.org | News search | Key. Free plan is development-only | Refuses to run without `NEWSAPI_PRODUCTION_PLAN=true` |
| IOM DTM | Internal displacement, by assessment round | Key from the DTM developer portal | Sudan IDPs; shows the round date |
| HDX HAPI | Standard indicators (IDPs, people in need, …) | App identifier (name + email), no secret | Sudan IDPs when no DTM key is set; people in need for Sudan and Palestine |
| ReliefWeb API | Humanitarian reports | Approved app name; 1,000 calls a day | Title, organisation, date and link only; skipped until `RELIEFWEB_APPNAME` is set |
| HDX CKAN | Dataset catalogue with licences | Open | Admin → HDX datasets, for editors finding a source |

HAPI field names and filters are set per indicator in `provider_config`.
Check the [data-availability table](https://data.humdata.org/hapi) for each
country. If the filters match nothing, or several rows match where one was
expected, the fetch fails and logs why rather than guessing a number. All
figures from providers wait in the review queue before they appear.

### Adding sites and stories (Admin)

- **Add a site:** paste any address. WordPress sites are read through their
  REST API (`/wp-json/wp/v2/posts`: title, excerpt, featured image,
  categories, author), falling back to `/feed/` if the API is switched off.
  Other sites are read through the feed they advertise. A preview of the
  latest posts appears before saving. Once the terms box is ticked, the site
  is fetched immediately and then every hour. Every story links to its own
  page on the site.
- **Add a story:** headline, link, summary, publisher, language, time,
  optional countries and topics (tagged automatically if left empty) and an
  optional image. Editor-added stories are listed with a delete button.

Pages: World in numbers, For you, World, Palestine, Sudan, Sports, Arab world,
Muslim world. "For you" follows the sources and topics a reader picks under
"Sources & topics" (kept in their browser). Country flags are from
[flag-icons](https://github.com/lipis/flag-icons) (MIT) and icons from
[Lucide](https://lucide.dev) (ISC), both served locally.

This is Phase 1 of the implementation spec: a launchable baseline with the
data rules enforced in code. It lives here as a self-contained subproject and
shares nothing with the food-safety platform in the rest of this repository.

## Status

| Area | State |
|---|---|
| Arabic RTL and English LTR interface: menus, errors, search, settings | Built |
| Sections: World, Palestine, Sudan, Arab world, Muslim world, with declared country lists editable in admin | Built |
| Separate fields for article language, publisher country and story location; editor correction of tags | Built |
| Search and filters (language, country, topic, publisher, time, content type), ranking formula published | Built |
| Dedupe by canonical URL; clustering of the same story across publishers | Built |
| Dashboard scopes (World / Palestine / Sudan, plus crises added in admin) | Built |
| Metric rules: refuses values without a unit, period or link; no zero on failure; "no recent verified data" past a per-metric age limit; change shown only for comparable periods; charts only through comparable points; sources listed side by side, never averaged | Built and tested |
| Append-only value history, corrections as new versions, two-person approval of sensitive numbers | Built and tested |
| Adapters: GNews, World News API, NewsAPI.org (refuses to run without a declared paid plan), RSS/Atom, IOM DTM, ACLED | Built and tested against mocked responses; **not yet run against the live APIs** (no keys in this environment) |
| OCHA oPt figures | Entered by editors with a link to the report. OCHA has no general public API for these |
| Admin: monitoring (per-provider errors, latency, quota, data age), review queue, figure entry, sources, country lists, crises | Built |
| Saved articles, sharing the original link, font size, theme, time zone | Built |
| Demo mode with fake data, labelled on every card | Built |
| PostgreSQL | Supported through SQLAlchemy and wired in docker-compose; tests run on SQLite. **Not exercised on Postgres yet** |
| Alerts, machine translation, mobile apps, schema migrations (Alembic) | Not built (Phases 2 and 3). Tables are created at startup |

No humanitarian value ships with the code. The seed holds definitions only,
so until a provider or an editor supplies a figure, each card reads
«لا تتوفر بيانات حديثة موثقة».

## Run it locally

```bash
cd news-observatory/backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
ADMIN_PASSWORD=dev .venv/bin/python -m app.cli demo   # optional: fake, labelled content
ADMIN_PASSWORD=dev .venv/bin/uvicorn app.main:app --port 8000   # also runs the hourly jobs
# http://localhost:8000   admin: http://localhost:8000/admin  (admin / dev)
.venv/bin/pytest                                    # 77 tests
```

Remove the demo content with `python -m app.cli demo --clear`.

## Run with Docker

```bash
cd news-observatory
cp .env.example .env    # set ADMIN_TOKEN and any provider keys
docker compose up -d --build   # http://localhost:8090
```

`api` serves the site and the API. `worker` runs ingestion on its own schedule
and never on page load. Run exactly one worker.

## Turning a provider on

1. Set its key in `.env`. Keys are read only on the server and never reach the browser.
2. Check the provider's current plan, terms and attribution rules. Parameter
   names in `backend/app/providers/` follow the docs as they were when written,
   so verify them against the live docs.
3. In admin, open Sources, tick "Terms reviewed", then "Enabled". The API
   will not enable a source whose terms have not been reviewed.
4. DTM and ACLED metrics fetch automatically once their keys are set. Their
   field mapping can be changed per metric (`provider_config`). If several DTM
   operations report on the same day, the fetch stops with an error rather
   than adding them together.

Run a coverage comparison (Arabic, English, Palestine, Sudan, Arab world)
before relying on any provider. World News API's Palestinian coverage was thin
when evaluated.

## Layout

```
backend/app/
  models.py        sources, articles + tags, region lists, scopes, metrics, observations, fetch logs
  metrics.py       the number rules (validation, staleness, comparability, primary vs alternative)
  classify.py      language, place and topic tagging (Arabic prefix-aware)
  dedupe.py        canonical URLs and title fingerprints
  geo.py           gazetteer, Arab League and OIC member lists
  providers/       one adapter per provider
  ingest.py        news and metric jobs, per-call monitoring logs
  api/public.py    read API     api/admin.py   admin API (bearer token)
  seed.py          definitions only, no values     demo.py   labelled fake data
frontend/          static, dependency-free ES modules; strict CSP; i18n/ar.json, en.json
```

## API

Public: `/api/meta`, `/api/dashboard?scope=`, `/api/metrics/{id}`,
`/api/articles?section=&q=&lang=&country=&topic=&source=&content_type=&hours=&sort=&page=`,
`/api/articles/{id}`, `/api/search?q=`, `/api/sources`. OpenAPI is at `/api/docs`.

Admin (`Authorization: Bearer $ADMIN_TOKEN`): `/api/admin/status`,
`/api/admin/jobs/{ingest-news|ingest-metrics}`, sources, region lists, scopes,
metrics, `POST /metrics/{id}/observations`, `POST /observations/{id}/review`,
`POST /observations/{id}/correct`, `PATCH /articles/{id}/classification`.
