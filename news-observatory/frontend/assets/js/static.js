// Static mode: the same /api the server offers, answered in the browser from
// a JSON snapshot (data/*.json). Used when the site is hosted as plain files,
// e.g. on GitHub Pages. Reading, sections, search and filters all work;
// anything that changes data needs the real server.

const cache = {};
let base = "data/";

export function configure(path) { base = path; }

async function load(name) {
  if (!cache[name]) {
    cache[name] = fetch(base + name, { cache: "no-cache" }).then(r => {
      if (!r.ok) throw Object.assign(new Error(`HTTP ${r.status}`), { status: r.status });
      return r.json();
    });
  }
  return cache[name];
}

const norm = s => (s || "").toLowerCase()
  .replace(/[ً-ٰٟـ]/g, "").replace(/[إأآٱ]/g, "ا").replace(/ة/g, "ه").replace(/ى/g, "ي");

function sectionCountries(meta, section) {
  if (!section || section === "world" || section === "sports") return null;
  if (section === "palestine") return ["PS"];
  const region = meta.region_lists.find(r => r.key === section);
  if (region) return region.countries;
  const scope = meta.scopes.find(s => s.key === section);
  if (scope && scope.countries.length) return scope.countries;
  throw Object.assign(new Error("unknown section"), { status: 404 });
}

function score(a, breadth, now, ranking) {
  const hours = Math.max(0, (now - Date.parse(a.published_at)) / 3600000);
  const recency = 0.5 ** (hours / ranking.half_life_hours);
  return ranking.recency * recency + ranking.breadth * Math.min(1, (breadth - 1) / 4)
    + ranking.reliability * (a.reliability ?? 0.5);
}

async function queryArticles(p) {
  const [meta, all] = await Promise.all([load("meta.json"), load("articles.json")]);
  const countries = sectionCountries(meta, p.get("section"));
  const q = norm(p.get("q"));
  const topics = (p.get("topic") || "").split(",").filter(Boolean);
  const keys = (p.get("sources") || "").split(",").filter(Boolean);
  const since = p.get("hours") ? Date.now() - Number(p.get("hours")) * 3600000 : null;
  const rows = all.filter(a =>
    (!countries || a.event_countries.some(c => countries.includes(c))) &&
    (p.get("section") !== "sports" || a.topics.includes("sports")) &&
    (!q || norm(a.title).includes(q) || norm(a.description).includes(q)) &&
    (!p.get("lang") || a.language === p.get("lang")) &&
    (!p.get("country") || a.event_countries.includes(p.get("country").toUpperCase())) &&
    (!topics.length || a.topics.some(t => topics.includes(t))) &&
    (!p.get("source") || a.publisher.name === p.get("source")) &&
    (!keys.length || keys.includes(a.source_key)) &&
    (!p.get("content_type") || a.content_type === p.get("content_type")) &&
    (!since || Date.parse(a.published_at) >= since));
  // Collapse clusters: one lead per story, the other publishers counted.
  const clusters = new Map();
  for (const a of rows) {
    const k = a.cluster_id ?? a.id;
    if (!clusters.has(k)) clusters.set(k, []);
    clusters.get(k).push(a);
  }
  const now = Date.now();
  const leads = [...clusters.values()].map(members => {
    const lead = members.reduce((best, a) => ((a.reliability ?? .5) > (best.reliability ?? .5) ||
      ((a.reliability ?? .5) === (best.reliability ?? .5) && a.published_at > best.published_at)) ? a : best);
    const publishers = new Set(members.map(m => m.publisher.name));
    return { item: { ...lead, other_publishers: publishers.size - 1 }, score: score(lead, publishers.size, now, meta.ranking) };
  });
  leads.sort(p.get("sort") === "newest"
    ? (x, y) => y.item.published_at.localeCompare(x.item.published_at)
    : (x, y) => y.score - x.score);
  const perPage = Math.min(50, Number(p.get("per_page") || 20));
  const page = Math.max(1, Number(p.get("page") || 1));
  return { items: leads.slice((page - 1) * perPage, page * perPage).map(l => l.item), total: leads.length,
    page, pages: Math.max(1, Math.ceil(leads.length / perPage)), truncated: false };
}

async function articleDetail(id) {
  const [all, sources] = await Promise.all([load("articles.json"), load("sources.json")]);
  const a = all.find(x => String(x.id) === String(id));
  if (!a) throw Object.assign(new Error("unknown article"), { status: 404 });
  const cluster = a.cluster_id ?? a.id;
  const same = all.filter(x => (x.cluster_id ?? x.id) === cluster && x.id !== a.id);
  const related = a.event_countries.length ? all.filter(x => x.id !== a.id && (x.cluster_id ?? x.id) !== cluster
    && x.event_countries.some(c => a.event_countries.includes(c))).slice(0, 6) : [];
  const src = sources.find(s => s.key === a.source_key);
  return { article: { ...a, other_publishers: new Set(same.map(x => x.publisher.name).filter(n => n !== a.publisher.name)).size },
    same_story: same.slice(0, 20), related,
    source: src ? { name: src.name, url: src.url, license_note: src.license_note, attribution: null, terms_url: src.terms_url } : null };
}

export async function staticApi(path) {
  const url = new URL(path, "https://x/");
  const p = url.searchParams;
  const route = url.pathname;
  if (route.startsWith("/api/admin") || route.startsWith("/api/auth")) {
    throw Object.assign(new Error("static"), { status: 503, staticMode: true });
  }
  if (route === "/api/meta") return load("meta.json");
  if (route === "/api/dashboard") return load(`dashboard-${p.get("scope") || "world"}.json`);
  if (route.startsWith("/api/metrics/")) return load(`metrics/${encodeURIComponent(route.split("/").pop())}.json`);
  if (route === "/api/articles") return queryArticles(p);
  if (route.startsWith("/api/articles/")) return articleDetail(route.split("/").pop());
  if (route === "/api/sources") return load("sources.json");
  if (route === "/api/search") {
    const q = norm(p.get("q"));
    const [news, reports, dash, sources] = await Promise.all([
      queryArticles(new URLSearchParams({ q: p.get("q"), lang: p.get("lang") || "", content_type: "news", per_page: 10 })),
      queryArticles(new URLSearchParams({ q: p.get("q"), lang: p.get("lang") || "", content_type: "humanitarian_report", per_page: 10 })),
      load("dashboard-world.json"), load("sources.json")]);
    return { q: p.get("q"), articles: news, reports,
      metrics: dash.cards.filter(c => norm(c.name.ar).includes(q) || norm(c.name.en).includes(q)),
      sources: sources.filter(s => norm(s.name).includes(q)) };
  }
  throw Object.assign(new Error("not found"), { status: 404 });
}
