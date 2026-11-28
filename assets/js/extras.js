// Today's conditions beside the news: weather, exchange rates, earthquakes.
// All three come from public services that need no key (see
// github.com/public-apis/public-apis), asked directly by the reader's browser,
// so nothing secret ships with the page. Each shows its source and time.
import { h, t, settings, fmtNumber, fmtDateTime, fmtRelative, externalLink } from "./core.js";
import { icon } from "./icons.js";

// --- cities ----------------------------------------------------------------
// The first five are shown until a reader picks their own.
export const CITIES = [
  ["khartoum", "الخرطوم", "Khartoum", 15.5007, 32.5599],
  ["jerusalem", "القدس", "Jerusalem", 31.7683, 35.2137],
  ["riyadh", "الرياض", "Riyadh", 24.7136, 46.6753],
  ["cairo", "القاهرة", "Cairo", 30.0444, 31.2357],
  ["newyork", "نيويورك", "New York", 40.7128, -74.006],
  ["gaza", "غزة", "Gaza", 31.5017, 34.4668],
  ["makkah", "مكة المكرمة", "Makkah", 21.3891, 39.8579],
  ["madinah", "المدينة المنورة", "Madinah", 24.5247, 39.5692],
  ["jeddah", "جدة", "Jeddah", 21.4858, 39.1925],
  ["dammam", "الدمام", "Dammam", 26.4207, 50.0888],
  ["portsudan", "بورتسودان", "Port Sudan", 19.6158, 37.2164],
  ["elfasher", "الفاشر", "El Fasher", 13.6279, 25.3494],
  ["dubai", "دبي", "Dubai", 25.2048, 55.2708],
  ["doha", "الدوحة", "Doha", 25.2854, 51.531],
  ["kuwait", "الكويت", "Kuwait City", 29.3759, 47.9774],
  ["manama", "المنامة", "Manama", 26.2285, 50.586],
  ["muscat", "مسقط", "Muscat", 23.588, 58.3829],
  ["amman", "عمّان", "Amman", 31.9539, 35.9106],
  ["beirut", "بيروت", "Beirut", 33.8938, 35.5018],
  ["damascus", "دمشق", "Damascus", 33.5138, 36.2765],
  ["baghdad", "بغداد", "Baghdad", 33.3152, 44.3661],
  ["sanaa", "صنعاء", "Sana'a", 15.3694, 44.191],
  ["tripoli", "طرابلس", "Tripoli", 32.8872, 13.1913],
  ["tunis", "تونس", "Tunis", 36.8065, 10.1815],
  ["algiers", "الجزائر", "Algiers", 36.7538, 3.0588],
  ["rabat", "الرباط", "Rabat", 34.0209, -6.8416],
  ["istanbul", "إسطنبول", "Istanbul", 41.0082, 28.9784],
  ["london", "لندن", "London", 51.5074, -0.1278],
  ["paris", "باريس", "Paris", 48.8566, 2.3522],
  ["kualalumpur", "كوالالمبور", "Kuala Lumpur", 3.139, 101.6869],
  ["jakarta", "جاكرتا", "Jakarta", -6.2088, 106.8456],
];
const DEFAULT_CITIES = ["khartoum", "jerusalem", "riyadh", "cairo", "newyork"];
const KEY = "obs.cities";

function chosenCities() {
  try {
    const ids = JSON.parse(localStorage.getItem(KEY) || "null");
    if (Array.isArray(ids) && ids.length) return ids.filter(id => CITIES.some(c => c[0] === id));
  } catch { /* storage unavailable */ }
  return DEFAULT_CITIES;
}
function saveCities(ids) {
  try { localStorage.setItem(KEY, JSON.stringify(ids)); } catch { /* this page view only */ }
}
const cityName = c => (settings.lang === "ar" ? c[1] : c[2]);

// WMO weather codes as Open-Meteo reports them.
function condition(code, day) {
  if (code === 0) return [day ? "sun" : "moon_clear", "wx.clear"];
  if (code <= 2) return [day ? "cloud_sun" : "cloud", "wx.partly"];
  if (code === 3) return ["cloud", "wx.cloudy"];
  if (code === 45 || code === 48) return ["cloud_fog", "wx.fog"];
  if (code >= 51 && code <= 67) return ["cloud_rain", code >= 61 ? "wx.rain" : "wx.drizzle"];
  if ((code >= 71 && code <= 77) || code === 85 || code === 86) return ["cloud_snow", "wx.snow"];
  if (code >= 80 && code <= 82) return ["cloud_rain", "wx.showers"];
  if (code >= 95) return ["cloud_lightning", "wx.storm"];
  return ["cloud", "wx.cloudy"];
}

