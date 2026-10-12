// Pages. Each view returns a node (or a promise of one) for <main>.
import { icon } from "./icons.js";
import { translateButton, translatedPageUrl, targetLanguage } from "./translate.js";
import { h, t, L, settings, saveSettings, saved, prefs, api, qs, fmtDate, fmtDateTime, fmtNumber,
  fmtPeriod, externalLink, langName } from "./core.js";
import { META, metricCard, articleList, emptyState, errorState, loading, trendChart, typeBadge,
  countryName, observationFacts, valueBlock, bdi, demoBadge, flag, avatar, countryChip,
  TOPIC_ICONS, leadStory, newsTicker } from "./components.js";

function section(titleKey, ...children) {
  return h("section", { class: "block" }, h("h2", {}, t(titleKey)), ...children);
}

function lazy(promiseFn) {
  const slot = h("div", { class: "lazy" }, loading());
  promiseFn().then(node => slot.replaceChildren(...(node ? [node] : [])))
    .catch(err => slot.replaceChildren(errorState(err)));
  return slot;
}

// --- home ---------------------------------------------------------------
export function homeView(params) {
  const scope = params.get("scope") || "world";
  const scopes = META.scopes;
  const switcher = h("div", { class: "segmented", role: "tablist", "aria-label": t("home.scope") },
    scopes.map(s => h("a", { role: "tab", href: `#/?scope=${s.key}`, "aria-selected": String(s.key === scope),
      class: s.key === scope ? "active" : "" },
      s.countries.length === 1 ? flag(s.countries[0]) : icon("world", 16), L(s.name))));

  const header = h("div", { class: "home-head" },
    h("div", {},
      h("h1", {}, t("home.title")),
      h("p", { class: "muted" }, t("home.lede"))),
    h("div", { class: "updated" },
      h("span", { class: "muted small" }, t("home.updated")), " ",
      h("strong", {}, META.last_updated ? bdi(fmtDateTime(META.last_updated)) : t("home.never")),
      h("div", { class: "muted small" }, META.refresh_minutes?.news === 60
        ? t("home.cadence") : t("home.cadence.minutes", { n: META.refresh_minutes?.news }))),
    switcher);

  const dashboard = api(`/api/dashboard${qs({ scope })}`);
  dashboard.catch(() => {}); // each consumer renders its own error
  const cards = lazy(async () => {
    const data = await dashboard;
    if (!data.cards.length) return emptyState(t("empty.metrics"));
    // Indicators with a current value get a full card. Those without one are
    // listed compactly, each still saying plainly that no recent verified
    // data is available, so the front page is not a wall of empty cards.
    const live = data.cards.filter(c => c.status === "current");
    const waiting = data.cards.filter(c => c.status !== "current");
    return h("div", {},
      live.length ? h("div", { class: "grid cards" }, live.map(c => metricCard(c))) : null,
      waiting.length ? h("details", { class: "waiting card", open: live.length ? null : true },
        h("summary", {}, t("home.waiting", { n: waiting.length })),
        h("ul", { class: "waiting-list" }, waiting.map(c => h("li", {},
          h("a", { href: `#/metric/${c.metric_id}` }, L(c.name)),
          h("span", { class: "muted small" }, t("metric.no_recent")),
          externalLink(c.primary_source_url, c.primary_producer))))) : null);
  });

  // The front page leads in the reader's language when there is enough news
  // in it, and never leads with sport.
  const sectionKey = scope === "world" ? null : scope;
  const news = (async () => {
    const own = await api(`/api/articles${qs({ content_type: "news", per_page: 12, lang: settings.lang,
      section: sectionKey })}`);
    if (own.items.length >= 6) return own;
    return api(`/api/articles${qs({ content_type: "news", per_page: 12, section: sectionKey })}`);
  })();
  news.catch(() => {});
  const topNews = lazy(async () => {
    const data = await news;
    if (!data.items.length) return emptyState(t("empty.articles"));
    const leadIndex = Math.max(0, data.items.findIndex(a => !a.topics.includes("sports")));
    const lead = data.items[leadIndex];
    const rest = data.items.filter((_, i) => i !== leadIndex).slice(0, 8);
    return h("div", { class: "top-stories" }, leadStory(lead),
      rest.length ? articleList(rest, { showDescription: false, grid: true }) : null);
  });
  const ticker = lazy(async () => {
    const data = await api(`/api/articles${qs({ content_type: "news", per_page: 12, sort: "newest" })}`);
    return newsTicker(data.items);
  });

  const trends = lazy(async () => {
    const data = await dashboard;
    const withSeries = data.cards.filter(c => c.status === "current");
    const details = await Promise.all(withSeries.map(c => api(`/api/metrics/${c.metric_id}`)));
    const charts = details.filter(d => d.series.length >= 2);
    if (!charts.length) return emptyState(t("empty.trends"));
    return h("div", { class: "grid trends" }, charts.map(d => h("div", { class: "card" },
      h("h3", { class: "card-title" }, h("a", { href: `#/metric/${d.card.metric_id}` }, L(d.card.name))),
      trendChart(d.series, { height: 130, label: L(d.card.name) }))));
  });

  const humanitarian = lazy(async () => {
    const data = await api(`/api/articles${qs({ content_type: "humanitarian_report", per_page: 6,
      sort: "newest", section: scope === "world" ? null : scope })}`);
    return articleList(data.items);
  });

  const quick = h("div", { class: "quick" },
    h("a", { class: "quick-link", href: "#/section/palestine" }, flag("PS", { size: "lg" }), t("section.palestine")),
    h("a", { class: "quick-link", href: "#/section/sudan" }, flag("SD", { size: "lg" }), t("section.sudan")),
    h("a", { class: "quick-link", href: "#/section/sports" }, icon("sports", 24), t("section.sports")),
    h("a", { class: "quick-link", href: "#/foryou" }, icon("foryou", 24), t("nav.foryou")));

  return h("div", { class: "home" }, ticker, header,
    h("section", { class: "block numbers" }, h("h2", {}, t("home.numbers")), cards),
    h("p", { class: "small muted how-link" }, h("a", { href: "#/how" }, t("how.link"))),
    h("div", { class: "columns" },
      h("div", {}, section("home.top", topNews), section("home.quick", quick)),
      h("div", {},
        section("home.trends", trends),
        h("section", { class: "block humanitarian" }, h("h2", {}, t("home.humanitarian")),
          h("p", { class: "muted small" }, t("home.humanitarian.note")), humanitarian))));
}

