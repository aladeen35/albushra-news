// Admin panel: monitoring, review of sensitive numbers, number entry,
// sources, region lists and scopes. Talks to /api/admin with a bearer token
// kept in sessionStorage for this tab only.
import { h, t, L, api, isStatic, fmtDate, fmtDateTime, fmtNumber, fmtPeriod, externalLink } from "./core.js";
import { META, errorState, loading, typeBadge, countryName } from "./components.js";
import { icon } from "./icons.js";
import { ghAdminView } from "./ghadmin.js";

function token() { try { return sessionStorage.getItem("obs.admin") || ""; } catch { return ""; } }
function setToken(v) { try { sessionStorage.setItem("obs.admin", v); } catch { /* ignore */ } }
function adminUser() { try { return sessionStorage.getItem("obs.admin.user") || ""; } catch { return ""; } }
function setUser(v) { try { sessionStorage.setItem("obs.admin.user", v); } catch { /* ignore */ } }
const call = (path, opts = {}) => api(`/api/admin${path}`, { ...opts, token: token() });

const TABS = ["status", "addsite", "addnews", "reviews", "entry", "hdx", "sources", "regions", "scopes"];

export function adminView(params, rerender) {
  // GitHub Pages build: admin through the repository (see ghadmin.js).
  if (isStatic() && META.static?.repo) return ghAdminView(params, rerender);
  if (isStatic()) {
    return h("div", { class: "login-wrap" }, h("div", { class: "login-card card" },
      h("div", { class: "login-head" }, h("img", { src: "assets/icons/icon-192.png", alt: "", width: 72, height: 72 }),
        h("h1", {}, t("admin.signin.title")), h("p", { class: "muted" }, t("static.admin")))));
  }
  if (!token()) return login(rerender);
  const tab = TABS.includes(params.get("tab")) ? params.get("tab") : "status";
  const nav = h("nav", { class: "segmented", "aria-label": t("admin.title") },
    TABS.map(k => h("a", { href: `#/admin?tab=${k}`, class: k === tab ? "active" : "",
      "aria-current": k === tab ? "page" : null }, t(`admin.tab.${k}`))));
  const body = h("div", {}, loading());
  ({ status, addsite, addnews, reviews, entry, hdx, sources, regions, scopes })[tab](body, rerender)
    .catch(err => {
      if (err.status === 401 || err.status === 503) { setToken(""); rerender(); return; }
      body.replaceChildren(errorState(err));
    });
  return h("div", { class: "admin" },
    h("div", { class: "admin-head" },
      h("h1", { class: "page-title" }, icon("admin", 28), t("admin.title")),
      h("div", { class: "admin-user" }, adminUser() ? h("span", { class: "muted small" }, t("admin.signed_in_as", { u: adminUser() })) : null,
        h("button", { class: "btn ghost", type: "button", onclick: () => { setToken(""); setUser(""); rerender(); } }, t("admin.logout")))),
    nav, body);
}

function login(rerender) {
  const out = h("div");
  const user = h("input", { id: "adm-user", name: "username", autocomplete: "username", required: true,
    dir: "ltr", value: "admin" });
  const pass = h("input", { id: "adm-pass", name: "password", type: "password", autocomplete: "current-password",
    required: true, dir: "ltr" });
  const submit = h("button", { class: "btn wide", type: "submit" }, icon("admin", 18), t("admin.login"));
  const form = h("form", { class: "login-card card" },
    h("div", { class: "login-head" },
      h("img", { src: "assets/icons/icon-192.png", alt: "", width: 72, height: 72 }),
      h("h1", {}, t("admin.signin.title")),
      h("p", { class: "muted" }, t("admin.signin.lede"))),
    h("label", { class: "field", for: "adm-user" }, h("span", {}, t("admin.signin.user")), user),
    h("label", { class: "field", for: "adm-pass" }, h("span", {}, t("admin.signin.pass")), pass),
    submit, out,
    h("p", { class: "muted small" }, t("admin.signin.note")));
  form.addEventListener("submit", async e => {
    e.preventDefault();
    submit.disabled = true;
    try {
      const r = await api("/api/auth/login", { method: "POST", body: { username: user.value, password: pass.value } });
      setToken(r.token);
      setUser(r.username);
      rerender();
    } catch (err) {
      msg(out, err.status === 401 ? t("admin.signin.wrong") : err.status === 429 ? t("admin.signin.locked")
        : err.status === 503 ? t("admin.signin.disabled") : err.message, false);
      submit.disabled = false;
    }
  });
  return h("div", { class: "login-wrap" }, form);
}