export function weatherStrip() {
  const wrap = h("section", { class: "block weather", "aria-label": t("wx.title") });
  const render = async () => {
    const ids = chosenCities();
    const cities = ids.map(id => CITIES.find(c => c[0] === id));
    const head = h("div", { class: "extras-head" }, h("h2", {}, t("wx.title")),
      h("button", { type: "button", class: "btn ghost small-btn", onclick: () => picker(ids) }, t("wx.choose")));
    const row = h("div", { class: "wx-row" }, cities.map(c => h("div", { class: "wx-card loading-card" }, h("strong", {}, cityName(c)))));
    wrap.replaceChildren(head, row);
    try {
      const url = "https://api.open-meteo.com/v1/forecast?" + new URLSearchParams({
        latitude: cities.map(c => c[3]).join(","), longitude: cities.map(c => c[4]).join(","),
        current: "temperature_2m,weather_code,is_day,wind_speed_10m",
        daily: "temperature_2m_max,temperature_2m_min", forecast_days: "1", timezone: "auto" });
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const list = Array.isArray(data) ? data : [data];
      row.replaceChildren(...cities.map((c, i) => {
        const d = list[i];
        const [ic, label] = condition(d.current.weather_code, d.current.is_day);
        return h("div", { class: "wx-card" },
          h("strong", { class: "wx-city" }, cityName(c)),
          h("div", { class: "wx-now" }, icon(ic, 30), h("span", { class: "wx-temp" }, h("bdi", { dir: "ltr" }, `${Math.round(d.current.temperature_2m)}°`))),
          h("span", { class: "wx-cond" }, t(label)),
          h("span", { class: "muted small" }, h("bdi", { dir: "ltr" },
            `${Math.round(d.daily.temperature_2m_max[0])}° / ${Math.round(d.daily.temperature_2m_min[0])}°`),
            " · ", t("wx.wind", { n: Math.round(d.current.wind_speed_10m) })));
      }));
      wrap.append(h("p", { class: "muted tiny source-line" }, t("wx.source"), " ",
        externalLink("https://open-meteo.com/", "Open-Meteo.com"), " (CC BY 4.0)"));
    } catch {
      row.replaceChildren(h("p", { class: "muted small" }, t("wx.failed")));
    }
  };
  // Choose cities: a checklist in the original order, saved in this browser.
  const picker = ids => {
    const chosen = new Set(ids);
    const list = h("div", { class: "city-list" }, CITIES.map(c => {
      const box = h("input", { type: "checkbox", checked: chosen.has(c[0]) });
      box.addEventListener("change", () => { box.checked ? chosen.add(c[0]) : chosen.delete(c[0]); });
      return h("label", { class: "radio" }, box, cityName(c));
    }));
    const done = h("button", { type: "button", class: "btn" }, t("wx.done"));
    done.addEventListener("click", () => {
      const next = CITIES.map(c => c[0]).filter(id => chosen.has(id));
      saveCities(next.length ? next : DEFAULT_CITIES);
      render();
    });
    const reset = h("button", { type: "button", class: "btn ghost" }, t("wx.reset"));
    reset.addEventListener("click", () => { saveCities(DEFAULT_CITIES); render(); });
    wrap.replaceChildren(h("h2", {}, t("wx.choose")), h("p", { class: "muted small" }, t("wx.choose_note")), list,
      h("div", { class: "actions" }, done, reset));
  };
  render();
  return wrap;
}

// --- exchange rates ---------------------------------------------------------
const RATES = ["sar", "sdg", "egp", "aed", "eur", "gbp"];
const RATE_URLS = ["https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.min.json",
  "https://latest.currency-api.pages.dev/v1/currencies/usd.min.json"];

export function ratesBox() {
  const box = h("section", { class: "block rates" }, h("h2", {}, t("fx.title")), h("p", { class: "loading" }, t("loading")));
  (async () => {
    let data = null;
    for (const url of RATE_URLS) {
      try {
        const res = await fetch(url);
        if (res.ok) { data = await res.json(); break; }
      } catch { /* try the mirror */ }
    }
    if (!data?.usd) { box.replaceChildren(h("h2", {}, t("fx.title")), h("p", { class: "muted small" }, t("fx.failed"))); return; }
    box.replaceChildren(h("h2", {}, t("fx.title")),
      h("table", { class: "rates-table" }, h("tbody", {}, RATES.filter(c => data.usd[c]).map(c => h("tr", {},
        h("th", { scope: "row" }, t(`fx.${c}`)),
        h("td", {}, h("bdi", { dir: "ltr" }, fmtNumber(data.usd[c], { maximumFractionDigits: data.usd[c] < 10 ? 3 : 1 }))))))),
      h("p", { class: "muted tiny" }, t("fx.per_usd")),
      h("p", { class: "muted tiny" }, t("fx.sdg_note")),
      h("p", { class: "muted tiny source-line" }, t("fx.source", { date: data.date }), " ",
        externalLink("https://github.com/fawazahmed0/exchange-api", "Currency API")));
  })();
  return box;
}

