from datetime import date, timedelta

import pytest

import a_grade_finder as g
from factories import make_brand, make_volume

CREDS = ("cid", "lic", "secret")
TODAY = date(2026, 9, 30)


class FakeDataLab:
    """키워드별로 '하루 값 함수(날짜 → 지수)'를 돌려주는 가짜 데이터랩"""

    def __init__(self, shapes):
        self.shapes = shapes
        self.calls = []

    def daily(self, keyword, start, end):
        self.calls.append(keyword)
        shape = self.shapes.get(keyword)
        if shape is None:
            return []
        days = (end - start).days + 1
        return [{"date": start + timedelta(days=i), "value": float(shape(start + timedelta(days=i)))}
                for i in range(days)]


def fake_volumes(totals):
    def _get(keywords, *creds):
        return {k: {"pc": totals.get(k, 0) // 10, "mobile": totals.get(k, 0) - totals.get(k, 0) // 10,
                    "total": totals.get(k, 0), "found": k in totals, "error": False} for k in keywords}
    return _get


def quiet_then_rise(rise_from):
    return lambda d: 3.4 if d >= rise_from else 1.0


@pytest.fixture
def patch_volumes(monkeypatch):
    def _apply(totals):
        monkeypatch.setattr(g, "get_naver_search_volumes", fake_volumes(totals))
    return _apply


def test_sudden_rise_is_rocket_and_passes(patch_volumes):
    patch_volumes({"리포데이": 10200})
    lab = FakeDataLab({"리포데이": quiet_then_rise(TODAY - timedelta(days=60))})
    v = g.check_search_spike(["리포데이"], CREDS, today=TODAY, datalab=lab)
    assert v.passed is True
    assert v.keyword == "리포데이"
    assert v.rise_level == g.RISE_ROCKET
    assert v.rise_prev == 6000 and v.rise_volume == 20400 and v.rise_jump == 14400
    assert v.rise_window_days == 60
    assert (date.fromisoformat(v.rise_end) - date.fromisoformat(v.rise_start)).days == 59
    assert v.rise_end == (TODAY - timedelta(days=1)).isoformat()
    assert v.windows and v.windows[-1]["volume"] == 20400
    assert v.months, "달력 월별 참고 그래프도 채워야 함"


def test_high_but_flat_brand_still_checks_trend(patch_volumes):
    # 예전에는 최근 30일 ≥ 1만이면 추이를 건너뛰었음 → 이제는 꾸준형으로 표시
    patch_volumes({"디마프": 42000})
    lab = FakeDataLab({"디마프": lambda d: 1.0})
    v = g.check_search_spike(["디마프"], CREDS, today=TODAY, datalab=lab)
    assert lab.calls == ["디마프"]
    assert v.passed is False
    assert v.rise_level == g.RISE_FLAT


def test_steepest_passing_keyword_is_representative(patch_volumes):
    # 브랜드명은 검색량이 더 크지만 꾸준, 제품명은 1만을 넘으며 급상승 → 제품명이 대표
    patch_volumes({"브랜드": 30000, "제품": 10200})
    lab = FakeDataLab({"브랜드": lambda d: 1.0, "제품": quiet_then_rise(TODAY - timedelta(days=60))})
    v = g.check_search_spike(["브랜드", "제품"], CREDS, today=TODAY, datalab=lab)
    assert v.keyword == "제품"
    assert v.rise_level == g.RISE_ROCKET
    assert v.passed is True


def test_low_volume_keyword_checks_past_trend(patch_volumes):
    patch_volumes({"작은브랜드": 120})
    lab = FakeDataLab({"작은브랜드": lambda d: 1.0})
    v = g.check_search_spike(["작은브랜드"], CREDS, today=TODAY, datalab=lab)
    assert lab.calls == ["작은브랜드"]
    assert v.passed is False
    assert v.peak_volume == 120
    assert v.rise_level == g.RISE_FLAT


def test_past_peak_within_year_passes(patch_volumes):
    # 5개월 전에 30일 1만을 넘었다가 내려온 브랜드도 ① 통과
    peak_from = TODAY - timedelta(days=150)
    shape = lambda d: 10.0 if peak_from <= d < peak_from + timedelta(days=30) else 1.0
    patch_volumes({"과거브랜드": 3000})
    lab = FakeDataLab({"과거브랜드": shape})
    v = g.check_search_spike(["과거브랜드"], CREDS, today=TODAY, datalab=lab)
    assert v.passed is True
    assert v.peak_volume == 30000
    assert v.peak_month.startswith("~")
    assert v.rise_level == g.RISE_ROCKET


@pytest.mark.parametrize("recent,passed", [(4999, False), (5000, False), (6000, False)])
def test_sixty_day_threshold(patch_volumes, recent, passed):
    patch_volumes({"브랜드": recent})
    v = g.check_search_spike(["브랜드"], CREDS, today=TODAY,
                             datalab=FakeDataLab({"브랜드": lambda d: 1.0}))
    assert v.passed is passed
    assert v.peak_volume == recent
    assert v.search_window_days == 30
    assert v.grade_windows[-1]["volume"] == recent
    assert v.windows[-1]["volume"] == recent * 2


def test_no_trend_does_not_double_recent_thirty_days(patch_volumes):
    patch_volumes({"브랜드": 6000})
    v = g.check_search_spike(["브랜드"], CREDS, today=TODAY, datalab=FakeDataLab({}))
    assert v.passed is None
    assert v.peak_volume == 6000
    assert not v.peak_is_lower_bound  # 최근 30일 실측 검색량