function msg(el, text, ok = true) {
  el.replaceChildren(h("p", { class: ok ? "ok" : "error", role: "status" }, text));
}

// --- status ---
async function status(body) {
  const s = await call("/status");
  const jobBtn = (job) => {
    const out = h("span", { class: "small" });
    const b = h("button", { class: "btn ghost", type: "button" }, t(`admin.job.${job}`));
    b.addEventListener("click", async () => {
      b.disabled = true; out.textContent = t("loading");
      try { const r = await call(`/jobs/${job}`, { method: "POST" }); out.textContent = JSON.stringify(r); }
      catch (err) { out.textContent = err.message; }
      b.disabled = false;
    });
    return h("span", {}, b, " ", out);
  };
  body.replaceChildren(
    h("div", { class: "grid stats" },
      stat(t("admin.articles_total"), s.articles_total), stat(t("admin.articles_24h"), s.articles_24h),
      stat(t("admin.pending"), s.pending_reviews), stat(t("admin.stale"), s.stale_alerts.length)),
    h("p", {}, jobBtn("ingest-news"), " ", jobBtn("ingest-metrics")),
    h("h2", {}, t("admin.sources_health")),
    table(["admin.col.source", "admin.col.state", "admin.col.last_ok", "admin.col.last_fail", "admin.col.calls",
      "admin.col.latency", "admin.col.quota"], s.sources.map(x => [
      x.name, [x.enabled ? t("source.enabled") : t("source.disabled"), x.configured ? "" : ` · ${t("admin.not_configured")}`,
        x.terms_reviewed ? "" : ` · ${t("admin.terms_pending")}`].join(""),
      fmtDateTime(x.last_success_at), [fmtDateTime(x.last_failure_at), x.last_error ? h("div", { class: "small error-text" }, x.last_error) : null],
      `${x.calls_24h} / ${x.errors_24h} ${t("admin.errors")}`, x.avg_latency_ms ? `${x.avg_latency_ms} ms` : "—",
      x.quota_remaining || (x.daily_request_limit ? `${t("admin.limit")} ${x.daily_request_limit}` : "—")])),
    h("h2", {}, t("admin.metrics_health")),
    table(["admin.col.metric", "admin.col.state", "admin.col.age", "admin.col.last_fetch"], s.metrics.map(m => [
      L(m.name), t(`status.${m.status}`), m.age_days === null ? "—" : t("admin.days", { n: m.age_days, max: m.max_age_days }),
      m.last_fetch ? [`${m.last_fetch.status} · ${fmtDateTime(m.last_fetch.at)}`,
        m.last_fetch.error ? h("div", { class: "small error-text" }, m.last_fetch.error) : null]
        : m.provider === "manual" ? t("admin.manual") : "—"])),
    h("h2", {}, t("admin.recent_calls")),
    table(["admin.col.target", "admin.col.state", "admin.col.time", "admin.col.items", "admin.col.latency"],
      s.recent_calls.map(c => [c.target, [c.status, c.error ? h("div", { class: "small error-text" }, c.error) : null],
        fmtDateTime(c.at), `${c.items} (${c.new} ${t("admin.new")})`, c.latency_ms ? `${c.latency_ms} ms` : "—"])));
}

function stat(label, value) {
  return h("div", { class: "card stat" }, h("div", { class: "muted small" }, label), h("div", { class: "value" }, fmtNumber(value)));
}

function table(headKeys, rows) {
  if (!rows.length) return h("p", { class: "empty" }, t("empty.generic"));
  return h("div", { class: "table-wrap" }, h("table", {},
    h("thead", {}, h("tr", {}, headKeys.map(k => h("th", { scope: "col" }, t(k))))),
    h("tbody", {}, rows.map(r => h("tr", {}, r.map(c => h("td", {}, c)))))));
}

