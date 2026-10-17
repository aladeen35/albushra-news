// "Share as a card": the story drawn as a newspaper clipping (1080×1350 PNG),
// shared with a caption that links back to the story in Al-Bushra News.
//
// Layout follows what the story has: headline at the top always; with a
// picture and a summary, the picture sits in a corner and the summary wraps
// around it; a picture alone runs large; a summary alone is set as a column;
// a bare headline is set larger. Publishers' pictures are drawn only when
// their server allows it (CORS); otherwise the card is laid out without one.
import { h, t, settings } from "./core.js";
import { icon } from "./icons.js";

const W = 1080, H = 1350, M = 72;
const INK = "#1d1b17", INK_SOFT = "#4a463d", PAPER = "#efe8d8", RULE = "rgba(29,27,23,.35)", RED = "#a3241a";
const HEAD = '"Rakkas", "Markazi", serif', BODY = '"Markazi", serif';

function loadImage(src, cors = true) {
  return new Promise(resolve => {
    if (!src) return resolve(null);
    const img = new Image();
    if (cors) img.crossOrigin = "anonymous";
    img.referrerPolicy = "no-referrer";
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = src;
    setTimeout(() => resolve(null), 8000);
  });
}

// Split text into lines no wider than `width(i)` (the i-th line's width).
function wrap(ctx, text, width, maxLines) {
  const words = String(text || "").split(/\s+/).filter(Boolean);
  const lines = [];
  let line = "";
  for (const word of words) {
    const test = line ? `${line} ${word}` : word;
    if (ctx.measureText(test).width > width(lines.length) && line) {
      lines.push(line);
      line = word;
      if (lines.length === maxLines) break;
    } else line = test;
  }
  if (lines.length < maxLines && line) lines.push(line);
  const used = lines.join(" ").split(/\s+/).length;
  if (used < words.length && lines.length) {
    let last = lines[lines.length - 1];
    while (last && ctx.measureText(last + " …").width > width(lines.length - 1)) last = last.replace(/\s*\S+$/, "");
    lines[lines.length - 1] = `${last} …`;
  }
  return lines;
}

function rule(ctx, y, double = false, x0 = M, x1 = W - M) {
  ctx.fillStyle = INK;
  ctx.fillRect(x0, y, x1 - x0, double ? 2 : 1.5);
  if (double) ctx.fillRect(x0, y + 6, x1 - x0, 2);
}

// Draw `img` to cover the box, cropped from the centre, inside a print frame.
function framedImage(ctx, img, x, y, w, h) {
  ctx.fillStyle = "#f7f1e3";
  ctx.fillRect(x - 10, y - 10, w + 20, h + 20);
  ctx.strokeStyle = INK;
  ctx.lineWidth = 2;
  ctx.strokeRect(x - 10, y - 10, w + 20, h + 20);
  const scale = Math.max(w / img.naturalWidth, h / img.naturalHeight);
  const sw = w / scale, sh = h / scale;
  ctx.drawImage(img, (img.naturalWidth - sw) / 2, (img.naturalHeight - sh) / 2, sw, sh, x, y, w, h);
}

function grain(ctx) {
  ctx.fillStyle = PAPER;
  ctx.fillRect(0, 0, W, H);
  // A light, fixed speckle so the paper is not flat; deterministic, so every card matches.
  let seed = 7;
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  for (let i = 0; i < 9000; i++) {
    ctx.fillStyle = `rgba(90,76,50,${0.03 + rnd() * 0.05})`;
    ctx.fillRect(rnd() * W, rnd() * H, 1.4, 1.4);
  }
  ctx.strokeStyle = INK;
  ctx.lineWidth = 2;
  ctx.strokeRect(28, 28, W - 56, H - 56);
  ctx.lineWidth = 1;
  ctx.strokeRect(38, 38, W - 76, H - 76);
}

