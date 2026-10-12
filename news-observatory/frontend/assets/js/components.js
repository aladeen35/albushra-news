// Reusable pieces: number-type badge, metric card, article row, trend chart.
import { icon } from "./icons.js";
import { translateButton } from "./translate.js";
import { h, t, L, other, settings, fmtNumber, fmtCompact, fmtSigned, fmtDate, fmtDateTime,
  fmtRelative, fmtPeriod, externalLink, langName, saved } from "./core.js";

export let META = null;
export function setMeta(m) { META = m; }

export function countryName(code) {
  const c = META?.countries?.[code];
  return c ? L(c) : code;
}

export function typeBadge(type) {
  // Colour is a hint; the label always says the type in words.
  return h("span", { class: `badge type-${type}`, title: t(`type.${type}.help`) }, t(`type.${type}`));
}

export function demoBadge() {
  return h("span", { class: "badge demo" }, t("demo.badge"));
}

export function bdi(text, dir) {
  return h("bdi", dir ? { dir } : {}, text);
}

export function valueBlock(obs, big = true) {
  const compact = fmtCompact(obs.value);
  return h("div", { class: big ? "value big" : "value" },
    h("span", { class: "num" }, bdi(fmtNumber(obs.value), "ltr")),
    h("span", { class: "unit" }, L(obs.unit)),
    compact ? h("span", { class: "compact" }, "(", bdi(compact), ")") : null,
    obs.value_low !== null && obs.value_low !== undefined
      ? h("div", { class: "range" }, t("metric.range", {
          low: fmtNumber(obs.value_low), high: fmtNumber(obs.value_high) }))
      : null,
    obs.review_status === "pending" ? unreviewedNote(obs) : null);
}

// Figures go live as soon as they arrive; until an editor approves one, say so.
export function unreviewedNote(obs) {
  return h("p", { class: "unreviewed", role: "note" }, icon("alert", 15), " ",
    t("metric.unreviewed", { producer: obs.producer }));
}

function factRow(label, ...value) {
  return h("div", { class: "fact" }, h("dt", {}, label), h("dd", {}, ...value));
}

export function observationFacts(obs, card) {
  return h("dl", { class: "facts" },
    factRow(t("metric.area"), L(obs.area)),
    factRow(t("metric.population"), L(obs.population)),
    factRow(t("metric.period"), bdi(fmtPeriod(obs)),
      obs.period_label ? h("span", { class: "muted" }, ` · ${obs.period_label}`) : null),
    factRow(t("metric.published"), bdi(fmtDate(obs.published_at))),
    factRow(t("metric.fetched"), bdi(fmtDateTime(obs.fetched_at)),
      h("span", { class: "muted small" }, ` · ${t("metric.fetched.note")}`)),
    factRow(t("metric.producer"), externalLink(obs.source_url, obs.producer)),
    card?.methodology ? factRow(t("metric.method"), L(card.methodology)) : null,
    obs.coverage_note ? factRow(t("metric.coverage"), obs.coverage_note) : null,
    card?.uncertainty ? factRow(t("metric.uncertainty"), L(card.uncertainty)) : null);
}

function changeLine(card) {
  if (card.change) {
    const d = card.change.delta;
    return h("p", { class: `change ${d > 0 ? "up" : d < 0 ? "down" : ""}` },
      bdi(fmtSigned(d), "ltr"), " ", L(card.unit), " ",
      h("span", { class: "muted" }, t("metric.change.vs", { period: fmtPeriod(card.change.previous) })));
  }
  const reason = card.change_unavailable_reason;
  return h("p", { class: "change none muted small" },
    t(`change.${reason}`) !== `change.${reason}` ? t(`change.${reason}`) : t("change.none"));
}

