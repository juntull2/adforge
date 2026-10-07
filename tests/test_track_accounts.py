"""연결 계정 추적: 찾은 숨은 계정의 이름·광고 문구로 다시 검색 (가짜 메타 클라이언트)"""
import copy
import time
from datetime import datetime, timedelta

import pytest

import a_grade_finder as g
from factories import make_ad, make_brand

TARGET = "https://www.re4day.co.kr/goods/1"
OTHER = "https://other-brand.example.com/p/1"


def raw_ad(ad_id, page_id, page_name, link=TARGET, body="여드름 속관리 하루 한 알 루틴 공개합니다", days=90):
    ad = {"snapshot": {}}
    ad.update(ad_archive_id=ad_id, collation_id=f"c-{ad_id}", page_id=page_id, page_name=page_name,
              start_date=int(time.mktime((datetime.now() - timedelta(days=days)).timetuple())))
    ad["snapshot"].update(link_url=link, caption="", body={"text": body}, page_id=page_id, page_name=page_name)
    ad["snapshot"]["videos"] = []
    return ad


class FakeMeta:
    def __init__(self, searches, pages):
        self.searches = searches          # 검색어 → [광고]
        self.pages = pages                # page_id → [광고]
        self.queries = []
        self.page_calls = []
        self.request_count = 0
        self.failed_queries = []

    def search(self, query, search_type="keyword_unordered", active_status="active", started_before=None, max_pages=3):
        self.queries.append((query, search_type))
        return copy.deepcopy(self.searches.get(query, []))

    def page_ads(self, page_id, active_status="active", max_pages=1):
        self.page_calls.append(page_id)
        return copy.deepcopy(self.pages.get(page_id, []))


@pytest.fixture
def brand():
    return make_brand(key="re4day.co.kr", name="리포데이", ads=[make_ad(ad_id="seed", page_id="p-official",
                                                                        page_name="리포데이", key="re4day.co.kr")])


def world():
    hidden1 = raw_ad("a1", "p-h1", "건강ㅎŁ 삶 되찾ブl", body="피부과 300 쓰기 전에 꼭 보세요 진짜로")
    hidden2 = raw_ad("a2", "p-h2", "행복한 일상 클리닉", body="이 문구는 두 번째 숨은 계정이 쓰는 문구입니다")
    hidden3 = raw_ad("a3", "p-h3", "دوکان سلامت", body="세 번째 단계에서만 나오는 아랍어 계정 광고")
    decoy = raw_ad("x1", "p-decoy", "건강ㅎŁ 삶 되찾ブl 팬", link=OTHER)
    official2 = raw_ad("o2", "p-official2", "리포데이 공식몰")
    searches = {
        "re4day.co.kr": [hidden1, official2],
        # 숨은 계정 이름으로 검색하면 또 다른 숨은 계정이 나옴 (다른 브랜드 랜딩 광고는 무시)
        "건강ㅎŁ 삶 되찾ブl": [hidden1, hidden2, decoy],
        # 두 번째 숨은 계정의 광고 문구로 검색하면 아랍어 계정이 나옴
        "이 문구는 두 번째 숨은 계정이 쓰는 문구입니다": [hidden2, hidden3],
        "리포데이 공식몰": [raw_ad("never", "p-never", "공식 이름 검색으로만 나오는 계정")],
    }
    pages = {"p-h1": [hidden1], "p-h2": [hidden2], "p-h3": [hidden3], "p-official2": [official2], "p-decoy": [decoy]}
    return FakeMeta(searches, pages)


def test_hidden_account_names_and_copy_are_searched_again(brand):
    meta = world()
    accounts = g.track_brand_accounts(meta, g.LinkResolver(), brand, g.ScanSettings())
    by_name = {a.page_name: a for a in accounts}

    assert ("건강ㅎŁ 삶 되찾ブl", "keyword_unordered") in meta.queries
    assert by_name["건강ㅎŁ 삶 되찾ブl"].depth == 0
    assert by_name["건강ㅎŁ 삶 되찾ブl"].found_via.startswith("도메인")

    h2 = by_name["행복한 일상 클리닉"]
    assert h2.depth == 1 and h2.confidence == g.CONFIRMED
    assert h2.found_via == "위장 계정 '건강ㅎŁ 삶 되찾ブl' 이름"

    h3 = by_name["دوکان سلامت"]
    assert h3.depth == 2 and h3.account_type == g.ACCOUNT_ARABIC
    assert "광고 문구" in h3.found_via and "행복한 일상 클리닉" in h3.found_via

    # 다른 브랜드 랜딩으로 가는 광고의 페이지는 연결 계정이 아님
    assert "건강ㅎŁ 삶 되찾ブl 팬" not in by_name
    # 공식 계정도 이름으로 검색해 추가 연결 계정을 찾습니다.
    assert ("리포데이 공식몰", "keyword_unordered") in meta.queries
    assert "공식 이름 검색으로만 나오는 계정" in by_name
    # 같은 검색은 한 번만
    assert len(meta.queries) == len(set(meta.queries))