// --- sections & search filters --------------------------------------------
const SECTION_TITLES = { world: "section.world", palestine: "section.palestine", sudan: "section.sudan",
  arab_world: "section.arab_world", islamic_world: "section.islamic_world" };

function filterBar(params, base) {
  const field = (name, label, control) => h("label", { class: "filter" }, h("span", {}, label), control);
  const select = (name, options, value) => h("select", { name },
    options.map(([v, label]) => h("option", { value: v, selected: v === (value || "") }, label)));
  const countries = Object.keys(META.countries).sort((a, b) => countryName(a).localeCompare(countryName(b), settings.lang));
  const form = h("form", { class: "filters", role: "search" },
    field("q", t("filter.q"), h("input", { name: "q", type: "search", value: params.get("q") || "",
      maxlength: 200, placeholder: t("filter.q.placeholder") })),
    field("lang", t("filter.lang"), select("lang", [["", t("filter.any")], ["ar", langName("ar")], ["en", langName("en")]], params.get("lang"))),
    field("country", t("filter.country"), select("country", [["", t("filter.any")], ...countries.map(c => [c, countryName(c)])], params.get("country"))),
    field("topic", t("filter.topic"), select("topic", [["", t("filter.any")], ...META.topics.map(x => [x, t(`topic.${x}`)])], params.get("topic"))),
    field("content_type", t("filter.ctype"), select("content_type", [["", t("filter.any")], ...META.content_types.map(x => [x, t(`ctype.${x}`)])], params.get("content_type"))),
    field("hours", t("filter.time"), select("hours", [["", t("filter.any")], ["6", t("filter.h6")], ["24", t("filter.h24")], ["168", t("filter.d7")], ["720", t("filter.d30")]], params.get("hours"))),
    field("source", t("filter.source"), h("input", { name: "source", value: params.get("source") || "", maxlength: 200 })),
    field("sort", t("filter.sort"), select("sort", [["relevance", t("filter.sort.relevance")], ["newest", t("filter.sort.newest")]], params.get("sort"))),
    h("button", { type: "submit", class: "btn" }, t("filter.apply")));
  form.addEventListener("submit", e => {
    e.preventDefault();
    const p = new URLSearchParams();
    for (const [k, v] of new FormData(form)) if (v) p.set(k, v);
    location.hash = `${base}?${p}`;
  });
  return form;
}

