// "Fetch details" for the add-story form: paste the story's link, get its
// title, summary, picture, publisher and date to review before saving.
//
// With a server, the server reads the page (/api/admin/articles/preview).
// On GitHub Pages there is no server and browsers may not read other sites,
// so the page asks Microlink (microlink.io, free, no key) for the same
// link-preview tags. Nothing is saved until the editor presses save.
import { h, t } from "./core.js";
import { META } from "./components.js";
import { icon } from "./icons.js";

async function microlink(url) {
  const res = await fetch(`https://api.microlink.io/?url=${encodeURIComponent(url)}`, { referrerPolicy: "no-referrer" });
  const data = await res.json().catch(() => null);
  if (!res.ok || data?.status !== "success") throw new Error(data?.message || `HTTP ${res.status}`);
  const d = data.data || {};
  return { title: d.title, description: d.description, image_url: (d.image?.url || "").startsWith("https://") ? d.image.url : null,
    publisher_name: d.publisher, author: d.author, published_at: d.date, language: (d.lang || "").slice(0, 2) };
}

const localInput = iso => {
  const d = new Date(iso);
  return isNaN(d) ? null : new Date(d - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};

// A country from the site's address, when it is a country domain we know (.sa, .sd, …).
function countryFromHost(url) {
  try {
    const tld = new URL(url).hostname.split(".").pop().toUpperCase();
    return tld.length === 2 && META.countries?.[tld] ? tld : null;
  } catch { return null; }
}

// Adds the button beside the link field and an image preview; `serverCall`
// is given on the server build, left out on GitHub Pages.
export function previewTools(form, { serverCall } = {}) {
  const urlInput = form.elements.url;
  const imageInput = form.elements.image_url;
  const out = h("div", { class: "preview-out", role: "status" });
  const img = h("img", { alt: "", referrerpolicy: "no-referrer", hidden: true, class: "preview-img" });
  const showImage = () => {
    const src = imageInput.value.trim();
    img.hidden = !src.startsWith("https://");
    if (!img.hidden) img.src = src;
  };
  imageInput.addEventListener("input", showImage);
  img.addEventListener("error", () => { img.hidden = true; });

  const btn = h("button", { type: "button", class: "btn ghost" }, icon("search", 16), " ", t("preview.fetch"));
  btn.addEventListener("click", async () => {
    const url = urlInput.value.trim();
    if (!/^https?:\/\//.test(url)) { out.replaceChildren(h("p", { class: "error" }, t("preview.need_link"))); return; }
    btn.disabled = true; btn.setAttribute("aria-busy", "true");
    out.replaceChildren(h("p", { class: "muted small" }, t("preview.working")));
    try {
      const d = serverCall ? await serverCall(url) : await microlink(url);
      const set = (name, value) => { if (value && form.elements[name]) form.elements[name].value = value; };
      set("title", d.title);
      set("description", d.description);
      set("publisher_name", d.publisher_name);
      set("image_url", d.image_url);
      if (d.published_at) set("published_at", localInput(d.published_at));
      const lang = d.language === "en" || d.language === "ar" ? d.language
        : /\p{Script=Arabic}/u.test(d.title || "") ? "ar" : "en";
      set("language", lang);
      const country = countryFromHost(url);
      if (country && form.elements.publisher_country && !form.elements.publisher_country.value) set("publisher_country", country);
      showImage();
      out.replaceChildren(h("p", { class: "ok" }, d.title ? t("preview.done") : t("preview.partial")));
    } catch (err) {
      out.replaceChildren(h("p", { class: "error" }, t("preview.failed"), " ", h("span", { class: "muted small" }, err.message)));
    } finally {
      btn.disabled = false; btn.removeAttribute("aria-busy");
    }
  });
  urlInput.closest(".field").after(h("div", { class: "preview-row" }, btn,
    h("span", { class: "muted small" }, serverCall ? t("preview.note.server") : t("preview.note.static"))), out);
  imageInput.closest(".field").after(img);
}
