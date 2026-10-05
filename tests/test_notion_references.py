import json
import os
from datetime import date

import pytest

import a_grade_finder as g
import notion_references as nr
from notion_sync import NotionError
from factories import make_ad, make_brand
from fake_notion import FakeNotion, legacy_workspace

TODAY = date(2026, 9, 30)
ENV_KEYS = (nr.ENV_PAGE, nr.ENV_BRAND_DB, nr.ENV_BRAND_DS, nr.ENV_AD_DB, nr.ENV_AD_DS)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def setup_workspace(fake):
    legacy_workspace(fake)
    saved = {}

    def writer(values):
        saved.update(values)
        os.environ.update(values)

    plan = nr.plan_setup(fake, "legacy-db")
    log = nr.apply_setup(fake, plan, env_writer=writer)
    return plan, log, saved


# ── 스키마 ────────────────────────────────────────────────

def test_ad_schema_has_human_columns_and_valid_formula():
    schema = nr.ad_schema("brand-ds", {"소재링크": "rich_text", "편집일": "date", "대표님 피드백": "rich_text"})
    for name in nr.HUMAN_ONLY:
        assert name in schema
    assert schema[nr.H_EDITED] == {"date": {}}
    assert f'prop("{nr.A_START}")' in schema[nr.A_DAYS]["formula"]["expression"]
    assert nr.A_START in schema
    groups = {o["group"] for o in schema[nr.A_STATUS]["status"]["options"]}
    assert groups <= {"To-do", "In progress", "Complete"}
    assert schema[nr.A_BRAND]["relation"]["data_source_id"] == "brand-ds"


def test_human_schema_falls_back_to_defaults():
    assert nr.human_schema({"소재링크": "formula"})[nr.H_MATERIAL] == {"url": {}}
    assert nr.human_schema({})[nr.H_EDITED] == {"date": {}}


def test_rollup_points_at_existing_columns():
    rollup = nr.rollup_schema()[nr.B_MAX_DAYS]["rollup"]
    assert rollup["relation_property_name"] == nr.B_ADS
    assert rollup["rollup_property_name"] == nr.A_DAYS
    assert nr.A_DAYS in nr.ad_schema("x", {})


# ── setup ────────────────────────────────────────────────

def test_plan_is_read_only_and_lists_steps():
    fake = FakeNotion()
    legacy_workspace(fake, {"소재링크": "rich_text", "편집일": "date", "대표님 피드백": "rich_text"})
    plan = nr.plan_setup(fake, "legacy-db")
    assert not plan.problems
    assert plan.parent_page_id == "parent-page"
    assert plan.human_types[nr.H_MATERIAL] == "rich_text"
    assert all(method in ("GET", "CHILDREN", "QUERY") for method, _, _ in fake.requests)
    text = nr.format_plan(plan)
    assert nr.PAGE_TITLE in text and "제작 영상 링크(rich_text)" in text


def test_plan_stops_on_duplicate_page():
    fake = FakeNotion()
    parent = legacy_workspace(fake)
    fake.children[parent].append({"id": "old", "type": "child_page", "child_page": {"title": nr.PAGE_TITLE}})
    plan = nr.plan_setup(fake, "legacy-db")
    assert plan.problems
    with pytest.raises(RuntimeError):
        nr.apply_setup(fake, plan, env_writer=lambda v: None)


def test_apply_creates_page_tables_relation_rollup_views():
    fake = FakeNotion()
    plan, log, saved = setup_workspace(fake)
    assert set(saved) == set(ENV_KEYS)
    brand_props = fake.sources[saved[nr.ENV_BRAND_DS]]["properties"]
    ad_props = fake.sources[saved[nr.ENV_AD_DS]]["properties"]
    assert nr.B_ADS in brand_props and brand_props[nr.B_ADS]["type"] == "relation"
    assert nr.B_MAX_DAYS in brand_props
    assert ad_props[nr.A_STATUS]["type"] == "status"
    for name in nr.HUMAN_ONLY:
        assert name in ad_props
    assert fake.views == []  # 기본 보기만 사용; 추가 탭 없음
    # 기존 DB에는 쓰지 않음
    assert not any(path.startswith(("databases/legacy", "data_sources/legacy")) for m, path, _ in fake.requests
                   if m in ("PATCH", "POST"))


