"""테스트용 가짜 노션 (메모리에서 페이지·데이터 소스·블록을 흉내 냅니다). 실제 노션에는 아무것도 쓰지 않습니다."""
import copy
import itertools

from notion_sync import NotionError


class FakeNotion:
    def __init__(self):
        self.ids = itertools.count(1)
        self.pages = {}          # id → page(json)
        self.sources = {}        # data source id → {"properties": {...}, "database_id": ...}
        self.databases = {}      # db id → {"parent": ..., "data_sources": [...]}
        self.children = {}       # block/page id → [block]
        self.views = []
        self.requests = []       # (method, path, json)
        self.fail_next = []      # [(method, path_prefix, NotionError)]

    def _id(self, prefix):
        return f"{prefix}-{next(self.ids)}"

    def _maybe_fail(self, method, path):
        for i, (m, prefix, err) in enumerate(self.fail_next):
            if m == method and path.startswith(prefix):
                self.fail_next.pop(i)
                raise err

    # ── 읽기 ──────────────────────────────────────────────
    def get(self, path, params=None):
        self.requests.append(("GET", path, None))
        kind, _, rest = path.partition("/")
        if kind == "databases":
            return copy.deepcopy(self.databases[rest])
        if kind == "data_sources":
            return copy.deepcopy(self.sources[rest])
        if kind == "pages":
            return copy.deepcopy(self.pages[rest])
        raise KeyError(path)

    def query_data_source(self, data_source_id, filter=None, sorts=None):
        self.requests.append(("QUERY", data_source_id, None))
        return [copy.deepcopy(p) for p in self.pages.values()
                if p.get("parent", {}).get("data_source_id") == data_source_id and not p.get("in_trash")]

    def block_children(self, block_id):
        self.requests.append(("CHILDREN", block_id, None))
        return [copy.deepcopy(b) for b in self.children.get(block_id, []) if not b.get("in_trash")]

    # ── 쓰기 ──────────────────────────────────────────────
    def post(self, path, json=None):
        self.requests.append(("POST", path, copy.deepcopy(json)))
        self._maybe_fail("POST", path)
        if path == "pages":
            return self._create_page(json)
        if path == "databases":
            return self._create_database(json)
        if path == "views":
            self.views.append(json)
            return {"id": self._id("view")}
        raise KeyError(path)

    def patch(self, path, json=None):
        self.requests.append(("PATCH", path, copy.deepcopy(json)))
        self._maybe_fail("PATCH", path)
        kind, _, rest = path.partition("/")
        if kind == "pages":
            page = self.pages[rest]
            for name, value in (json.get("properties") or {}).items():
                page["properties"][name] = self._value(page, name, value)
            return copy.deepcopy(page)
        if kind == "data_sources":
            props = self.sources[rest]["properties"]
            for key, value in (json.get("properties") or {}).items():
                name = next((n for n, m in props.items() if m.get("id") == key), key)
                if set(value) == {"name"}:
                    props[value["name"]] = props.pop(name)
                else:
                    props[key] = self._schema_prop(key, value)
            return copy.deepcopy(self.sources[rest])
        if kind == "blocks" and rest.endswith("/children"):
            parent = rest[: -len("/children")]
            blocks = [self._block(b) for b in json["children"]]
            items = self.children.setdefault(parent, [])
            position = json.get("position") or {"type": "end"}
            if position["type"] == "start":
                items[0:0] = blocks
            elif position["type"] == "after_block":
                idx = next(i for i, b in enumerate(items) if b["id"] == position["after_block"]["id"])
                items[idx + 1: idx + 1] = blocks
            else:
                items.extend(blocks)
            return {"results": blocks}
        raise KeyError(path)

    def delete(self, path):
        self.requests.append(("DELETE", path, None))
        _, _, block_id = path.partition("/")
        for items in self.children.values():
            for b in items:
                if b["id"] == block_id:
                    b["in_trash"] = True
        return {"id": block_id, "in_trash": True}

    # ── 내부 ──────────────────────────────────────────────
    def _block(self, block):
        b = copy.deepcopy(block)
        b["id"] = self._id("blk")
        for key in ("rich_text",):
            inner = b.get(b["type"], {})
            for r in inner.get(key, []):
                r.setdefault("plain_text", r.get("text", {}).get("content", ""))
        return b

    def _schema_prop(self, name, meta):
        kind = next(iter(meta))
        prop = {"id": self._id("prop"), "name": name, "type": kind, kind: copy.deepcopy(meta[kind])}
        return prop

    def _create_database(self, body):
        db_id, ds_id = self._id("db"), self._id("ds")
        props = {name: self._schema_prop(name, meta) for name, meta in body["initial_data_source"]["properties"].items()}
        for name, prop in props.items():
            if prop["type"] == "relation" and prop["relation"].get("type") == "dual_property":
                target = self.sources[prop["relation"]["data_source_id"]]["properties"]
                synced_name = f"Related to {name}"
                target[synced_name] = {"id": self._id("prop"), "name": synced_name, "type": "relation",
                                       "relation": {"data_source_id": ds_id}}
                prop["relation"]["dual_property"] = {"synced_property_id": target[synced_name]["id"],
                                                     "synced_property_name": synced_name}
        self.sources[ds_id] = {"id": ds_id, "properties": props, "database_id": db_id}
        self.databases[db_id] = {"id": db_id, "parent": body["parent"], "data_sources": [{"id": ds_id, "name": "x"}]}
        self.children.setdefault(body["parent"]["page_id"], []).append(
            {"id": db_id, "type": "child_database", "child_database": {"title": body["title"][0]["text"]["content"]}})
        return {"id": db_id, "data_sources": [{"id": ds_id}]}

    def _value(self, page, name, value):
        kind = next(iter(value))
        out = {"type": kind, kind: copy.deepcopy(value[kind])}
        if kind in ("title", "rich_text"):
            for r in out[kind]:
                r.setdefault("plain_text", r.get("text", {}).get("content", ""))
        return out

    def _create_page(self, body):
        page_id = self._id("page")
        page = {"id": page_id, "parent": body["parent"], "properties": {}}
        for name, value in (body.get("properties") or {}).items():
            page["properties"][name] = self._value(page, name, value)
        self.pages[page_id] = page
        self.children[page_id] = [self._block(b) for b in body.get("children") or []]
        if body["parent"].get("type") == "page_id":
            title = body["properties"]["title"]["title"][0]["text"]["content"]
            self.children.setdefault(body["parent"]["page_id"], []).append(
                {"id": page_id, "type": "child_page", "child_page": {"title": title}})
        return {"id": page_id}

    # ── 확인용 ────────────────────────────────────────────
    def rows(self, data_source_id):
        return self.query_data_source(data_source_id)

    def written_properties(self):
        """POST pages / PATCH pages 요청에 들어간 칸 이름들 (요청마다)"""
        out = []
        for method, path, body in self.requests:
            if (method == "POST" and path == "pages") or (method == "PATCH" and path.startswith("pages/")):
                out.append((method, set((body or {}).get("properties", {}))))
        return out


def legacy_workspace(fake: FakeNotion, human_types=None):
    """기존 '메타 광고 레퍼런스 모음' 페이지와 기획표 DB를 가짜로 만듭니다."""
    parent_id = "parent-page"
    fake.pages[parent_id] = {"id": parent_id, "parent": {"type": "workspace"},
                             "properties": {"title": {"type": "title", "title": [{"plain_text": "메타 광고 레퍼런스 모음"}]}}}
    fake.children[parent_id] = []
    human_types = human_types or {"소재링크": "rich_text", "편집일": "date", "대표님 피드백": "rich_text"}
    props = {name: {"id": f"h-{name}", "type": kind} for name, kind in human_types.items()}
    props["광고 카피"] = {"id": "title", "type": "title"}
    fake.sources["legacy-ds"] = {"id": "legacy-ds", "properties": props}
    fake.databases["legacy-db"] = {"id": "legacy-db", "parent": {"type": "page_id", "page_id": parent_id},
                                   "data_sources": [{"id": "legacy-ds", "name": "광고 레퍼런스 기획표"}]}
    return parent_id
