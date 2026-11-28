// Machine translation of a story's title and summary, Arabic <-> English.
//
// Runs in the reader's browser against MyMemory (mymemory.translated.net),
// which needs no key, so nothing secret ships in the page. Each reader has
// their own daily allowance; when it runs out, the reader gets a link to the
// same text in Google Translate instead. Translations are labelled as
// machine translations and the original is one tap away.
import { icon } from "./icons.js";
import { h, t } from "./core.js";

const ENDPOINT = "https://api.mymemory.translated.net/get";
const MAX_CHUNK = 450;  // MyMemory takes up to 500 bytes of query per call
const cache = new Map();

export function targetLanguage(lang) {
  return lang === "ar" ? "en" : "ar";
}

// Split long text at sentence or word boundaries into pieces the API accepts.
function chunks(text) {
  const out = [];
  let rest = text.trim();
  while (rest.length > MAX_CHUNK) {
    const slice = rest.slice(0, MAX_CHUNK);
    let cut = Math.max(slice.lastIndexOf(". "), slice.lastIndexOf("، "), slice.lastIndexOf("؟ "),
      slice.lastIndexOf("! "));
    if (cut < MAX_CHUNK / 2) cut = slice.lastIndexOf(" ");
    if (cut <= 0) cut = MAX_CHUNK - 1;
    out.push(rest.slice(0, cut + 1).trim());
    rest = rest.slice(cut + 1).trim();
  }
  if (rest) out.push(rest);
  return out;
}

async function translateChunk(text, from, to) {
  const url = `${ENDPOINT}?q=${encodeURIComponent(text)}&langpair=${from}|${to}`;
  const res = await fetch(url, { referrerPolicy: "no-referrer" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  const out = data?.responseData?.translatedText;
  if (Number(data?.responseStatus) !== 200 || !out || data.quotaFinished || /MYMEMORY WARNING/i.test(out)) {
    throw new Error(data?.responseDetails || "translation unavailable");
  }
  return out;
}

export async function translateText(text, from, to) {
  const key = `${from}|${to}|${text}`;
  if (!cache.has(key)) {
    const job = Promise.all(chunks(text).map(c => translateChunk(c, from, to))).then(parts => parts.join(" "));
    cache.set(key, job);
    job.catch(() => cache.delete(key));
  }
  return cache.get(key);
}

// The publisher's page itself, through Google's page translator.
export function translatedPageUrl(url, to) {
  return `https://translate.google.com/translate?sl=auto&tl=${to}&u=${encodeURIComponent(url)}`;
}

function googleTextUrl(text, from, to) {
  return `https://translate.google.com/?sl=${from}&tl=${to}&op=translate&text=${encodeURIComponent(text)}`;
}

// A toggle that swaps the given elements' text for its translation and back.
// `targets` are {el, block}: `el` holds the text, `block` is the line it sits
// on; the machine-translation note goes after the last block.
export function translateButton(lang, targets, { compact = false } = {}) {
  const from = lang === "en" ? "en" : "ar";
  const to = targetLanguage(lang);
  const originals = targets.map(({ el }) => ({ text: el.textContent, lang: el.getAttribute("lang"),
    dir: el.getAttribute("dir") }));
  const label = t(`translate.to_${to}`);
  const btn = h("button", { type: "button", class: compact ? "icon-btn translate-btn" : "btn ghost translate-btn",
    "aria-pressed": "false", "aria-label": label, title: label }, icon("languages", compact ? 18 : 16),
    compact ? null : h("span", {}, label));
  const note = h("p", { class: "mt-note small", hidden: true });
  let state = "original";

  const setLabel = text => {
    btn.setAttribute("aria-label", text);
    btn.title = text;
    if (!compact) btn.lastChild.textContent = text;
  };
  const restore = () => {
    targets.forEach(({ el }, i) => {
      el.textContent = originals[i].text;
      for (const attr of ["lang", "dir"]) {
        if (originals[i][attr]) el.setAttribute(attr, originals[i][attr]); else el.removeAttribute(attr);
      }
    });
    note.hidden = true;
    btn.setAttribute("aria-pressed", "false");
    setLabel(label);
    state = "original";
  };

  btn.addEventListener("click", async () => {
    if (state === "busy") return;
    if (state === "translated") return restore();
    if (!note.isConnected) targets.at(-1).block.after(note);
    state = "busy";
    btn.setAttribute("aria-busy", "true");
    setLabel(t("translate.working"));
    try {
      const results = await Promise.all(originals.map(o => translateText(o.text, from, to)));
      targets.forEach(({ el }, i) => {
        el.textContent = results[i];
        el.setAttribute("lang", to);
        el.setAttribute("dir", to === "ar" ? "rtl" : "ltr");
      });
      note.replaceChildren(icon("languages", 13), " ", t("translate.note"));
      btn.setAttribute("aria-pressed", "true");
      setLabel(t("translate.show_original"));
      state = "translated";
    } catch {
      const all = originals.map(o => o.text).join("\n\n");
      note.replaceChildren(t("translate.failed"), " ",
        h("a", { href: googleTextUrl(all, from, to), target: "_blank", rel: "noopener noreferrer" },
          t("translate.google"), " ↗"));
      setLabel(label);
      state = "original";
    } finally {
      btn.removeAttribute("aria-busy");
      note.hidden = false;
    }
  });
  return btn;
}
