"""Temporary: try candidate news sites' RSS feeds from GitHub's runners and report what works."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.providers.base import HttpClient, ProviderError
from app.providers.news import RssAdapter, discover_feeds

C = [
 ("okaz", "https://www.okaz.com.sa", ["https://www.okaz.com.sa/rss"]),
 ("alriyadh", "https://www.alriyadh.com", ["https://www.alriyadh.com/section.main.xml", "https://www.alriyadh.com/rss"]),
 ("sabq", "https://sabq.org", ["https://sabq.org/rss", "https://sabq.org/feed"]),
 ("alwatan_sa", "https://www.alwatan.com.sa", ["https://www.alwatan.com.sa/rss"]),
 ("almadina", "https://www.al-madina.com", ["https://www.al-madina.com/rss"]),
 ("youm7", "https://www.youm7.com", ["https://www.youm7.com/rss/SectionRss?SectionID=65", "https://www.youm7.com/rss/SectionRss?SectionID=97"]),
 ("ahram", "https://gate.ahram.org.eg", ["https://gate.ahram.org.eg/rss/1.aspx"]),
 ("masrawy", "https://www.masrawy.com", ["https://www.masrawy.com/rss/feed"]),
 ("cnn_ar", "https://arabic.cnn.com", ["https://arabic.cnn.com/api/v1/rss/rss.xml"]),
 ("rt_ar", "https://arabic.rt.com", ["https://arabic.rt.com/rss/"]),
 ("independent_ar", "https://www.independentarabia.com", ["https://www.independentarabia.com/rss"]),
 ("alquds_alarabi", "https://www.alquds.co.uk", ["https://www.alquds.co.uk/feed/"]),
 ("alaraby", "https://www.alaraby.co.uk", ["https://www.alaraby.co.uk/rss"]),
 ("arab48", "https://www.arab48.com", ["https://www.arab48.com/rss"]),
 ("euronews_ar", "https://arabic.euronews.com", ["https://arabic.euronews.com/rss"]),
 ("alhurra", "https://www.alhurra.com", ["https://www.alhurra.com/rss"]),
 ("wafa", "https://www.wafa.ps", ["https://www.wafa.ps/rss.aspx"]),
 ("maan", "https://www.maannews.net", ["https://www.maannews.net/rss"]),
 ("palinfo", "https://palinfo.com", ["https://palinfo.com/feed/"]),
 ("alayyam_ps", "https://www.al-ayyam.ps", []),
 ("altaghyeer", "https://www.altaghyeer.info", ["https://www.altaghyeer.info/ar/feed/"]),
 ("darfur24", "https://www.darfur24.com", ["https://www.darfur24.com/feed/"]),
 ("ultrasudan", "https://ultrasudan.ultrasawt.com", ["https://ultrasudan.ultrasawt.com/rss.xml"]),
 ("alsudani", "https://www.alsudaninews.com", ["https://www.alsudaninews.com/feed/"]),
 ("bajnews", "https://www.bajnews.net", ["https://www.bajnews.net/feed/"]),
 ("sudanakhbar", "https://www.sudanakhbar.com", ["https://www.sudanakhbar.com/feed"]),
 ("mee", "https://www.middleeasteye.net", ["https://www.middleeasteye.net/rss"]),
 ("thenational", "https://www.thenationalnews.com", ["https://www.thenationalnews.com/arc/outboundfeeds/rss/?outputType=xml"]),
 ("nyt_world", "https://www.nytimes.com", ["https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "https://rss.nytimes.com/services/xml/rss/nyt/MiddleEast.xml"]),
 ("npr_world", "https://www.npr.org", ["https://feeds.npr.org/1004/rss.xml"]),
 ("skynews_en", "https://news.sky.com", ["https://feeds.skynews.com/feeds/rss/world.xml"]),
 ("cbs_world", "https://www.cbsnews.com", ["https://www.cbsnews.com/latest/rss/world"]),
 ("abc_au", "https://www.abc.net.au", ["https://www.abc.net.au/news/feed/51120/rss.xml"]),
 ("filgoal", "https://www.filgoal.com", ["https://www.filgoal.com/rss"]),
 ("kooora", "https://www.kooora.com", []),
 ("alarabiya_sport", "https://www.alarabiya.net/sport", ["https://www.alarabiya.net/feed/rss2/ar/sport.xml"]),
 ("spaceflight", "https://www.spaceflightnews.net", []),
]
http = HttpClient(retries=0)
rss = RssAdapter(http)
out = {}
for key, site, guesses in C:
    tried = list(guesses)
    try:
        tried += [u for u in discover_feeds(http, site) if u not in tried][:4]
    except Exception as e:
        print(f"[{key}] discovery failed: {e}")
    ok = []
    for url in tried:
        try:
            r = rss.fetch(url, key)
            if r.items:
                imgs = sum(1 for i in r.items if i.image_url)
                ok.append({"url": url, "items": len(r.items), "images": imgs, "lang": r.items[0].language,
                           "sample": r.items[0].title[:80]})
        except (ProviderError, Exception) as e:
            print(f"[{key}] {url}: {str(e)[:100]}")
    print(f"== {key}: {'OK' if ok else 'NONE'} {json.dumps(ok, ensure_ascii=False)}")
    out[key] = ok
# keyless widgets reachable?
for url in ["https://api.open-meteo.com/v1/forecast?latitude=15.5&longitude=32.5&current=temperature_2m",
            "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json",
            "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson"]:
    try:
        resp, _ = http.request("GET", url)
        print("WIDGET OK", url, resp.headers.get("access-control-allow-origin"), resp.text[:120].replace("\n", " "))
    except Exception as e:
        print("WIDGET FAIL", url, e)