function pager(data, params, base) {
  if (data.pages <= 1) return null;
  const link = (page, label) => { const p = new URLSearchParams(params); p.set("page", page);
    return h("a", { class: "btn ghost", href: `${base}?${p}` }, label); };
  return h("nav", { class: "pager", "aria-label": t("pager.label") },
    data.page > 1 ? link(data.page - 1, t("pager.prev")) : null,
    h("span", { class: "muted" }, t("pager.of", { page: data.page, pages: data.pages })),
    data.page < data.pages ? link(data.page + 1, t("pager.next")) : null);
}

export function sectionView(params, key) {
  const base = `#/section/${key}`;
  const region = META.region_lists.find(r => r.key === key);
  const scope = META.scopes.find(s => s.key === key);
  const title = SECTION_TITLES[key] ? t(SECTION_TITLES[key]) : scope ? L(scope.name) : key;
  const note = region
    ? h("details", { class: "definition" }, h("summary", {}, t("section.definition", { n: region.countries.length })),
        h("p", {}, L(region.definition)),
        h("p", { class: "small" }, region.countries.map(countryName).join(settings.lang === "ar" ? "، " : ", ")),
        region.reference_url ? h("p", { class: "small" }, externalLink(region.reference_url, t("section.reference"))) : null)
    : h("p", { class: "muted small" }, t(`section.${key}.note`) !== `section.${key}.note` ? t(`section.${key}.note`) : "");
  const list = lazy(async () => {
    const p = Object.fromEntries(params);
    const data = await api(`/api/articles${qs({ ...p, section: key })}`);
    return h("div", {}, h("p", { class: "muted small" }, t("results.count", { n: data.total })),
      articleList(data.items), pager(data, params, base));
  });
  const mark = key === "sports" ? icon("sports", 28) : key === "world" ? icon("world", 28)
    : key === "arab_world" ? icon("arab", 28) : key === "islamic_world" ? icon("islamic", 28)
    : scope?.countries?.length === 1 ? flag(scope.countries[0], { size: "lg" }) : null;
  const flags = region ? h("div", { class: "flag-strip", "aria-hidden": "true" }, region.countries.map(c => flag(c))) : null;
  return h("div", {}, h("h1", { class: "page-title" }, mark, title), flags, note, filterBar(params, base), list);
}

