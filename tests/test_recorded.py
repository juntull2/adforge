import base64
import json
from dataclasses import replace

import a_grade_finder as g
from factories import make_ad, make_brand, make_report

def raw_sample_ad():
    efg = base64.b64encode(json.dumps({"xpv_asset_id": "1049710707770329"}).encode()).decode()
    return {"ad_archive_id": "sample", "collation_id": "1625301855796543",
            "snapshot": {"body": {"text": "에너지 넘치는 찌남매랑 함께하는 하루"},
                         "videos": [{"video_hd_url": f"https://video.example/video.mp4?efg={efg}"}]}}


def test_video_asset_id_from_efg_sample():
    assert g.video_asset_id(raw_sample_ad()) == "1049710707770329"


def test_summary_carries_identity_fields():
    ad = raw_sample_ad()
    from datetime import date
    s = g.summarize_ad(ad, date(2026, 9, 30), None)
    assert s.collation_id == "1625301855796543"
    assert s.video_asset_id == "1049710707770329"
    assert s.fingerprint.startswith("에너지넘치는찌남매랑")


def test_fingerprint_ignores_short_or_empty_copy():
    assert g.creative_fingerprint("") == ""
    assert g.creative_fingerprint("ㅤ") == ""
    assert g.creative_fingerprint("🔥 피부과에서 300 쓰기 전에!\n#광고") == "피부과에서300쓰기전에"


def keys_with(**kw):
    keys = g.RecordedKeys(loaded=True)
    for name, values in kw.items():
        getattr(keys, name).update(values)
    return keys


def test_match_rules():
    ad = make_ad(ad_id="9", collation_id="c9", video_asset_id="v9", fingerprint="피부과에서300쓰기전에")
    assert keys_with(ad_ids={"9"}).match(ad, "re4day.co.kr") == "광고 ID 같음"
    assert keys_with(collation_ids={"c9"}).match(ad, "re4day.co.kr") == "묶음 ID 같음"
    assert keys_with(asset_ids={"v9"}).match(ad, "re4day.co.kr") == "같은 영상"
    same_fp = keys_with(fingerprints={("re4day.co.kr", "피부과에서300쓰기전에")})
    assert same_fp.match(ad, "re4day.co.kr") == "같은 브랜드·같은 첫 문장"
    # 다른 브랜드가 같은 문장을 쓰면 제외하지 않음
    assert same_fp.match(ad, "other.kr") == ""
    # 문구가 없어 지문이 빈 광고는 지문으로 제외하지 않음
    assert same_fp.match(replace(ad, fingerprint=""), "re4day.co.kr") == ""
    assert g.RecordedKeys().match(ad, "re4day.co.kr") == ""


def test_mark_recorded_keeps_grades_and_order():
    a1 = make_ad(ad_id="1")
    a2 = make_ad(ad_id="2", copy="완전히 다른 두 번째 광고 문구입니다")
    brand = make_brand(ads=[a1, a2])
    other = make_brand(key="demaf.kr", name="디마프", ads=[make_ad(ad_id="3", key="demaf.kr")])
    report = make_report([brand, other])
    before = [(b.name, b.is_a_grade) for b in report.brands]
    count = g.mark_recorded(report, keys_with(ad_ids={"1", "3"}))
    assert count == 2
    assert a1.recorded == "광고 ID 같음" and a2.recorded == ""
    assert [(b.name, b.is_a_grade) for b in report.brands] == before
    assert report.recorded_checked


def test_merge_collations_keeps_oldest_and_counts_variants():
    ads = [
        {"ad_archive_id": "1", "collation_id": "c", "start_date": 1780000000},
        {"ad_archive_id": "2", "collation_id": "c", "start_date": 1770000000},
        {"ad_archive_id": "3", "collation_id": "", "start_date": 1775000000},
        {"ad_archive_id": "4", "collation_id": "c", "start_date": 1779000000},
    ]
    merged = g.merge_collations(ads)
    assert [a["ad_archive_id"] for a in merged] == ["2", "3"]
    assert merged[0]["_variants"] == 3 and merged[1]["_variants"] == 1
