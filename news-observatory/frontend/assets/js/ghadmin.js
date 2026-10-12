// Admin for the GitHub Pages build. There is no server: changes are committed
// to the repository's content/ folder through GitHub's API, and the hourly
// build (also triggered by each commit) applies them. Signing in takes a
// fine-grained GitHub token limited to this one repository.
import { h, t, L, every, fmtDate, fmtDateTime, fmtNumber, fmtPeriod, externalLink } from "./core.js";
import { META, countryName, typeBadge, loading, errorState } from "./components.js";
import { icon } from "./icons.js";

const API = "https://api.github.com";
const KEY = "obs.gh";

function readToken() {
  try { return sessionStorage.getItem(KEY) || localStorage.getItem(KEY) || ""; } catch { return ""; }
}
function saveToken(value, remember) {
  try {
    sessionStorage.removeItem(KEY); localStorage.removeItem(KEY);
    if (value) (remember ? localStorage : sessionStorage).setItem(KEY, value);
  } catch { /* storage unavailable: signed in for this page view only */ }
}
let memoryToken = "";
const token = () => memoryToken || readToken();
const repo = () => META.static.repo;
const contentPath = name => `${META.static.content_path || "content"}/${name}`;
let editor = "";

async function gh(path, { method = "GET", body } = {}) {
  const res = await fetch(API + path, { method, headers: {
    Accept: "application/vnd.github+json", Authorization: `Bearer ${token()}`,
    "X-GitHub-Api-Version": "2022-11-28", ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined });
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw Object.assign(new Error(data?.message || `HTTP ${res.status}`), { status: res.status });
  return data;
}

const encode = text => {
  const bytes = new TextEncoder().encode(text);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
};
const decode = b64 => new TextDecoder().decode(Uint8Array.from(atob(b64.replace(/\n/g, "")), c => c.charCodeAt(0)));

async function readContent(name, fallback) {
  try {
    const f = await gh(`/repos/${repo()}/contents/${contentPath(name)}`);
    return { data: JSON.parse(decode(f.content)), sha: f.sha };
  } catch (err) {
    if (err.status === 404) return { data: fallback, sha: null };
    throw err;
  }
}

// Read, change, commit. If someone else committed in between (409/422), retry once.
async function update(name, fallback, change, message) {
  for (let attempt = 0; attempt < 2; attempt++) {
    const { data, sha } = await readContent(name, fallback);
    const next = change(structuredClone(data));
    try {
      return await gh(`/repos/${repo()}/contents/${contentPath(name)}`, { method: "PUT", body: {
        message: `${message} — ${editor}`, content: encode(JSON.stringify(next, null, 1) + "\n"),
        ...(sha ? { sha } : {}) } });
    } catch (err) {
      if (attempt === 0 && (err.status === 409 || err.status === 422)) continue;
      throw err;
    }
  }
}

function msg(el, text, ok = true, extra = null) {
  el.replaceChildren(h("p", { class: ok ? "ok" : "error", role: "status" }, text, extra ? " " : "", extra));
}
function savedNote(el) {
  msg(el, t("gh.saved"), true, externalLink(`https://github.com/${repo()}/actions`, t("gh.watch_build")));
}
const field = (label, control) => h("label", { class: "field" }, h("span", {}, label), control);

// --- sign-in ---------------------------------------------------------------
function signIn(rerender) {
  const out = h("div");
  const input = h("input", { id: "gh-token", type: "password", required: true, dir: "ltr", autocomplete: "off",
    placeholder: "github_pat_…" });
  const remember = h("input", { type: "checkbox", id: "gh-remember" });
  const form = h("form", { class: "login-card card" },
    h("div", { class: "login-head" }, h("img", { src: "assets/icons/icon-192.png", alt: "", width: 72, height: 72 }),
      h("h1", {}, t("admin.signin.title")), h("p", { class: "muted" }, t("gh.lede"))),
    field(t("gh.token"), input),
    h("label", { class: "radio", for: "gh-remember" }, remember, t("gh.remember")),
    h("button", { class: "btn wide", type: "submit" }, icon("admin", 18), t("admin.login")), out,
    h("details", { class: "definition" }, h("summary", {}, t("gh.how")),
      h("ol", { class: "small" },
        h("li", {}, externalLink("https://github.com/settings/personal-access-tokens/new", t("gh.how.1"))),
        h("li", {}, t("gh.how.2", { repo: repo() })),
        h("li", {}, t("gh.how.3")),
        h("li", {}, t("gh.how.4")))),
    h("p", { class: "muted small" }, t("gh.security")));
  form.addEventListener("submit", async e => {
    e.preventDefault();
    memoryToken = input.value.trim();
    try {
      const r = await gh(`/repos/${repo()}`);
      if (!r.permissions?.push) throw Object.assign(new Error(t("gh.no_write")), { status: 403 });
      saveToken(memoryToken, remember.checked);
      rerender();
    } catch (err) {
      memoryToken = "";
      msg(out, err.status === 401 ? t("gh.bad_token") : err.message, false);
    }
  });
  return h("div", { class: "login-wrap" }, form);
}

// --- tabs -------------------------------------------------------------------
const TABS = ["status", "addnews", "addsite", "reviews", "entry", "sources", "settings"];
const FETCH_CHOICES = [10, 15, 20, 30, 45, 60, 120, 180, 360];  // same list as app/content.py

export function ghAdminView(params, rerender) {
  if (!token()) return signIn(rerender);
  const tab = TABS.includes(params.get("tab")) ? params.get("tab") : "status";
  const body = h("div", {}, loading());
  const who = h("span", { class: "muted small" }, t("admin.signed_in_as", { u: editor || "…" }));
  (async () => {
    if (!editor) {
      try { editor = (await gh("/user")).login; } catch { editor = "editor"; }
      who.textContent = t("admin.signed_in_as", { u: editor });
    }
    await ({ status, addnews, addsite, reviews, entry, sources, settings: settingsTab })[tab](body, rerender);
  })().catch(err => {
    if (err.status === 401) { saveToken(""); memoryToken = ""; rerender(); return; }
    body.replaceChildren(errorState(err));
  });
  const rebuildOut = h("span", { class: "small" });
  const rebuild = h("button", { class: "btn ghost", type: "button" }, t("gh.rebuild"));
  rebuild.addEventListener("click", async () => {
    try {
      await gh(`/repos/${repo()}/actions/workflows/${META.static.workflow || "pages.yml"}/dispatches`,
        { method: "POST", body: { ref: "main" } });
      rebuildOut.replaceChildren(t("gh.rebuild.started"), " ",
        externalLink(`https://github.com/${repo()}/actions`, t("gh.watch_build")));
    } catch (err) {
      rebuildOut.textContent = err.status === 403 ? t("gh.rebuild.no_permission") : err.message;
    }
  });
  return h("div", { class: "admin" },
    h("div", { class: "admin-head" },
      h("h1", { class: "page-title" }, icon("admin", 28), t("admin.title")),
      h("div", { class: "admin-user" }, who,
        h("button", { class: "btn ghost", type: "button", onclick: () => { saveToken(""); memoryToken = ""; rerender(); } },
          t("admin.logout")))),
    h("p", { class: "muted small" }, t("gh.how_it_works"), " ", rebuild, " ", rebuildOut),
    h("nav", { class: "segmented", "aria-label": t("admin.title") },
      TABS.map(k => h("a", { href: `#/admin?tab=${k}`, class: k === tab ? "active" : "",
        "aria-current": k === tab ? "page" : null }, t(`gh.tab.${k}`)))),
    body);
}

async function loadData(name) {
  const res = await fetch(`data/${name}`, { cache: "no-cache" });
  return res.ok ? res.json() : null;
}

function table(headKeys, rows) {
  if (!rows.length) return h("p", { class: "empty" }, t("empty.generic"));
  return h("div", { class: "table-wrap" }, h("table", {},
    h("thead", {}, h("tr", {}, headKeys.map(k => h("th", { scope: "col" }, t(k))))),
    h("tbody", {}, rows.map(r => h("tr", {}, r.map(c => h("td", {}, c)))))));
}

async function status(body) {
  const [st, report] = await Promise.all([loadData("status.json"), loadData("content-report.json")]);
  if (!st) { body.replaceChildren(h("p", { class: "empty" }, t("empty.generic"))); return; }
  body.replaceChildren(
    h("p", {}, t("gh.last_build"), " ", h("strong", {}, fmtDateTime(st.generated_at)), " · ",
      t("gh.stories", { n: fmtNumber(st.articles_total) })),
    report?.skipped?.length ? h("div", { class: "error" }, h("strong", {}, t("gh.skipped")),
      h("ul", {}, report.skipped.map(s => h("li", { dir: "auto" }, s)))) : null,
    h("h2", {}, t("admin.sources_health")),
    table(["admin.col.source", "admin.col.state", "admin.col.calls", "admin.col.items", "admin.col.last_fail"],
      st.sources.filter(s => s.calls || s.enabled).map(s => [s.name,
        s.enabled ? t("source.enabled") : t("source.disabled"), `${s.calls} / ${s.errors} ${t("admin.errors")}`,
        `${s.items} (${s.new} ${t("admin.new")})`, s.last_error ? h("span", { class: "small error-text" }, s.last_error) : "—"])),
    h("h2", {}, t("admin.metrics_health")),
    table(["admin.col.metric", "admin.col.calls", "admin.col.items", "admin.col.last_fail"],
      st.metrics.map(m => [L(m.name), String(m.calls), String(m.new),
        m.last_error ? h("span", { class: "small error-text" }, m.last_error) : "—"])));
}

function countrySelect(name) {
  const codes = Object.keys(META.countries).sort((a, b) => countryName(a).localeCompare(countryName(b)));
  return h("select", { name }, h("option", { value: "" }, "—"), codes.map(c => h("option", { value: c }, countryName(c))));
}

async function addnews(body, rerender) {
  const out = h("div");
  const now = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  const topics = h("div", { class: "row" }, META.topics.map(x =>
    h("label", { class: "radio" }, h("input", { type: "checkbox", name: "topics", value: x }), t(`topic.${x}`))));
  const form = h("form", { class: "card form" }, h("h2", {}, t("admin.news.title")),
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
    h("button", { class: "btn", type: "submit" }, t("admin.news.publish")), out);
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const fd = new FormData(form);
    const story = { title: fd.get("title").trim(), url: fd.get("url").trim(), description: fd.get("description") || null,
      publisher_name: fd.get("publisher_name").trim(), publisher_country: fd.get("publisher_country") || null,
      language: fd.get("language"), published_at: new Date(fd.get("published_at")).toISOString(),
      content_type: fd.get("content_type"), topics: fd.getAll("topics"),
      event_countries: (fd.get("event_countries") || "").split(/[\s,،]+/).filter(Boolean).map(c => c.toUpperCase()),
      entered_by: editor, added_at: new Date().toISOString() };
    try {
      await update("articles.json", [], list => [...list.filter(a => a.url !== story.url), story], `خبر: ${story.title.slice(0, 60)}`);
      savedNote(out); form.reset(); renderList();
    } catch (err) { msg(out, err.message, false); }
  });
  const hideOut = h("div");
  const hideInput = h("input", { type: "url", dir: "ltr", required: true, placeholder: "https://" });
  const hideForm = h("form", { class: "card form" }, h("h2", {}, t("gh.hide.title")),
    h("p", { class: "muted small" }, t("gh.hide.note")), field(t("admin.news.link"), hideInput),
    h("button", { class: "btn ghost danger", type: "submit" }, t("gh.hide.button")), hideOut);
  hideForm.addEventListener("submit", async e => {
    e.preventDefault();
    const url = hideInput.value.trim();
    try {
      await update("hidden.json", [], list => [...list.filter(x => x.url !== url), { url, by: editor, at: new Date().toISOString() }], "إخفاء خبر");
      savedNote(hideOut); hideForm.reset();
    } catch (err) { msg(hideOut, err.message, false); }
  });
  const listSlot = h("div");
  async function renderList() {
    const { data } = await readContent("articles.json", []);
    listSlot.replaceChildren(h("h2", {}, t("admin.news.recent")), table(
      ["admin.news.headline", "article.publisher", "admin.entered_by", "admin.col.state"],
      data.slice().reverse().map(a => [h("a", { href: a.url, target: "_blank", rel: "noopener noreferrer", dir: "auto" }, a.title),
        a.publisher_name, a.entered_by || "—",
        h("button", { class: "btn ghost danger", type: "button", onclick: async ev => {
          ev.target.disabled = true;
          await update("articles.json", [], list => list.filter(x => x.url !== a.url), "حذف خبر");
          renderList();
        } }, t("admin.news.delete"))])));
  }
  await renderList();
  body.replaceChildren(form, listSlot, hideForm);
}

