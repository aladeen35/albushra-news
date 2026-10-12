"""Automatic tagging: language, the places a story is about, and its topics.

Every result here is a suggestion. The publisher's country comes from the
provider and is stored separately; nothing in this module looks at it, because
"published in X" and "about X" are different facts.
"""
from __future__ import annotations

import re
from functools import lru_cache

from .geo import AMBIGUOUS_AR, AMBIGUOUS_EN, COUNTRIES

_TASHKEEL = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_ARABIC_CHAR = re.compile(r"[؀-ۿ]")
_LATIN_CHAR = re.compile(r"[A-Za-z]")


def normalize_ar(text: str) -> str:
    text = _TASHKEEL.sub("", text)
    text = re.sub("[إأآٱ]", "ا", text)
    return text.replace("ة", "ه").replace("ى", "ي")


def detect_language(text: str) -> str:
    arabic = len(_ARABIC_CHAR.findall(text))
    latin = len(_LATIN_CHAR.findall(text))
    if arabic == 0 and latin == 0:
        return "und"
    return "ar" if arabic >= latin else "en"


_AR_SUFFIX = r"(?:ي|يه|يين|يون|يا)?"


def _ar_pattern(term: str) -> str:
    term = normalize_ar(term)
    words = term.split()
    if words[0].startswith("ال") and len(words[0]) > 3:
        core = re.escape(term[2:])
        lead = rf"(?:(?:و|ف)?(?:ب|ك)?ال|(?:و|ف)?لل){core}"
    else:
        lead = rf"(?:و|ف)?(?:(?:ب|ك)?ال|لل|ب|ل|ك)?{re.escape(term)}"
    return rf"(?<![\w]){lead}{_AR_SUFFIX}(?![\w])"


def _en_pattern(term: str) -> str:
    return rf"(?<![\w]){re.escape(term)}(?:'s)?(?![\w])"


@lru_cache(maxsize=1)
def _country_terms() -> list[tuple[int, re.Pattern, str, str]]:
    """(length, compiled pattern, code, script), longest first."""
    terms: list[tuple[int, re.Pattern, str, str]] = []
    for code, (en, ar, en_alias, ar_alias) in COUNTRIES.items():
        for term in (en, *en_alias):
            if term in AMBIGUOUS_EN:
                continue
            terms.append((len(term), re.compile(_en_pattern(term), re.IGNORECASE), code, "en"))
        for term in (ar, *ar_alias):
            if normalize_ar(term) in AMBIGUOUS_AR:
                continue
            terms.append((len(term), re.compile(_ar_pattern(term)), code, "ar"))
    terms.sort(key=lambda t: -t[0])
    return terms


def detect_countries(text: str) -> list[str]:
    """Places the text is about, longest name winning (South Sudan beats Sudan)."""
    if not text:
        return []
    candidates = {"en": text, "ar": normalize_ar(text)}
    taken: dict[str, list[tuple[int, int]]] = {"en": [], "ar": []}
    found: set[str] = set()
    for _, pattern, code, script in _country_terms():
        haystack = candidates[script]
        for m in pattern.finditer(haystack):
            span = (m.start(), m.end())
            if any(span[0] < e and s < span[1] for s, e in taken[script]):
                continue
            taken[script].append(span)
            found.add(code)
    return sorted(found)


TOPIC_KEYWORDS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "conflict": (("war", "attack", "airstrike", "air strike", "shelling", "killed", "militia",
                  "ceasefire", "truce", "troops", "army", "fighting", "rsf", "rapid support",
                  "hostilities", "drone strike", "bombard", "armed"),
                 ("حرب", "قصف", "هجوم", "اشتباك", "مقتل", "قتلي", "غاره", "غارات", "مسلح", "هدنه",
                  "وقف اطلاق النار", "الدعم السريع", "معارك", "الجيش", "عمليات عسكريه", "مسيره")),
    "politics": (("election", "minister", "president", "parliament", "government", "diplomat",
                  "talks", "summit", "sanction", "prime minister", "un security council"),
                 ("انتخاب", "وزير", "رئيس", "برلمان", "حكومه", "دبلوماس", "مفاوضات", "قمه",
                  "عقوبات", "مجلس الامن")),
    "economy": (("economy", "economic", "inflation", "market", "oil price", "trade", "currency",
                 "gdp", "bank", "investment", "budget", "export", "import"),
                ("اقتصاد", "تضخم", "اسواق", "سعر النفط", "تجاره", "عمله", "البنك", "استثمار",
                 "ميزانيه", "صادرات", "واردات")),
    "society": (("refugee", "displaced", "displacement", "humanitarian", "aid", "famine", "food",
                 "education", "school", "children", "women", "migrants", "shelter"),
                ("لاجئ", "نازح", "نزوح", "انساني", "مساعدات", "مجاعه", "غذاء", "تعليم", "مدارس",
                 "اطفال", "نساء", "مهاجر", "ايواء")),
    "environment": (("climate", "flood", "drought", "earthquake", "wildfire", "heatwave",
                     "pollution", "emissions", "storm"),
                    ("مناخ", "فيضان", "سيول", "جفاف", "زلزال", "حرائق", "موجه حر", "تلوث",
                     "انبعاثات", "عاصفه")),
    "health": (("health", "hospital", "cholera", "disease", "outbreak", "vaccine", "who ",
                "malnutrition", "medical", "epidemic"),
               ("صحه", "مستشفي", "كوليرا", "مرض", "تفشي", "لقاح", "الصحه العالميه", "سوء التغذيه",
                "طبي", "وباء")),
    "technology": (("technology", "artificial intelligence", " ai ", "software", "cyber",
                    "internet", "satellite", "smartphone", "startup"),
                   ("تكنولوجيا", "تقنيه", "الذكاء الاصطناعي", "برمجيات", "سيبراني", "الانترنت",
                    "اقمار صناعيه", "ناشئه")),
    "sports": (("football", "match", "league", "world cup", "olympic", "tournament", "fifa",
                "champions", "sport", "coach", "striker", "midfielder", "goalkeeper", "premier league",
                "la liga", "nba", "tennis", "formula 1", "grand prix"),
               ("كره القدم", "مباراه", "الدوري", "كاس العالم", "اولمبي", "بطوله", "فيفا", "منتخب",
                "رياضه", "رياضي", "مدرب", "لاعب", "ملعب", "نادي", "حارس مرمي", "التنس", "الفورمولا",
                "دوري ابطال", "الدوري الممتاز")),
}


def detect_topics(text: str) -> list[str]:
    if not text:
        return []
    en = f" {text.lower()} "
    ar = normalize_ar(text)
    found = []
    for topic, (en_words, ar_words) in TOPIC_KEYWORDS.items():
        if any(re.search(rf"(?<![a-z]){re.escape(w.strip())}", en) if w.strip() == w
               else w in en for w in en_words) or any(w in ar for w in ar_words):
            found.append(topic)
    return found