// --- earthquakes -------------------------------------------------------------
// Magnitude 4.5 and above in the past week, within the Arab and wider Muslim
// world (a box from West Africa to Indonesia), from the USGS feed.
const QUAKE_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson";
const inRegion = ([lon, lat]) => lat > -11 && lat < 45 && lon > -20 && lon < 141;

export function quakesBox() {
  const box = h("section", { class: "block quakes" }, h("h2", {}, t("eq.title")), h("p", { class: "loading" }, t("loading")));
  (async () => {
    try {
      const res = await fetch(QUAKE_URL);
      if (!res.ok) throw new Error();
      const data = await res.json();
      const list = data.features.filter(f => inRegion(f.geometry.coordinates))
        .sort((a, b) => b.properties.time - a.properties.time).slice(0, 6);
      box.replaceChildren(h("h2", {}, t("eq.title")),
        list.length ? h("ul", { class: "quake-list" }, list.map(f => h("li", {},
          h("span", { class: `mag m${Math.min(7, Math.floor(f.properties.mag))}` }, h("bdi", { dir: "ltr" }, f.properties.mag.toFixed(1))),
          h("span", { class: "quake-place" }, externalLink(f.properties.url, h("bdi", { dir: "ltr" }, f.properties.place || "—")),
            h("span", { class: "muted tiny" }, " · ", fmtRelative(new Date(f.properties.time).toISOString())))))) :
          h("p", { class: "muted small" }, t("eq.none")),
        h("p", { class: "muted tiny source-line" }, t("eq.source"), " ", externalLink("https://earthquake.usgs.gov/", "USGS")));
    } catch {
      box.replaceChildren(h("h2", {}, t("eq.title")), h("p", { class: "muted small" }, t("eq.failed")));
    }
  })();
  return box;
}

// --- prayer times ------------------------------------------------------------
// From Aladhan (aladhan.com), no key. Without a `method` the service applies
// the authority nearest the city (Umm al-Qura in Saudi Arabia, the Egyptian
// authority in Egypt and Sudan, and so on); the box names the method used.
const PRAYERS = ["Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"];
const PRAYER_KEY = "obs.prayer_city";

export function prayerBox() {
  const box = h("section", { class: "block prayer" });
  let cityId;
  try { cityId = localStorage.getItem(PRAYER_KEY); } catch { /* no storage */ }
  if (!CITIES.some(c => c[0] === cityId)) cityId = chosenCities()[0];
  const render = async () => {
    const city = CITIES.find(c => c[0] === cityId);
    const select = h("select", { "aria-label": t("pr.city"), class: "prayer-city" },
      CITIES.map(c => h("option", { value: c[0], selected: c[0] === cityId }, cityName(c))));
    select.addEventListener("change", () => {
      cityId = select.value;
      try { localStorage.setItem(PRAYER_KEY, cityId); } catch { /* this page view only */ }
      render();
    });
    const head = h("div", { class: "extras-head" }, h("h2", {}, t("pr.title")), select);
    box.replaceChildren(head, h("p", { class: "loading" }, t("loading")));
    try {
      const res = await fetch("https://api.aladhan.com/v1/timings?" + new URLSearchParams({ latitude: city[3], longitude: city[4] }));
      const data = (await res.json())?.data;
      if (!res.ok || !data?.timings) throw new Error();
      const tz = data.meta?.timezone;
      // Now, in the city's own time, to mark the next prayer.
      const now = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: tz })
        .format(new Date());
      const clean = v => String(v).slice(0, 5);
      const next = PRAYERS.filter(p => p !== "Sunrise").find(p => clean(data.timings[p]) > now) || "Fajr";
      const hijri = data.date?.hijri;
      box.replaceChildren(head,
        hijri ? h("p", { class: "hijri" }, `${hijri.day} ${settings.lang === "ar" ? hijri.month.ar : hijri.month.en} ${hijri.year} ${t("pr.ah")}`) : null,
        h("table", { class: "prayer-table" }, h("tbody", {}, PRAYERS.map(p => h("tr", { class: p === next ? "next" : "" },
          h("th", { scope: "row" }, t(`pr.${p.toLowerCase()}`), p === next ? h("span", { class: "next-tag" }, t("pr.next")) : null),
          h("td", {}, h("bdi", { dir: "ltr" }, clean(data.timings[p]))))))),
        h("p", { class: "muted tiny source-line" }, t("pr.source", { method: data.meta?.method?.name || "—" }), " ",
          externalLink("https://aladhan.com/", "Aladhan")));
    } catch {
      box.replaceChildren(head, h("p", { class: "muted small" }, t("pr.failed")));
    }
  };
  render();
  return box;
}

// Prayer times, exchange rates and earthquakes side by side, under the weather.
export function todayRow() {
  return h("div", { class: "today-row" }, prayerBox(), ratesBox(), quakesBox());
}
