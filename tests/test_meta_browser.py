"""브라우저 수집 결과의 기간·부분 수집·재사용 계약과 자원 정리."""
import copy

import pytest

import a_grade_finder as g
from meta_ad_library import AdLibraryBlocked
from meta_browser_client import BrowserAdLibraryClient
from meta_browser_worker import connections, collect


def result(ads):
    return dict(ads=ads, requests=2, pages_collected=2, has_next_page=True, stop_reason="page_limit")


def client_with_results(monkeypatch, responses):
    client = BrowserAdLibraryClient()
    class Input:
        def write(self, text): pass
        def flush(self): pass
    class Process:
        stdin = Input()
    monkeypatch.setattr(client, "_start", lambda: None)
    client._process = Process()
    for response in responses:
        client._responses.put(copy.deepcopy(response))
    return client


def test_browser_ads_filter_dates_preserve_metadata_and_independent_cache(monkeypatch):
    ads = [{"ad_archive_id": "old", "start_date": "2026-05-01"},
           {"ad_archive_id": "new", "start_date": "2026-09-30"}]
    client = client_with_results(monkeypatch, [result(ads)])
    found = client.search("피지 영양제", started_before="2026-08-08", max_pages=2)
    assert [a["ad_archive_id"] for a in found] == ["old"]
    assert found.pages_collected == 2 and found.incomplete and found.has_next_page
    found[0]["ad_archive_id"] = "edited"
    again = client.search("피지 영양제", started_before="2026-08-08", max_pages=2)
    assert again[0]["ad_archive_id"] == "old" and client.request_count == 2


def test_browser_failure_is_not_an_empty_success_and_is_not_cached(monkeypatch):
    client = client_with_results(monkeypatch, [{"error": "접속 확인 필요"}, result([])])
    with pytest.raises(AdLibraryBlocked, match="접속 확인 필요"):
        client.search("여드름")
    assert client.failed_queries == ["여드름"]
    assert client.last_error["source"] == "browser"
    assert client.search("여드름") == []
    assert client.last_error == {}


def test_empty_direct_account_lookup_searches_name_and_excludes_other_accounts(monkeypatch):
    client = client_with_results(monkeypatch, [result([]), result([
        {"ad_archive_id": "wanted", "page_id": "123", "page_name": "건강 꿀팁"},
        {"ad_archive_id": "other", "page_id": "456", "page_name": "건강 꿀팁 팬"}])])
    client.remember_page("123", "건강 꿀팁")
    ads = client.page_ads("123", max_pages=30)
    assert [ad["ad_archive_id"] for ad in ads] == ["wanted"]
    assert ads.incomplete and ads.stop_reason == "account_name_fallback"


def test_nested_browser_responses_extract_connections():
    conn = {"edges": [], "page_info": {"has_next_page": False}}
    payload = {"data": {"x": [{"ad_library_main": {"search_results_connection": conn}}]}}
    assert list(connections(payload)) == [conn]


def test_browser_start_failure_is_reported_as_connection_error(monkeypatch):
    client = BrowserAdLibraryClient()
    def fail_start():
        raise OSError("cannot start")
    monkeypatch.setattr(client, "_start", fail_start)
    with pytest.raises(AdLibraryBlocked, match="시작하거나 연결하지 못했습니다"):
        client.search("test")
    assert client.failed_queries == ["test"]


def test_failed_keyword_does_not_skip_remaining_keywords():
    class Client:
        request_count = 0
        failed_queries = []
        queries = []
        def search(self, keyword, **kwargs):
            self.queries.append(keyword)
            if keyword == "first":
                raise AdLibraryBlocked("temporary failure")
            return []
    class Resolver:
        def resolve_many(self, urls): pass
        def landing_infos(self, urls): return {}
    client = Client()
    report = g.find_a_grade_ads(g.ScanSettings(scan_keywords=["first", "second", "third"], track_accounts=False),
                              (), client=client, resolver=Resolver(), save=False)
    assert client.queries == ["first", "second", "third"]
    assert report.scan_incomplete
    assert len(report.meta_diagnostics["keywords"]) == 3


def test_browser_keeps_first_screen_if_loading_next_screen_fails():
    class Page:
        first = property(lambda self: self)
        last = property(lambda self: self)
        def on(self, *args): pass
        def remove_listener(self, *args): pass
        def goto(self, *args, **kwargs): return None
        def get_by_text(self, *args): return self
        def wait_for(self, **kwargs): pass
        def wait_for_timeout(self, *args): pass
        def evaluate(self, *args): return [{"ad_archive_id": "kept"}]
        def get_by_role(self, *args, **kwargs): return self
        def count(self): return 1
        def is_visible(self): return True
        def click(self, **kwargs): raise RuntimeError("next screen failed")
    found = collect(Page(), {"query": "test", "max_pages": 3})
    assert found["ads"] == [{"ad_archive_id": "kept"}]
    assert found["stop_reason"] == "browser_error" and found["has_next_page"]
    assert found["warning"] == "next screen failed"


def test_browser_waits_for_cards_that_arrive_after_five_seconds():
    class Page:
        first = property(lambda self: self)
        waits = 0
        def on(self, *args): pass
        def remove_listener(self, *args): pass
        def goto(self, *args, **kwargs): return None
        def get_by_text(self, *args): return self
        def wait_for(self, **kwargs): pass
        def wait_for_timeout(self, delay):
            if delay == 500:
                self.waits += 1
        def evaluate(self, script):
            if script.startswith("window."):
                return None
            ids = ["first", "delayed"] if self.waits >= 12 else ["first"]
            return [{"ad_archive_id": aid} for aid in ids]
        def get_by_role(self, *args, **kwargs): return self
        def count(self): return 0
        def locator(self, *args): return self
        def inner_text(self): return "results"
        def screenshot(self, **kwargs): pass
    found = collect(Page(), {"query": "test", "max_pages": 2})
    assert [ad["ad_archive_id"] for ad in found["ads"]] == ["first", "delayed"]
    assert found["pages_collected"] == 2


def test_interrupted_partial_browser_results_are_not_cached(monkeypatch):
    partial = result([{"ad_archive_id": "one"}])
    partial.update(stop_reason="browser_error", warning="interrupted")
    client = client_with_results(monkeypatch, [partial, result([{"ad_archive_id": "two"}])])
    assert client.search("test")[0]["ad_archive_id"] == "one"
    assert client.last_error["message"] == "interrupted"
    assert client.search("test")[0]["ad_archive_id"] == "two"


@pytest.mark.parametrize("fail", [False, True])
def test_scan_uses_browser_and_closes_on_success_or_interruption(monkeypatch, fail):
    events = []
    class Browser:
        def __init__(self, country): events.append(country)
        def __enter__(self): return self
        def __exit__(self, *args): events.append("closed")
    import meta_browser_client
    monkeypatch.setattr(meta_browser_client, "BrowserAdLibraryClient", Browser)
    def scan(*args):
        assert isinstance(args[3], Browser)
        if fail:
            raise RuntimeError("interrupted")
        return "report"
    monkeypatch.setattr(g, "_find_a_grade_ads", scan)
    if fail:
        with pytest.raises(RuntimeError, match="interrupted"):
            g.find_a_grade_ads(g.ScanSettings(), ())
    else:
        assert g.find_a_grade_ads(g.ScanSettings(), ()) == "report"
    assert events == ["KR", "closed"]