export function metricCard(card, { compact = false } = {}) {
  const obs = card.current;
  const scope = META?.scopes?.find(s => s.key === card.scope);
  const head = h("div", { class: "card-head" },
    scope ? h("span", { class: "chip" }, L(scope.name)) : null,
    obs ? typeBadge(obs.number_type) : typeBadge(card.default_number_type),
    (obs || card.last_known)?.is_demo ? demoBadge() : null);
  const title = h("h3", { class: "card-title", id: `m-${card.metric_id}` },
    h("a", { href: `#/metric/${card.metric_id}` }, L(card.name)),
    h("span", { class: "alt-name", lang: settings.lang === "ar" ? "en" : "ar",
      dir: settings.lang === "ar" ? "ltr" : "rtl" }, other(card.name)));

  let body;
  if (card.status === "current") {
    body = [valueBlock(obs), changeLine(card), compact ? h("dl", { class: "facts" },
      factRow(t("metric.period"), bdi(fmtPeriod(obs))),
      factRow(t("metric.producer"), externalLink(obs.source_url, obs.producer))) : observationFacts(obs, card)];
  } else {
    const last = card.last_known;
    body = [h("p", { class: "no-data" }, t("metric.no_recent")),
      h("p", { class: "muted small" }, last
        ? t("metric.stale.detail", { date: fmtDate(last.period_end), days: card.max_age_days })
        : t("metric.no_data.detail", { producer: card.primary_producer })),
      h("dl", { class: "facts" },
        factRow(t("metric.area"), L(card.area)),
        factRow(t("metric.unit"), L(card.unit)),
        factRow(t("metric.producer"), externalLink(card.primary_source_url, card.primary_producer)))];
  }
  return h("article", { class: `card metric status-${card.status}`, "aria-labelledby": `m-${card.metric_id}` },
    head, title, ...body,
    card.alternatives ? h("p", { class: "small" }, h("a", { href: `#/metric/${card.metric_id}` },
      t("metric.alternatives", { n: card.alternatives }))) : null,
    h("a", { class: "more", href: `#/metric/${card.metric_id}` }, t("metric.details")));
}

export const TOPIC_ICONS = { politics: "politics", conflict: "conflict", economy: "economy",
  society: "society", environment: "environment", health: "health", technology: "technology",
  sports: "sports" };

export function flag(code, { size = "sm" } = {}) {
  if (!code || !META?.countries?.[code]) return null;
  return h("img", { class: `flag flag-${size}`, src: `assets/flags/${code.toLowerCase()}.svg`,
    alt: "", title: countryName(code), loading: "lazy", width: size === "lg" ? 28 : 18,
    height: size === "lg" ? 21 : 13.5 });
}

export function countryChip(code) {
  return h("span", { class: "tag" }, flag(code), countryName(code));
}

// A publisher badge: initials on a colour picked from the name, so every
// source is recognisable without hot-linking its logo from its own site.
export function avatar(name, { size = "sm" } = {}) {
  // Letters only (no brackets or dashes). Arabic names get one letter, since
  // joined initials read as a word; Latin names get two.
  const words = (name || "").split(/[\s—–-]+/).map(w => w.replace(/[^\p{L}]/gu, "")).filter(Boolean);
  const arabic = /\p{Script=Arabic}/u.test(words[0] || "");
  const first = arabic ? (words[0].replace(/^ال(?=..)/, "")[0] || "") : words.slice(0, 2).map(w => w[0]).join("");
  let hash = 0;
  for (const ch of name || "") hash = (hash * 31 + ch.codePointAt(0)) >>> 0;
  return h("span", { class: `avatar avatar-${size} hue-${hash % 8}`, "aria-hidden": "true" },
    first.toUpperCase() || "?");
}

function saveButton(a) {
  const btn = h("button", { type: "button", class: "icon-btn", "aria-pressed": String(saved.has(a.id)),
    "aria-label": saved.has(a.id) ? t("article.unsave") : t("article.save") }, icon("saved"));
  btn.addEventListener("click", () => {
    const on = saved.toggle(a);
    btn.setAttribute("aria-pressed", String(on));
    btn.setAttribute("aria-label", on ? t("article.unsave") : t("article.save"));
  });
  return btn;
}

