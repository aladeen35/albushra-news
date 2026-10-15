"""Send the new stories and the daily numbers to Telegram (runs after each Pages build).

    TELEGRAM_BOT_TOKEN=… CONTENT_DIR=../../content python scripts/publish_telegram.py ../../site

Without a token it only carries the "already posted" record forward. With
TELEGRAM_TEST=true it sends one test message to each configured channel and
nothing else.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402

from app import telegram as tgm  # noqa: E402

MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]


def previous_state(repo: str | None) -> dict:
    if not repo:
        return {}
    try:
        r = httpx.get(f"https://raw.githubusercontent.com/{repo}/gh-pages/data/telegram-state.json", timeout=20)
        return r.json() if r.status_code == 200 else {}
    except (httpx.HTTPError, ValueError):
        return {}


def region_quakes(feed: str) -> list[dict]:
    r = httpx.get(f"https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/{feed}.geojson", timeout=30)
    r.raise_for_status()
    out = []
    for f in r.json()["features"]:
        lon, lat = f["geometry"]["coordinates"][:2]
        if -11 < lat < 45 and -20 < lon < 141:
            out.append({"id": f["id"], "mag": f["properties"]["mag"], "place": f["properties"]["place"] or "—",
                        "time": f["properties"]["time"], "url": f["properties"]["url"]})
    return sorted(out, key=lambda q: q["time"], reverse=True)


def prayer_times(cities: list) -> tuple[list, str | None]:
    out, hijri = [], None
    for name, lat, lon in cities:
        try:
            d = httpx.get("https://api.aladhan.com/v1/timings", params={"latitude": lat, "longitude": lon},
                          timeout=20).json()["data"]
            out.append((name, {k: str(v)[:5] for k, v in d["timings"].items()}))
            if not hijri:
                h = d["date"]["hijri"]
                hijri = f"{h['day']} {h['month']['ar']} {h['year']} هـ"
        except Exception as exc:  # one city failing does not stop the post
            print(f"prayer times for {name}: {exc}")
    return out, hijri


def main(site_dir: str) -> int:
    state_box: dict = {}
    try:
        return run(site_dir, state_box)
    finally:
        # Always carry the record forward, even after an error, so nothing is posted twice.
        if "save" in state_box:
            state_box["save"]()


def run(site_dir: str, state_box: dict) -> int:
    site_path = Path(site_dir)
    data = site_path / "data"
    folder = Path(os.environ.get("CONTENT_DIR", "../../content"))
    repo = os.environ.get("GITHUB_REPOSITORY")
    owner, _, name = (repo or "/").partition("/")
    site = os.environ.get("SITE_URL") or (f"https://{owner}.github.io/{name}" if repo else "")
    config = tgm.load_config(folder)
    state = previous_state(repo)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    now = tgm.utcnow()

    def save():
        (data / "telegram-state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    state_box["save"] = save

    if not token:
        print("TELEGRAM_BOT_TOKEN is not set: nothing sent.")
        save()
        return 0
    tg = tgm.Telegram(token)

    chats = [(c.get("name") or c["key"], tgm.chat_id(c.get("chat"))) for c in config["channels"]]
    chats.append(("أرقام العالم", tgm.chat_id(config["numbers"].get("chat"))))
    if os.environ.get("TELEGRAM_TEST", "").lower() == "true":
        for label, chat in chats:
            if not chat:
                continue
            try:
                tg.send(chat, f"✅ <b>البشرى للأخبار</b>\n\nرسالة تجريبية لقناة «{label}». الربط يعمل، "
                              f"وسيبدأ النشر التلقائي مع التحديث التالي.\n\n🔗 {site}/")
                print(f"test sent to {chat}")
            except RuntimeError as exc:
                print(f"test to {chat} failed: {exc}")
        save()
        return 0

    articles = json.loads((data / "articles.json").read_text(encoding="utf-8"))
    sent = tgm.publish_stories(tg, config, articles, state, site, now)
    print(f"stories sent: {sent}")

    numbers_chat = tgm.chat_id(config["numbers"].get("chat"))
    if numbers_chat:
        # A strong earthquake (6+) in the region is posted when it happens.
        try:
            alerted = set(state.get("quakes", []))
            for q in region_quakes("4.5_day"):
                if q["mag"] >= 6 and q["id"] not in alerted:
                    tg.send(numbers_chat, f"🔴 <b>البشرى للأخبار — زلزال</b>\n\nزلزال بقوة <b>{q['mag']:.1f}</b>\n"
                                          f"{q['place']}\n\nالمصدر: USGS\n🔗 {q['url']}")
                    alerted.add(q["id"])
            state["quakes"] = list(alerted)[-200:]
        except Exception as exc:
            print(f"earthquake alert skipped: {exc}")
        today = tgm.numbers_due(config, state, now)
        if today:
            dash = {}
            for key, title in (("sudan", "🇸🇩 السودان"), ("palestine", "🇵🇸 فلسطين")):
                try:
                    dash[title] = json.loads((data / f"dashboard-{key}.json").read_text(encoding="utf-8"))["cards"]
                except (OSError, ValueError, KeyError):
                    pass
            try:
                quakes = region_quakes("4.5_day")
            except Exception as exc:
                print(f"earthquakes skipped: {exc}")
                quakes = []
            prayers, hijri = prayer_times(config["numbers"].get("cities") or [])
            y, m, d = (int(x) for x in today.split("-"))
            from datetime import date
            day = date(y, m, d)
            label = f"{DAYS[day.weekday()]} {d} {MONTHS[m - 1]} {y}"
            try:
                tg.send(numbers_chat, tgm.numbers_text(dash, quakes, prayers, hijri, label, site))
                state["numbers_date"] = today
                print("daily numbers sent")
            except RuntimeError as exc:
                print(f"daily numbers failed: {exc}")
    save()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "../../site"))