// --- article ----------------------------------------------------------------
export async function articleView(id) {
  const data = await api(`/api/articles/${encodeURIComponent(id)}`);
  const a = data.article;
  const dir = a.language === "ar" ? "rtl" : a.language === "en" ? "ltr" : "auto";
  const saveBtn = h("button", { class: "btn ghost", type: "button" },
    saved.has(a.id) ? t("article.unsave") : t("article.save"));
  saveBtn.addEventListener("click", () => {
    saveBtn.textContent = saved.toggle(a) ? t("article.unsave") : t("article.save");
  });
  const title = h("h1", { lang: a.language, dir }, a.title);
  const lede = a.description ? h("p", { class: "lede", lang: a.language, dir }, a.description) : null;
  const shareBtn = h("button", { class: "btn ghost", type: "button" }, t("article.share"));
  shareBtn.addEventListener("click", async () => {
    try {
      if (navigator.share) await navigator.share({ title: a.title, url: a.url });
      else { await navigator.clipboard.writeText(a.url); shareBtn.textContent = t("article.copied"); }
    } catch { /* dismissed */ }
  });
  const facts = h("dl", { class: "facts" },
    h("div", { class: "fact" }, h("dt", {}, t("article.publisher")), h("dd", { class: "with-avatar" },
      avatar(a.publisher.name), bdi(a.publisher.name),
      a.publisher.country ? h("span", { class: "muted" }, ` · ${t("article.publisher_country")} `, flag(a.publisher.country),
        ` ${countryName(a.publisher.country)}`) : null)),
    a.author ? h("div", { class: "fact" }, h("dt", {}, t("article.writer")), h("dd", {}, bdi(a.author))) : null,
    h("div", { class: "fact" }, h("dt", {}, t("article.language")), h("dd", {}, langName(a.language))),
    h("div", { class: "fact" }, h("dt", {}, t("article.published")), h("dd", {}, bdi(fmtDateTime(a.published_at)))),
    h("div", { class: "fact" }, h("dt", {}, t("article.fetched")), h("dd", {}, bdi(fmtDateTime(a.fetched_at)))),
    h("div", { class: "fact" }, h("dt", {}, t("article.about")), h("dd", {},
      a.event_countries.length ? a.event_countries.map(countryChip) : t("article.about.none"),
      h("span", { class: "muted small" }, ` · ${a.classification_edited ? t("article.class.edited") : t("article.class.auto")}`))),
    a.topics.length ? h("div", { class: "fact" }, h("dt", {}, t("filter.topic")),
      h("dd", {}, a.topics.map(x => t(`topic.${x}`)).join(settings.lang === "ar" ? "، " : ", "))) : null);
  return h("article", { class: "article-page" },
    h("div", { class: "article-meta" }, a.content_type !== "news" ? h("span", { class: "badge ctype" }, t(`ctype.${a.content_type}`)) : null,
      a.is_demo ? demoBadge() : null),
    title,
    lede,
    h("p", { class: "muted small" }, t("article.summary_note")),
    h("div", { class: "actions" },
      h("a", { class: "btn", href: a.url, target: "_blank", rel: "noopener noreferrer" }, t("article.open_original"), " ↗"),
      translateButton(a.language, [{ el: title, block: title }, ...(lede ? [{ el: lede, block: lede }] : [])]),
      h("a", { class: "btn ghost", href: translatedPageUrl(a.url, targetLanguage(a.language)), target: "_blank",
        rel: "noopener noreferrer" }, t(`translate.page_${targetLanguage(a.language)}`), " ↗"),
      saveBtn, shareBtn),
    facts,
    data.source?.license_note ? h("p", { class: "muted small" }, t("article.terms"), " ", data.source.license_note) : null,
    data.same_story.length ? section("article.same_story", articleList(data.same_story, { showDescription: false })) : null,
    data.related.length ? section("article.related", articleList(data.related, { showDescription: false })) : null);
}