def test_apply_falls_back_to_select_status():
    fake = FakeNotion()
    legacy_workspace(fake)
    plan = nr.plan_setup(fake, "legacy-db")
    original_post = fake.post
    calls = {"n": 0}

    def post(path, json=None):
        if path == "databases" and nr.A_STATUS in json["initial_data_source"]["properties"]:
            calls["n"] += 1
            if calls["n"] == 1:
                raise NotionError(400, "validation_error", "status options invalid")
        return original_post(path, json)

    fake.post = post
    log = nr.apply_setup(fake, plan, env_writer=lambda v: os.environ.update(v))
    ad_props = fake.sources[os.environ[nr.ENV_AD_DS]]["properties"]
    assert ad_props[nr.A_STATUS]["type"] == "select"
    assert any("선택 칸" in line for line in log)


def test_second_setup_has_nothing_to_do():
    fake = FakeNotion()
    setup_workspace(fake)
    plan = nr.plan_setup(fake, "legacy-db")
    assert "이미 설정" in plan.steps[0]


# ── 저장 (있으면 갱신) + 칸 소유 ────────────────────────────

def make_store(fake):
    return nr.ReferenceStore(fake, os.environ[nr.ENV_BRAND_DS], os.environ[nr.ENV_AD_DS]).load()


def test_upsert_twice_keeps_one_row_and_never_writes_human_columns():
    fake = FakeNotion()
    setup_workspace(fake)
    brand = make_brand()
    ad = brand.ads[0]
    ad.collation_id, ad.video_asset_id, ad.fingerprint = "col-1", "asset-1", "피부과에서300쓰기전에"

    store = make_store(fake)
    bid, created_b = store.upsert_brand(brand, TODAY)
    aid, created_a = store.upsert_ad(ad, brand, bid, account_type="공식 계정", title="첫 제목", status="진행",
                                     video_link="https://drive.google.com/file/1")
    assert created_b and created_a

    # 사람이 노션에서 칸을 채움
    fake.pages[aid]["properties"]["대표님 피드백"] = {"type": "rich_text", "rich_text": [{"plain_text": "좋아요"}]}
    fake.pages[aid]["properties"][nr.H_EDITED] = {"type": "date", "date": {"start": "2026-10-01"}}
    fake.pages[aid]["properties"][nr.H_MATERIAL] = {"type": "rich_text", "rich_text": [{"plain_text": "https://my-video.example/edited"}]}
    fake.pages[aid]["properties"][nr.A_TITLE] = {"type": "title", "title": [{"plain_text": "사람이 고친 제목"}]}

    store2 = make_store(fake)
    bid2, created_b2 = store2.upsert_brand(brand, TODAY)
    aid2, created_a2 = store2.upsert_ad(ad, brand, bid2, account_type="공식 계정", title="새 제목", status="완료",
                                        video_link="https://facebook.example/v.mp4")
    assert (bid2, aid2) == (bid, aid) and not created_b2 and not created_a2
    assert len(fake.rows(os.environ[nr.ENV_AD_DS])) == 1
    assert len(fake.rows(os.environ[nr.ENV_BRAND_DS])) == 1

    for _, names in fake.written_properties():
        assert not names & nr.HUMAN_PROTECTED, names
    page = fake.pages[aid]["properties"]
    assert page["대표님 피드백"]["rich_text"][0]["plain_text"] == "좋아요"
    assert page[nr.H_EDITED]["date"]["start"] == "2026-10-01"
    assert page[nr.H_MATERIAL]["rich_text"][0]["plain_text"] == "https://my-video.example/edited"
    assert page[nr.A_TITLE]["title"][0]["plain_text"] == "사람이 고친 제목"
    assert page[nr.A_STATUS]["status"]["name"] == "진행"
    assert page[nr.A_VIDEO]["url"] == "https://drive.google.com/file/1"


def test_strip_human_protects_current_and_legacy_names():
    props = {name: {"rich_text": []} for name in nr.HUMAN_PROTECTED}
    props[nr.A_TITLE] = {"title": []}
    assert nr.strip_human(props) == {nr.A_TITLE: {"title": []}}