// --- reviews ---
async function reviews(body, rerender) {
  const rows = await call("/reviews");
  if (!rows.length) { body.replaceChildren(h("p", { class: "empty" }, t("admin.no_reviews"))); return; }
  body.replaceChildren(h("p", { class: "muted small" }, t("admin.review.note")),
    ...rows.map(o => {
      const out = h("div");
      const reviewer = h("input", { required: true, minlength: 2, placeholder: t("admin.reviewer") });
      const note = h("input", { placeholder: t("admin.note") });
      const act = decision => async () => {
        try {
          await call(`/observations/${o.id}/review`, { method: "POST",
            body: { decision, reviewer: reviewer.value, note: note.value || null } });
          rerender();
        } catch (err) { msg(out, err.message, false); }
      };
      return h("div", { class: "card review" },
        h("h3", {}, L(o.metric.name), " ", typeBadge(o.number_type)),
        h("p", { class: "value" }, fmtNumber(o.value), " ", L(o.unit)),
        h("p", { class: "small" }, `${t("metric.period")}: ${fmtPeriod(o)} · ${t("metric.published")}: ${fmtDate(o.published_at)}`),
        h("p", { class: "small" }, t("metric.producer"), ": ", externalLink(o.source_url, o.producer),
          ` · ${t("admin.entered_by")}: ${o.entered_by}`),
        o.correction_note ? h("p", { class: "small" }, t("history.correction"), " ", o.correction_note) : null,
        h("div", { class: "row" }, reviewer, note,
          h("button", { class: "btn", type: "button", onclick: act("approve") }, t("admin.approve")),
          h("button", { class: "btn ghost danger", type: "button", onclick: act("reject") }, t("admin.reject"))),
        out);
    }));
}

// --- number entry ---
async function entry(body) {
  const metrics = await call("/metrics");
  const out = h("div");
  const f = (name, label, attrs = {}) => h("label", { class: "field" }, h("span", {}, label),
    h("input", { name, ...attrs }));
  const select = h("select", { name: "metric", required: true },
    metrics.map(m => h("option", { value: m.metric_id }, `${L(m.name)} (${m.metric_id})`)));
  const types = h("select", { name: "number_type" }, ["", "reported", "verified", "estimated", "projected"]
    .map(x => h("option", { value: x }, x ? t(`type.${x}`) : t("admin.default_type"))));
  const form = h("form", { class: "card form" },
    h("label", { class: "field" }, h("span", {}, t("admin.col.metric")), select),
    f("value", t("history.value"), { type: "number", step: "any", min: 0, required: true }),
    h("div", { class: "row" }, f("value_low", t("admin.low"), { type: "number", step: "any", min: 0 }),
      f("value_high", t("admin.high"), { type: "number", step: "any", min: 0 })),
    h("div", { class: "row" }, f("period_start", t("admin.period_start"), { type: "date", required: true }),
      f("period_end", t("admin.period_end"), { type: "date", required: true })),
    f("period_label", t("admin.period_label")),
    f("published_at", t("metric.published"), { type: "date", required: true }),
    h("label", { class: "field" }, h("span", {}, t("history.type")), types),
    f("producer", t("metric.producer"), { placeholder: t("admin.default_producer") }),
    f("source_url", t("admin.source_url"), { type: "url", required: true, placeholder: "https://" }),
    f("coverage_key", t("admin.coverage_key"), { required: true }),
    f("coverage_note", t("metric.coverage")),
    f("methodology_note", t("metric.method")),
    f("entered_by", t("admin.entered_by"), { required: true, minlength: 2 }),
    h("p", { class: "muted small" }, t("admin.entry.note")),
    h("button", { class: "btn", type: "submit" }, t("admin.submit")), out);
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(form));
    const payload = {};
    for (const [k, v] of Object.entries(fd)) if (k !== "metric" && v !== "") payload[k] = v;
    for (const k of ["value", "value_low", "value_high"]) if (k in payload) payload[k] = Number(payload[k]);
    try {
      const o = await call(`/metrics/${fd.metric}/observations`, { method: "POST", body: payload });
      msg(out, t("admin.saved", { v: o.version, status: t(`review.${o.review_status}`) }));
      form.reset();
    } catch (err) { msg(out, err.message, false); }
  });
  body.replaceChildren(form);
}

// --- sources ---
async function sources(body, rerender) {
  const list = await call("/sources");
  body.replaceChildren(h("p", { class: "muted small" }, t("admin.sources.note")),
    ...list.filter(s => !s.is_demo).map(s => {
      const out = h("div");
      const toggle = (field) => h("label", { class: "radio" }, h("input", { type: "checkbox", checked: s[field],
        onchange: async e => {
          try { await call(`/sources/${s.key}`, { method: "PATCH", body: { [field]: e.target.checked } }); rerender(); }
          catch (err) { e.target.checked = !e.target.checked; msg(out, err.message, false); }
        } }), t(`admin.src.${field}`));
      return h("div", { class: "card" },
        h("h3", {}, s.name, " ", h("span", { class: "muted small" }, `${s.provider} · ${(s.languages || []).join(", ")}`)),
        s.license_note ? h("p", { class: "small" }, s.license_note) : null,
        s.terms_url ? h("p", { class: "small" }, externalLink(s.terms_url, t("admin.terms"))) : null,
        h("div", { class: "row" }, toggle("terms_reviewed"), toggle("enabled"), toggle("allow_description"), toggle("allow_images")),
        h("p", { class: "small muted" }, t("admin.reliability"), `: ${s.reliability}`,
          s.daily_request_limit ? ` · ${t("admin.limit")} ${s.daily_request_limit}` : ""),
        out);
    }));
}