async function addsite(body) {
  const out = h("div");
  const form = h("form", { class: "card form" }, h("h2", {}, t("admin.site.title")),
    h("p", { class: "muted small" }, t("gh.site.note")),
    field(t("admin.site.url"), h("input", { name: "url", type: "url", required: true, dir: "ltr", placeholder: "https://example.com" })),
    field(t("admin.site.name"), h("input", { name: "name", required: true, minlength: 2 })),
    h("div", { class: "row" },
      field(t("gh.site.type"), h("select", { name: "type" }, h("option", { value: "wordpress" }, "WordPress"),
        h("option", { value: "rss" }, t("gh.site.rss")))),
      field(t("filter.lang"), h("select", { name: "language" }, h("option", { value: "ar" }, "العربية"), h("option", { value: "en" }, "English"))),
      field(t("admin.site.country"), countrySelect("country")),
      field(t("admin.site.group"), h("select", { name: "group" },
        ["saudi", "arab", "sudan", "sports", "international", "humanitarian"].map(g => h("option", { value: g }, t(`group.${g}`)))))),
    field(t("gh.site.feed"), h("input", { name: "feed_url", type: "url", dir: "ltr", placeholder: t("gh.site.feed.placeholder") })),
    h("label", { class: "radio" }, h("input", { type: "checkbox", name: "terms", required: true }), t("admin.site.terms")),
    h("button", { class: "btn", type: "submit" }, t("admin.site.save")), out);
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const fd = new FormData(form);
    const site = { url: fd.get("url").trim().replace(/\/+$/, ""), name: fd.get("name").trim(), type: fd.get("type"),
      language: fd.get("language"), country: fd.get("country") || null, group: fd.get("group"),
      feed_url: fd.get("feed_url") || null, added_by: editor, added_at: new Date().toISOString() };
    if (!site.url.startsWith("https://")) { msg(out, t("gh.site.https"), false); return; }
    try {
      await update("sites.json", [], list => [...list.filter(s => s.url !== site.url), site], `موقع: ${site.name}`);
      savedNote(out); form.reset();
    } catch (err) { msg(out, err.message, false); }
  });
  body.replaceChildren(form);
}

