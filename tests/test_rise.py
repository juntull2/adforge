from datetime import date, timedelta

from naver_datalab import (
    RISE_FLAT,
    RISE_ROCKET,
    RISE_UP,
    find_steepest_rise,
    format_rise,
    rolling_30d_volumes,
)

START = date(2025, 8, 1)


def daily_series(values):
    """values: 하루 값 목록 → 데이터랩 일간 추이 형식"""
    return [{"date": START + timedelta(days=i), "value": float(v)} for i, v in enumerate(values)]


def test_rolling_sums_and_scaling():
    # 60일 동안 하루 1.0 → 최근 30일 지수 합 30, 실측 3,000 → 하루 100건
    windows = rolling_30d_volumes(daily_series([1.0] * 60), 3000)
    assert len(windows) == 31
    assert windows[0]["end"] == START + timedelta(days=29)
    assert all(w["volume"] == 3000 for w in windows)


def test_missing_days_count_as_zero():
    # 데이터랩이 뺀 날: 앞 30일은 하루 걸러 하나만 있음
    points = [{"date": START + timedelta(days=i), "value": 1.0} for i in range(0, 30, 2)]
    points += [{"date": START + timedelta(days=i), "value": 1.0} for i in range(30, 60)]
    windows = rolling_30d_volumes(points, 3000, start=START, end=START + timedelta(days=59))
    assert windows[0]["volume"] == 1500      # 15일만 있음 → 절반
    assert windows[-1]["volume"] == 3000


def test_quiet_year_then_sudden_rise_is_rocket():
    # 1년 가까이 하루 ~100건(30일 3,000) → 마지막 30일 하루 ~340건(30일 10,200)
    values = [1.0] * 335 + [3.4] * 30
    windows = rolling_30d_volumes(daily_series(values), 10200)
    rise = find_steepest_rise(windows, min_jump=7000, min_ratio=3.0)
    assert rise["level"] == RISE_ROCKET
    assert rise["volume"] == 10200
    assert rise["prev_volume"] == 3000
    assert rise["jump"] == 7200
    assert rise["ratio"] == 3.4
    assert rise["baseline"] == 3000
    assert rise["end"] == START + timedelta(days=364)
    assert rise["start"] == START + timedelta(days=335)
    assert rise["peak_volume"] == 10200


def test_already_high_brand_is_only_up():
    # 30일 44,000 → 67,000 (1.5배): 증가폭은 크지만 원래 높은 브랜드
    values = [44.0] * 60 + [67.0] * 30
    windows = rolling_30d_volumes(daily_series(values), 67 * 30 * 10)
    rise = find_steepest_rise(windows)
    assert rise["level"] == RISE_UP
    assert rise["prev_volume"] == 13200 and rise["volume"] == 20100


def test_flat_brand():
    windows = rolling_30d_volumes(daily_series([2.0] * 120), 6000)
    rise = find_steepest_rise(windows)
    assert rise["level"] == RISE_FLAT
    assert rise["jump"] == 0


def test_rise_across_month_boundary_is_one_window():
    # 6/20 ~ 7/19 사이에만 오른 급상승: 달력 월로 자르면 두 달에 나뉘지만 30일 구간 하나로 잡혀야 함
    start = date(2026, 3, 1)
    rise_from = date(2026, 6, 20)
    points = []
    for i in range(200):
        d = start + timedelta(days=i)
        points.append({"date": d, "value": 10.0 if rise_from <= d < rise_from + timedelta(days=30) else 1.0})
    end = start + timedelta(days=199)
    windows = rolling_30d_volumes(points, 30 * 100, start=start, end=end)   # 최근 30일 지수 합 30 → 하루 100건
    rise = find_steepest_rise(windows)
    assert rise["level"] == RISE_ROCKET
    assert rise["start"] == rise_from
    assert rise["volume"] == 30000 and rise["prev_volume"] == 3000


def test_rise_from_zero_has_no_ratio():
    values = [0.0] * 60 + [5.0] * 30
    points = [p for p in daily_series(values) if p["value"] > 0]    # 데이터랩은 0인 날을 뺌
    windows = rolling_30d_volumes(points, 15000, start=START, end=START + timedelta(days=89))
    rise = find_steepest_rise(windows)
    assert rise["level"] == RISE_ROCKET
    assert rise["ratio"] is None
    assert "신규" in format_rise(rise)


def test_since_limits_peak_and_rise():
    # 오래전 급상승은 since 이전이라 무시
    values = [1.0] * 40 + [20.0] * 30 + [1.0] * 300
    windows = rolling_30d_volumes(daily_series(values), 3000)
    since = START + timedelta(days=200)
    rise = find_steepest_rise(windows, since=since)
    assert rise["level"] == RISE_FLAT
    assert rise["peak_volume"] == 3000


def test_format_rise_text():
    values = [1.0] * 335 + [3.4] * 30
    rise = find_steepest_rise(rolling_30d_volumes(daily_series(values), 10200))
    assert format_rise(rise) == "3,000 → 10,200 (+7,200, 3.4배) · 7/2~7/31 · 평소 3,000"


def test_empty_inputs():
    assert rolling_30d_volumes([], 1000) == []
    assert rolling_30d_volumes(daily_series([0.0] * 40), 1000) == []
    assert find_steepest_rise([])["level"] == RISE_FLAT
    assert format_rise({}) == "추이 없음"
