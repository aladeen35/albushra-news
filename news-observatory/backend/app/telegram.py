"""Posting the site's stories to Telegram channels, after each build.

Channels and what each carries live in content/channels.json (edited from the
admin page). The bot's token is a repository secret (TELEGRAM_BOT_TOKEN) and
never reaches the site. What was already posted is remembered in
data/telegram-state.json, published with the site, so a story is sent once.

Each message: the platform's name, the headline, a short summary, the
publisher, and a link to the story inside Al-Bushra News. With a picture the
message is that picture with the text as its caption.
"""
from __future__ import annotations

import html
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

API = "https://api.telegram.org"
MAX_PER_RUN = 45          # all channels together; Telegram allows ~20 a minute per channel
PAUSE = 3.2               # seconds between two messages
FRESH_HOURS = 6           # older stories are never posted
REMEMBER = 3000           # ids kept per channel

DEFAULT_CHANNELS = {
    "channels": [
        {"key": "main", "name": "الشاملة", "chat": "", "filter": "top", "limit": 5},
        {"key": "sudan", "name": "السودان", "chat": "", "filter": "sudan", "limit": 15},
        {"key": "palestine", "name": "فلسطين", "chat": "", "filter": "palestine", "limit": 15},
        {"key": "saudi", "name": "السعودية", "chat": "", "filter": "saudi", "limit": 15},
        {"key": "sports", "name": "الرياضة", "chat": "", "filter": "sports", "limit": 5},
    ],
    "numbers": {"chat": "", "hour": 6, "tz": "Asia/Riyadh",
                "cities": [["الخرطوم", 15.5007, 32.5599], ["مكة المكرمة", 21.3891, 39.8579],
                           ["القدس", 31.7683, 35.2137]]},
    "language": "ar",
}