export async function drawCard(a) {
  await Promise.all([`64px ${HEAD}`, `36px ${BODY}`, `bold 36px ${BODY}`].map(f =>
    document.fonts?.load(f, "البشرى News").catch(() => null)));
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");
  const ui = settings.lang === "ar" ? "rtl" : "ltr";
  const dir = a.language === "en" ? "ltr" : a.language === "ar" ? "rtl" : ui;
  const start = d => (d === "rtl" ? W - M : M);
  const [photo, logo] = await Promise.all([loadImage(a.image_url), loadImage("assets/icons/icon-128.png", false)]);
  grain(ctx);

  // Masthead
  ctx.textBaseline = "alphabetic";
  ctx.direction = ui;
  ctx.textAlign = "center";
  ctx.fillStyle = INK;
  ctx.font = `92px ${HEAD}`;
  ctx.fillText(t("app.name"), W / 2, 158);
  rule(ctx, 186, true);
  ctx.font = `26px ${BODY}`;
  ctx.fillStyle = INK_SOFT;
  const date = new Intl.DateTimeFormat(settings.lang === "ar" ? "ar-u-ca-gregory-nu-latn" : "en-GB",
    { day: "numeric", month: "long", year: "numeric", timeZone: settings.timeZone }).format(new Date(a.published_at));
  ctx.textAlign = ui === "rtl" ? "right" : "left";
  ctx.fillText(date, start(ui), 228);
  ctx.textAlign = ui === "rtl" ? "left" : "right";
  ctx.fillText(t("app.edition"), ui === "rtl" ? M : W - M, 228);
  ctx.textAlign = "center";
  ctx.font = `28px ${HEAD}`;
  ctx.fillStyle = INK;
  ctx.fillText(t("app.motto"), W / 2, 228);
  rule(ctx, 246);

  // Kicker band: publisher
  const band = `${t("share.card.from")} ${a.publisher?.name || ""}`;
  ctx.font = `bold 30px ${BODY}`;
  const bw = Math.min(W - 2 * M, ctx.measureText(band).width + 48);
  const bx = dir === "rtl" ? W - M - bw : M;
  ctx.fillStyle = INK;
  ctx.fillRect(bx, 270, bw, 50);
  ctx.fillStyle = PAPER;
  ctx.direction = dir;
  ctx.textAlign = "center";
  ctx.fillText(band, bx + bw / 2, 305);

  const hasDesc = !!(a.description && a.description.trim().length > 20);
  const body = { top: 0, bottom: H - 190 };

  // Headline: as large as fits in its line budget.
  ctx.direction = dir;
  ctx.textAlign = dir === "rtl" ? "right" : "left";
  ctx.fillStyle = INK;
  const maxLines = !photo && !hasDesc ? 6 : 4;
  let size = !photo && !hasDesc ? 104 : 76, lines;
  for (; size >= 48; size -= 4) {
    ctx.font = `${size}px ${HEAD}`;
    lines = wrap(ctx, a.title, () => W - 2 * M, 99);
    if (lines.length <= maxLines) break;
  }
  ctx.font = `${size}px ${HEAD}`;
  lines = wrap(ctx, a.title, () => W - 2 * M, maxLines);
  const lh = size * 1.32;
  let y = 352 + size;
  if (!photo && !hasDesc) y = Math.max(y, (360 + body.bottom) / 2 - (lines.length * lh) / 2 + size * .8);
  for (const line of lines) { ctx.fillText(line, start(dir), y); y += lh; }
  y += 8 - lh + size * .4;
  rule(ctx, y);
  body.top = y + 34;

  ctx.font = `38px ${BODY}`;
  const bodyLh = 58;
  if (photo && hasDesc) {
    // Picture in the corner, summary flowing beside and under it.
    const pw = 410, ph = Math.min(400, Math.round(pw * photo.naturalHeight / photo.naturalWidth) || 300, body.bottom - body.top - 20);
    const px = dir === "rtl" ? W - M - pw - 10 : M + 10;
    framedImage(ctx, photo, px, body.top + 10, pw, ph);
    const sideW = W - 2 * M - pw - 56;
    // Lines whose top would sit above the frame's lower edge stay beside the picture.
    const besideLines = Math.ceil((ph + 40) / bodyLh);
    const total = Math.floor((body.bottom - body.top) / bodyLh);
    ctx.fillStyle = INK;
    const text = wrap(ctx, a.description, i => (i < besideLines ? sideW : W - 2 * M), total);
    let ty = body.top + 40;
    text.forEach((line, i) => {
      const x = i < besideLines ? (dir === "rtl" ? W - M - pw - 56 : M + pw + 56) : start(dir);
      ctx.fillText(line, x, ty);
      ty += bodyLh;
    });
  } else if (photo) {
    const pw = W - 2 * M - 20, ph = Math.min(body.bottom - body.top - 30, Math.round(pw * 0.62));
    framedImage(ctx, photo, M + 10, body.top + 10, pw, ph);
  } else if (hasDesc) {
    // A single column with a large opening quote mark, set a little larger.
    ctx.font = `44px ${BODY}`;
    ctx.fillStyle = RED;
    ctx.font = `120px ${HEAD}`;
    ctx.fillText(dir === "rtl" ? "”" : "“", start(dir), body.top + 92);
    ctx.font = `44px ${BODY}`;
    ctx.fillStyle = INK;
    const text = wrap(ctx, a.description, () => W - 2 * M - 90, Math.floor((body.bottom - body.top - 40) / 66));
    let ty = body.top + 70;
    for (const line of text) { ctx.fillText(line, dir === "rtl" ? W - M - 90 : M + 90, ty); ty += 66; }
  }

  // Footer: where to read the whole story.
  rule(ctx, H - 168, true);
  ctx.direction = ui;
  ctx.textAlign = ui === "rtl" ? "right" : "left";
  if (logo) ctx.drawImage(logo, ui === "rtl" ? W - M - 70 : M, H - 140, 70, 70);
  const fx = ui === "rtl" ? W - M - 90 : M + 90;
  ctx.fillStyle = INK;
  ctx.font = `34px ${HEAD}`;
  ctx.fillText(t("share.card.read"), fx, H - 108);
  ctx.font = `26px ${BODY}`;
  ctx.fillStyle = INK_SOFT;
  ctx.fillText(t("share.card.source", { name: a.publisher?.name || "—" }), fx, H - 72);
  return canvas;
}

