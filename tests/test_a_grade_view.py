"""A급 탭 화면 (네트워크·노션 없이 Streamlit AppTest로 확인)"""
import os

import pytest
from streamlit.testing.v1 import AppTest

import a_grade_finder as g
import a_grade_view as v
from factories import make_brand, make_report, make_volume

APP = os.path.join(os.path.dirname(__file__), "apps", "a_grade_app.py")


@pytest.fixture(autouse=True)
def isolated_saved_reports(monkeypatch, tmp_path):
    monkeypatch.setattr(v, "_REPORT_DIR", tmp_path)


@pytest.fixture
def report(monkeypatch):
    rocket = make_brand(key="re4day.co.kr", name="리포데이")
    flat = make_brand(key="demaf.kr", name="디마프",
                      volume=make_volume(keyword="디마프", peak=42340, level=g.RISE_FLAT, jump=0, ratio=1.0))
    miss = make_brand(key="orncia.com", name="오르엔시아",
                      volume=make_volume(passed=False, keyword="오르엔시아", peak=100, level=""))
    rep = make_report([flat, miss, rocket])
    monkeypatch.setattr(v, "find_a_grade_ads", lambda settings, creds, progress=None: rep)
    for key in ("NOTION_TOKEN", "NOTION_AD_SOURCE_ID", "NOTION_BRAND_SOURCE_ID"):
        monkeypatch.delenv(key, raising=False)
    return rep


def run_app():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.button(key="ag_run").click().run()
    return at


def test_results_sorted_by_rise_and_show_jump(report):
    at = run_app()
    assert not at.exception
    summary = at.dataframe[0].value
    assert list(summary["브랜드"]) == ["리포데이", "디마프", "오르엔시아"]
    assert summary.iloc[0]["급상승"] == g.RISE_ROCKET
    assert summary.iloc[0]["60일 증가"] == "+7,100 (3.3배)"
    assert summary.iloc[1]["급상승"] == g.RISE_FLAT
    labels = [e.label for e in at.expander]
    assert any("리포데이" in label and g.RISE_ROCKET in label for label in labels)


def test_setup_guide_when_tables_missing(report, monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    at = run_app()
    assert not at.exception
    assert any("notion_references.py setup" in m.value for m in at.markdown)
    assert not any(b.key and b.key.endswith("_save") for b in at.button)


def test_token_form_when_no_token(report):
    at = run_app()
    assert not at.exception
    assert any("노션 연동 설정 필요" in e.label for e in at.expander)


def test_spike_thresholds_flow_into_settings(report, monkeypatch):
    seen = {}

    def fake_find(settings, creds, progress=None):
        seen["settings"] = settings
        return report

    monkeypatch.setattr(v, "find_a_grade_ads", fake_find)
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.number_input(key="ag_spike_jump").set_value(9000)
    at.number_input(key="ag_spike_ratio").set_value(2.5)
    at.button(key="ag_run").click().run()
    assert seen["settings"].spike_min_jump == 9000
    assert seen["settings"].spike_min_ratio == 2.5


def test_keyword_collection_limit_is_independent_from_account_limit(report, monkeypatch):
    seen = {}
    def fake_find(settings, creds, progress=None):
        seen["settings"] = settings
        return report
    monkeypatch.setattr(v, "find_a_grade_ads", fake_find)
    at = AppTest.from_file(APP, default_timeout=60).run()
    keywords = "\n".join(g.DEFAULT_SCAN_KEYWORDS)
    at.text_area(key="ag_scan_keywords").set_value(keywords)
    at.number_input(key="ag_pages").set_value(30)
    at.number_input(key="ag_account_pages").set_value(45)
    at.button(key="ag_run").click().run()
    assert not at.exception
    assert len(seen["settings"].scan_keywords) == 10
    assert seen["settings"].pages_per_keyword == 30
    assert seen["settings"].account_pages == 45


def test_failed_empty_scan_keeps_previous_results(report, monkeypatch):
    at = run_app()
    failed = make_report([])
    failed.scan_incomplete = True
    failed.warnings = ["Rate limit exceeded"]
    failed.meta_requests = 2
    failed.meta_diagnostics = {"source": "web_graphql", "http_status": 200, "codes": [1675004]}
    monkeypatch.setattr(v, "find_a_grade_ads", lambda *args, **kwargs: failed)
    at.button(key="ag_run").click().run()
    assert not at.exception
    assert at.session_state[v._STATE_KEY] is report
    assert len(at.dataframe[0].value) == 3
    assert any("이전 결과" in msg.value for msg in at.info)
    assert any("Rate limit" in msg.value for msg in at.warning)
    assert any("이번 자동 검색 진단" == e.label for e in at.expander)
    assert any("1675004" in msg.value for msg in at.json)
    del failed.meta_diagnostics  # 코드 갱신 전 생성된 세션 결과도 계속 표시됩니다.
    at.checkbox(key="ag_track").uncheck().run()
    assert not at.exception
    assert any("이전 결과" in msg.value for msg in at.info)


def test_successful_empty_scan_does_not_show_stale_brands(report, monkeypatch):
    at = run_app()
    empty = make_report([])
    monkeypatch.setattr(v, "find_a_grade_ads", lambda *args, **kwargs: empty)
    at.button(key="ag_run").click().run()
    assert not at.exception
    assert at.session_state[v._STATE_KEY] is empty
    assert not at.dataframe


def test_saved_results_restore_on_new_session(report, tmp_path):
    g.save_report(report, str(tmp_path / "a_grade_20261001.json"))
    empty = make_report([])
    empty.scan_incomplete = True
    g.save_report(empty, str(tmp_path / "a_grade_20261007.json"))
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert len(at.dataframe[0].value) == 3
    assert at.session_state[v._STATE_KEY].generated_at == report.generated_at
    selected = at.selectbox(key="ag_saved_report")
    selected.select(str(tmp_path / "a_grade_20261007.json"))
    at.button(key="ag_load_report").click().run()
    assert not at.exception
    assert not at.dataframe
    assert any("유지할 새 결과가 없습니다" in msg.value for msg in at.info)