// --- metric -------------------------------------------------------------
export async function metricView(id) {
  const d = await api(`/api/metrics/${encodeURIComponent(id)}`);
  const c = d.card;
  const shown = c.current || c.last_known;
  const historyRows = d.history.map(o => h("tr", { class: o.superseded ? "superseded" : "" },
    h("td", {}, bdi(`v${o.version}`)),
    h("td", {}, bdi(fmtNumber(o.value), "ltr"), " ", L(o.unit)),
    h("td", {}, bdi(fmtPeriod(o)), o.period_label ? h("div", { class: "muted small" }, o.period_label) : null),
    h("td", {}, bdi(fmtDate(o.published_at))),
    h("td", {}, typeBadge(o.number_type)),
    h("td", {}, externalLink(o.source_url, o.producer)),
    h("td", { class: "small" }, o.superseded ? t("history.superseded") : "",
      o.correction_note ? h("div", {}, t("history.correction"), " ", o.correction_note) : null)));
  return h("div", { class: "metric-page" },
    h("p", {}, h("a", { href: `#/?scope=${c.scope}` }, "← ", t("nav.back_dashboard"))),
    metricCard(c),
    c.status === "stale" && shown ? section("metric.last_known",
      h("p", { class: "muted" }, t("metric.last_known.note")), valueBlock(shown, false), observationFacts(shown, c)) : null,
    section("metric.trend", trendChart(d.series, { label: L(c.name) }),
      d.history.length > d.series.length ? h("p", { class: "muted small" }, t("chart.excluded")) : null),
    section("metric.definition",
      h("dl", { class: "facts" },
        h("div", { class: "fact" }, h("dt", {}, t("metric.population")), h("dd", {}, L(c.population))),
        h("div", { class: "fact" }, h("dt", {}, t("metric.method")), h("dd", {}, L(c.methodology))),
        c.uncertainty ? h("div", { class: "fact" }, h("dt", {}, t("metric.uncertainty")), h("dd", {}, L(c.uncertainty))) : null,
        h("div", { class: "fact" }, h("dt", {}, t("metric.max_age")), h("dd", {}, t("metric.max_age.value", { days: c.max_age_days }))),
        h("div", { class: "fact" }, h("dt", {}, t("metric.def_version")), h("dd", {}, bdi(`v${c.definition_version}`))))),
    d.alternatives.length ? section("metric.alt_sources", h("p", { class: "muted small" }, t("metric.alt.note")),
      h("ul", { class: "alts" }, d.alternatives.map(o => h("li", {},
        h("strong", {}, bdi(fmtNumber(o.value), "ltr")), " ", L(o.unit), " — ", externalLink(o.source_url, o.producer),
        h("span", { class: "muted small" }, ` · ${fmtPeriod(o)} · `), typeBadge(o.number_type))))) : null,
    section("metric.history", d.history.length ? h("div", { class: "table-wrap" }, h("table", {},
      h("thead", {}, h("tr", {}, ["history.version", "history.value", "metric.period", "metric.published",
        "history.type", "metric.producer", "history.notes"].map(k => h("th", { scope: "col" }, t(k))))),
      h("tbody", {}, historyRows))) : emptyState(t("history.empty"))));
}

// --- search ---------------------------------------------------------------
export function searchView(params) {
  const q = params.get("q") || "";
  const form = h("form", { class: "searchbar", role: "search" },
    h("input", { type: "search", name: "q", value: q, minlength: 2, maxlength: 200, required: true,
      "aria-label": t("search.label"), placeholder: t("filter.q.placeholder") }),
    h("select", { name: "lang", "aria-label": t("filter.lang") },
      [["", t("filter.any_lang")], ["ar", langName("ar")], ["en", langName("en")]].map(([v, l]) =>
        h("option", { value: v, selected: v === (params.get("lang") || "") }, l))),
    h("button", { class: "btn", type: "submit" }, t("search.go")));
  form.addEventListener("submit", e => {
    e.preventDefault();
    const fd = new FormData(form);
    location.hash = `#/search${qs({ q: fd.get("q"), lang: fd.get("lang") })}`;
  });
  const results = q.trim().length < 2 ? emptyState(t("search.hint")) : lazy(async () => {
    const r = await api(`/api/search${qs({ q, lang: params.get("lang") })}`);
    return h("div", {},
      r.metrics.length ? section("search.metrics", h("ul", { class: "plain" }, r.metrics.map(m =>
        h("li", {}, h("a", { href: `#/metric/${m.metric_id}` }, L(m.name)), " ",
          h("span", { class: "muted small" }, `· ${m.primary_producer}`))))) : null,
      section("search.news", articleList(r.articles.items)),
      section("search.reports", articleList(r.reports.items)),
      r.sources.length ? section("search.sources", h("ul", { class: "plain" }, r.sources.map(s =>
        h("li", {}, externalLink(s.url, s.name))))) : null);
  });
  return h("div", {}, h("h1", {}, t("search.title")), form, results);
}

