"""A급 탭 화면 (네트워크·노션 없이 Streamlit AppTest로 확인)"""
import os

import pytest
from streamlit.testing.v1 import AppTest

import a_grade_finder as g
import a_grade_view as v
from factories import make_brand, make_report, make_volume

APP = os.path.join(os.path.dirname(__file__), "apps", "a_grade_app.py")


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
