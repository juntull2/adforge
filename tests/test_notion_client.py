import json as jsonlib

import pytest
import requests

from notion_sync import NOTION_API_VERSION, NotionClient, NotionError, blank_to_none


class FakeResponse:
    def __init__(self, status=200, data=None, headers=None):
        self.status_code = status
        self._data = data if data is not None else {}
        self.headers = headers or {}
        self.content = jsonlib.dumps(self._data).encode()
        self.text = self.content.decode()

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, headers=None, json=None, params=None, timeout=None):
        self.calls.append({"method": method, "url": url, "headers": headers, "json": json, "params": params})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_client(responses):
    session = FakeSession(responses)
    sleeps = []
    client = NotionClient("secret", session=session, sleep=sleeps.append, min_interval=0)
    return client, session, sleeps


def test_uses_new_api_version():
    assert NOTION_API_VERSION == "2026-03-11"
    client, session, _ = make_client([FakeResponse(data={"ok": 1})])
    client.get("users/me")
    assert session.calls[0]["headers"]["Notion-Version"] == "2026-03-11"
    assert session.calls[0]["url"] == "https://api.notion.com/v1/users/me"


def test_paginate_post_follows_cursor():
    client, session, _ = make_client([
        FakeResponse(data={"results": [1, 2], "has_more": True, "next_cursor": "c1"}),
        FakeResponse(data={"results": [3], "has_more": False, "next_cursor": None}),
    ])
    rows = client.query_data_source("ds", filter={"property": "x"})
    assert rows == [1, 2, 3]
    assert "start_cursor" not in session.calls[0]["json"]
    assert session.calls[1]["json"]["start_cursor"] == "c1"
    assert session.calls[1]["json"]["filter"] == {"property": "x"}


def test_paginate_get_uses_params():
    client, session, _ = make_client([
        FakeResponse(data={"results": ["a"], "has_more": True, "next_cursor": "n"}),
        FakeResponse(data={"results": ["b"], "has_more": False}),
    ])
    assert client.block_children("blk") == ["a", "b"]
    assert session.calls[1]["params"]["start_cursor"] == "n"


def test_retries_429_with_retry_after():
    client, session, sleeps = make_client([
        FakeResponse(429, {"code": "rate_limited"}, headers={"Retry-After": "2"}),
        FakeResponse(502, {}),
        FakeResponse(200, {"id": "p1"}),
    ])
    assert client.post("pages", json={})["id"] == "p1"
    assert len(session.calls) == 3
    assert 2.0 in sleeps


def test_retries_network_error_then_gives_up():
    client, session, _ = make_client([requests.ConnectionError("boom")] * 5)
    with pytest.raises(NotionError) as err:
        client.get("x")
    assert err.value.code == "network_error"
    assert len(session.calls) == 5


def test_client_error_raises_without_retry():
    client, session, _ = make_client([FakeResponse(400, {"code": "validation_error", "message": "bad"})])
    with pytest.raises(NotionError) as err:
        client.patch("pages/1", json={})
    assert err.value.status == 400 and err.value.code == "validation_error"
    assert len(session.calls) == 1


def test_blank_to_none():
    assert blank_to_none({"url": "", "nested": [{"u": " "}, "x"], "n": 0}) == {"url": None, "nested": [{"u": None}, "x"], "n": 0}