def test_rounds_and_budget_limit(brand, monkeypatch):
    monkeypatch.setattr(g, "MAX_TRACK_ROUNDS", 1)
    accounts = g.track_brand_accounts(world(), g.LinkResolver(), brand, g.ScanSettings())
    names = {a.page_name for a in accounts}
    assert "행복한 일상 클리닉" in names
    assert "دوکان سلامت" not in names          # 2단계는 넘지 않음

    monkeypatch.setattr(g, "MAX_TRACK_ROUNDS", 3)
    monkeypatch.setattr(g, "MAX_EXPAND_QUERIES", 0)
    meta = world()
    accounts = g.track_brand_accounts(meta, g.LinkResolver(), brand, g.ScanSettings())
    assert all(a.depth == 0 for a in accounts)
    assert ("건강ㅎŁ 삶 되찾ブl", "keyword_unordered") not in meta.queries


def test_account_name_search_uses_configured_collection_limit(brand):
    meta = world()
    original = meta.search
    limits = {}
    def search(query, **kwargs):
        limits[query] = kwargs["max_pages"]
        return original(query, **kwargs)
    meta.search = search
    g.track_brand_accounts(meta, g.LinkResolver(), brand,
                           g.ScanSettings(pages_per_keyword=7, account_pages=30))
    assert limits["re4day.co.kr"] == 7
    assert limits["건강ㅎŁ 삶 되찾ブl"] == 30
    assert limits["리포데이 공식몰"] == 30


def test_brand_terms_exclude_page_name_keywords():
    brand = make_brand(key="oliveyoung.co.kr/p/A1", name="닥터지")
    brand.keywords = ["오늘의 팁", "닥터지"]
    brand.volume.keyword = "닥터지"
    assert g.classify_page_name("오늘의 팁", g._brand_terms(brand))[0] == g.ACCOUNT_HIDDEN
    assert g.classify_page_name("닥터지 공식", g._brand_terms(brand))[0] == g.ACCOUNT_OFFICIAL


class BlockedMeta(FakeMeta):
    """검색이 모두 실패하는 메타 (차단 상황)"""

    def search(self, query, search_type="keyword_unordered", active_status="active", started_before=None, max_pages=3):
        self.failed_queries.append(f"{search_type}:{query}")
        return []

    def page_ads(self, page_id, active_status="active", max_pages=1):
        self.failed_queries.append(f"page:{page_id}")
        return []


def test_failed_searches_keep_previously_found_accounts(brand):
    g.track_brand(brand, g.ScanSettings(), client=world(), resolver=g.LinkResolver())
    before = {a.page_id for a in brand.accounts}
    assert len(before) >= 4 and brand.tracking_failed == 0

    g.track_brand(brand, g.ScanSettings(), client=BlockedMeta({}, {}), resolver=g.LinkResolver())
    assert {a.page_id for a in brand.accounts} == before
    assert brand.tracking_failed > 0
    assert "이전에 찾은 계정 유지" in brand.tracking_note


