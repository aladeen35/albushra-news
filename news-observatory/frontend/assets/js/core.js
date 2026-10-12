// Core: DOM helper, settings, i18n, formatting, API client.
// Data from the API is only ever inserted with textContent / attributes,
// never innerHTML, and links are restricted to http(s).

export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "href") { const u = safeUrl(v); if (u) el.setAttribute("href", u); }
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

export function safeUrl(u) {
  if (typeof u !== "string") return null;
  if (u.startsWith("#") || u.startsWith("/")) return u;
  try {
    const p = new URL(u);
    return p.protocol === "https:" || p.protocol === "http:" ? p.href : null;
  } catch { return null; }
}

export function externalLink(url, ...children) {
  return h("a", { href: url, target: "_blank", rel: "noopener noreferrer", class: "ext" }, ...children,
    h("span", { class: "ext-mark", "aria-hidden": "true" }, " ↗"));
}

// --- settings (per-viewer conveniences; the page works without storage) ---
const DEFAULTS = { lang: null, timeZone: null, fontSize: "m", theme: "light" };

function readStore(key, fallback) {
  try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; }
  catch { return fallback; }
}
function writeStore(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage unavailable */ }
}

export const settings = Object.assign({}, DEFAULTS, readStore("obs.settings", {}));
if (!settings.lang) settings.lang = (navigator.language || "ar").toLowerCase().startsWith("en") ? "en" : "ar";
if (!settings.timeZone) {
  try { settings.timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"; }
  catch { settings.timeZone = "UTC"; }
}

export function saveSettings(patch) {
  Object.assign(settings, patch);
  writeStore("obs.settings", settings);
  applySettings();
}

export function applySettings() {
  const root = document.documentElement;
  root.lang = settings.lang;
  root.dir = settings.lang === "ar" ? "rtl" : "ltr";
  root.dataset.font = settings.fontSize;
  if (settings.theme === "auto") delete root.dataset.theme; else root.dataset.theme = settings.theme;
}

// Saved articles: a snapshot so the list renders even if the article ages out.
export const saved = {
  all() { return readStore("obs.saved", []); },
  has(id) { return this.all().some(a => a.id === id); },
  toggle(article) {
    const list = this.all();
    const i = list.findIndex(a => a.id === article.id);
    if (i >= 0) list.splice(i, 1);
    else list.unshift({ id: article.id, title: article.title, url: article.url, language: article.language,
      publisher: article.publisher, published_at: article.published_at, saved_at: new Date().toISOString() });
    writeStore("obs.saved", list.slice(0, 200));
    return i < 0;
  },
};

// A reader's favourite sources and topics, for the "For you" page.
export const prefs = {
  get() { return Object.assign({ sources: [], topics: [] }, readStore("obs.prefs", {})); },
  set(value) { writeStore("obs.prefs", value); },
  toggle(kind, key) {
    const p = this.get();
    const list = new Set(p[kind]);
    if (list.has(key)) list.delete(key); else list.add(key);
    p[kind] = [...list];
    this.set(p);
    return list.has(key);
  },
};

// --- i18n ---
const dictionaries = {};

export async function loadLanguage(lang) {
  if (!dictionaries[lang]) {
    const res = await fetch(`i18n/${lang}.json`, { cache: "no-cache" });
    dictionaries[lang] = await res.json();
  }
}

export function t(key, vars) {
  const dict = dictionaries[settings.lang] || {};
  let s = dict[key] ?? dictionaries.en?.[key] ?? key;
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, v);
  return s;
}

// "20 minutes", "an hour", "3 hours": how often the site refreshes.
export function every(minutes) {
  const n = Number(minutes) || 60;
  if (n % 60) return t(n <= 10 ? "every.minutes_few" : "every.minutes", { n });
  const hours = n / 60;
  return hours === 1 ? t("every.hour") : hours === 2 ? t("every.2hours") : t("every.hours", { n: hours });
}

// Pick the current language from {ar, en} objects coming from the API.
export function L(obj) {
  if (!obj) return "";
  if (typeof obj === "string") return obj;
  return obj[settings.lang] || obj.en || obj.ar || "";
}
export function other(obj) {
  if (!obj || typeof obj === "string") return "";
  return settings.lang === "ar" ? obj.en : obj.ar;
}

// --- formatting ---
// Gregorian calendar and Latin digits in both languages, so a figure reads
// the same in Arabic and English and never mixes digit systems in one line.
function locale() { return settings.lang === "ar" ? "ar-u-ca-gregory-nu-latn" : "en-GB"; }

export function fmtNumber(n, opts = {}) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat(locale(), { maximumFractionDigits: 1, ...opts }).format(n);
}
export function fmtCompact(n) {
  if (Math.abs(n) < 10000) return null;
  return new Intl.NumberFormat(locale(), { notation: "compact", maximumFractionDigits: 2 }).format(n);
}
export function fmtSigned(n) {
  return (n > 0 ? "+" : n < 0 ? "−" : "±") + fmtNumber(Math.abs(n));
}
export function fmtDate(iso) {
  if (!iso) return "—";
  const d = iso.length === 10 ? new Date(iso + "T00:00:00Z") : new Date(iso);
  // Plain dates (periods, publication days) are calendar days, not instants:
  // show them in UTC so a time zone never shifts them by a day.
  return new Intl.DateTimeFormat(locale(), { dateStyle: "medium",
    timeZone: iso.length === 10 ? "UTC" : settings.timeZone }).format(d);
}
export function fmtDateTime(iso) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat(locale(), { dateStyle: "medium", timeStyle: "short",
    timeZone: settings.timeZone }).format(new Date(iso));
}
export function fmtRelative(iso) {
  if (!iso) return "";
  const diff = (new Date(iso).getTime() - Date.now()) / 1000;
  const rtf = new Intl.RelativeTimeFormat(locale(), { numeric: "auto" });
  const abs = Math.abs(diff);
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
  return rtf.format(Math.round(diff / 86400), "day");
}
export function fmtPeriod(obs) {
  if (obs.period_start === obs.period_end) return fmtDate(obs.period_end);
  return `${fmtDate(obs.period_start)} – ${fmtDate(obs.period_end)}`;
}

export function langName(code) {
  return t(`lang.${code}`) === `lang.${code}` ? code : t(`lang.${code}`);
}

// --- API ---
export class ApiError extends Error {
  constructor(status, detail) { super(detail || `HTTP ${status}`); this.status = status; }
}

// Static hosting (GitHub Pages and the like) marks the page with
// <meta name="albushra-static" content="data/">; /api is then answered from
// the JSON snapshot in that folder.
const STATIC_BASE = document.querySelector('meta[name="albushra-static"]')?.content || null;
export const isStatic = () => STATIC_BASE !== null;

export async function api(path, { method = "GET", body, token } = {}) {
  if (STATIC_BASE !== null) {
    const { staticApi, configure } = await import("./static.js");
    configure(STATIC_BASE);
    try { return await staticApi(path); }
    catch (err) { throw new ApiError(err.status || 0, err.staticMode ? t("static.admin") : err.message); }
  }
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  let res;
  try {
    res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, t("error.network"));
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = data?.detail;
    throw new ApiError(res.status, typeof detail === "string" ? detail
      : Array.isArray(detail) ? detail.map(d => `${(d.loc || []).slice(-1)[0]}: ${d.msg}`).join("; ")
      : res.status === 429 ? t("error.rate") : `HTTP ${res.status}`);
  }
  return data;
}

export function qs(params) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== "") p.set(k, v);
  const s = p.toString();
  return s ? `?${s}` : "";
}