// --- region lists ---
async function regions(body) {
  body.replaceChildren(...META.region_lists.map(r => {
    const out = h("div");
    const area = h("textarea", { rows: 3, dir: "ltr" }, r.countries.join(" "));
    const save = h("button", { class: "btn", type: "button" }, t("admin.save"));
    save.addEventListener("click", async () => {
      try {
        const res = await call(`/region-lists/${r.key}`, { method: "PUT",
          body: { countries: area.value.split(/[\s,،]+/).filter(Boolean) } });
        msg(out, t("admin.region.saved", { n: res.countries.length })
          + (res.not_in_gazetteer.length ? ` ${t("admin.region.unknown")} ${res.not_in_gazetteer.join(", ")}` : ""));
      } catch (err) { msg(out, err.message, false); }
    });
    return h("div", { class: "card" }, h("h3", {}, L(r.name)), h("p", { class: "small" }, L(r.definition)),
      h("p", { class: "small muted" }, r.countries.map(countryName).join(" · ")),
      h("label", {}, t("admin.region.codes")), area, save, out);
  }));
}

// --- scopes ---
async function scopes(body, rerender) {
  const list = await call("/scopes");
  const out = h("div");
  const form = h("form", { class: "card form" }, h("h3", {}, t("admin.scope.new")),
    ...[["key", "admin.scope.key", { pattern: "[a-z0-9_\\-]{2,64}", required: true }],
      ["name_ar", "admin.scope.name_ar", { required: true, dir: "rtl" }],
      ["name_en", "admin.scope.name_en", { required: true, dir: "ltr" }],
      ["countries", "admin.scope.countries", { dir: "ltr", placeholder: "YE" }],
      ["queries_ar", "admin.scope.queries_ar", { dir: "rtl" }],
      ["queries_en", "admin.scope.queries_en", { dir: "ltr" }]].map(([n, k, a]) =>
      h("label", { class: "field" }, h("span", {}, t(k)), h("input", { name: n, ...a }))),
    h("button", { class: "btn", type: "submit" }, t("admin.save")), out);
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(form));
    const split = v => (v || "").split(/[,،]/).map(x => x.trim()).filter(Boolean);
    try {
      await call("/scopes", { method: "POST", body: { key: fd.key, name_ar: fd.name_ar, name_en: fd.name_en,
        countries: split(fd.countries), queries: { ar: split(fd.queries_ar), en: split(fd.queries_en) } } });
      rerender();
    } catch (err) { msg(out, err.message, false); }
  });
  body.replaceChildren(
    table(["admin.scope.key", "admin.scope.name", "admin.scope.countries", "admin.col.state"], list.map(s => [
      s.key, `${s.name_ar} / ${s.name_en}`, (s.countries || []).join(", ") || "—",
      s.enabled ? t("source.enabled") : t("source.disabled")])),
    h("p", { class: "muted small" }, t("admin.scope.note")), form);
}

// --- add a site by its address (WordPress, or any site with a news feed) ---
const GROUPS = ["saudi", "arab", "sudan", "sports", "international", "humanitarian"];

function countrySelect(name) {
  const codes = Object.keys(META.countries).sort((a, b) => countryName(a).localeCompare(countryName(b)));
  return h("select", { name }, h("option", { value: "" }, "—"),
    codes.map(c => h("option", { value: c }, countryName(c))));
}

