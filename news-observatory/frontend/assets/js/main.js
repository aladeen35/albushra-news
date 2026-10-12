// Router and shell. Hash routes keep the app a static bundle any server can host.
import { every, h, t, settings, applySettings, loadLanguage, api, saveSettings, fmtDateTime } from "./core.js";
import { setMeta, META, errorState, loading, flag } from "./components.js";
import { homeView, sectionView, articleView, metricView, searchView, howView, settingsView,
  savedView, sourcesView, forYouView } from "./views.js";
import { icon } from "./icons.js";
import { adminView } from "./admin.js";

// [href, label key, icon name or null, flag code or null]
const NAV = [
  ["#/", "nav.home", "home", null], ["#/foryou", "nav.foryou", "foryou", null],
  ["#/section/world", "section.world", "world", null], ["#/section/palestine", "section.palestine", null, "PS"],
  ["#/section/saudi", "section.saudi", null, "SA"], ["#/section/sudan", "section.sudan", null, "SD"], ["#/section/sports", "section.sports", "sports", null],
  ["#/section/arab_world", "section.arab_world", "arab", null],
  ["#/section/islamic_world", "section.islamic_world", "islamic", null],
];
// The phone tab bar, as in the reference design.
const TABS = [
  ["#/", "nav.home", "home", null], ["#/section/saudi", "section.saudi", null, "SA"],
  ["#/section/sudan", "section.sudan", null, "SD"], ["#/section/sports", "section.sports", "sports", null],
  ["#/foryou", "nav.foryou", "foryou", null], ["#/saved", "nav.saved", "saved", null],
];

function navMark(iconName, code) {
  return code ? flag(code) : icon(iconName, 17);
}

function parse() {
  const raw = location.hash.replace(/^#/, "") || "/";
  const [path, query = ""] = raw.split("?");
  return { parts: path.split("/").filter(Boolean), params: new URLSearchParams(query) };
}

function shell() {
  const route = location.hash.split("?")[0] || "#/";
  const langBtn = h("button", { class: "btn ghost lang-switch", type: "button",
    lang: settings.lang === "ar" ? "en" : "ar" }, settings.lang === "ar" ? "English" : "العربية");
  langBtn.addEventListener("click", async () => {
    const next = settings.lang === "ar" ? "en" : "ar";
    await loadLanguage(next);
    saveSettings({ lang: next });
    render();
  });
  const search = h("form", { class: "header-search", role: "search" },
    h("input", { type: "search", name: "q", "aria-label": t("search.label"), placeholder: t("search.placeholder"),
      minlength: 2, maxlength: 200 }));
  search.addEventListener("submit", e => {
    e.preventDefault();
    const q = new FormData(search).get("q");
    if (q) location.hash = `#/search?q=${encodeURIComponent(q)}`;
  });
  document.querySelector("header").replaceChildren(
    h("a", { class: "skip", href: "#main", onclick: e => { e.preventDefault(); document.getElementById("main").focus(); } }, t("a11y.skip")),
    h("div", { class: "brandbar" }, h("div", { class: "bar" },
      h("a", { class: "brand", href: "#/" }, h("img", { src: "assets/icons/icon-128.png", alt: "", width: 40, height: 40 }),
        h("span", { class: "brand-text" }, h("strong", {}, t("app.name")), h("small", {}, t("app.tagline")))),
      search,
      h("nav", { class: "tools", "aria-label": t("nav.tools") },
        h("a", { href: "#/sources", title: t("nav.sources"), class: "tool" }, icon("sources", 20), h("span", {}, t("nav.sources"))),
        h("a", { href: "#/saved", title: t("nav.saved"), class: "tool" }, icon("saved", 20), h("span", {}, t("nav.saved"))),
        h("a", { href: "#/settings", title: t("nav.settings"), class: "tool" }, icon("settings", 20), h("span", {}, t("nav.settings"))),
        langBtn))),
    h("nav", { class: "sections", "aria-label": t("nav.sections") }, h("div", { class: "sections-inner" },
      NAV.map(([href, key, ic, code]) => h("a", { href, "aria-current": route === href ? "page" : null },
        navMark(ic, code), h("span", {}, t(key)))))),
    // replaceChildren() would print a bare null as text, so skip it.
    ...(META?.demo ? [h("div", { class: "demo-banner", role: "note" }, t("demo.banner"))] : []),
    ...(META?.static ? [h("div", { class: "static-banner", role: "note" },
      t(META.static.repo ? "static.banner.pages" : "static.banner",
        { time: fmtDateTime(META.static.generated_at), every: every(META.static.fetch_minutes) }))] : []));
  document.querySelector("nav.tabbar").replaceChildren(
    ...TABS.map(([href, key, ic, code]) => h("a", { href, "aria-current": route === href ? "page" : null },
      navMark(ic, code), h("span", {}, t(key)))));
  document.querySelector("footer").replaceChildren(h("div", { class: "footer-inner" },
    h("div", { class: "footer-grid" },
      h("div", { class: "footer-brand" },
        h("a", { class: "brand", href: "#/" }, h("img", { src: "assets/icons/icon-128.png", alt: "", width: 44, height: 44 }),
          h("span", { class: "brand-text" }, h("strong", {}, t("app.name")), h("small", {}, t("app.tagline")))),
        h("p", {}, t("footer.about"))),
      h("nav", { "aria-label": t("footer.sections") }, h("h3", {}, t("footer.sections")),
        h("ul", {}, NAV.slice(2).map(([href, key]) => h("li", {}, h("a", { href }, t(key)))))),
      h("nav", { "aria-label": t("footer.more") }, h("h3", {}, t("footer.more")),
        h("ul", {},
          h("li", {}, h("a", { href: "#/how" }, t("nav.how"))),
          h("li", {}, h("a", { href: "#/sources" }, t("nav.sources"))),
          h("li", {}, h("a", { href: "#/saved" }, t("nav.saved"))),
          h("li", {}, h("a", { href: "#/settings" }, t("nav.settings"))),
          h("li", {}, h("a", { href: "#/admin" }, icon("admin", 14), " ", t("nav.admin")))))),
    h("p", { class: "footer-rights" }, t("footer.rights", { y: new Date().getFullYear() }))));
  document.title = t("app.name");
}

async function render() {
  applySettings();
  shell();
  const main = document.getElementById("main");
  const { parts, params } = parse();
  main.replaceChildren(loading());
  try {
    let view;
    const [a, b] = parts;
    if (!a) view = homeView(params);
    else if (a === "section" && b) view = sectionView(params, b);
    else if (a === "article" && b) view = await articleView(b);
    else if (a === "metric" && b) view = await metricView(b);
    else if (a === "search") view = searchView(params);
    else if (a === "how") view = howView();
    else if (a === "settings") view = settingsView(render);
    else if (a === "saved") view = savedView();
    else if (a === "sources") view = await sourcesView(render);
    else if (a === "foryou") view = forYouView(params);
    else if (a === "admin") view = adminView(params, render);
    else view = h("p", { class: "empty" }, t("error.not_found"));
    main.replaceChildren(view);
  } catch (err) {
    main.replaceChildren(err.status === 404 ? h("p", { class: "empty" }, t("error.not_found")) : errorState(err));
  }
}

async function boot() {
  applySettings();
  await Promise.all([loadLanguage("en"), loadLanguage(settings.lang)]);
  try { setMeta(await api("/api/meta")); }
  catch (err) { shell(); document.getElementById("main").replaceChildren(errorState(err)); return; }
  window.addEventListener("hashchange", () => { render(); window.scrollTo(0, 0); });
  render();
}

boot();