def test_update_request_has_no_create_only_columns():
    fake = FakeNotion()
    setup_workspace(fake)
    brand = make_brand()
    store = make_store(fake)
    bid, _ = store.upsert_brand(brand, TODAY)
    store.upsert_ad(brand.ads[0], brand, bid)
    fake.requests.clear()
    store.upsert_ad(brand.ads[0], brand, bid, title="x", status="완료", appeals=["시술대체"])
    store.upsert_brand(brand, TODAY)
    patches = [names for method, names in fake.written_properties() if method == "PATCH"]
    assert patches
    ad_patch = next(names for names in patches if nr.A_AD_ID in names)
    assert not ad_patch & set(nr.AD_CREATE_ONLY)
    brand_patch = next(names for names in patches if nr.B_KEY in names)
    assert nr.B_TITLE not in brand_patch


def test_auto_block_replaced_in_place_other_blocks_untouched():
    fake = FakeNotion()
    setup_workspace(fake)
    brand = make_brand()
    store = make_store(fake)
    bid, _ = store.upsert_brand(brand, TODAY)
    # 사람이 본문 위·아래에 메모
    fake.children[bid].insert(0, {"id": "memo-top", "type": "paragraph",
                                  "paragraph": {"rich_text": [{"plain_text": "위 메모"}]}})
    fake.children[bid].append({"id": "memo-bottom", "type": "paragraph",
                               "paragraph": {"rich_text": [{"plain_text": "아래 메모"}]}})
    brand.volume.peak_volume = 99999
    store.upsert_brand(brand, TODAY)
    live = [b for b in fake.children[bid] if not b.get("in_trash")]
    assert [b["id"] for b in live][0] == "memo-top"
    assert [b["id"] for b in live][-1] == "memo-bottom"
    autos = [b for b in live if b["type"] == "callout"]
    assert len(autos) == 1
    assert "99,999" in json.dumps(autos[0], ensure_ascii=False)
    deleted = [path for method, path, _ in fake.requests if method == "DELETE"]
    assert len(deleted) == 1   # 옛 자동 기록 박스만 휴지통으로


def test_brand_properties_values():
    brand = make_brand()
    brand.audience = {"ok": True, "gender": {"여성": 48.8, "남성": 51.2}, "target_4050": 56.3}
    props = nr.brand_properties(brand, TODAY, create=True)
    assert props[nr.B_RISE] == {"select": {"name": g.RISE_ROCKET}}
    assert props[nr.B_JUMP] == {"number": 7100}
    assert props[nr.B_FEMALE] == {"number": 48.8}
    assert props[nr.B_MALL] == {"url": "https://re4day.co.kr"}
    assert props[nr.B_ACCOUNTS] == {"number": None}      # 추적 전
    no_rise = make_brand(volume=None)
    no_rise.volume = g.VolumeCheck(passed=True, keyword="x", peak_volume=12000)
    assert nr.brand_properties(no_rise, TODAY, create=False)[nr.B_RISE] == {"select": None}


def test_blank_values_become_null():
    ad = make_ad(landing_url="", library_url="")
    brand = make_brand(ads=[ad])
    props = nr.ad_properties(ad, brand, "b1", create=True)
    assert props[nr.A_LANDING] == {"url": None}
    assert props[nr.A_COLLATION] == {"rich_text": []}
    assert nr.p_multi(["a,b", "A,B", ""]) == {"multi_select": [{"name": "a b"}]}


def test_recorded_keys_from_store():
    fake = FakeNotion()
    setup_workspace(fake)
    brand = make_brand()
    ad = brand.ads[0]
    ad.collation_id, ad.video_asset_id, ad.fingerprint = "col-1", "asset-1", "피부과에서300쓰기전에"
    store = make_store(fake)
    bid, _ = store.upsert_brand(brand, TODAY)
    store.upsert_ad(ad, brand, bid)
    keys = make_store(fake).recorded_keys()
    assert keys.ad_ids == {ad.ad_id}
    assert keys.collation_ids == {"col-1"} and keys.asset_ids == {"asset-1"}
    assert keys.fingerprints == {("re4day.co.kr", "피부과에서300쓰기전에")}


def test_store_requires_setup(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    with pytest.raises(RuntimeError):
        nr.ReferenceStore.from_env()