// The story's address inside Al-Bushra News (this site or app), for the caption.
export function storyLink(a) {
  return `${location.origin}${location.pathname}#/article/${encodeURIComponent(a.id)}`;
}

export function caption(a) {
  return `${a.title}\n\n${t("share.card.caption")}\n${storyLink(a)}`;
}

const blobOf = canvas => new Promise(r => canvas.toBlob(r, "image/png"));

// Opens a preview with Share / Save / Copy; sharing needs a fresh tap, so the
// share sheet opens from the dialog's button, not after drawing.
export async function openShareCard(a) {
  const dialog = h("dialog", { class: "share-dialog", "aria-label": t("share.card.title") });
  const body = h("div", { class: "share-body" }, h("p", { class: "loading" }, t("share.card.drawing")));
  dialog.append(h("div", { class: "share-head" }, h("strong", {}, t("share.card.title")),
    h("button", { type: "button", class: "icon-btn", "aria-label": t("share.card.close"), onclick: () => dialog.close() }, "✕")), body);
  dialog.addEventListener("close", () => dialog.remove());
  document.body.append(dialog);
  dialog.showModal();
  let canvas;
  try {
    canvas = await drawCard(a);
  } catch (err) {
    body.replaceChildren(h("p", { class: "error" }, t("share.card.failed"), " ", err.message));
    return;
  }
  const png = canvas.toDataURL("image/png");
  const text = caption(a);
  const out = h("p", { class: "muted small", role: "status" });
  const shareBtn = h("button", { type: "button", class: "btn" }, icon("share", 16), t("share.card.share"));
  shareBtn.addEventListener("click", async () => {
    try {
      if (window.AlBushraApp?.shareImage) {
        if (!window.AlBushraApp.shareImage(png, text)) throw new Error("app");
        return;
      }
      const file = new File([await blobOf(canvas)], "albushra-news.png", { type: "image/png" });
      if (navigator.canShare?.({ files: [file] })) {
        await navigator.share({ files: [file], text });
        return;
      }
      await save();
      await copy();
      out.textContent = t("share.card.saved_and_copied");
    } catch (err) {
      if (err?.name !== "AbortError") out.textContent = t("share.card.failed");
    }
  });
  const save = async () => {
    const link = h("a", { href: png, download: "albushra-news.png" });
    link.click();
  };
  const copy = async () => {
    try { await navigator.clipboard.writeText(text); return true; } catch { return false; }
  };
  const saveBtn = h("button", { type: "button", class: "btn ghost" }, t("share.card.save"));
  saveBtn.addEventListener("click", save);
  const copyBtn = h("button", { type: "button", class: "btn ghost" }, t("share.card.copy"));
  copyBtn.addEventListener("click", async () => { out.textContent = (await copy()) ? t("share.card.copied") : text; });
  body.replaceChildren(
    h("img", { class: "share-preview", src: png, alt: a.title }),
    h("div", { class: "actions" }, shareBtn, saveBtn, copyBtn), out,
    h("p", { class: "small share-caption", dir: "auto" }, text));
}

export function shareCardButton(a, { compact = true } = {}) {
  const label = t("share.card.button");
  const btn = h("button", { type: "button", class: compact ? "icon-btn" : "btn ghost", title: label, "aria-label": label },
    icon("share", compact ? 18 : 16), compact ? null : h("span", {}, label));
  btn.addEventListener("click", () => openShareCard(a));
  return btn;
}