def load_config(folder: Path) -> dict:
    try:
        data = json.loads((folder / "channels.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return DEFAULT_CHANNELS
    merged = {**DEFAULT_CHANNELS, **data}
    merged["numbers"] = {**DEFAULT_CHANNELS["numbers"], **(data.get("numbers") or {})}
    return merged


def chat_id(raw: str) -> str:
    """'albushra_sd', '@albushra_sd', 't.me/albushra_sd' or a numeric id -> what the API takes."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    raw = raw.rsplit("/", 1)[-1] if "t.me/" in raw else raw
    return raw if raw.startswith("@") or raw.lstrip("-").isdigit() else "@" + raw


# --- choosing stories -----------------------------------------------------------

def _matches(a: dict, kind: str) -> bool:
    countries = a.get("event_countries") or []
    if kind == "sudan":
        return "SD" in countries
    if kind == "palestine":
        return "PS" in countries
    if kind == "saudi":
        return "SA" in countries or ((a.get("publisher") or {}).get("country") == "SA" and not countries)
    if kind == "sports":
        return "sports" in (a.get("topics") or [])
    return True  # "top": every story, ranked


def pick(articles: list[dict], kind: str, limit: int, seen: set[str], now: datetime,
         language: str | None = "ar") -> list[dict]:
    """The best new stories for one channel: fresh, not yet posted, one per story cluster."""
    cutoff = now - timedelta(hours=FRESH_HOURS)
    breadth: dict = {}
    for a in articles:
        k = a.get("cluster_id") or a["id"]
        breadth[k] = breadth.get(k, 0) + 1
    posted_clusters = {a.get("cluster_id") for a in articles if a["id"] in seen and a.get("cluster_id")}
    best: dict = {}
    for a in articles:
        if a["id"] in seen or a.get("is_demo") or not _matches(a, kind):
            continue
        if language and a.get("language") != language:
            continue
        try:
            published = datetime.fromisoformat(a["published_at"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if published < cutoff or published > now + timedelta(minutes=10):
            continue
        cluster = a.get("cluster_id") or a["id"]
        if cluster in posted_clusters:
            continue
        hours = (now - published).total_seconds() / 3600
        score = 0.5 ** (hours / 3) + 0.25 * min(1, (breadth[cluster] - 1) / 4) + 0.3 * a.get("reliability", 0.5)
        if cluster not in best or score > best[cluster][0]:
            best[cluster] = (score, a)
    ranked = sorted(best.values(), key=lambda x: x[0], reverse=True)[:limit]
    # Oldest first, so the channel reads in the order things happened.
    return sorted((a for _, a in ranked), key=lambda a: a["published_at"])


# --- messages ------------------------------------------------------------------

def story_link(site: str, a: dict) -> str:
    return f"{site.rstrip('/')}/#/article/{a['id']}"


def story_text(a: dict, site: str, limit: int = 1000) -> str:
    e = html.escape
    desc = (a.get("description") or "").strip()
    if len(desc) > 320:
        desc = desc[:320].rsplit(" ", 1)[0] + " …"
    parts = ["📰 <b>البشرى للأخبار</b>", f"<b>{e(a['title'].strip())}</b>"]
    if desc:
        parts.append(e(desc))
    parts.append(f"المصدر: {e((a.get('publisher') or {}).get('name') or '—')}")
    parts.append(f'🔗 <a href="{e(story_link(site, a))}">اقرأ الخبر في البشرى للأخبار</a>')
    text = "\n\n".join(parts)
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _fmt(n: float) -> str:
    return f"{int(round(n)):,}"


def numbers_text(dashboards: dict, quakes: list[dict], prayers: list[tuple], hijri: str | None, today: str,
                 site: str) -> str:
    e = html.escape
    out = ["📊 <b>البشرى للأخبار — أرقام اليوم</b>", e(today + (f" · {hijri}" if hijri else ""))]
    for title, cards in dashboards.items():
        lines = []
        for c in cards:
            cur = c.get("current")
            if not cur or c.get("status") != "current" or cur.get("is_demo"):
                continue
            note = "" if cur.get("review_status") == "approved" else " (لم يراجعه محرر)"
            lines.append(f"• {e(c['name']['ar'])}: <b>{_fmt(cur['value'])}</b> {e(cur['unit']['ar'])}"
                         f" — {e(cur['producer'])}، حتى {e(cur['period_end'])}{note}")
        if lines:
            out.append(f"<b>{e(title)}</b>\n" + "\n".join(lines))
    if quakes:
        out.append("<b>🌍 زلازل آخر 24 ساعة (4.5 فأكثر)</b>\n" + "\n".join(
            f"• {q['mag']:.1f} — {e(q['place'])}" for q in quakes[:6]))
    else:
        out.append("<b>🌍 زلازل آخر 24 ساعة</b>\nلم تُسجَّل زلازل بقوة 4.5 فأكثر في المنطقة.")
    if prayers:
        out.append("<b>🕌 مواقيت الصلاة</b>\n" + "\n".join(
            f"• {e(city)}: الفجر {t['Fajr']} · الظهر {t['Dhuhr']} · العصر {t['Asr']} · المغرب {t['Maghrib']}"
            f" · العشاء {t['Isha']}" for city, t in prayers))
    out.append(f'🔗 <a href="{e(site.rstrip("/"))}/">البشرى للأخبار — العالم بالأرقام</a>')
    out.append("المصادر: OCHA وIOM وHDX للأرقام، USGS للزلازل، Aladhan للمواقيت.")
    return "\n\n".join(out)


# --- sending -------------------------------------------------------------------

class Telegram:
    def __init__(self, token: str, http: httpx.Client | None = None, pause: float = PAUSE):
        self.base = f"{API}/bot{token}"
        self.http = http or httpx.Client(timeout=30)
        self.pause = pause

    def _call(self, method: str, payload: dict) -> dict:
        for attempt in range(3):
            r = self.http.post(f"{self.base}/{method}", json=payload)
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if r.status_code == 429:  # too fast: wait as told
                time.sleep(min(60, (data.get("parameters") or {}).get("retry_after", 5)) + 1)
                continue
            if not data.get("ok"):
                raise RuntimeError(data.get("description") or f"HTTP {r.status_code}")
            return data["result"]
        raise RuntimeError("rate limited")

    def send(self, chat: str, text: str, photo: str | None = None) -> None:
        if photo:
            try:
                self._call("sendPhoto", {"chat_id": chat, "photo": photo, "caption": text[:1024], "parse_mode": "HTML"})
                time.sleep(self.pause)
                return
            except RuntimeError:
                pass  # the picture was refused: send the text alone
        self._call("sendMessage", {"chat_id": chat, "text": text[:4096], "parse_mode": "HTML",
                                   "link_preview_options": {"is_disabled": True}})
        time.sleep(self.pause)


def publish_stories(tg: Telegram, config: dict, articles: list[dict], state: dict, site: str,
                    now: datetime, log=print) -> int:
    sent = 0
    posted = state.setdefault("posted", {})
    for ch in config["channels"]:
        chat = chat_id(ch.get("chat"))
        if not chat or ch.get("enabled") is False:
            continue
        seen = set(posted.get(ch["key"], []))
        batch = pick(articles, ch.get("filter", "top"), int(ch.get("limit", 5)), seen, now,
                     config.get("language") or None)
        for a in batch:
            if sent >= MAX_PER_RUN:
                break
            photo = a.get("image_url") if str(a.get("image_url") or "").startswith("https://") else None
            try:
                tg.send(chat, story_text(a, site, 1024 if photo else 4096), photo)
                seen.add(a["id"])
                sent += 1
            except RuntimeError as exc:
                log(f"[{ch['key']}] {chat}: {exc}")
                break  # a channel that refuses (bot not admin, wrong name) is skipped this round
        posted[ch["key"]] = list(seen)[-REMEMBER:]
    return sent


def numbers_due(config: dict, state: dict, now: datetime) -> str | None:
    """Today's local date if the daily numbers post is due, else None."""
    n = config["numbers"]
    if not chat_id(n.get("chat")):
        return None
    local = now.astimezone(ZoneInfo(n.get("tz") or "Asia/Riyadh"))
    today = local.date().isoformat()
    if local.hour >= int(n.get("hour", 6)) and state.get("numbers_date") != today:
        return today
    return None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
