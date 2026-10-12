from app.classify import detect_countries, detect_language, detect_topics
from app.dedupe import canonical_url, title_fingerprint


def test_longest_name_wins():
    assert detect_countries("South Sudan and Sudan talks") == ["SD", "SS"]
    assert detect_countries("محادثات في جنوب السودان") == ["SS"]
    assert detect_countries("Guinea-Bissau election") == ["GW"]


def test_arabic_prefixes_and_aliases():
    assert detect_countries("قصف على خان يونس") == ["PS"]
    assert detect_countries("مساعدات بالسودان وللسودانيين") == ["SD"]
    assert detect_countries("الدوري السعودي") == ["SA"]


def test_everyday_arabic_words_are_not_countries():
    # مالي = "financial", جنين = "foetus", عمان = Oman or Amman
    assert detect_countries("وزير المالية: الوضع المالي مستقر") == []
    assert detect_countries("صحة الجنين") == []
    assert detect_countries("اجتماع في عمان") == []


def test_language_and_topics():
    assert detect_language("نزوح جديد في السودان") == "ar"
    assert detect_language("New displacement in Sudan") == "en"
    assert "conflict" in detect_topics("غارات على المدينة")
    assert "health" in detect_topics("Cholera outbreak in camps")


def test_canonical_url_strips_tracking_and_amp():
    assert (canonical_url("http://www.Example.com/a/b/amp/?utm_source=x&b=2&a=1#f")
            == "https://example.com/a/b?a=1&b=2")


def test_same_story_different_outlets_share_fingerprint():
    assert title_fingerprint("UN warns of famine in Sudan - Reuters") == \
        title_fingerprint("Sudan: UN warns of famine | AP News")
    assert title_fingerprint("UN warns of famine in Sudan") != title_fingerprint("UN warns of famine in Yemen")
