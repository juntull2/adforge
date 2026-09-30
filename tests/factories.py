"""테스트용 객체 생성 도우미 (네트워크 없이 A급 결과를 만듭니다)."""
from dataclasses import asdict
from datetime import date, timedelta

import a_grade_finder as g


def make_ad(ad_id="1", page_id="11", page_name="리포데이", key="re4day.co.kr", days=121, copy="피부과에서 300 쓰기 전에",
            **extra):
    start = (date.today() - timedelta(days=days)).isoformat()
    base = dict(
        ad_id=ad_id, page_id=page_id, page_name=page_name, start_date=start, running_days=days,
        media_type="영상", copy=copy, hook=copy[:40], caption=key, landing_url=f"https://{key}/p",
        store_key=key, video_url="https://video.example/v.mp4", thumbnail_url="",
        library_url=f"https://www.facebook.com/ads/library/?id={ad_id}", search_keyword="먹는 여드름",
        relevance=["여드름", "영양제"],
    )
    base.update(extra)
    return g.AdSummary(**base)


def make_volume(passed=True, keyword="리포데이", peak=23810, level=g.RISE_ROCKET, jump=7100, ratio=3.3, **extra):
    today = date.today()
    base = dict(
        passed=passed, keyword=keyword, peak_month="최근 30일", peak_volume=peak, recent_30d=peak,
        recent_pc=3160, recent_mobile=peak - 3160,
        months=[{"month": "2026-06", "volume": peak, "days": 30, "partial": False}],
        windows=[{"end": (today - timedelta(days=60 - i)).isoformat(), "volume": 3000 + i * 100} for i in range(60)],
        checked=[{"keyword": keyword, "recent_30d": peak, "peak_month": "최근 30일", "peak_volume": peak,
                  "rise_level": level, "rise_jump": jump, "note": ""}],
        rise_level=level,
        rise_start=(today - timedelta(days=30)).isoformat() if level else "",
        rise_end=(today - timedelta(days=1)).isoformat() if level else "",
        rise_volume=peak if level else 0, rise_prev=peak - jump if level else 0, rise_jump=jump if level else 0,
        rise_ratio=ratio if level else None, rise_baseline=peak - jump if level else 0,
    )
    base.update(extra)
    return g.VolumeCheck(**base)


def make_brand(key="re4day.co.kr", name="리포데이", ads=None, volume=None, **extra):
    brand = g.BrandCandidate(
        key=key, name=name, site_name=name, keywords=[name], ads=ads if ads is not None else [make_ad(key=key)],
        relevance_terms=["여드름", "영양제"], volume=volume if volume is not None else make_volume(keyword=name),
        landing_url=f"https://{key}/p", product_hint="파이토업",
        **extra,
    )
    g.grade_brand(brand, g.ScanSettings())
    return brand


def make_report(brands, generated_at="2026-09-30T12:00:00"):
    settings = g.ScanSettings()
    return g.AGradeReport(
        generated_at=generated_at, settings=asdict(settings), scanned_ads=sum(len(b.ads) for b in brands),
        long_running_ads=sum(len(b.ads) for b in brands), relevant_ads=sum(len(b.ads) for b in brands),
        brands=g.sort_brands(brands),
    )