export function articleItem(a, { showDescription = true } = {}) {
  const dir = a.language === "ar" ? "rtl" : a.language === "en" ? "ltr" : "auto";
  const topic = a.topics.find(x => TOPIC_ICONS[x]);
  const titleLink = h("a", { href: `#/article/${a.id}` }, a.title);
  const title = h("h3", { class: "article-title", lang: a.language, dir }, titleLink);
  const desc = showDescription && a.description ? h("p", { class: "article-desc", lang: a.language, dir }, a.description) : null;
  const targets = [{ el: titleLink, block: title }, ...(desc ? [{ el: desc, block: desc }] : [])];
  return h("li", { class: `article card-article ${a.content_type}${a.image_url ? " has-image" : ""}` },
    a.image_url ? h("a", { class: "thumb", href: `#/article/${a.id}`, tabindex: "-1", "aria-hidden": "true" },
      h("img", { src: a.image_url, alt: "", loading: "lazy", referrerpolicy: "no-referrer" })) : null,
    h("div", { class: "article-body" },
      h("div", { class: "article-meta" },
        avatar(a.publisher.name),
        h("span", { class: "publisher" }, bdi(a.publisher.name || "—")),
        flag(a.publisher.country),
        h("span", { class: "dot", "aria-hidden": "true" }, "·"),
        h("time", { datetime: a.published_at, title: fmtDateTime(a.published_at) }, fmtRelative(a.published_at)),
        h("span", { class: "lang-tag", title: t("article.language") }, langName(a.language)),
        a.content_type !== "news" ? h("span", { class: "badge ctype" }, icon("report", 13), t(`ctype.${a.content_type}`)) : null,
        a.is_demo ? demoBadge() : null),
      title,
      desc,
      h("div", { class: "article-foot" },
        topic ? h("span", { class: "topic-chip" }, icon(TOPIC_ICONS[topic], 14), t(`topic.${topic}`)) : null,
        a.event_countries.slice(0, 3).map(countryChip),
        a.other_publishers ? h("span", { class: "muted small" }, t("article.others", { n: a.other_publishers })) : null,
        h("span", { class: "spacer" }),
        externalLink(a.url, t("article.original")),
        translateButton(a.language, targets, { compact: true }),
        saveButton(a))));
}

// The day's lead: the highest-ranked story, given the width a front page gives it.
export function leadStory(a) {
  const dir = a.language === "ar" ? "rtl" : a.language === "en" ? "ltr" : "auto";
  const titleLink = h("a", { href: `#/article/${a.id}` }, a.title);
  const title = h("h2", { class: "lead-title", lang: a.language, dir }, titleLink);
  const desc = a.description ? h("p", { class: "lead-desc", lang: a.language, dir }, a.description) : null;
  const targets = [{ el: titleLink, block: title }, ...(desc ? [{ el: desc, block: desc }] : [])];
  return h("article", { class: `lead-story${a.image_url ? " has-image" : ""}` },
    a.image_url ? h("a", { class: "lead-thumb", href: `#/article/${a.id}`, tabindex: "-1", "aria-hidden": "true" },
      h("img", { src: a.image_url, alt: "", referrerpolicy: "no-referrer" })) : null,
    h("div", { class: "lead-body" },
      h("span", { class: "kicker" }, t("home.lead")),
      title,
      desc,
      h("div", { class: "article-meta" }, avatar(a.publisher.name), h("span", { class: "publisher" }, bdi(a.publisher.name)),
        flag(a.publisher.country), h("span", { class: "dot" }, "·"),
        h("time", { datetime: a.published_at, title: fmtDateTime(a.published_at) }, fmtRelative(a.published_at)),
        a.other_publishers ? h("span", { class: "muted" }, ` · ${t("article.others", { n: a.other_publishers })}`) : null,
        a.is_demo ? demoBadge() : null),
      h("div", { class: "actions" }, h("a", { class: "btn", href: `#/article/${a.id}` }, t("home.lead.read")),
        externalLink(a.url, t("article.open_original")), translateButton(a.language, targets))));
}