async function addsite(body) {
  const out = h("div");
  const preview = h("div");
  const urlInput = h("input", { name: "url", type: "url", required: true, dir: "ltr", placeholder: "https://example.com" });
  const inspectForm = h("form", { class: "card form" },
    h("h2", {}, t("admin.site.title")),
    h("p", { class: "muted small" }, t("admin.site.note")),
    h("label", { class: "field" }, h("span", {}, t("admin.site.url")), urlInput),
    h("button", { class: "btn", type: "submit" }, t("admin.site.inspect")), out);
  inspectForm.addEventListener("submit", async e => {
    e.preventDefault();
    msg(out, t("admin.site.checking"));
    preview.replaceChildren();
    try {
      const info = await call("/sites/inspect", { method: "POST", body: { url: urlInput.value } });
      out.replaceChildren();
      preview.replaceChildren(saveForm(info));
    } catch (err) {
      out.replaceChildren(h("div", { class: "error", role: "alert" },
        h("strong", {}, err.status === 422 ? t("admin.site.not_found") : t("error.title")),
        h("div", { class: "small", dir: "ltr" }, err.message)));
    }
  });
  body.replaceChildren(inspectForm, preview);
}

function saveForm(info) {
  const out = h("div");
  const field = (label, control) => h("label", { class: "field" }, h("span", {}, label), control);
  const form = h("form", { class: "card form" },
    h("h3", {}, info.type === "wordpress" ? t("admin.site.found_wp") : t("admin.site.found_rss")),
    h("p", { class: "small muted", dir: "ltr" }, info.type === "rss" ? info.feed_url : `${info.url}/wp-json/wp/v2/posts`),
    h("ul", { class: "plain" }, info.sample.map(p => h("li", {},
      h("a", { href: p.url, target: "_blank", rel: "noopener noreferrer", dir: "auto" }, p.title),
      h("div", { class: "muted small" }, fmtDateTime(p.published_at), p.author ? ` · ${p.author}` : "")))),
    field(t("admin.site.name"), h("input", { name: "name", required: true, minlength: 2, value: info.name || "" })),
    h("div", { class: "row" },
      field(t("filter.lang"), h("select", { name: "language" },
        ["ar", "en"].map(l => h("option", { value: l, selected: l === info.language }, l === "ar" ? "العربية" : "English")))),
      field(t("admin.site.country"), countrySelect("country")),
      field(t("admin.site.group"), h("select", { name: "group" }, GROUPS.map(g => h("option", { value: g }, t(`group.${g}`))))),
      field(t("filter.topic"), h("select", { name: "topic" }, h("option", { value: "" }, t("admin.site.any_topic")),
        META.topics.map(x => h("option", { value: x }, t(`topic.${x}`)))))),
    h("label", { class: "radio" }, h("input", { type: "checkbox", name: "terms_reviewed" }), t("admin.site.terms")),
    h("label", { class: "radio" }, h("input", { type: "checkbox", name: "allow_images" }), t("admin.src.allow_images")),
    h("p", { class: "muted small" }, t("admin.site.enable_note")),
    h("button", { class: "btn", type: "submit" }, t("admin.site.save")), out);
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const fd = new FormData(form);
    try {
      const s = await call("/sites", { method: "POST", body: {
        url: info.url, type: info.type, feed_url: info.feed_url || null, name: fd.get("name"),
        language: fd.get("language"), country: fd.get("country") || null, group: fd.get("group"),
        topic: fd.get("topic") || null, terms_reviewed: fd.get("terms_reviewed") === "on",
        allow_images: fd.get("allow_images") === "on" } });
      msg(out, s.enabled ? t("admin.site.saved_on", { n: s.first_fetch?.new ?? 0 }) : t("admin.site.saved_off"));
      form.querySelector("button[type=submit]").disabled = true;
    } catch (err) { msg(out, err.message, false); }
  });
  return form;
}

