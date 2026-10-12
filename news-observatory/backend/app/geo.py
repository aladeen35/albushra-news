"""Country gazetteer and the two declared region lists.

The gazetteer is what turns headline text into "this story is about country X".
It is deliberately simple and editable: automatic matches are suggestions an
editor can correct (Article.classification_edited), never the last word.

Region lists are seeded from published memberships and then live in the
database (RegionList), so an editor can change them without a deploy.
"""
from __future__ import annotations

# code: (english name, arabic name, extra english aliases, extra arabic aliases)
COUNTRIES: dict[str, tuple[str, str, tuple[str, ...], tuple[str, ...]]] = {
    "AF": ("Afghanistan", "أفغانستان", ("Afghan", "Kabul"), ("كابول", "افغاني")),
    "AL": ("Albania", "ألبانيا", ("Albanian", "Tirana"), ("تيرانا",)),
    "DZ": ("Algeria", "الجزائر", ("Algerian", "Algiers"), ("جزائري",)),
    "AZ": ("Azerbaijan", "أذربيجان", ("Azerbaijani", "Baku"), ("باكو",)),
    "BH": ("Bahrain", "البحرين", ("Bahraini", "Manama"), ("بحريني", "المنامة")),
    "BD": ("Bangladesh", "بنغلاديش", ("Bangladeshi", "Dhaka"), ("دكا",)),
    "BJ": ("Benin", "بنين", ("Beninese",), ()),
    "BN": ("Brunei", "بروناي", (), ()),
    "BF": ("Burkina Faso", "بوركينا فاسو", ("Ouagadougou",), ("واغادوغو",)),
    "CM": ("Cameroon", "الكاميرون", ("Cameroonian", "Yaounde"), ()),
    "TD": ("Chad", "تشاد", ("Chadian", "N'Djamena"), ("تشادي", "انجامينا")),
    "KM": ("Comoros", "جزر القمر", ("Comorian",), ("القمر المتحدة",)),
    "CI": ("Ivory Coast", "ساحل العاج", ("Cote d'Ivoire", "Côte d'Ivoire"), ("كوت ديفوار",)),
    "DJ": ("Djibouti", "جيبوتي", ("Djiboutian",), ()),
    "EG": ("Egypt", "مصر", ("Egyptian", "Cairo"), ("مصري", "القاهرة")),
    "GA": ("Gabon", "الغابون", ("Gabonese",), ()),
    "GM": ("Gambia", "غامبيا", ("Gambian",), ()),
    "GN": ("Guinea", "غينيا", ("Guinean", "Conakry"), ("كوناكري",)),
    "GW": ("Guinea-Bissau", "غينيا بيساو", ("Guinea Bissau",), ()),
    "GY": ("Guyana", "غيانا", ("Guyanese",), ()),
    "ID": ("Indonesia", "إندونيسيا", ("Indonesian", "Jakarta"), ("جاكرتا", "اندونيسي")),
    "IR": ("Iran", "إيران", ("Iranian", "Tehran"), ("ايراني", "طهران")),
    "IQ": ("Iraq", "العراق", ("Iraqi", "Baghdad", "Mosul"), ("عراقي", "بغداد", "الموصل")),
    "JO": ("Jordan", "الأردن", ("Jordanian", "Amman"), ("اردني", "عمان الاردنية")),
    "KZ": ("Kazakhstan", "كازاخستان", ("Kazakh", "Astana"), ()),
    "KW": ("Kuwait", "الكويت", ("Kuwaiti",), ("كويتي",)),
    "KG": ("Kyrgyzstan", "قيرغيزستان", ("Kyrgyz", "Bishkek"), ()),
    "LB": ("Lebanon", "لبنان", ("Lebanese", "Beirut"), ("لبناني", "بيروت")),
    "LY": ("Libya", "ليبيا", ("Libyan", "Tripoli", "Benghazi"), ("ليبي", "طرابلس الغرب", "بنغازي")),
    "MY": ("Malaysia", "ماليزيا", ("Malaysian", "Kuala Lumpur"), ("ماليزي",)),
    "MV": ("Maldives", "جزر المالديف", ("Maldivian",), ("المالديف",)),
    "ML": ("Mali", "مالي", ("Malian", "Bamako"), ("باماكو",)),
    "MR": ("Mauritania", "موريتانيا", ("Mauritanian", "Nouakchott"), ("موريتاني", "نواكشوط")),
    "MA": ("Morocco", "المغرب", ("Moroccan", "Rabat"), ("مغربي", "الرباط")),
    "MZ": ("Mozambique", "موزمبيق", ("Mozambican",), ()),
    "NE": ("Niger", "النيجر", ("Niamey",), ("نيامي",)),
    "NG": ("Nigeria", "نيجيريا", ("Nigerian", "Abuja", "Lagos"), ("نيجيري", "ابوجا")),
    "OM": ("Oman", "عُمان", ("Omani", "Muscat"), ("سلطنة عمان", "مسقط", "عماني")),
    "PK": ("Pakistan", "باكستان", ("Pakistani", "Islamabad", "Karachi"), ("باكستاني", "اسلام اباد")),
    "PS": ("Palestine", "فلسطين", ("Palestinian", "Gaza", "West Bank", "Ramallah", "Jenin",
                                  "Khan Younis", "Rafah", "Nablus", "Hebron", "East Jerusalem"),
           ("فلسطيني", "غزة", "قطاع غزة", "الضفة الغربية", "رام الله", "جنين", "خان يونس",
            "رفح", "نابلس", "الخليل", "القدس الشرقية")),
    "QA": ("Qatar", "قطر", ("Qatari", "Doha"), ("قطري", "الدوحة")),
    "SA": ("Saudi Arabia", "السعودية", ("Saudi", "Riyadh", "Jeddah"),
           ("المملكة العربية السعودية", "سعودي", "الرياض", "جدة")),
    "SN": ("Senegal", "السنغال", ("Senegalese", "Dakar"), ("داكار",)),
    "SL": ("Sierra Leone", "سيراليون", (), ()),
    "SO": ("Somalia", "الصومال", ("Somali", "Mogadishu"), ("صومالي", "مقديشو")),
    "SD": ("Sudan", "السودان", ("Sudanese", "Khartoum", "Darfur", "El Fasher", "Omdurman",
                               "Port Sudan", "Kordofan", "Al Jazirah"),
           ("سوداني", "الخرطوم", "دارفور", "الفاشر", "ام درمان", "بورتسودان", "كردفان",
            "الجزيرة السودانية")),
    "SR": ("Suriname", "سورينام", (), ()),
    "SY": ("Syria", "سوريا", ("Syrian", "Damascus", "Aleppo", "Idlib"),
           ("سورية", "سوري", "دمشق", "حلب", "ادلب")),
    "TJ": ("Tajikistan", "طاجيكستان", ("Tajik", "Dushanbe"), ()),
    "TG": ("Togo", "توغو", ("Togolese",), ()),
    "TN": ("Tunisia", "تونس", ("Tunisian", "Tunis"), ("تونسي",)),
    "TR": ("Turkey", "تركيا", ("Türkiye", "Turkish", "Ankara", "Istanbul"),
           ("تركي", "انقرة", "اسطنبول")),
    "TM": ("Turkmenistan", "تركمانستان", ("Ashgabat",), ()),
    "UG": ("Uganda", "أوغندا", ("Ugandan", "Kampala"), ()),
    "AE": ("United Arab Emirates", "الإمارات", ("UAE", "Emirati", "Abu Dhabi", "Dubai"),
           ("الامارات العربية المتحدة", "اماراتي", "ابوظبي", "أبو ظبي", "دبي")),
    "UZ": ("Uzbekistan", "أوزبكستان", ("Uzbek", "Tashkent"), ()),
    "YE": ("Yemen", "اليمن", ("Yemeni", "Sanaa", "Aden", "Hodeidah"),
           ("يمني", "صنعاء", "عدن", "الحديدة")),
    # Outside both declared lists; listed because they appear constantly.
    "SS": ("South Sudan", "جنوب السودان", ("Juba",), ("جوبا",)),
    "IL": ("Israel", "إسرائيل", ("Israeli", "Tel Aviv"), ("اسرائيلي", "تل ابيب")),
    "US": ("United States", "الولايات المتحدة", ("U.S.", "USA", "Washington", "American"),
           ("امريكا", "أمريكا", "واشنطن", "امريكي")),
    "GB": ("United Kingdom", "المملكة المتحدة", ("Britain", "British", "London", "UK"),
           ("بريطانيا", "بريطاني", "لندن")),
    "FR": ("France", "فرنسا", ("French", "Paris"), ("فرنسي", "باريس")),
    "DE": ("Germany", "ألمانيا", ("German", "Berlin"), ("الماني", "برلين")),
    "RU": ("Russia", "روسيا", ("Russian", "Moscow", "Kremlin"), ("روسي", "موسكو", "الكرملين")),
    "UA": ("Ukraine", "أوكرانيا", ("Ukrainian", "Kyiv", "Kiev"), ("اوكراني", "كييف")),
    "CN": ("China", "الصين", ("Chinese", "Beijing"), ("صيني", "بكين")),
    "IN": ("India", "الهند", ("Indian", "New Delhi"), ("هندي", "نيودلهي")),
    "JP": ("Japan", "اليابان", ("Japanese", "Tokyo"), ("ياباني", "طوكيو")),
    "ET": ("Ethiopia", "إثيوبيا", ("Ethiopian", "Addis Ababa"), ("اثيوبي", "اديس ابابا")),
    "ER": ("Eritrea", "إريتريا", ("Eritrean", "Asmara"), ()),
    "KE": ("Kenya", "كينيا", ("Kenyan", "Nairobi"), ("نيروبي",)),
    "CD": ("DR Congo", "الكونغو الديمقراطية", ("Democratic Republic of the Congo", "Kinshasa"), ()),
    "MM": ("Myanmar", "ميانمار", ("Burma", "Rohingya"), ("بورما", "الروهينغا")),
    "BR": ("Brazil", "البرازيل", ("Brazilian",), ()),
    "CA": ("Canada", "كندا", ("Canadian", "Ottawa"), ()),
    "AU": ("Australia", "أستراليا", ("Australian",), ()),
    "IT": ("Italy", "إيطاليا", ("Italian", "Rome"), ("روما",)),
    "ES": ("Spain", "إسبانيا", ("Spanish", "Madrid"), ("مدريد",)),
}