// A strip of the latest headlines across the top of the front page.
export function newsTicker(items) {
  if (!items.length) return null;
  return h("div", { class: "ticker", role: "region", "aria-label": t("ticker.label") },
    h("span", { class: "ticker-label" }, icon("radio", 16), t("ticker.label")),
    // The list runs twice so the scroll loops without a jump; the copy is
    // hidden from screen readers and keyboard focus.
    h("div", { class: "ticker-track" }, h("ul", {}, [false, true].map(copy => items.map(a => h("li", copy
      ? { "aria-hidden": "true" } : {},
      h("time", { datetime: a.published_at }, fmtRelative(a.published_at)),
      h("a", { href: `#/article/${a.id}`, lang: a.language, dir: "auto", tabindex: copy ? "-1" : null }, a.title),
      h("span", { class: "ticker-pub" }, a.publisher.name)))))));
}

export function articleList(items, opts) {
  if (!items.length) return emptyState(t("empty.articles"));
  return h("ul", { class: `articles${opts?.grid ? " grid-articles" : ""}` }, items.map(a => articleItem(a, opts)));
}

export function emptyState(text) { return h("p", { class: "empty" }, text); }
export function errorState(err) {
  return h("div", { class: "error", role: "alert" }, h("strong", {}, t("error.title")), " ", err.message || String(err));
}
export function loading() { return h("p", { class: "loading", "aria-busy": "true" }, t("loading")); }

// Line chart for one comparable series. The API only returns a series whose
// points share definition, coverage, unit and type; with fewer than two there
// is nothing honest to draw.
export function trendChart(series, { height = 160, label } = {}) {
  if (!series || series.length < 2) return h("p", { class: "muted small" }, t("chart.insufficient"));
  const W = 560, H = height, P = { l: 76, r: 76, t: 22, b: 26 };
  const xs = series.map(o => new Date(o.period_end + "T00:00:00Z").getTime());
  const ys = series.map(o => o.value);
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
  const lo = Math.min(...ys), hi = Math.max(...ys);
  const pad = (hi - lo) * 0.15 || hi * 0.1 || 1;
  const [y0, y1] = [Math.max(0, lo - pad), hi + pad];
  const rtl = settings.lang === "ar";
  const X = x => { const f = (x - x0) / ((x1 - x0) || 1); return P.l + (rtl ? 1 - f : f) * (W - P.l - P.r); };
  const Y = y => H - P.b - ((y - y0) / ((y1 - y0) || 1)) * (H - P.t - P.b);
  const NS = "http://www.w3.org/2000/svg";
  const s = (tag, attrs) => { const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); return e; };
  // direction=ltr: anchors below are computed in LTR terms; the RTL flip is done in X().
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img", direction: "ltr",
    "aria-label": label || t("chart.label") });
  svg.append(s("line", { x1: P.l, x2: W - P.r, y1: H - P.b, y2: H - P.b, class: "axis" }));
  const d = series.map((o, i) => `${i ? "L" : "M"}${X(xs[i]).toFixed(1)},${Y(o.value).toFixed(1)}`).join(" ");
  svg.append(s("path", { d, class: "line" }));
  series.forEach((o, i) => {
    const c = s("circle", { cx: X(xs[i]), cy: Y(o.value), r: 4.5, class: "dot" });
    const tt = s("title", {}); tt.textContent = `${fmtPeriod(o)}: ${fmtNumber(o.value)} ${L(o.unit)}`;
    c.append(tt); svg.append(c);
  });
  for (const i of [0, series.length - 1]) {
    const tx = s("text", { x: X(xs[i]), y: H - 8, class: "tick",
      "text-anchor": (i === 0) !== rtl ? "start" : "end" });
    tx.textContent = fmtDate(series[i].period_end);
    svg.append(tx);
  }
  const last = series[series.length - 1];
  const vt = s("text", { x: X(xs[xs.length - 1]), y: Math.max(12, Y(last.value) - 10), class: "tick strong",
    "text-anchor": rtl ? "start" : "end" });
  vt.textContent = fmtNumber(last.value);
  svg.append(vt);
  return h("figure", { class: "chart-wrap" }, svg,
    h("figcaption", { class: "muted small" }, t("chart.caption", { n: series.length })));
}
