// Screenshots of the running site, for the live check: node screenshots.mjs <base> <outdir>
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const [base = "http://localhost:8000", out = "shots"] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
const errors = [];
const pages = [
  ["home-ar", "/#/", "ar", 1280], ["home-en", "/#/", "en", 1280], ["home-mobile", "/#/", "ar", 390],
  ["sudan", "/#/section/sudan", "ar", 1280], ["sports", "/#/section/sports", "ar", 1280],
  ["palestine", "/#/section/palestine", "ar", 390], ["admin", "/admin", "ar", 1280],
];
for (const [name, path, lang, width] of pages) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 } });
  await ctx.addInitScript(([l]) => localStorage.setItem("obs.settings",
    JSON.stringify({ lang: l, theme: "light", timeZone: "Asia/Riyadh" })), [lang]);
  const page = await ctx.newPage();
  page.on("pageerror", e => errors.push(`${name}: ${e.message}`));
  await page.goto(base + path);
  await page.waitForTimeout(2500);
  // An error the page shows politely is still an error.
  const shown = await page.locator(".error").allInnerTexts();
  for (const text of shown) errors.push(`${name}: page shows an error: ${text.trim()}`);
  await page.screenshot({ path: `${out}/${name}.png`, fullPage: width > 400 });
  await ctx.close();
}
await browser.close();
console.log(errors.length ? errors.join("\n") : "screenshots taken, no page errors");
if (errors.length) process.exit(1);
