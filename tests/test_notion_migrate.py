import copy
import json
import os
import time
from datetime import date, datetime, timedelta

import pytest

import a_grade_finder as g
import notion_migrate as nm
import notion_references as nr
from factories import make_volume
from fake_notion import FakeNotion, legacy_workspace

ROOT = os.path.dirname(os.path.dirname(__file__))
TODAY = date.today()


# ── 제목·링크 해석 ────────────────────────────────────────

def test_parse_titles_from_real_notion_export():
    with open(os.path.join(ROOT, "final_verified_notion.txt"), encoding="utf-8") as f:
        titles = [line.strip() for line in f if line.startswith("[")]
    parsed = {t: nm.parse_title(t) for t in titles}
    cel = next(p for t, p in parsed.items() if "셀라이징" in t)
    assert cel["appeals"] == ["진피재생", "시술대체"]
    assert cel["media_type"] == "영상"
    assert cel["brand"] == "셀라이징"
    assert cel["headline"] == "프락셀 레이저 부작용 고발 & 손상 진피 재생 크림"
    celimax = next(p for t, p in parsed.items() if "셀리맥스" in t)
    assert celimax["appeals"] == [] and celimax["brand"] == "셀리맥스"


def test_parse_title_without_appeal_or_media():
    assert nm.parse_title("[영상] Clinö (2026-07-22)")["headline"] == "Clinö (2026-07-22)"
    assert nm.parse_title("메디옥실") == {"appeals": [], "media_type": "", "brand": "", "headline": "메디옥실"}


def test_extract_ad_ids_from_urls_and_body():
    texts = [
        "https://www.facebook.com/ads/library/?id=1974644779903348",
        "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&id=1010797825339694&view_all_page_id=1",
        "집행 일수: 78일 이상 연속 집행 중 (2026-06-29 시작, Ad ID: 2431969680621794, 1316372663462040)",
        "https://www.facebook.com/ads/library/?active_status=all&q=%EB%A6%AC&search_type=keyword_unordered",
    ]
    assert nm.extract_ad_ids(texts) == ["1974644779903348", "1010797825339694", "2431969680621794", "1316372663462040"]


def row(title="", props=None, body="", ad_ids=None, landing=""):
    return nm.LegacyRow(source="기획표", row_id="r", title=title, props=props or {}, body=body,
                        ad_ids=ad_ids or [], landing=landing)


@pytest.mark.parametrize("title,props,ids,landing,keep,reason", [
    ("[대본/기획] 레티라겐 - 벤치마킹 기반 숏폼 위닝 광고 대본 3종", {}, ["1"], "", False, "우리 기획물"),
    ("배우_촬영가이드_및_대본_레티라겐_범용", {}, [], "", False, "우리 기획물"),
    ("📌 [필독 가이드] D2C 위닝 브랜드 '엄격한 2대 판별 기준'", {}, ["1"], "", False, "안내 행"),
    ("[제외] 토리든 - 네이버플러스 플랫폼 광고", {}, [], "", False, "제외로 표시된 행"),
    ("", {}, [], "", False, "빈 행"),
    ("[영상] 누오 - 뽀얀 피부", {}, [], "https://nuokr.com", False, "메타 광고 ID가 없어"),
    ("[영상] 리포데이 - 속관리", {}, ["2431969680621794"], "https://re4day.co.kr", True, ""),
])
def test_classify_rows(title, props, ids, landing, keep, reason):
    ok, why = nm.classify_row(row(title, props, ad_ids=ids, landing=landing))
    assert ok is keep
    assert why.startswith(reason)


def test_build_row_never_reads_human_columns():
    page = {"id": "p1", "properties": {
        "광고 카피": {"type": "title", "title": [{"plain_text": "[영상] 리포데이 - 속관리"}]},
        "대표님 피드백": {"type": "rich_text", "rich_text": [{"plain_text": "https://www.facebook.com/ads/library/?id=999999999999"}]},
        "소재링크": {"type": "rich_text", "rich_text": [{"plain_text": "https://drive.google.com/file/d/human/view"}]},
        "레퍼런스링크": {"type": "url", "url": "https://www.facebook.com/ads/library/?id=2431969680621794"},
        "자사몰 판매 제품명": {"type": "rich_text", "rich_text": [{"plain_text": "파이토업 (Phyto-Up)"}]},
    }}
    r = nm.build_row("기획표", page, body="")
    assert "대표님 피드백" not in r.props and "소재링크" not in r.props
    assert r.ad_ids == ["2431969680621794"]
    assert r.drive_link == ""
    assert r.product_names == ["리포데이", "파이토업"]