# League of Arab States: 22 members.
ARAB_LEAGUE = ["DZ", "BH", "KM", "DJ", "EG", "IQ", "JO", "KW", "LB", "LY", "MR", "MA", "OM",
               "PS", "QA", "SA", "SO", "SD", "SY", "TN", "AE", "YE"]

# Organisation of Islamic Cooperation: 57 member states.
OIC_MEMBERS = ["AF", "AL", "DZ", "AZ", "BH", "BD", "BJ", "BN", "BF", "CM", "TD", "KM", "CI",
               "DJ", "EG", "GA", "GM", "GN", "GW", "GY", "ID", "IR", "IQ", "JO", "KZ", "KW",
               "KG", "LB", "LY", "MY", "MV", "ML", "MR", "MA", "MZ", "NE", "NG", "OM", "PK",
               "PS", "QA", "SA", "SN", "SL", "SO", "SD", "SR", "SY", "TJ", "TG", "TN", "TR",
               "TM", "UG", "AE", "UZ", "YE"]


# Arabic forms that are also everyday words (مالي = "financial", بنين = "sons",
# جنين = "foetus") or that name two places (عمان = Oman and Amman). They are
# kept for display but never used to tag a story; the aliases still match.
AMBIGUOUS_AR = {"مالي", "بنين", "جنين", "عمان"}
AMBIGUOUS_EN = {"Indian"}


def country_name(code: str, lang: str = "en") -> str:
    entry = COUNTRIES.get(code)
    if not entry:
        return code
    return entry[1] if lang == "ar" else entry[0]
