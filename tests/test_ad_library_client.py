"""메타 클라이언트: 실패가 이어지면 멈추고, 성공하면 다시 셉니다 (네트워크 없이 _post를 바꿔 끼움)."""
import pytest

import meta_ad_library as m

OK = {"edges": [{"node": {"collated_results": [{"ad_archive_id": "1"}]}}], "page_info": {"has_next_page": False}}


def make_client(results, monkeypatch):
    sleeps = []
    monkeypatch.setattr(m.time, "sleep", sleeps.append)
    client = m.AdLibraryClient(min_interval=0, retry_wait=5, max_consecutive_failures=3)
    queue = list(results)

    def fake_post(variables):
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    client._post = fake_post
    return client, sleeps


def test_retry_once_with_backoff_then_success(monkeypatch):
    client, sleeps = make_client([None, OK], monkeypatch)
    assert [a["ad_archive_id"] for a in client.search("x")] == ["1"]
    assert sleeps == [5] and client.failed_queries == []


def test_circuit_breaker_after_consecutive_failures(monkeypatch):
    blocked = m.AdLibraryBlocked("no token")
    client, sleeps = make_client([None, None, blocked, None, None, blocked], monkeypatch)
    assert client.search("a") == []
    assert client.search("b") == []
    with pytest.raises(m.AdLibraryBlocked):
        client.search("c")
    assert client.failed_queries == ["keyword_unordered:a", "keyword_unordered:b", "keyword_unordered:c"]
    assert sleeps == [5, 10, 15]      # 실패가 이어질수록 더 오래 쉼


def test_success_resets_failure_count(monkeypatch):
    client, _ = make_client([None, None, OK, None, None, None, None], monkeypatch)
    client.search("a")
    client.search("b")
    client.search("c")
    client.search("d")      # b 성공으로 다시 세기 때문에 c·d 연속 실패(2회)로는 멈추지 않음
    assert client.failed_queries == ["keyword_unordered:a", "keyword_unordered:c", "keyword_unordered:d"]


class FakeResponse:
    status_code = 200

    def __init__(self, text):
        self.text = text


class FakeSession:
    def __init__(self, text):
        self.text = text
        self.posts = 0

    def post(self, url, data=None, headers=None, timeout=None):
        self.posts += 1
        return FakeResponse(self.text)


def test_rate_limit_stops_immediately_without_retry(monkeypatch):
    sleeps = []
    monkeypatch.setattr(m.time, "sleep", sleeps.append)
    client = m.AdLibraryClient(min_interval=0)
    client._lsd, client._referer = "token", "ref"
    client._sess = FakeSession('{"errors":[{"message":"Rate limit exceeded","severity":"CRITICAL","code":1675004}]}')
    with pytest.raises(m.AdLibraryRateLimited):
        client.search("re4day.co.kr")
    assert client._sess.posts == 1 and sleeps == []          # 다시 시도하지 않음
    assert client.rate_limited and client.failed_queries == ["keyword_unordered:re4day.co.kr"]
    assert client.last_error == {"source": "web_graphql", "http_status": 200, "codes": [1675004]}
    with pytest.raises(m.AdLibraryRateLimited):
        client.page_ads("123")
    assert client._sess.posts == 1                           # 한도 초과 뒤에는 요청 자체를 보내지 않음


def test_page_pagination_and_limit_metadata(monkeypatch):
    first = {"edges": OK["edges"], "page_info": {"has_next_page": True, "end_cursor": "next"}}
    client, _ = make_client([first, OK], monkeypatch)
    variables = []
    original = client._post
    def post(v):
        variables.append(v)
        return original(v)
    client._post = post
    result = client.page_ads("123", max_pages=20)
    assert len(result) == 2 and not result.incomplete
    assert variables[1]["cursor"] == "next"
    client, _ = make_client([first], monkeypatch)
    result = client.page_ads("123", max_pages=1)
    assert result.incomplete and result.has_next_page and result.stop_reason == "page_limit"


def test_partial_page_results_survive_rate_limit_and_failure(monkeypatch):
    first = {"edges": OK["edges"], "page_info": {"has_next_page": True, "end_cursor": "next"}}
    for failure in ([m.AdLibraryRateLimited("limited")], [None, None]):
        client, _ = make_client([first] + failure, monkeypatch)
        result = client.page_ads("123", max_pages=20)
        assert len(result) == 1 and result.incomplete and result.stop_reason


def test_bootstrap_uses_home_and_real_session_metadata(monkeypatch):
    calls = []
    session = object()
    monkeypatch.setattr(m, "_make_session", lambda: session)
    def get_page(sess, url, max_retry):
        calls.append((sess, url, max_retry))
        return FakeResponse('"LSD",[],{"token":"real-token"},"__spin_r":123,"__spin_t":456,"__spin_b":"trunk","hsi":"789"')
    monkeypatch.setattr(m, "_get_page", get_page)
    client = m.AdLibraryClient(min_interval=0)
    client._connect()
    assert calls == [(session, "https://www.facebook.com/", 1)]
    assert client._lsd == "real-token" and client.request_count == 1
    assert client._session_fields == {"__spin_r": "123", "__rev": "123", "__spin_t": "456", "__spin_b": "trunk", "__hsi": "789"}


def test_unrelated_token_cannot_be_used_as_lsd():
    assert m._extract_lsd('{"token":"unrelated-token"}') == ""
    assert m._extract_lsd('<input name="lsd" value="real-token">') == "real-token"


def test_http_429_does_not_trigger_session_retry(monkeypatch):
    sleeps = []
    monkeypatch.setattr(m.time, "sleep", sleeps.append)
    response = FakeResponse("")
    response.status_code = 429
    class Session:
        posts = 0
        def post(self, *args, **kwargs):
            self.posts += 1
            return response
    client = m.AdLibraryClient(min_interval=0)
    client._lsd = "token"
    client._sess = Session()
    with pytest.raises(m.AdLibraryRateLimited):
        client.search("x")
    assert client._sess.posts == 1 and not sleeps and client.rate_limited
    assert client.last_error == {"source": "web_graphql", "http_status": 429, "codes": []}


def test_repeated_account_queries_use_independent_cached_results(monkeypatch):
    client, _ = make_client([OK], monkeypatch)
    first = client.page_ads("123")
    first[0]["ad_archive_id"] = "modified"
    second = client.page_ads("123")
    assert second[0]["ad_archive_id"] == "1"
    assert second.pages_collected == 1 and not second.incomplete


def test_failed_results_are_not_cached(monkeypatch):
    client, _ = make_client([None, None, OK], monkeypatch)
    assert client.search("x").stop_reason == "failed"
    assert len(client.search("x")) == 1