// --- add a story by hand ---
async function addnews(body, rerender) {
  const out = h("div");
  const field = (label, control) => h("label", { class: "field" }, h("span", {}, label), control);
  const now = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  const topics = h("div", { class: "row" }, META.topics.map(x =>
    h("label", { class: "radio" }, h("input", { type: "checkbox", name: "topics", value: x }), t(`topic.${x}`))));
  const form = h("form", { class: "card form" },
    h("h2", {}, t("admin.news.title")),
    h("p", { class: "muted small" }, t("admin.news.note")),
    field(t("admin.news.headline"), h("input", { name: "title", required: true, minlength: 5, maxlength: 400, dir: "auto" })),
    field(t("admin.news.link"), h("input", { name: "url", type: "url", required: true, dir: "ltr", placeholder: "https://" })),
    field(t("admin.news.summary"), h("textarea", { name: "description", rows: 3, maxlength: 1000, dir: "auto" })),
    h("div", { class: "row" },
      field(t("article.publisher"), h("input", { name: "publisher_name", required: true, minlength: 2 })),
      field(t("admin.site.country"), countrySelect("publisher_country")),
      field(t("filter.lang"), h("select", { name: "language" }, h("option", { value: "ar" }, "العربية"), h("option", { value: "en" }, "English")))),
    h("div", { class: "row" },
      field(t("article.published"), h("input", { name: "published_at", type: "datetime-local", required: true, value: now })),
      field(t("filter.ctype"), h("select", { name: "content_type" }, META.content_types.map(c => h("option", { value: c }, t(`ctype.${c}`)))))),
    field(t("admin.news.countries"), h("input", { name: "event_countries", dir: "ltr", placeholder: "SD, SA" })),
    h("fieldset", {}, h("legend", {}, t("filter.topic")), topics),
    field(t("admin.news.image"), h("input", { name: "image_url", type: "url", dir: "ltr", placeholder: "https://" })),
    field(t("admin.entered_by"), h("input", { name: "entered_by", required: true, minlength: 2 })),
    h("button", { class: "btn", type: "submit" }, t("admin.news.publish")), out);
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const fd = new FormData(form);
    const codes = (fd.get("event_countries") || "").split(/[\s,،]+/).filter(Boolean).map(c => c.toUpperCase());
    const chosen = fd.getAll("topics");
    try {
      const r = await call("/articles", { method: "POST", body: {
        title: fd.get("title"), url: fd.get("url"), description: fd.get("description") || null,
        publisher_name: fd.get("publisher_name"), publisher_country: fd.get("publisher_country") || null,
        language: fd.get("language"), published_at: new Date(fd.get("published_at")).toISOString(),
        content_type: fd.get("content_type"), image_url: fd.get("image_url") || null,
        event_countries: codes.length ? codes : null, topics: chosen.length ? chosen : null,
        entered_by: fd.get("entered_by") } });
      out.replaceChildren(h("p", { class: "ok", role: "status" }, t("admin.news.saved"), " ",
        h("a", { href: `#/article/${r.id}` }, t("admin.news.view"))));
      form.reset();
      rerender_list();
    } catch (err) { msg(out, err.message, false); }
  });
  const listSlot = h("div");
  async function rerender_list() {
    const rows = await call("/articles");
    listSlot.replaceChildren(h("h2", {}, t("admin.news.recent")), table(
      ["admin.news.headline", "article.publisher", "admin.entered_by", "article.published", "admin.col.state"],
      rows.map(a => [h("a", { href: `#/article/${a.id}`, dir: "auto" }, a.title), a.publisher, a.entered_by,
        fmtDateTime(a.published_at), h("button", { class: "btn ghost danger", type: "button", onclick: async () => {
          if (!confirm(t("admin.news.confirm_delete"))) return;
          await call(`/articles/${a.id}`, { method: "DELETE" }); rerender_list();
        } }, t("admin.news.delete"))])));
  }
  await rerender_list();
  body.replaceChildren(form, listSlot);
}

// --- find a dataset on HDX: where a figure can come from, and under which licence ---
async function hdx(body) {
  const out = h("div");
  const q = h("input", { name: "q", required: true, minlength: 2, dir: "auto", placeholder: "internally displaced" });
  const country = h("select", { name: "country" }, [["", t("filter.any")], ["SDN", "السودان / Sudan"],
    ["PSE", "فلسطين / Palestine"]].map(([v, l]) => h("option", { value: v }, l)));
  const form = h("form", { class: "card form" }, h("h2", {}, t("admin.hdx.title")),
    h("p", { class: "muted small" }, t("admin.hdx.note")),
    h("div", { class: "row" }, h("label", { class: "field" }, h("span", {}, t("filter.q")), q),
      h("label", { class: "field" }, h("span", {}, t("filter.country")), country)),
    h("button", { class: "btn", type: "submit" }, t("search.go")));
  form.addEventListener("submit", async e => {
    e.preventDefault();
    out.replaceChildren(loading());
    try {
      const rows = await call(`/hdx/search?q=${encodeURIComponent(q.value)}${country.value ? `&country=${country.value}` : ""}`);
      out.replaceChildren(table(["admin.hdx.dataset", "admin.hdx.org", "admin.hdx.license", "admin.hdx.updated", "admin.hdx.formats"],
        rows.map(d => [externalLink(d.url, d.title), d.organization || "—", d.license || "—",
          d.updated ? fmtDate(d.updated.slice(0, 10)) : "—", (d.formats || []).join(", ")])));
    } catch (err) { msg(out, err.message, false); }
  });
  body.replaceChildren(form, out);
}
