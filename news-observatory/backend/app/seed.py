"""Initial configuration: region lists, scopes, metric definitions, sources.

Seeds *definitions only*. No humanitarian value is seeded: every number on the
dashboard must arrive from a provider or be entered by an editor with a link to
the report it came from. Until then the card says so.

Sources are seeded disabled with terms_reviewed=False. An operator enables a
source after checking its plan, terms and attribution rules.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .geo import ARAB_LEAGUE, OIC_MEMBERS
from .models import Metric, RegionList, Scope, Source

REGION_LISTS = [
    dict(key="arab_world", name_ar="العالم العربي", name_en="Arab world",
         definition_ar="الدول الأعضاء في جامعة الدول العربية (22 دولة). القائمة قابلة للتعديل من لوحة الإدارة.",
         definition_en="Member states of the League of Arab States (22). Editable from the admin panel.",
         reference_url="https://www.lasportal.org/", countries=ARAB_LEAGUE),
    dict(key="islamic_world", name_ar="العالم الإسلامي", name_en="Muslim world",
         definition_ar="الدول الأعضاء في منظمة التعاون الإسلامي (57 دولة). لا يُستنتج التصنيف من لغة المقال أو ديانة كاتبه.",
         definition_en="Member states of the Organisation of Islamic Cooperation (57). Never inferred from "
                       "an article's language or its author's religion.",
         reference_url="https://www.oic-oci.org/states/", countries=OIC_MEMBERS),
]

SCOPES = [
    dict(key="world", name_ar="العالم", name_en="World", countries=[], sort_order=0, queries={}),
    dict(key="palestine", name_ar="فلسطين", name_en="Palestine", countries=["PS"], sort_order=10,
         queries={"ar": ["فلسطين", "غزة", "الضفة الغربية"], "en": ["Palestine", "Gaza", "West Bank"]}),
    dict(key="sudan", name_ar="السودان", name_en="Sudan", countries=["SD"], sort_order=20,
         queries={"ar": ["السودان"], "en": ["Sudan"]}),
]

_OCHA_CASUALTIES = "https://www.ochaopt.org/data/casualties"

METRICS = [
    # --- Sudan -----------------------------------------------------------
    dict(metric_id="sd_idps", scope_key="sudan", display_order=10,
         name_ar="النازحون داخليًا في السودان", name_en="Internally displaced people in Sudan",
         unit_ar="شخص", unit_en="people",
         area_ar="السودان — المستوى الوطني", area_en="Sudan — national",
         population_ar="النازحون داخليًا الموجودون في مواقع النزوح وقت جولة التقييم",
         population_en="IDPs present in displacement locations at the time of the assessment round",
         default_number_type="estimated", primary_producer="IOM DTM",
         primary_source_url="https://dtm.iom.int/sudan",
         methodology_ar="تقديرات جولات التقييم الميداني لمصفوفة تتبع النزوح (DTM) عبر مخبرين رئيسيين على "
                        "مستوى المواقع، مجمّعة على المستوى الوطني. الرقم لقطة في تاريخ الجولة وليس عدًّا لحظيًا.",
         methodology_en="Estimates from DTM field assessment rounds (key informants at location level), "
                        "aggregated nationally. The figure is a snapshot on the round date, not a live count.",
         uncertainty_ar="قد لا تشمل التغطية المناطق التي يتعذر الوصول إليها.",
         uncertainty_en="Coverage may exclude areas that cannot be accessed.",
         max_age_days=75, provider="dtm",
         provider_config={"endpoint": "IdpAdmin0Data", "params": {"CountryName": "Sudan"},
                          "value_field": "numPresentIdpInd", "date_field": "reportingDate",
                          "round_field": "roundNumber", "coverage_key": "dtm:admin0:SDN:idps-present",
                          "source_url": "https://dtm.iom.int/sudan",
                          # Used when no DTM key is set: HDX HAPI republishes
                          # DTM's figures by admin-1 area for one round.
                          "hapi": {"endpoint": "affected-people/idps",
                                   "params": {"location_code": "SDN", "admin_level": 1},
                                   "match": {"admin_level": 1}, "value_field": "population",
                                   "aggregate": "sum", "producer": "IOM DTM",
                                   "coverage_key": "hapi:idps:SDN:admin1-sum"}}),
    dict(metric_id="sd_returnees", scope_key="sudan", display_order=20,
         name_ar="العائدون في السودان", name_en="Returnees in Sudan",
         unit_ar="شخص", unit_en="people",
         area_ar="السودان — المستوى الوطني", area_en="Sudan — national",
         population_ar="العائدون إلى مناطقهم الأصلية بحسب تعريف DTM",
         population_en="People returned to their areas of origin, as defined by DTM",
         default_number_type="estimated", primary_producer="IOM DTM",
         primary_source_url="https://dtm.iom.int/sudan",
         methodology_ar="يُدخل يدويًا من تقارير DTM المنشورة مع رابط التقرير وتاريخ الجولة.",
         methodology_en="Entered by an editor from published DTM reports, with the report link and round date.",
         max_age_days=90, provider="manual"),
    dict(metric_id="sd_acled_events_30d", scope_key="sudan", display_order=30,
         name_ar="أحداث الصراع المسجلة لدى ACLED في السودان (30 يومًا)",
         name_en="Conflict events recorded by ACLED in Sudan (30 days)",
         unit_ar="حدث", unit_en="events",
         area_ar="السودان", area_en="Sudan",
         population_ar="أحداث سياسية وعنيفة وفق تصنيف ACLED",
         population_en="Political violence and protest events as classified by ACLED",
         default_number_type="reported", primary_producer="ACLED",
         primary_source_url="https://acleddata.com/",
         methodology_ar="عدد الأحداث في نافذة 30 يومًا تنتهي قبل 7 أيام من تاريخ الجلب لتجنب نقص التسجيل "
                        "المتأخر. بيانات أحداث وفق منهجية ومصادر ACLED، وليست تعدادًا رسميًا شاملًا.",
         methodology_en="Count of events in a 30-day window ending 7 days before retrieval, to avoid late-coding "
                        "undercounts. Event data under ACLED's methodology and sources, not an official census.",
         max_age_days=21, provider="acled",
         provider_config={"country": "Sudan", "measure": "events", "window_days": 30, "lag_days": 7}),
    dict(metric_id="sd_acled_fatalities_30d", scope_key="sudan", display_order=40,
         name_ar="الوفيات المبلّغ عنها في أحداث سجّلتها ACLED في السودان (30 يومًا)",
         name_en="Reported fatalities in ACLED-recorded events in Sudan (30 days)",
         unit_ar="حالة وفاة", unit_en="fatalities",
         area_ar="السودان", area_en="Sudan",
         population_ar="جميع الأطراف والمدنيون كما ترد في سجلات ACLED",
         population_en="All parties and civilians as coded in ACLED records",
         default_number_type="reported", primary_producer="ACLED",
         primary_source_url="https://acleddata.com/",
         methodology_ar="مجموع حقل الوفيات المبلّغ عنها في الأحداث المسجلة خلال النافذة. تقدّر ACLED الوفيات "
                        "بتحفظ، ولا يمثل الرقم حصيلة شاملة لكل الضحايا.",
         methodology_en="Sum of the reported-fatalities field across recorded events in the window. ACLED codes "
                        "fatalities conservatively; this is not a complete toll of all victims.",
         max_age_days=21, provider="acled",
         provider_config={"country": "Sudan", "measure": "fatalities", "window_days": 30, "lag_days": 7}),
    # --- Palestine --------------------------------------------------------
    dict(metric_id="ps_gaza_killed", scope_key="palestine", display_order=10,
         name_ar="الوفيات في غزة", name_en="Fatalities in Gaza",
         unit_ar="حالة وفاة", unit_en="fatalities",
         area_ar="قطاع غزة", area_en="Gaza Strip",
         population_ar="الفلسطينيون الذين قتلوا، بحسب تعريف المصدر وفترته",
         population_en="Palestinians killed, per the source's definition and period",
         default_number_type="reported", primary_producer="OCHA oPt",
         primary_source_url=_OCHA_CASUALTIES,
         methodology_ar="يُدخل من تحديثات OCHA المنشورة مع ذكر الجهة التي أبلغت عن الرقم. ترد أرقام التحديثات "
                        "الإنسانية مبلّغًا عنها قبل التحقق المستقل.",
         methodology_en="Entered from published OCHA updates, naming the body that reported the figure. Figures "
                        "in humanitarian updates are reported before independent verification.",
         max_age_days=14, provider="manual"),
    dict(metric_id="ps_gaza_injured", scope_key="palestine", display_order=20,
         name_ar="الإصابات في غزة", name_en="Injuries in Gaza",
         unit_ar="مصاب", unit_en="injured people",
         area_ar="قطاع غزة", area_en="Gaza Strip",
         population_ar="الفلسطينيون المصابون، بحسب تعريف المصدر وفترته",
         population_en="Palestinians injured, per the source's definition and period",
         default_number_type="reported", primary_producer="OCHA oPt",
         primary_source_url=_OCHA_CASUALTIES,
         methodology_ar="يُدخل من تحديثات OCHA المنشورة. بطاقة مستقلة عن الوفيات ولا تُجمع معها.",
         methodology_en="Entered from published OCHA updates. Kept separate from fatalities, never summed.",
         max_age_days=14, provider="manual"),
    dict(metric_id="ps_gaza_idps", scope_key="palestine", display_order=30,
         name_ar="النازحون في غزة", name_en="Displaced people in Gaza",
         unit_ar="شخص", unit_en="people",
         area_ar="قطاع غزة", area_en="Gaza Strip",
         population_ar="النازحون داخليًا بحسب تعريف المصدر",
         population_en="Internally displaced people, per the source's definition",
         default_number_type="estimated", primary_producer="OCHA oPt",
         primary_source_url="https://www.ochaopt.org/data",
         methodology_ar="تقدير من التقارير الإنسانية المنشورة؛ يُذكر تاريخ التقدير ونطاقه.",
         methodology_en="Estimate from published humanitarian reporting; the estimate's date and scope are stated.",
         max_age_days=30, provider="manual"),
    dict(metric_id="ps_wb_killed", scope_key="palestine", display_order=40,
         name_ar="الوفيات في الضفة الغربية", name_en="Fatalities in the West Bank",
         unit_ar="حالة وفاة", unit_en="fatalities",
         area_ar="الضفة الغربية بما فيها القدس الشرقية", area_en="West Bank including East Jerusalem",
         population_ar="بحسب تعريف قاعدة بيانات OCHA للضحايا والفترة المحددة",
         population_en="Per the OCHA casualties database definition and the stated period",
         default_number_type="verified", primary_producer="OCHA oPt",
         primary_source_url=_OCHA_CASUALTIES,
         methodology_ar="من قاعدة بيانات OCHA للضحايا، التي لا تضيف الحالات قبل التحقق المستقل.",
         methodology_en="From OCHA's casualties database, which adds cases only after independent verification.",
         max_age_days=30, provider="manual"),
    dict(metric_id="ps_wb_injured", scope_key="palestine", display_order=50,
         name_ar="الإصابات في الضفة الغربية", name_en="Injuries in the West Bank",
         unit_ar="مصاب", unit_en="injured people",
         area_ar="الضفة الغربية بما فيها القدس الشرقية", area_en="West Bank including East Jerusalem",
         population_ar="بحسب تعريف قاعدة بيانات OCHA للضحايا والفترة المحددة",
         population_en="Per the OCHA casualties database definition and the stated period",
         default_number_type="verified", primary_producer="OCHA oPt",
         primary_source_url=_OCHA_CASUALTIES,
         methodology_ar="من قاعدة بيانات OCHA للضحايا بعد التحقق.",
         methodology_en="From OCHA's casualties database, after verification.",
         max_age_days=30, provider="manual"),
]

def _people_in_need(metric_id, scope, iso3, name_ar, name_en, area_ar, area_en, order):
    return dict(
        metric_id=metric_id, scope_key=scope, display_order=order,
        name_ar=name_ar, name_en=name_en, unit_ar="شخص", unit_en="people",
        area_ar=area_ar, area_en=area_en,
        population_ar="الأشخاص المحتاجون للمساعدة (الاحتياج المشترك بين القطاعات) وفق خطة الاستجابة",
        population_en="People in need (intersectoral) as defined by the humanitarian needs overview",
        default_number_type="estimated", primary_producer="OCHA HNO",
        primary_source_url="https://data.humdata.org/hapi",
        methodology_ar="تقدير سنوي من النظرة العامة على الاحتياجات الإنسانية (HNO) تنسقه OCHA، "
                       "ويُجلب عبر HDX HAPI. يُعرض نطاق السنة المرجعية لا تاريخ الجلب.",
        methodology_en="Annual estimate from the OCHA-coordinated Humanitarian Needs Overview, retrieved "
                       "through HDX HAPI. The reference year is shown, not the retrieval date.",
        uncertainty_ar="تقدير تخطيطي وليس عدًّا؛ يُراجع مرة أو مرتين في السنة.",
        uncertainty_en="A planning estimate, not a count; revised once or twice a year.",
        max_age_days=450, provider="hapi",
        # Field values as HAPI returned them in the live check: the total row
        # has an empty category.
        provider_config={"endpoint": "affected-people/humanitarian-needs",
                         "params": {"location_code": iso3, "admin_level": 0},
                         "match": {"admin_level": 0, "sector_name": "Intersectoral",
                                   "population_status": "INN", "category": ["", "total"]},
                         "value_field": "population", "aggregate": "single", "producer": "OCHA HNO",
                         "coverage_key": f"hapi:hno:{iso3}:intersectoral-inn-total"})


METRICS += [
    _people_in_need("sd_people_in_need", "sudan", "SDN", "المحتاجون للمساعدة الإنسانية في السودان",
                    "People in need of humanitarian assistance in Sudan", "السودان — المستوى الوطني",
                    "Sudan — national", 15),
    _people_in_need("ps_people_in_need", "palestine", "PSE", "المحتاجون للمساعدة الإنسانية في فلسطين",
                    "People in need of humanitarian assistance in Palestine",
                    "الأرض الفلسطينية المحتلة", "Occupied Palestinian territory", 60),
]
# HAPI carries no humanitarian-needs rows for Palestine (checked live), so
# this one is entered by editors from OCHA oPt's published appeal.
METRICS[-1].update(provider="manual", provider_config={}, primary_producer="OCHA oPt",
                   primary_source_url="https://www.ochaopt.org/data",
                   methodology_ar="يُدخل من النداء الإنساني المنشور لـ OCHA في الأرض الفلسطينية المحتلة، مع الرابط وسنة الخطة.",
                   methodology_en="Entered by an editor from OCHA oPt's published humanitarian appeal, with its link "
                                  "and plan year.")


SOURCES = [
    dict(key="gnews", name="GNews", url="https://gnews.io", kind="news_api", provider="gnews",
         languages=["ar", "en"], terms_url="https://gnews.io/terms",
         license_note="Free plan: 100 requests a day, up to 10 articles each, 12-hour delay, "
                      "development and non-commercial use only. A paid plan is needed for a public app.",
         reliability=0.6, daily_request_limit=90,
         config={"headlines": [{"lang": "ar", "category": "world"},
                               {"lang": "en", "category": "world"}]}),
    dict(key="worldnews", name="World News API", url="https://worldnewsapi.com", kind="news_api",
         provider="worldnews", languages=["ar", "en"],
         terms_url="https://worldnewsapi.com/terms/",
         license_note="Free plan: 50 API points a day. Palestinian-territory coverage lists only two "
                      "sources; use as a complement, never alone.",
         reliability=0.55, daily_request_limit=40,
         config={"country_feeds": [{"country": "ps", "language": "ar"}]}),
    dict(key="newsapi", name="NewsAPI.org", url="https://newsapi.org", kind="news_api",
         provider="newsapi", languages=["ar", "en"], terms_url="https://newsapi.org/terms",
         license_note="Developer plan: 100 requests a day, 24-hour delay, development and testing only; "
                      "the adapter refuses to run without a declared paid plan.",
         reliability=0.55, daily_request_limit=90),
    dict(key="ocha_opt", name="OCHA oPt", url="https://www.ochaopt.org", kind="humanitarian",
         provider="rss", languages=["en"], country=None, terms_url="https://www.ochaopt.org/",
         license_note="Add the official feed URL after reviewing reuse terms.", reliability=0.9,
         config={"feeds": []}),
    dict(key="iom_dtm", name="IOM DTM", url="https://dtm.iom.int", kind="humanitarian",
         provider="rss", languages=["en"], terms_url="https://dtm.iom.int/terms-and-conditions",
         license_note="Add the official feed URL after reviewing reuse terms.", reliability=0.9,
         config={"feeds": []}),
]


# Public RSS feeds published by the outlets and agencies themselves. They are
# seeded enabled so the hourly job has something to read with no keys, but
# terms_reviewed stays False: someone must still confirm each publisher's
# reuse terms before a public launch. Only headline, short summary, publisher
# and link are shown; images and full text are off.
SOURCE_GROUPS = ("saudi", "arab", "sudan", "sports", "international", "humanitarian")
_FEED_NOTE = ("Publisher's own public RSS feed. Headline, summary and link only; "
              "confirm the publisher's reuse terms before a public launch.")


def _feed_source(key, name, url, country, reliability, feeds, kind="rss", group="international"):
    # `group` only arranges the sources screen; `country` stays the
    # publisher's real base, which is what "publisher country" means.
    return dict(key=key, name=name, url=url, kind=kind, provider="rss",
                languages=sorted({f["language"] for f in feeds}), country=country,
                terms_url=url, license_note=_FEED_NOTE, reliability=reliability,
                enabled=True, terms_reviewed=False, allow_images=True,
                config={"group": group, "feeds": feeds})


TRUSTED_FEEDS = [
    _feed_source("bbc", "BBC News", "https://www.bbc.com", "GB", 0.85, [
        {"url": "https://feeds.bbci.co.uk/arabic/rss.xml", "language": "ar"},
        {"url": "https://feeds.bbci.co.uk/news/world/rss.xml", "language": "en"}]),
    _feed_source("aljazeera", "Al Jazeera", "https://www.aljazeera.com", "QA", 0.8, [
        {"url": "https://www.aljazeera.com/xml/rss/all.xml", "language": "en"}]),
    _feed_source("france24", "France 24", "https://www.france24.com", "FR", 0.8, [
        {"url": "https://www.france24.com/ar/rss", "language": "ar"},
        {"url": "https://www.france24.com/en/rss", "language": "en"}]),
    _feed_source("dw", "DW", "https://www.dw.com", "DE", 0.8, [
        {"url": "https://rss.dw.com/rdf/rss-ar-all", "language": "ar"},
        {"url": "https://rss.dw.com/rdf/rss-en-world", "language": "en"}]),
    _feed_source("guardian", "The Guardian", "https://www.theguardian.com", "GB", 0.8, [
        {"url": "https://www.theguardian.com/world/rss", "language": "en"}]),
    _feed_source("un_news", "UN News / أخبار الأمم المتحدة", "https://news.un.org", None, 0.85, [
        {"url": "https://news.un.org/feed/subscribe/ar/news/all/rss.xml", "language": "ar"},
        {"url": "https://news.un.org/feed/subscribe/en/news/all/rss.xml", "language": "en"}]),
    # UN News' humanitarian-aid desk: the UN's own reporting on humanitarian
    # operations, shown with the humanitarian updates, apart from the press.
    _feed_source("un_humanitarian", "أخبار الأمم المتحدة — الشؤون الإنسانية", "https://news.un.org", None, 0.85, [
        {"url": "https://news.un.org/feed/subscribe/ar/news/topic/humanitarian-aid/feed/rss.xml",
         "language": "ar", "content_type": "humanitarian_report"},
        {"url": "https://news.un.org/feed/subscribe/en/news/topic/humanitarian-aid/feed/rss.xml",
         "language": "en", "content_type": "humanitarian_report"}], kind="humanitarian", group="humanitarian"),
    _feed_source("reliefweb", "ReliefWeb (OCHA)", "https://reliefweb.int", None, 0.9, [
        {"url": "https://reliefweb.int/updates/rss.xml", "language": "en",
         "content_type": "humanitarian_report"}], kind="humanitarian", group="humanitarian"),

    # --- Saudi Arabia ---------------------------------------------------------
    # Each feed also names its site: if the address stops answering, the job
    # reads the feed the site itself advertises and remembers it.
    _feed_source("spa", "واس — وكالة الأنباء السعودية", "https://www.spa.gov.sa", "SA", 0.85, [
        {"url": "https://www.spa.gov.sa/rss/ar", "language": "ar", "site": "https://www.spa.gov.sa/ar"},
        {"url": "https://www.spa.gov.sa/rss/en", "language": "en", "site": "https://www.spa.gov.sa/en"}],
        group="saudi"),
    _feed_source("alarabiya", "العربية", "https://www.alarabiya.net", "AE", 0.8, [
        {"url": "https://www.alarabiya.net/feed/rss2/ar.xml", "language": "ar",
         "site": "https://www.alarabiya.net"},
        {"url": "https://english.alarabiya.net/feed/rss2/en.xml", "language": "en",
         "site": "https://english.alarabiya.net"},
        {"url": "https://www.alarabiya.net/feed/rss2/ar/sport.xml", "language": "ar",
         "site": "https://www.alarabiya.net/sport", "topic": "sports"}], group="saudi"),
    _feed_source("aawsat", "الشرق الأوسط", "https://aawsat.com", "GB", 0.8, [
        {"url": "https://aawsat.com/feed", "language": "ar", "site": "https://aawsat.com"}],
        group="saudi"),
    _feed_source("arabnews", "Arab News", "https://www.arabnews.com", "SA", 0.75, [
        {"url": "https://www.arabnews.com/rss.xml", "language": "en", "site": "https://www.arabnews.com"}],
        group="saudi"),
    _feed_source("arriyadiyah", "الرياضية", "https://arriyadiyah.com", "SA", 0.7, [
        {"url": "https://arriyadiyah.com/rss", "language": "ar", "site": "https://arriyadiyah.com",
         "topic": "sports"}], group="sports"),

    # --- Arab world -----------------------------------------------------------
    _feed_source("aljazeera_ar", "الجزيرة نت", "https://www.aljazeera.net", "QA", 0.8, [
        {"url": "https://www.aljazeera.net/aljazeerarss/a7c186be-1baa-4bd4-9d80-a84db769f779/"
                "73d0e1b4-532f-45ef-b135-bfdff8b8cab9", "language": "ar",
         "site": "https://www.aljazeera.net"}], group="arab"),
    _feed_source("skynewsarabia", "سكاي نيوز عربية", "https://www.skynewsarabia.com", "AE", 0.75, [
        {"url": "https://www.skynewsarabia.com/rss", "language": "ar",
         "site": "https://www.skynewsarabia.com"},
        {"url": "https://www.skynewsarabia.com/rss/sport", "language": "ar",
         "site": "https://www.skynewsarabia.com/sport", "topic": "sports"}], group="arab"),
    _feed_source("aa_ar", "الأناضول", "https://www.aa.com.tr/ar", "TR", 0.75, [
        {"url": "https://www.aa.com.tr/ar/rss/default?cat=guncel", "language": "ar",
         "site": "https://www.aa.com.tr/ar"}], group="arab"),

    # --- Sudan ----------------------------------------------------------------
    _feed_source("suna", "سونا — وكالة السودان للأنباء", "https://suna-sd.net", "SD", 0.7, [
        {"url": "https://suna-sd.net/feed", "language": "ar", "site": "https://suna-sd.net"}],
        group="sudan"),
    _feed_source("sudantribune", "سودان تربيون", "https://sudantribune.net", "FR", 0.75, [
        {"url": "https://sudantribune.net/feed/", "language": "ar", "site": "https://sudantribune.net"},
        {"url": "https://sudantribune.com/feed/", "language": "en", "site": "https://sudantribune.com"}],
        group="sudan"),
    _feed_source("dabanga", "راديو دبنقا", "https://www.dabangasudan.org", "NL", 0.75, [
        {"url": "https://www.dabangasudan.org/ar/feed", "language": "ar",
         "site": "https://www.dabangasudan.org/ar"},
        {"url": "https://www.dabangasudan.org/en/feed", "language": "en",
         "site": "https://www.dabangasudan.org/en"}], group="sudan"),

    # --- Sports ---------------------------------------------------------------
    _feed_source("bbc_sport", "BBC Sport", "https://www.bbc.com/sport", "GB", 0.8, [
        {"url": "https://feeds.bbci.co.uk/sport/rss.xml", "language": "en", "topic": "sports"}],
        group="sports"),
    _feed_source("yallakora", "يلا كورة", "https://www.yallakora.com", "EG", 0.65, [
        {"url": "https://www.yallakora.com/rss", "language": "ar", "site": "https://www.yallakora.com",
         "topic": "sports"}], group="sports"),
]

# When a publisher's feed cannot be read (missing, or refusing feed readers),
# its latest stories are taken from GDELT's index of the same domain.
_GDELT_DOMAINS = {"spa": "spa.gov.sa", "alarabiya": "alarabiya.net", "suna": "suna-sd.net",
                  "yallakora": "yallakora.com", "sudantribune": "sudantribune.net",
                  "reliefweb": "reliefweb.int", "aawsat": "aawsat.com", "arriyadiyah": "arriyadiyah.com"}
for _src in TRUSTED_FEEDS:
    if _src["key"] in _GDELT_DOMAINS:
        _src["config"]["gdelt_domain"] = _GDELT_DOMAINS[_src["key"]]

SOURCES += TRUSTED_FEEDS

# Open and approved-access APIs. GDELT needs no key; ReliefWeb's API waits for
# an approved application name and is skipped (and logged) until it is set.
SOURCES += [
    dict(key="gdelt", name="GDELT", url="https://www.gdeltproject.org", kind="news_api",
         provider="gdelt", languages=["ar", "en"], terms_url="https://www.gdeltproject.org/about.html",
         license_note="Open GDELT DOC 2.0 index. Headline, publisher domain and link only. The time "
                      "shown is when GDELT first saw the article. One call per 5 seconds.",
         reliability=0.5, enabled=True, terms_reviewed=False, allow_images=True,
         config={"group": "international",
                 "queries": {"ar": ["السعودية"], "en": ["Saudi Arabia"]}}),
    dict(key="reliefweb_api", name="ReliefWeb API", url="https://reliefweb.int", kind="humanitarian",
         provider="reliefweb", languages=["en", "ar"], terms_url="https://reliefweb.int/terms-conditions",
         license_note="Needs RELIEFWEB_APPNAME approved by ReliefWeb; 1,000 calls a day. Title, "
                      "organisation, date and link only: report bodies belong to their publishers.",
         reliability=0.9, enabled=True, terms_reviewed=False, allow_description=False,
         allow_images=True, config={"group": "humanitarian", "countries": ["SDN", "PSE"]}),
]


def _upsert(session: Session, model, key_field: str, rows: list[dict], update: bool) -> None:
    for row in rows:
        existing = session.scalar(select(model).where(getattr(model, key_field) == row[key_field]))
        if existing is None:
            session.add(model(**row))
        elif update:
            for k, v in row.items():
                setattr(existing, k, v)


def seed(session: Session, update_definitions: bool = False) -> None:
    """Idempotent. Editor changes survive unless update_definitions=True."""
    _upsert(session, RegionList, "key", REGION_LISTS, update_definitions)
    _upsert(session, Scope, "key", SCOPES, update_definitions)
    _upsert(session, Metric, "metric_id", METRICS, update_definitions)
    _upsert(session, Source, "key", SOURCES, False)
    session.commit()