@pytest.mark.parametrize("jump,level", [(6998, g.RISE_UP), (7000, g.RISE_ROCKET)])
def test_sixty_day_rise_boundary(patch_volumes, jump, level):
    recent = int((3000 + jump) / 2)
    patch_volumes({"브랜드": recent})
    old_ratio = 1500 / recent
    lab = FakeDataLab({"브랜드": lambda d: 1.0 if d >= TODAY - timedelta(days=60) else old_ratio})
    v = g.check_search_spike(["브랜드"], CREDS, today=TODAY, datalab=lab)
    assert v.rise_jump == jump
    assert v.rise_level == level
    assert v.rise_volume == 3000 + jump and v.rise_prev == 3000
    assert v.passed is False  # 60일 증가폭만 충족하고 30일 검색량은 1만 미달


def test_sixty_day_rise_can_compare_at_start_of_lookback(patch_volumes):
    since = TODAY - timedelta(days=365)
    patch_volumes({"브랜드": 3000})
    lab = FakeDataLab({"브랜드": lambda d: 10.0 if since - timedelta(days=59) <= d <= since else 1.0})
    v = g.check_search_spike(["브랜드"], CREDS, today=TODAY, datalab=lab)
    assert v.rise_end == since.isoformat()
    assert v.rise_prev == 6000 and v.rise_volume == 60000


def test_thresholds_are_configurable(patch_volumes):
    patch_volumes({"리포데이": 10200})
    lab = FakeDataLab({"리포데이": quiet_then_rise(TODAY - timedelta(days=60))})
    v = g.check_search_spike(["리포데이"], CREDS, today=TODAY, datalab=lab, min_jump=16000, min_ratio=3.0)
    assert v.rise_level == g.RISE_UP


def test_no_credentials():
    v = g.check_search_spike(["리포데이"], ("", "", ""), today=TODAY)
    assert v.passed is None


def test_grade_requires_rise():
    flat = make_brand(key="a.kr", name="꾸준", volume=make_volume(keyword="꾸준", level=g.RISE_FLAT, jump=0))
    assert not flat.is_a_grade


def test_sort_order_a_grade_then_rise_then_jump():
    rocket_small = make_brand(key="r1.kr", name="로켓작음", volume=make_volume(keyword="로켓작음", jump=7200))
    rocket_big = make_brand(key="r2.kr", name="로켓큼", volume=make_volume(keyword="로켓큼", jump=20000))
    up = make_brand(key="u.kr", name="상승", volume=make_volume(keyword="상승", level=g.RISE_UP, jump=30000, ratio=1.8))
    flat = make_brand(key="f.kr", name="꾸준", volume=make_volume(keyword="꾸준", level=g.RISE_FLAT, jump=0))
    unknown = make_brand(key="n.kr", name="추이없음", volume=make_volume(keyword="추이없음", level=""))
    not_a = make_brand(key="x.kr", name="미달", volume=make_volume(passed=False, keyword="미달", jump=50000))
    ordered = g.sort_brands([not_a, flat, up, unknown, rocket_small, rocket_big])
    assert [b.name for b in ordered] == ["로켓큼", "로켓작음", "상승", "미달", "꾸준", "추이없음"]


def test_jump_passes_even_below_three_times(patch_volumes):
    patch_volumes({"브랜드": 10000})
    lab = FakeDataLab({"브랜드": lambda d: 1.0 if d >= TODAY - timedelta(days=60) else 13000 / 20000})
    v = g.check_search_spike(["브랜드"], CREDS, today=TODAY, datalab=lab)
    assert v.peak_volume == 10000 and v.rise_volume == 20000 and v.rise_jump == 7000
    assert v.rise_ratio < 3 and v.passed is True
    assert v.search_window_days == 30 and v.rise_window_days == 60
    assert v.grade_windows[-1]["volume"] == 10000
    assert v.windows[-1]["volume"] == 20000


def test_sixty_day_sum_cannot_replace_thirty_day_threshold(patch_volumes):
    patch_volumes({"브랜드": 9999})
    lab = FakeDataLab({"브랜드": quiet_then_rise(TODAY - timedelta(days=60))})
    v = g.check_search_spike(["브랜드"], CREDS, today=TODAY, datalab=lab)
    assert v.rise_volume > 10000 and v.rise_jump > 7000
    assert v.peak_volume == 9999 and v.passed is False


def test_settings_from_old_report_dict():
    s = g.ScanSettings.from_dict({"min_running_days": 60, "unknown_field": 1})
    assert s.spike_min_jump == g.SPIKE_MIN_JUMP and s.spike_min_ratio == g.SPIKE_MIN_RATIO


def test_rise_summary_text():
    v = make_volume(level=g.RISE_ROCKET, peak=10200, jump=7100, ratio=3.3)
    text = g.rise_summary(v)
    assert text.startswith(g.RISE_ROCKET)
    assert "3,100 → 10,200 (+7,100, 3.3배)" in text
    assert g.rise_summary(make_volume(level="")) == "추이 없음"


def test_legacy_rise_is_not_written_as_sixty_day_rise():
    import notion_references as n
    import a_grade_view as v
    volume = make_volume(rise_window_days=30)
    brand = make_brand(volume=volume)
    props = n.brand_properties(brand, TODAY, create=False)
    assert props[n.B_JUMP]["number"] is None
    assert props[n.B_RISE]["select"] is None
    assert "재확인" in v._rise_jump_text(volume)
    assert "30일 기준" in g.rise_summary(volume)