def test_legacy_brand_names():
    assert nm.legacy_brand_names("Cèlisîng (셀라이징)") == ["Cèlisîng", "셀라이징"]
    assert nm.legacy_brand_names("피부 과학의 모든 것 (누오)") == ["누오"]
    assert nm.legacy_brand_names("ખ 건강 ન딨ન") == []
    assert nm.legacy_brand_names("") == []


# ── 계획 → 실행 (가짜 노션·가짜 메타) ─────────────────────

def raw_ad(ad_id, days, link="https://www.re4day.co.kr/goods/1", body="여드름 속관리 영양제 하루 한 알이면 끝", page="리포데이"):
    sample = json.load(open(os.path.join(ROOT, "scratch", "raw_response.json"), encoding="utf-8"))
    ad = copy.deepcopy(sample["data"]["ad_library_main"]["search_results_connection"]["edges"][0]["node"]["collated_results"][0])
    ad["ad_archive_id"] = ad_id
    ad["collation_id"] = f"col-{ad_id}"
    ad["page_name"] = page
    ad["page_id"] = f"pid-{page}"
    ad["start_date"] = int(time.mktime((datetime.now() - timedelta(days=days)).timetuple()))
    ad["snapshot"]["link_url"] = link
    ad["snapshot"]["caption"] = ""
    ad["snapshot"]["body"] = {"text": body}
    return ad


class FakeLookup:
    def __init__(self, ads):
        self.ads = ads

    def find(self, ad_id):
        ad = self.ads.get(ad_id)
        return (copy.deepcopy(ad), "ID 검색") if ad else (None, "지금 게재 중인 광고에서 찾지 못함 (게재 종료 또는 확인 불가)")


class FakeResolver(g.LinkResolver):
    def resolve_many(self, urls):
        list(urls)

    def landing_infos(self, urls_by_key):
        return {k: {"site_name": "리포데이", "og_title": "파이토업 플러스", "title": "", "description": "",
                    "final_url": u} for k, u in urls_by_key.items()}


def add_legacy_row(fake, ds, title, props):
    page_props = {"광고 카피": {"type": "title", "title": [{"plain_text": title}]}}
    page_props.update(props)
    page_id = fake._id("legacy-page")
    fake.pages[page_id] = {"id": page_id, "parent": {"data_source_id": ds}, "properties": page_props}
    fake.children[page_id] = []
    return page_id


def url_prop(u):
    return {"type": "url", "url": u}


@pytest.fixture
def world(monkeypatch):
    for key in (nr.ENV_PAGE, nr.ENV_BRAND_DB, nr.ENV_BRAND_DS, nr.ENV_AD_DB, nr.ENV_AD_DS):
        monkeypatch.delenv(key, raising=False)
    fake = FakeNotion()
    legacy_workspace(fake)
    add_legacy_row(fake, "legacy-ds", "[💊 이너뷰티 / 속관리] [영상] 리포데이 - 피지 줄이는 속관리 (78일 롱런)", {
        "레퍼런스링크": url_prop("https://drive.google.com/file/d/drive-1/view?usp=drivesdk"),
        "서브계정 영상 링크": url_prop("https://www.facebook.com/ads/library/?id=111111111111"),
        "대표님 피드백": {"type": "rich_text", "rich_text": [{"plain_text": "사람이 쓴 피드백"}]},
    })
    add_legacy_row(fake, "legacy-ds", "[영상] 짧은광고 - 게재 30일", {
        "레퍼런스링크": url_prop("https://www.facebook.com/ads/library/?id=222222222222")})
    add_legacy_row(fake, "legacy-ds", "[영상] 끝난광고", {
        "레퍼런스링크": url_prop("https://www.facebook.com/ads/library/?id=333333333333")})
    add_legacy_row(fake, "legacy-ds", "[영상] 다이어트 - 체지방", {
        "레퍼런스링크": url_prop("https://www.facebook.com/ads/library/?id=444444444444")})
    add_legacy_row(fake, "legacy-ds", "[대본/기획] 레티라겐 대본 3종", {})
    lookup = FakeLookup({
        # 문구 없는 영상 광고: 기존 행 제목(피지·이너뷰티)으로 연관성 판단
        "111111111111": raw_ad("111111111111", 90, body=""),
        "222222222222": raw_ad("222222222222", 30),
        "444444444444": raw_ad("444444444444", 120, link="https://diet.example.com/p", body="체지방 다이어트 보조제 할인",
                               page="다이어트몰"),
    })
    monkeypatch.setattr(g, "check_search_spike", lambda keywords, *a, **k: make_volume(keyword=keywords[0]))
    plan = nm.plan_migration(fake, "legacy-db", ("c", "l", "s"), lookup=lookup, resolver=FakeResolver(),
                             meta=object(), progress=lambda m: None, fetch_audience=False)
    return fake, plan


