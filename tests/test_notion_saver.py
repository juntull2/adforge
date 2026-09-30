"""A급 탭 '노션에 기록' — 가짜 노션으로 저장·재저장·기록된 소재 제외를 확인합니다."""
import os

import pytest
from streamlit.testing.v1 import AppTest

import a_grade_finder as g
import a_grade_view as v
import notion_reference_panel as panel
import notion_references as nr
from factories import make_ad, make_brand, make_report
from fake_notion import FakeNotion, legacy_workspace

APP = os.path.join(os.path.dirname(__file__), "apps", "a_grade_app.py")
TOKEN = "ag_notion_2026-09-30T120000"


@pytest.fixture
def notion(monkeypatch):
    fake = FakeNotion()
    legacy_workspace(fake)
    for key in (nr.ENV_PAGE, nr.ENV_BRAND_DB, nr.ENV_BRAND_DS, nr.ENV_AD_DB, nr.ENV_AD_DS, "GOOGLE_DRIVE_FOLDER_URL"):
        monkeypatch.delenv(key, raising=False)
    plan = nr.plan_setup(fake, "legacy-db")
    ids = {}
    nr.apply_setup(fake, plan, env_writer=ids.update)
    for k, val in ids.items():
        monkeypatch.setenv(k, val)
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setattr(panel, "open_store",
                        lambda: nr.ReferenceStore(fake, ids[nr.ENV_BRAND_DS], ids[nr.ENV_AD_DS]).load())
    return fake, ids


def build_report():
    rocket = make_brand(key="re4day.co.kr", name="리포데이", ads=[
        make_ad(ad_id="1", page_name="리포데이", copy="피부과에서 300 쓰기 전에 꼭 보세요"),
        make_ad(ad_id="2", page_id="22", page_name="건강ㅎŁ 삶 되찾ブl", copy="속관리 하루 한 알 루틴 공개합니다"),
    ])
    miss = make_brand(key="orncia.com", name="오르엔시아", ads=[make_ad(ad_id="9", key="orncia.com")])
    miss.volume.passed = False
    g.grade_brand(miss, g.ScanSettings())
    return make_report([rocket, miss])


def open_app(monkeypatch, report):
    monkeypatch.setattr(v, "find_a_grade_ads", lambda settings, creds, progress=None: report)
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.button(key="ag_run").click().run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_save_creates_brand_and_ads_without_human_columns(notion, monkeypatch):
    fake, ids = notion
    report = build_report()
    at = open_app(monkeypatch, report)
    at.button(key=f"{TOKEN}_save").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("새로 2개" in s.value for s in at.success)
    ads = fake.rows(ids[nr.ENV_AD_DS])
    brands = fake.rows(ids[nr.ENV_BRAND_DS])
    assert len(ads) == 2 and len(brands) == 1      # A급 브랜드만 · 미달 브랜드 광고는 저장 안 함
    types = sorted(p["properties"][nr.A_ACCOUNT_TYPE]["select"]["name"] for p in ads)
    assert types == ["공식 계정", "위장 계정"]
    assert all(p["properties"][nr.A_BRAND]["relation"][0]["id"] == brands[0]["id"] for p in ads)
    for _, names in fake.written_properties():
        assert not names & set(nr.HUMAN_ONLY)


def test_recorded_ads_hidden_on_next_search_and_resave_updates(notion, monkeypatch):
    fake, ids = notion
    first = build_report()
    at = open_app(monkeypatch, first)
    at.button(key=f"{TOKEN}_save").click().run()

    # 다시 탐색 (같은 광고가 다시 나옴)
    second = build_report()
    at = open_app(monkeypatch, second)
    assert all(a.recorded for a in second.a_grade_brands[0].ads)
    summary = at.dataframe[0].value
    assert summary.iloc[0]["광고 수"] == "새 소재 0 (노션 2)"
    assert [b.name for b in second.brands] == ["리포데이", "오르엔시아"]     # 순위·판정은 그대로
    assert any("노션에 새로 기록할 A급 소재가 없습니다" in i.value for i in at.info)

    # 노션에 있는 소재도 보기 → 다시 저장하면 갱신만
    at.checkbox(key=f"{TOKEN}_show_recorded").check().run()
    fake.requests.clear()
    # 기록된 소재는 기본으로 선택되지 않음 → 저장해도 아무것도 쓰지 않음
    at.button(key=f"{TOKEN}_save").click().run()
    assert any("선택된 항목이 없습니다" in w.value for w in at.warning)
    assert not fake.written_properties()
    # 전체 선택 후 저장하면 갱신만
    at.button(key=f"{TOKEN}_all").click().run()
    at.button(key=f"{TOKEN}_save").click().run()
    assert not at.exception
    assert len(fake.rows(ids[nr.ENV_AD_DS])) == 2
    patches = [names for method, names in fake.written_properties() if method == "PATCH"]
    posts = [names for method, names in fake.written_properties() if method == "POST"]
    assert patches and not posts
    for names in patches:
        assert not names & set(nr.HUMAN_ONLY)
        assert not names & set(nr.AD_CREATE_ONLY)


def test_same_video_on_other_page_is_treated_as_recorded(notion, monkeypatch):
    fake, ids = notion
    first = build_report()
    first.a_grade_brands[0].ads[0].video_asset_id = "asset-77"
    at = open_app(monkeypatch, first)
    at.button(key=f"{TOKEN}_save").click().run()

    second = make_report([make_brand(key="re4day.co.kr", name="리포데이", ads=[
        make_ad(ad_id="500", page_id="99", page_name="ㅈ6수ㅁй직", copy="전혀 다른 문구의 새 광고입니다", video_asset_id="asset-77"),
        make_ad(ad_id="501", page_id="98", page_name="진시황의 비밀", copy="이건 처음 보는 광고 문구입니다"),
    ])])
    open_app(monkeypatch, second)
    ads = second.a_grade_brands[0].ads
    assert ads[0].recorded == "같은 영상"
    assert ads[1].recorded == ""