// --- how we show numbers ----------------------------------------------------
export function howView() {
  const r = META.ranking;
  const p = key => h("p", {}, t(key));
  return h("div", { class: "prose" },
    h("h1", {}, t("how.title")),
    p("how.intro"),
    h("h2", {}, t("how.types")),
    h("dl", { class: "facts" }, ["reported", "verified", "estimated", "projected"].map(x =>
      h("div", { class: "fact" }, h("dt", {}, typeBadge(x)), h("dd", {}, t(`type.${x}.help`))))),
    h("h2", {}, t("how.dates")), p("how.dates.body"),
    h("h2", {}, t("how.stale")), p("how.stale.body"),
    h("h2", {}, t("how.compare")), p("how.compare.body"),
    h("h2", {}, t("how.sources")), p("how.sources.body"),
    h("h2", {}, t("how.casualties")), p("how.casualties.body"),
    h("h2", {}, t("how.economic")), p("how.economic.body"),
    h("h2", {}, t("how.corrections")), p("how.corrections.body"),
    h("h2", {}, t("how.sections")), p("how.sections.body"),
    META.region_lists.map(rl => h("p", { class: "small" }, h("strong", {}, L(rl.name)), ": ", L(rl.definition))),
    h("h2", {}, t("how.ranking")),
    h("p", {}, t("how.ranking.body", { recency: r.recency * 100, breadth: r.breadth * 100,
      reliability: r.reliability * 100, half: r.half_life_hours })),
    h("h2", {}, t("how.translation")), p("how.translation.body"),
    h("h2", {}, t("how.providers")),
    lazy(async () => {
      const sources = await api("/api/sources");
      return h("ul", { class: "plain" }, sources.map(s => h("li", {}, externalLink(s.url, s.name),
        h("span", { class: "muted small" }, ` · ${s.enabled ? t("source.enabled") : t("source.disabled")}`),
        s.license_note ? h("div", { class: "small muted" }, s.license_note) : null)));
    }));
}

// --- settings & saved ----------------------------------------------------
export function settingsView(rerender) {
  let zones = ["UTC"];
  try { zones = Intl.supportedValuesOf("timeZone"); } catch { /* old browser */ }
  if (!zones.includes(settings.timeZone)) zones.unshift(settings.timeZone);
  const radio = (name, value, label) => h("label", { class: "radio" },
    h("input", { type: "radio", name, value, checked: settings[name] === value,
      onchange: () => { saveSettings({ [name]: value }); rerender(); } }), label);
  const tz = h("select", { id: "tz", onchange: e => { saveSettings({ timeZone: e.target.value }); rerender(); } },
    zones.map(z => h("option", { value: z, selected: z === settings.timeZone }, z)));
  return h("div", { class: "prose" },
    h("h1", {}, t("settings.title")),
    h("fieldset", {}, h("legend", {}, t("settings.language")),
      radio("lang", "ar", "العربية"), radio("lang", "en", "English")),
    h("fieldset", {}, h("legend", {}, t("settings.font")),
      radio("fontSize", "s", t("settings.font.s")), radio("fontSize", "m", t("settings.font.m")),
      radio("fontSize", "l", t("settings.font.l"))),
    h("fieldset", {}, h("legend", {}, t("settings.theme")),
      radio("theme", "auto", t("settings.theme.auto")), radio("theme", "dark", t("settings.theme.dark")),
      radio("theme", "light", t("settings.theme.light"))),
    h("fieldset", {}, h("legend", {}, h("label", { for: "tz" }, t("settings.timezone"))), tz),
    window.AlBushraApp ? h("fieldset", {}, h("legend", {}, t("settings.app")),
      h("p", { class: "muted small" }, t("settings.app.note")),
      h("button", { class: "btn ghost", type: "button", onclick: () => window.AlBushraApp.openServerSettings() },
        t("settings.app.server"))) : null,
    h("p", { class: "muted small" }, t("settings.privacy")),
    h("p", { class: "muted small" }, t("settings.alerts_later")));
}