async function reviews(body) {
  const [pending, approvals] = await Promise.all([loadData("pending.json"), readContent("approvals.json", [])]);
  const decided = new Set(approvals.data.map(a => `${a.metric_id}|${a.period_end}|${Number(a.value)}`));
  const rows = (pending || []).filter(o => !decided.has(`${o.metric.metric_id}|${o.period_end}|${Number(o.value)}`));
  if (!rows.length) { body.replaceChildren(h("p", { class: "empty" }, t("admin.no_reviews"))); return; }
  body.replaceChildren(h("p", { class: "muted small" }, t("admin.review.note")), ...rows.map(o => {
    const out = h("div");
    const act = decision => async () => {
      try {
        await update("approvals.json", [], list => [...list, { metric_id: o.metric.metric_id, period_end: o.period_end,
          value: o.value, decision, reviewer: editor, at: new Date().toISOString() }],
          `${decision === "approve" ? "اعتماد" : "رفض"} رقم: ${o.metric.metric_id}`);
        savedNote(out);
      } catch (err) { msg(out, err.message, false); }
    };
    return h("div", { class: "card review" },
      h("h3", {}, L(o.metric.name), " ", typeBadge(o.number_type)),
      h("p", { class: "value" }, fmtNumber(o.value), " ", L(o.unit)),
      h("p", { class: "small" }, `${t("metric.period")}: ${fmtPeriod(o)} · ${t("metric.published")}: ${fmtDate(o.published_at)}`),
      h("p", { class: "small" }, t("metric.producer"), ": ", externalLink(o.source_url, o.producer),
        ` · ${t("admin.entered_by")}: ${o.entered_by}`),
      h("div", { class: "row" },
        h("button", { class: "btn", type: "button", onclick: act("approve") }, t("admin.approve")),
        h("button", { class: "btn ghost danger", type: "button", onclick: act("reject") }, t("admin.reject"))), out);
  }));
}