def test_for_is_materials_are_merged_beyond_preview_and_retracking_is_idempotent():
    brand = make_brand(key="i-hi.co.kr", name="아이하이", ads=[make_ad(ad_id="seed", key="i-hi.co.kr")])
    ads = [raw_ad(str(i), "177441688795472", "For is", link="https://i-hi.co.kr/p",
                  body=f"여드름 영양제 후기 {i}") for i in range(8)]
    ads += [raw_ad("short", "177441688795472", "For is", link="https://i-hi.co.kr/p", days=10),
            raw_ad("irrelevant", "177441688795472", "For is", link="https://i-hi.co.kr/p", body="키 성장"),
            raw_ad("excluded", "177441688795472", "For is", link="https://i-hi.co.kr/p", body="강아지 영양제"),
            raw_ad("other", "177441688795472", "For is", link=OTHER)]
    class DeepMeta(FakeMeta):
        def page_ads(self, page_id, active_status="active", max_pages=1):
            assert max_pages == 20
            return super().page_ads(page_id, active_status, max_pages)
    meta = DeepMeta({"i-hi.co.kr": ads[:1]}, {"177441688795472": ads})
    g.track_brand(brand, g.ScanSettings(), client=meta, resolver=g.LinkResolver())
    assert {a.ad_id for a in brand.ads} == {"seed"} | {str(i) for i in range(8)}
    assert all(a.relevance for a in brand.ads)
    assert len(next(a for a in brand.accounts if a.page_name == "For is").sample_ads) == 5
    from a_grade_view import _export_ads, _visible_ads
    from notion_reference_panel import saver_rows
    from factories import make_report
    report = make_report([brand])
    assert len(_visible_ads(brand, False)) == 9
    assert len(_export_ads(report)) == 9
    assert len(saver_rows(report, False)) == 9
    before = [(a.ad_id, a.variants) for a in brand.ads]
    g.track_brand(brand, g.ScanSettings(), client=meta, resolver=g.LinkResolver())
    assert [(a.ad_id, a.variants) for a in brand.ads] == before


def test_interrupted_tracking_keeps_new_accounts_and_materials(brand):
    ad = raw_ad("new", "p-new", "For is")
    class Interrupted(FakeMeta):
        def page_ads(self, *args, **kwargs):
            raise g.AdLibraryBlocked("blocked")
    meta = Interrupted({"re4day.co.kr": [ad]}, {})
    g.track_brand(brand, g.ScanSettings(), client=meta, resolver=g.LinkResolver())
    assert "new" in {a.ad_id for a in brand.ads}
    assert "p-new" in {a.page_id for a in brand.accounts}
    assert brand.tracking_failed and brand.tracking_incomplete


def test_collation_variants_are_merged_without_double_counting(brand):
    ads = [raw_ad(str(i), "p-h", "For is", days=90+i) for i in range(3)]
    for ad in ads:
        ad["collation_id"] = "shared"
    meta = FakeMeta({"re4day.co.kr": ads}, {"p-h": ads})
    for _ in range(2):
        g.track_brand(brand, g.ScanSettings(), client=meta, resolver=g.LinkResolver())
        material = [a for a in brand.ads if a.collation_id == "shared"]
        assert len(material) == 1 and material[0].ad_id == "2" and material[0].variants == 3


@pytest.mark.parametrize("page_limit", [1, 20])
def test_real_client_second_page_reaches_material_list(brand, page_limit):
    import meta_ad_library as m
    brand = make_brand(key="i-hi.co.kr", name="아이하이", ads=[make_ad(ad_id="seed", key="i-hi.co.kr")])
    first = raw_ad("1015790094846837", "177441688795472", "For is", days=132,
                   link="https://i-hi.co.kr/p",
                   body="요즘 엄마들 사이에서 아이그램 유산균 얘기 진짜 많이 나오더라구요")
    second = raw_ad("955367360732844", "177441688795472", "For is", days=132,
                    link="https://i-hi.co.kr/p",
                    body="국내 유일! 특허 항비만 유산균으로 설계된")
    client = m.AdLibraryClient(min_interval=0)
    client.search = lambda *args, **kwargs: [first]
    def post(v):
        if v["viewAllPageID"] != "177441688795472":
            return {"edges": [], "page_info": {"has_next_page": False}}
        next_page = v["cursor"] is None
        return {"edges": [{"node": {"collated_results": [first if next_page else second]}}],
                "page_info": {"has_next_page": next_page, "end_cursor": "next" if next_page else None}}
    client._post = post
    g.track_brand(brand, g.ScanSettings(account_pages=page_limit), client=client, resolver=g.LinkResolver())
    ids = {a.ad_id for a in brand.ads}
    assert first["ad_archive_id"] in ids
    assert (second["ad_archive_id"] in ids) == (page_limit == 20)
    assert brand.tracking_incomplete == (page_limit == 1)
    if page_limit == 1:
        assert "페이지 제한" in brand.tracking_note


def test_old_settings_use_twenty_account_pages():
    assert g.ScanSettings.from_dict({"pages_per_keyword": 3}).account_pages == 20
