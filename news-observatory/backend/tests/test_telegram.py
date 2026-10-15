import json
from datetime import datetime, timedelta, timezone

import httpx

from app import telegram as tgm

NOW = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)


def art(i, hours=1, **kw):
    a = {"id": f"s{i}", "title": f"خبر {i}", "description": "ملخص الخبر " * 3, "language": "ar",
         "published_at": (NOW - timedelta(hours=hours)).isoformat(), "publisher": {"name": "واس", "country": "SA"},
         "event_countries": [], "topics": [], "reliability": 0.7, "cluster_id": None}
    a.update(kw)
    return a


def test_chat_names_are_normalised():
    assert tgm.chat_id("albushra") == "@albushra"
    assert tgm.chat_id("https://t.me/albushra") == "@albushra"
    assert tgm.chat_id("-1001234") == "-1001234" and tgm.chat_id(" ") == ""


def test_pick_filters_ranks_and_skips_old_seen_and_same_story():
    arts = [art(1, event_countries=["SD"]), art(2, hours=10, event_countries=["SD"]),
            art(3, event_countries=["SD"], cluster_id=7), art(4, event_countries=["SD"], cluster_id=7),
            art(5, event_countries=["PS"]), art(6, event_countries=["SD"], language="en"),
            art(7, event_countries=["SD"])]
    got = [a["id"] for a in tgm.pick(arts, "sudan", 10, {"s7"}, NOW)]
    assert "s2" not in got and "s5" not in got and "s6" not in got and "s7" not in got  # old, other place, English, seen
    assert len([g for g in got if g in ("s3", "s4")]) == 1  # one per story
    assert len(tgm.pick(arts, "top", 2, set(), NOW)) == 2


def test_story_message_and_publish_remembers_what_was_sent():
    sent = []

    def handler(request):
        body = json.loads(request.content)
        sent.append((request.url.path.rsplit("/", 1)[-1], body["chat_id"]))
        return httpx.Response(200, json={"ok": True, "result": {}})
    tg = tgm.Telegram("T", httpx.Client(transport=httpx.MockTransport(handler)), pause=0)
    config = {**tgm.DEFAULT_CHANNELS, "channels": [{"key": "sudan", "chat": "albushra_sd", "filter": "sudan", "limit": 5}]}
    arts = [art(1, event_countries=["SD"], image_url="https://img/x.jpg"), art(2, event_countries=["SD"])]
    state = {}
    assert tgm.publish_stories(tg, config, arts, state, "https://x.github.io/site", NOW) == 2
    assert {m for m, _ in sent} == {"sendPhoto", "sendMessage"} and all(c == "@albushra_sd" for _, c in sent)
    assert tgm.publish_stories(tg, config, arts, state, "https://x.github.io/site", NOW) == 0  # nothing twice
    text = tgm.story_text(arts[0], "https://x.github.io/site")
    assert "البشرى للأخبار" in text and "https://x.github.io/site/#/article/s1" in text and "المصدر: واس" in text


def test_numbers_post_is_due_once_a_day_after_the_hour():
    config = {**tgm.DEFAULT_CHANNELS, "numbers": {**tgm.DEFAULT_CHANNELS["numbers"], "chat": "@n", "hour": 6}}
    early = datetime(2026, 10, 15, 2, 0, tzinfo=timezone.utc)  # 05:00 in Makkah
    assert tgm.numbers_due(config, {}, early) is None
    assert tgm.numbers_due(config, {}, NOW) == "2026-10-15"
    assert tgm.numbers_due(config, {"numbers_date": "2026-10-15"}, NOW) is None
    text = tgm.numbers_text({"السودان": [{"name": {"ar": "النازحون"}, "status": "current", "current": {
        "value": 8600000, "unit": {"ar": "شخص"}, "producer": "IOM DTM", "period_end": "2026-08-26",
        "review_status": "approved"}}]}, [], [("الخرطوم", {"Fajr": "04:52", "Dhuhr": "11:58", "Asr": "15:18",
        "Maghrib": "17:47", "Isha": "18:59"})], "22 ربيع الآخر 1448 هـ", "الخميس 15 أكتوبر 2026", "https://x")
    assert "8,600,000" in text and "IOM DTM" in text and "الفجر 04:52" in text and "1448" in text