async function entry(body) {
  const dash = await loadData("dashboard-world.json");
  const out = h("div");
  const f = (name, label, attrs = {}) => field(label, h("input", { name, ...attrs }));
  const form = h("form", { class: "card form" }, h("h2", {}, t("admin.tab.entry")),
    field(t("admin.col.metric"), h("select", { name: "metric_id", required: true },
      (dash?.cards || []).map(m => h("option", { value: m.metric_id }, L(m.name))))),
    f("value", t("history.value"), { type: "number", step: "any", min: 0, required: true }),
    h("div", { class: "row" }, f("period_start", t("admin.period_start"), { type: "date", required: true }),
      f("period_end", t("admin.period_end"), { type: "date", required: true })),
    f("published_at", t("metric.published"), { type: "date", required: true }),
    f("source_url", t("admin.source_url"), { type: "url", required: true, dir: "ltr", placeholder: "https://" }),
    f("coverage_key", t("admin.coverage_key"), { required: true }),
    f("period_label", t("admin.period_label")),
    h("p", { class: "muted small" }, t("gh.entry.note")),
    h("button", { class: "btn", type: "submit" }, t("admin.submit")), out);
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(form));
    const figure = { ...fd, value: Number(fd.value), entered_by: editor, added_at: new Date().toISOString() };
    try {
      await update("figures.json", [], list => [...list, figure], `رقم: ${fd.metric_id}`);
      savedNote(out); form.reset();
    } catch (err) { msg(out, err.message, false); }
  });
  body.replaceChildren(form);
}