export function savedView() {
  const list = saved.all();
  return h("div", {}, h("h1", {}, t("saved.title")),
    h("p", { class: "muted small" }, t("saved.note")),
    list.length ? h("ul", { class: "articles" }, list.map(a => h("li", { class: "article" },
      h("div", { class: "article-meta" }, h("span", { class: "publisher" }, a.publisher?.name || ""),
        h("time", {}, fmtDateTime(a.published_at))),
      h("h3", { class: "article-title", lang: a.language, dir: "auto" }, h("a", { href: `#/article/${a.id}` }, a.title)),
      h("div", { class: "article-foot" }, externalLink(a.url, t("article.original")))))) : emptyState(t("saved.empty")));
}

// --- sources & topics (the reader's own picks) --------------------------------
const GROUP_ORDER = ["saudi", "arab", "sudan", "sports", "international", "humanitarian"];

function toggleRow(on, onChange, ...label) {
  const input = h("input", { type: "checkbox", role: "switch", checked: on, class: "switch-input" });
  input.addEventListener("change", () => onChange(input.checked));
  return h("label", { class: "toggle-row" }, ...label, input, h("span", { class: "switch", "aria-hidden": "true" }));
}

export async function sourcesView() {
  const list = (await api("/api/sources")).filter(s => s.enabled);
  const p = prefs.get();
  const groups = GROUP_ORDER.map(g => [g, list.filter(s => s.group === g)]).filter(([, l]) => l.length);
  const topics = h("div", { class: "topic-grid" }, META.topics.map(x => {
    const btn = h("button", { type: "button", class: "topic-tile", "aria-pressed": String(p.topics.includes(x)) },
      icon(TOPIC_ICONS[x], 26), h("span", {}, t(`topic.${x}`)));
    btn.addEventListener("click", () => btn.setAttribute("aria-pressed", String(prefs.toggle("topics", x))));
    return btn;
  }));
  return h("div", { class: "sources-page" },
    h("div", { class: "hero card" },
      h("div", {}, h("h1", {}, t("sources.title")), h("p", { class: "muted" }, t("sources.lede"))),
      h("a", { class: "btn", href: "#/foryou" }, icon("foryou", 18), t("sources.show"))),
    h("section", { class: "block" }, h("h2", {}, t("sources.topics")), topics),
    groups.map(([g, items]) => h("section", { class: "block" },
      h("h2", { class: "group-title" }, g === "saudi" ? flag("SA", { size: "lg" }) : g === "sudan" ? flag("SD", { size: "lg" })
        : icon(g === "sports" ? "sports" : g === "arab" ? "arab" : g === "humanitarian" ? "report" : "world", 22),
        t(`group.${g}`)),
      h("div", { class: "card list-card" }, items.map(src => toggleRow(p.sources.includes(src.key),
        () => prefs.toggle("sources", src.key),
        avatar(src.name, { size: "md" }),
        h("span", { class: "toggle-label" }, h("strong", {}, bdi(src.name)),
          h("span", { class: "muted small" }, flag(src.country), " ",
            (src.languages || []).map(langName).join(" · "),
            src.topics.length ? ` · ${src.topics.map(x => t(`topic.${x}`)).join(" · ")}` : ""))))))));
}

export function forYouView(params) {
  const p = prefs.get();
  if (!p.sources.length && !p.topics.length) {
    return h("div", { class: "card empty-hero" }, icon("foryou", 40), h("h1", {}, t("foryou.title")),
      h("p", { class: "muted" }, t("foryou.empty")),
      h("a", { class: "btn", href: "#/sources" }, icon("sources", 18), t("foryou.start")));
  }
  const page = Number(params.get("page") || 1);
  const list = lazy(async () => {
    const data = await api(`/api/articles${qs({ sources: p.sources.join(","), topic: p.topics.join(","),
      sort: "newest", page })}`);
    return h("div", {}, articleList(data.items, { grid: true }), pager(data, params, "#/foryou"));
  });
  return h("div", {},
    h("div", { class: "page-head" }, h("h1", { class: "page-title" }, icon("foryou", 28), t("foryou.title")),
      h("a", { class: "btn ghost", href: "#/sources" }, icon("sources", 18), t("foryou.edit"))),
    h("p", { class: "muted small" }, t("foryou.summary", { s: p.sources.length, t: p.topics.length })), list);
}