def test_plan_moves_only_long_running_relevant_a_grade(world):
    fake, plan = world
    decisions = {a["ad_id"]: (a["decision"], a["reason"]) for a in plan.ads}
    assert decisions["111111111111"][0] == nm.MOVE
    assert decisions["222222222222"] == (nm.SKIP, "② 게재 30일 (< 60일)")
    assert decisions["333333333333"][0] == nm.SKIP and "찾지 못함" in decisions["333333333333"][1]
    assert decisions["444444444444"][0] == nm.SKIP
    assert decisions["444444444444"][1].startswith("③ 제품 연관 키워드 없음")
    by_title = {r.title: r for r in plan.rows}
    assert by_title["[대본/기획] 레티라겐 대본 3종"].reason.startswith("우리 기획물")
    moved = plan.moving_brands()
    assert [b.key for b in moved] == ["re4day.co.kr"]
    report = nm.format_report(plan)
    assert "리포데이" in report and "사람이 쓴 피드백" not in report
    # 계획은 읽기만
    assert not fake.written_properties()


def test_plan_json_roundtrip_and_apply_is_idempotent(world, monkeypatch):
    fake, plan = world
    data = json.loads(json.dumps(nm.plan_to_dict(plan), ensure_ascii=False, default=str))
    assert "사람이 쓴 피드백" not in json.dumps(data, ensure_ascii=False)
    restored = nm.plan_from_dict(data)
    assert restored.moving_brands()[0].volume.rise_level == g.RISE_ROCKET

    ids = {}
    nr.apply_setup(fake, nr.plan_setup(fake, "legacy-db"), env_writer=ids.update)
    for k, v in ids.items():
        monkeypatch.setenv(k, v)
    store = nr.ReferenceStore(fake, ids[nr.ENV_BRAND_DS], ids[nr.ENV_AD_DS]).load()
    first = nm.apply_migration(restored, store, track=False, progress=lambda m: None)
    assert first == {"brands": 1, "ads_created": 1, "ads_updated": 0, "errors": []}
    store2 = nr.ReferenceStore(fake, ids[nr.ENV_BRAND_DS], ids[nr.ENV_AD_DS]).load()
    second = nm.apply_migration(nm.plan_from_dict(data), store2, track=False, progress=lambda m: None)
    assert second["ads_created"] == 0 and second["ads_updated"] == 1
    ads = fake.rows(ids[nr.ENV_AD_DS])
    assert len(ads) == 1
    props = ads[0]["properties"]
    assert props[nr.A_APPEAL]["multi_select"] == [{"name": "이너뷰티"}, {"name": "속관리"}]
    assert props[nr.A_VIDEO]["url"].startswith("https://drive.google.com/file/d/drive-1")
    assert props[nr.A_STATUS]["status"]["name"] == nr.STATUS_DEFAULT
    for name in nr.HUMAN_ONLY:
        assert name not in props
    # 기존 표 행은 그대로
    legacy_rows = fake.rows("legacy-ds")
    assert any("사람이 쓴 피드백" in json.dumps(r, ensure_ascii=False) for r in legacy_rows)
    assert not any(m == "PATCH" and p.startswith("pages/legacy") for m, p, _ in fake.requests)


def test_tidy_selects_only_template_blocks():
    fake = FakeNotion()
    parent = legacy_workspace(fake)
    fake.databases["legacy-db"]["title"] = [{"plain_text": "광고 레퍼런스 기획표"}]
    fake.children[parent] = [
        {"id": "b1", "type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "아래 표에 레퍼런스를 계속 추가해두면, …"}]}},
        {"id": "b2", "type": "table", "table": {}},
        {"id": "b3", "type": "heading_2", "heading_2": {"rich_text": [{"plain_text": "사용 팁"}]}},
        {"id": "keep", "type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "사람이 쓴 메모"}]}},
        {"id": "db", "type": "child_database", "child_database": {"title": "광고 레퍼런스 기획표"}},
    ]
    tidy = nm.plan_tidy(fake, "legacy-db")
    assert [b["id"] for b in tidy["template_blocks"]] == ["b1", "b2", "b3"]
    assert tidy["new_title"] == "(보관) 광고 레퍼런스 기획표"
    fake.patch = lambda path, json=None: fake.requests.append(("PATCH", path, json))
    log = nm.apply_tidy(fake, "legacy-db", tidy, rename=True, trash_template=False)
    assert len(log) == 1
    assert not any(m == "DELETE" for m, _, _ in fake.requests)