async function sources(body, rerender) {
  const [st, overrides] = await Promise.all([loadData("status.json"), readContent("sources.json", {})]);
  const out = h("div");
  // One switch per setting; each change is its own commit, merged with the
  // source's other settings.
  const sw = (s, key, label, on, verbs) => {
    const input = h("input", { type: "checkbox", role: "switch", checked: on, class: "switch-input" });
    input.addEventListener("change", async () => {
      try {
        await update("sources.json", {}, o => ({ ...o, [s.key]: { ...(o[s.key] || {}), [key]: input.checked } }),
          `${input.checked ? verbs[0] : verbs[1]}: ${s.name}`);
        savedNote(out);
      } catch (err) { input.checked = !input.checked; msg(out, err.message, false); }
    });
    return h("label", { class: "mini-switch" }, input, h("span", { class: "switch", "aria-hidden": "true" }),
      h("span", { class: "small" }, label));
  };
  body.replaceChildren(h("p", { class: "muted small" }, t("gh.sources.note")),
    h("p", { class: "muted small" }, t("gh.sources.images_note")), out,
    h("div", { class: "card list-card" }, (st?.sources || []).map(s => {
      const o = overrides.data[s.key] || {};
      return h("div", { class: "toggle-row source-row" },
        h("span", { class: "toggle-label" }, h("strong", {}, s.name),
          h("span", { class: "muted small" }, `${s.items} ${t("admin.new")} · ${s.errors} ${t("admin.errors")}`)),
        h("div", { class: "source-switches" },
          sw(s, "enabled", t("gh.sources.on"), o.enabled ?? s.enabled, ["تفعيل مصدر", "إيقاف مصدر"]),
          sw(s, "images", t("gh.sources.images"), o.images ?? s.images ?? true, ["عرض صور مصدر", "إخفاء صور مصدر"])));
    })));
}

async function settingsTab(body) {
  const { data } = await readContent("settings.json", {});
  const current = Number(data.fetch_minutes) || META.static.fetch_minutes || 20;
  const select = h("select", { name: "fetch_minutes" }, FETCH_CHOICES.map(n =>
    h("option", { value: n, selected: n === current }, `${t("gh.settings.every")} ${every(n)}`)));
  const out = h("div");
  const form = h("form", { class: "card form" },
    h("h2", {}, t("gh.settings.fetch")),
    field(t("gh.settings.fetch_label"), select),
    h("p", { class: "muted small" }, t("gh.settings.fetch_note")),
    h("button", { class: "btn", type: "submit" }, t("admin.save")), out);
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const n = Number(select.value);
    try {
      await update("settings.json", {}, o => ({ ...o, fetch_minutes: n }), `وقت الجلب: كل ${n} دقيقة`);
      savedNote(out);
    } catch (err) { msg(out, err.message, false); }
  });
  body.replaceChildren(form);
}
