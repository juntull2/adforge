"""
노션 A급 소재 레퍼런스 (🏢 브랜드 표 + 🎬 소재 표)
====================================================

- setup: 기존 "메타 광고 레퍼런스 모음" 페이지 안에 "📚 A급 소재 레퍼런스" 페이지와 두 표·보기를 만듭니다.
      python notion_references.py setup            ← 미리보기만 (노션에 쓰지 않음)
      python notion_references.py setup --apply    ← 실제로 만듦
- ReferenceStore: 브랜드는 '브랜드 키'(자사몰 도메인 등)로, 소재는 '광고 ID'로 찾아서 있으면 갱신, 없으면 만듭니다.

칸 소유 규칙
- 사람 전용: 제작 영상 링크 · 제작 날짜 · 대표님 피드백 (이전 칸 이름도 보호) → 자동 저장 요청에 넣지 않습니다.
- 처음만(CREATE_ONLY): 제목 · 진행 여부 · 소구 포인트 · 소재 본문 → 처음 만들 때만 쓰고 다시 저장할 때는 건드리지 않습니다.
- 비어 있을 때만(EMPTY_ONLY): 영상 원본 → 구글 드라이브 링크를 덮어쓰지 않습니다.
- 그 밖의 칸은 저장할 때마다 최신 값으로 갱신합니다.
- 브랜드 본문은 "🤖 adforge 자동 기록" 박스 안만 새로 쓰고, 그 밖에 적은 내용은 그대로 둡니다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from notion_sync import NotionClient, NotionError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")

PAGE_TITLE = "📚 A급 소재 레퍼런스"
BRAND_DB_TITLE = "🏢 브랜드"
AD_DB_TITLE = "🎬 소재"
AUTO_MARKER = "🤖 adforge 자동 기록"

ENV_PAGE = "NOTION_REFERENCE_PAGE_ID"
ENV_BRAND_DB = "NOTION_BRAND_DB_ID"
ENV_BRAND_DS = "NOTION_BRAND_SOURCE_ID"
ENV_AD_DB = "NOTION_AD_DB_ID"
ENV_AD_DS = "NOTION_AD_SOURCE_ID"

# ── 🏢 브랜드 칸 ─────────────────────────────────────────────
B_TITLE = "브랜드"
B_KEY = "브랜드 키"
B_MALL = "자사몰"
B_PRODUCT = "제품"
B_KEYWORD = "판정 키워드"
B_PEAK = "최고 30일 검색량"
B_RECENT = "최근 30일 검색량"
B_RISE = "급상승(60일)"
B_RISE_RANGE = "급상승 구간(60일)"
B_JUMP = "60일 증가폭"
B_RATIO = "60일 증가 배수"
B_BASELINE = "평소 60일 검색량"
B_FEMALE = "여성 비중(%)"
B_4050 = "4050 비중(%)"
B_ACCOUNTS = "연결 계정 수"
B_ACCOUNT_TYPES = "연결 계정 유형"
B_CHECKED = "마지막 확인"
B_ADS = "소재"
B_MAX_DAYS = "최장 게재일"

# ── 🎬 소재 칸 ───────────────────────────────────────────────
A_TITLE = "제목"
A_BRAND = "브랜드"
A_ACCOUNT = "광고 계정"
A_ACCOUNT_TYPE = "계정 유형"
A_MEDIA = "소재 유형"
A_APPEAL = "소구 포인트"
A_TERMS = "연관 키워드"
A_START = "게재 시작일"
A_DAYS = "게재일수"
A_STATUS = "진행 여부"
A_META = "메타 광고"
A_VIDEO = "영상 원본"
A_LANDING = "랜딩"
A_AD_ID = "광고 ID"
A_COLLATION = "묶음 ID"
A_ASSET = "영상 자산 ID"
A_FINGERPRINT = "소재 지문"

H_MATERIAL = "제작 영상 링크"
H_EDITED = "제작 날짜"
H_FEEDBACK = "대표님 피드백"
HUMAN_ONLY = (H_MATERIAL, H_EDITED, H_FEEDBACK)
HUMAN_ALIASES = {"소재링크": H_MATERIAL, "편집일": H_EDITED}
HUMAN_PROTECTED = frozenset((*HUMAN_ONLY, *HUMAN_ALIASES))
AD_CREATE_ONLY = (A_TITLE, A_STATUS, A_APPEAL)
BRAND_CREATE_ONLY = (B_TITLE,)
EMPTY_ONLY = (A_VIDEO,)

STATUS_DEFAULT = "검토중"
STATUS_OPTIONS = [("검토중", "gray", "To-do"), ("진행", "blue", "In progress"),
                  ("보류", "yellow", "In progress"), ("완료", "green", "Complete")]
RISE_OPTIONS = [("🚀 급상승", "orange"), ("📈 상승", "green"), ("➖ 꾸준", "gray")]
ACCOUNT_OPTIONS = [("공식 계정", "green"), ("숨은 계정", "blue"), ("위장 계정", "yellow"),
                   ("아랍어 계정", "red"), ("외국어 계정", "orange")]
MEDIA_OPTIONS = [("영상", "purple"), ("이미지", "blue"), ("캐러셀", "pink")]
# 사람 전용 칸을 기존 기획표에서 읽지 못했을 때 쓸 종류
HUMAN_DEFAULT_TYPES = {H_MATERIAL: "url", H_EDITED: "date", H_FEEDBACK: "rich_text"}
HUMAN_ALLOWED_TYPES = {"rich_text", "url", "date", "files", "people", "last_edited_time", "checkbox", "select"}
DAYS_FORMULA = f'dateBetween(now(), prop("{A_START}"), "days")'


def _options(items) -> list:
    return [{"name": name, "color": color} for name, color in items]


def brand_schema() -> dict:
    """브랜드 표 칸 정의 (소재 관계·최장 게재일 롤업은 소재 표를 만든 뒤 붙입니다)"""
    number = {"number": {"format": "number_with_commas"}}
    return {
        B_TITLE: {"title": {}},
        B_RISE: {"select": {"options": _options(RISE_OPTIONS)}},
        B_JUMP: dict(number),
        B_RATIO: {"number": {"format": "number"}},
        B_RISE_RANGE: {"rich_text": {}},
        B_BASELINE: dict(number),
        B_PEAK: dict(number),
        B_RECENT: dict(number),
        B_KEYWORD: {"rich_text": {}},
        B_PRODUCT: {"rich_text": {}},
        B_MALL: {"url": {}},
        B_FEMALE: {"number": {"format": "number"}},
        B_4050: {"number": {"format": "number"}},
        B_ACCOUNTS: {"number": {"format": "number"}},
        B_ACCOUNT_TYPES: {"multi_select": {"options": _options(ACCOUNT_OPTIONS)}},
        B_CHECKED: {"date": {}},
        B_KEY: {"rich_text": {}},
    }


def human_schema(types: dict) -> dict:
    types = {HUMAN_ALIASES.get(name, name): kind for name, kind in types.items()}
    out = {}
    for name in HUMAN_ONLY:
        kind = types.get(name) if types.get(name) in HUMAN_ALLOWED_TYPES else HUMAN_DEFAULT_TYPES[name]
        out[name] = {kind: {}}
    return out


def ad_schema(brand_data_source_id: str, human_types: dict, status_as_select: bool = False) -> dict:
    """소재 표 칸 정의. status_as_select=True면 진행 여부를 상태 대신 선택 칸으로 만듭니다(상태 칸 생성 실패 시)."""
    if status_as_select:
        status = {"select": {"options": [{"name": n, "color": c} for n, c, _ in STATUS_OPTIONS]}}
    else:
        status = {"status": {"options": [{"name": n, "color": c, "group": g} for n, c, g in STATUS_OPTIONS]}}
    schema = {
        A_TITLE: {"title": {}},
        A_BRAND: {"relation": {"data_source_id": brand_data_source_id, "type": "dual_property", "dual_property": {}}},
        A_STATUS: status,
        A_ACCOUNT: {"rich_text": {}},
        A_ACCOUNT_TYPE: {"select": {"options": _options(ACCOUNT_OPTIONS)}},
        A_MEDIA: {"select": {"options": _options(MEDIA_OPTIONS)}},
        A_APPEAL: {"multi_select": {"options": []}},
        A_TERMS: {"multi_select": {"options": []}},
        A_START: {"date": {}},
        A_DAYS: {"formula": {"expression": DAYS_FORMULA}},
        A_META: {"url": {}},
        A_VIDEO: {"url": {}},
        A_LANDING: {"url": {}},
        A_AD_ID: {"rich_text": {}},
        A_COLLATION: {"rich_text": {}},
        A_ASSET: {"rich_text": {}},
        A_FINGERPRINT: {"rich_text": {}},
    }
    schema.update(human_schema(human_types))
    return schema


def rollup_schema() -> dict:
    return {B_MAX_DAYS: {"rollup": {"relation_property_name": B_ADS, "rollup_property_name": A_DAYS,
                                    "function": "max"}}}


# ─────────────────────────────────────────────────────────────────
# .env
# ─────────────────────────────────────────────────────────────────

def write_env(values: dict, path: str = ENV_PATH) -> None:
    """KEY=value를 .env에 저장(있으면 교체)하고 현재 프로세스 환경변수에도 반영합니다."""
    content = ""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    for key, value in values.items():
        line = f"{key}={value}"
        pattern = rf"^{re.escape(key)}=.*$"
        if re.search(pattern, content, flags=re.MULTILINE):
            content = re.sub(pattern, lambda _m: line, content, flags=re.MULTILINE)
        else:
            content = content.rstrip() + f"\n{line}\n"
        os.environ[key] = value
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def configured_ids() -> dict:
    return {k: os.environ.get(k, "").strip() for k in (ENV_PAGE, ENV_BRAND_DB, ENV_BRAND_DS, ENV_AD_DB, ENV_AD_DS)}


def is_configured() -> bool:
    ids = configured_ids()
    return bool(ids[ENV_BRAND_DS] and ids[ENV_AD_DS])


# ─────────────────────────────────────────────────────────────────
# 블록 도우미
# ─────────────────────────────────────────────────────────────────

def _rt(text: str, link: str = "", bold: bool = False) -> dict:
    item = {"type": "text", "text": {"content": text[:2000]}}
    if link:
        item["text"]["link"] = {"url": link}
    if bold:
        item["annotations"] = {"bold": True}
    return item


def _chunks(text: str, size: int = 1900) -> list:
    text = text or ""
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]


def paragraph(text: str = "", *parts) -> dict:
    rich = [_rt(t) for t in _chunks(text)] if text else []
    rich += list(parts)
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": rich}}


def bullet(*parts) -> dict:
    rich = [p if isinstance(p, dict) else _rt(str(p)) for p in parts]
    return {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich}}


def heading(text: str, level: int = 3) -> dict:
    kind = f"heading_{level}"
    return {"object": "block", "type": kind, kind: {"rich_text": [_rt(text)]}}


def callout(text: str, emoji: str, color: str = "gray_background", children: list = None) -> dict:
    block = {"object": "block", "type": "callout",
             "callout": {"rich_text": [_rt(text, bold=True)], "icon": {"type": "emoji", "emoji": emoji}, "color": color}}
    if children:
        block["callout"]["children"] = children
    return block


def _plain(rich: list) -> str:
    return "".join(r.get("plain_text") or r.get("text", {}).get("content", "") for r in rich or [])


def guide_blocks() -> list:
    """새 페이지 맨 위 안내"""
    return [
        callout("A급 기준", "🏆", "yellow_background", [
            bullet("① 최근 1년 안에 동일한 브랜드·제품 키워드의 30일 검색량이 1만 건 이상인 이력과, 직전 60일 대비 60일 검색량 증가폭이 7,000건 이상인 이력 (네이버 최근 30일 실측 검색수로 데이터랩 일간 추이를 환산)"),
            bullet("② 메타 광고 라이브러리에서 60일 이상 게재 중"),
            bullet("③ 우리 제품(여드름·영양제 등)과 연관"),
        ]),
        callout("급상승 판정 (A급 필수 조건)", "🚀", "orange_background", [
            bullet("🚀 급상승: 30일 검색량 1만 건 이상 + 직전 60일 대비 60일 증가폭 7,000건 이상. 배수는 참고용"),
            bullet("📈 상승: 증가폭이 기준의 절반 이상이거나 1.5배 이상"),
            bullet("➖ 꾸준: 그 밖"),
        ]),
        callout("누가 어떤 칸을 쓰나요", "✍️", "blue_background", [
            bullet(_rt("사람 전용: ", bold=True), _rt(f"{H_MATERIAL} · {H_EDITED} · {H_FEEDBACK} — adforge는 이 칸을 절대 쓰지 않습니다.")),
            bullet(_rt("처음만: ", bold=True), _rt("제목 · 진행 여부 · 소구 포인트 · 소재 본문 — 처음 저장할 때만 채우고 이후엔 그대로 둡니다.")),
            bullet(_rt("자동 갱신: ", bold=True), _rt("그 밖의 칸과 브랜드 본문의 '🤖 adforge 자동 기록' 박스는 저장할 때마다 새 값으로 바뀝니다.")),
        ]),
    ]


# ─────────────────────────────────────────────────────────────────
# setup
# ─────────────────────────────────────────────────────────────────

@dataclass
class SetupPlan:
    parent_page_id: str = ""
    parent_title: str = ""
    legacy_db_id: str = ""
    human_types: dict = field(default_factory=dict)
    human_source: str = ""
    existing: dict = field(default_factory=dict)
    duplicate_page_id: str = ""
    steps: list = field(default_factory=list)
    problems: list = field(default_factory=list)


def _title_of_page(page: dict) -> str:
    for prop in (page.get("properties") or {}).values():
        if prop.get("type") == "title":
            return _plain(prop.get("title"))
    return ""


def plan_setup(client: NotionClient, legacy_db_id: str) -> SetupPlan:
    """읽기만 해서 무엇을 만들지 정리합니다."""
    plan = SetupPlan(legacy_db_id=legacy_db_id, existing={k: v for k, v in configured_ids().items() if v})
    if not legacy_db_id:
        plan.problems.append("NOTION_DATABASE_ID(기존 레퍼런스 DB)가 없어 부모 페이지를 찾을 수 없습니다.")
        return plan
    db = client.get(f"databases/{legacy_db_id}")
    parent = db.get("parent") or {}
    if parent.get("type") != "page_id":
        plan.problems.append(f"기존 DB의 부모가 페이지가 아닙니다: {parent.get('type')}")
        return plan
    plan.parent_page_id = parent["page_id"]
    plan.parent_title = _title_of_page(client.get(f"pages/{plan.parent_page_id}"))

    for ds in db.get("data_sources") or []:
        props = client.get(f"data_sources/{ds['id']}").get("properties") or {}
        found = {HUMAN_ALIASES.get(name, name): meta.get("type") for name, meta in props.items()
                 if name in HUMAN_PROTECTED}
        if found and len(found) > len(plan.human_types):
            plan.human_types, plan.human_source = found, ds.get("name", ds["id"])
    for block in client.block_children(plan.parent_page_id):
        if block.get("type") == "child_page" and block["child_page"].get("title") == PAGE_TITLE:
            plan.duplicate_page_id = block["id"]

    if plan.existing.get(ENV_BRAND_DS) and plan.existing.get(ENV_AD_DS):
        plan.steps.append("이미 설정돼 있습니다 (.env에 브랜드·소재 표 ID 있음). 만들 것이 없습니다.")
        return plan
    if plan.duplicate_page_id and not plan.existing.get(ENV_PAGE):
        plan.problems.append(
            f"'{plan.parent_title}' 안에 '{PAGE_TITLE}' 페이지가 이미 있습니다 ({plan.duplicate_page_id}). "
            f"새로 만들지 않고 멈춥니다. 그 페이지를 쓰려면 .env에 {ENV_PAGE}를 넣고 다시 실행하세요."
        )
        return plan

    types = human_schema(plan.human_types)
    human_desc = ", ".join(f"{k}({next(iter(v))})" for k, v in types.items())
    if not plan.existing.get(ENV_PAGE):
        plan.steps.append(f"페이지 만들기: '{plan.parent_title}' 안에 '{PAGE_TITLE}' + 안내 박스 3개 (A급 기준 · 급상승 · 칸 소유)")
    if not plan.existing.get(ENV_BRAND_DS):
        plan.steps.append(f"표 만들기: {BRAND_DB_TITLE} — 칸 {len(brand_schema())}개: " + ", ".join(brand_schema()))
    if not plan.existing.get(ENV_AD_DS):
        plan.steps.append(f"표 만들기: {AD_DB_TITLE} — 칸 {len(ad_schema('x', plan.human_types))}개: "
                          + ", ".join(ad_schema("x", plan.human_types)))
        plan.steps.append(f"사람 전용 칸 종류 (기존 '{plan.human_source or '기본값'}'에 맞춤): {human_desc}")
        plan.steps.append(f"관계: {AD_DB_TITLE}.{A_BRAND} ↔ {BRAND_DB_TITLE}.{B_ADS} (양방향)")
        plan.steps.append(f"수식: {A_DAYS} = {DAYS_FORMULA}")
        plan.steps.append(f"롤업: {BRAND_DB_TITLE}.{B_MAX_DAYS} = {B_ADS}.{A_DAYS} 최댓값")
        plan.steps.append("한 페이지에 브랜드·소재 표 배치; 추가 보기 탭은 만들지 않음")
    plan.steps.append(f".env에 저장: {ENV_PAGE}, {ENV_BRAND_DB}, {ENV_BRAND_DS}, {ENV_AD_DB}, {ENV_AD_DS} "
                      "(기존 NOTION_DATABASE_ID는 그대로)")
    plan.steps.append("기존 DB와 그 안의 행은 읽기만 하고 고치지 않습니다.")
    return plan


def format_plan(plan: SetupPlan) -> str:
    lines = [f"# 노션 setup 미리보기", "", f"- 부모 페이지: {plan.parent_title} ({plan.parent_page_id})",
             f"- 기존 DB: {plan.legacy_db_id}"]
    if plan.problems:
        lines += ["", "## 멈춤"] + [f"- {p}" for p in plan.problems]
    lines += ["", "## 할 일"] + [f"{i}. {s}" for i, s in enumerate(plan.steps, 1)]
    return "\n".join(lines)


def _prop_ids(client: NotionClient, data_source_id: str) -> dict:
    props = client.get(f"data_sources/{data_source_id}").get("properties") or {}
    return {name: meta for name, meta in props.items()}


def _create_database(client: NotionClient, page_id: str, title: str, emoji: str, schema: dict) -> tuple:
    db = client.post("databases", json={
        "parent": {"type": "page_id", "page_id": page_id},
        "title": [_rt(title)],
        "is_inline": True,
        "icon": {"type": "emoji", "emoji": emoji},
        "initial_data_source": {"properties": schema},
    })
    sources = db.get("data_sources") or []
    if not sources:
        raise NotionError(0, "no_data_source", f"{title} 표의 데이터 소스 ID를 받지 못했습니다")
    return db["id"], sources[0]["id"]


def apply_setup(client: NotionClient, plan: SetupPlan, env_writer=write_env) -> list:
    """plan_setup 결과대로 노션에 만듭니다. 단계마다 ID를 .env에 저장해서 중간에 실패해도 이어서 실행할 수 있습니다."""
    if plan.problems:
        raise RuntimeError("미리보기에서 멈춤 사유가 있어 실행하지 않습니다: " + " / ".join(plan.problems))
    ids = dict(configured_ids())
    ids.update({k: v for k, v in plan.existing.items() if v})
    log = []

    if not ids.get(ENV_PAGE):
        page = client.post("pages", json={
            "parent": {"type": "page_id", "page_id": plan.parent_page_id},
            "icon": {"type": "emoji", "emoji": "📚"},
            "properties": {"title": {"title": [_rt(PAGE_TITLE)]}},
            "children": guide_blocks(),
        })
        ids[ENV_PAGE] = page["id"]
        env_writer({ENV_PAGE: page["id"]})
        log.append(f"페이지 만듦: {PAGE_TITLE} ({page['id']})")

    if not ids.get(ENV_BRAND_DS):
        db_id, ds_id = _create_database(client, ids[ENV_PAGE], BRAND_DB_TITLE, "🏢", brand_schema())
        ids[ENV_BRAND_DB], ids[ENV_BRAND_DS] = db_id, ds_id
        env_writer({ENV_BRAND_DB: db_id, ENV_BRAND_DS: ds_id})
        log.append(f"표 만듦: {BRAND_DB_TITLE} ({db_id})")

    if not ids.get(ENV_AD_DS):
        try:
            db_id, ds_id = _create_database(client, ids[ENV_PAGE], AD_DB_TITLE, "🎬",
                                            ad_schema(ids[ENV_BRAND_DS], plan.human_types))
        except NotionError as exc:
            if exc.status != 400:
                raise
            log.append(f"⚠️ 상태 칸 만들기 실패({exc.message}) → 진행 여부를 선택 칸으로 만듭니다.")
            db_id, ds_id = _create_database(client, ids[ENV_PAGE], AD_DB_TITLE, "🎬",
                                            ad_schema(ids[ENV_BRAND_DS], plan.human_types, status_as_select=True))
        ids[ENV_AD_DB], ids[ENV_AD_DS] = db_id, ds_id
        env_writer({ENV_AD_DB: db_id, ENV_AD_DS: ds_id})
        log.append(f"표 만듦: {AD_DB_TITLE} ({db_id})")

        # 관계 반대쪽 칸 이름을 '소재'로
        relation = (_prop_ids(client, ds_id).get(A_BRAND) or {}).get("relation") or {}
        synced = (relation.get("dual_property") or {})
        synced_key = synced.get("synced_property_id") or synced.get("synced_property_name")
        if synced_key and synced.get("synced_property_name") != B_ADS:
            client.patch(f"data_sources/{ids[ENV_BRAND_DS]}", json={"properties": {synced_key: {"name": B_ADS}}})
        log.append(f"관계 연결: {AD_DB_TITLE}.{A_BRAND} ↔ {BRAND_DB_TITLE}.{B_ADS}")
        try:
            client.patch(f"data_sources/{ids[ENV_BRAND_DS]}", json={"properties": rollup_schema()})
            log.append(f"롤업 만듦: {B_MAX_DAYS}")
        except NotionError as exc:
            log.append(f"⚠️ 롤업 '{B_MAX_DAYS}' 만들기 실패 ({exc.message}) — 노션에서 직접 추가해 주세요.")
        log.append("브랜드·소재 표의 기본 보기만 사용 (추가 탭 없음)")
    return log


# ─────────────────────────────────────────────────────────────────
# 칸 값 만들기
# ─────────────────────────────────────────────────────────────────

def p_title(text: str) -> dict:
    return {"title": [_rt((text or "제목 없음")[:200])]}


def p_text(text) -> dict:
    text = str(text or "").strip()
    return {"rich_text": [_rt(t) for t in _chunks(text)] if text else []}


def p_url(url) -> dict:
    url = str(url or "").strip()
    return {"url": url if url.startswith("http") else None}


def p_number(value) -> dict:
    return {"number": value if isinstance(value, (int, float)) else None}


def p_select(name) -> dict:
    name = _option_name(name)
    return {"select": {"name": name} if name else None}


def p_multi(names) -> dict:
    seen, out = set(), []
    for n in names or []:
        n = _option_name(n)
        if n and n.lower() not in seen:
            seen.add(n.lower())
            out.append({"name": n})
    return {"multi_select": out}


def p_date(value) -> dict:
    value = str(value or "")[:10]
    return {"date": {"start": value} if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else None}


def p_relation(ids) -> dict:
    return {"relation": [{"id": i} for i in ids if i]}


def _option_name(name) -> str:
    """선택 옵션 이름: 쉼표 불가, 100자 이하"""
    return re.sub(r"\s+", " ", str(name or "").replace(",", " ")).strip()[:100]


def strip_human(props: dict) -> dict:
    """사람 전용 칸은 어떤 경우에도 요청에 넣지 않습니다."""
    return {k: v for k, v in props.items() if k not in HUMAN_PROTECTED}


def brand_key_of(brand) -> str:
    return brand.key or ""


def brand_properties(brand, today: date, create: bool) -> dict:
    from a_grade_finder import brand_mall_url

    v = brand.volume
    has_rise = bool(v and v.rise_end and getattr(v, "rise_window_days", 30) == 60)
    audience = getattr(brand, "audience", None) or {}
    gender = audience.get("gender") or {}
    types = sorted({a.account_type for a in brand.accounts or []})
    props = {
        B_KEY: p_text(brand_key_of(brand)),
        B_MALL: p_url(brand_mall_url(brand)),
        B_PRODUCT: p_text(brand.product_hint),
        B_KEYWORD: p_text(v.keyword if v else ""),
        B_PEAK: p_number(v.peak_volume if v and getattr(v, "search_window_days", 30) == 30 and not getattr(v, "peak_is_lower_bound", False) else None),
        B_RECENT: p_number(v.recent_30d if v else None),
        B_RISE: p_select(v.rise_level if has_rise else ""),
        B_RISE_RANGE: p_text(f"{v.rise_start} ~ {v.rise_end}" if has_rise else ""),
        B_JUMP: p_number(v.rise_jump if has_rise else None),
        B_RATIO: p_number(v.rise_ratio if has_rise else None),
        B_BASELINE: p_number(v.rise_baseline if has_rise else None),
        B_FEMALE: p_number(gender.get("여성") if audience.get("ok") else None),
        B_4050: p_number(audience.get("target_4050") if audience.get("ok") else None),
        B_ACCOUNTS: p_number(len(brand.accounts) if brand.tracked else None),
        B_ACCOUNT_TYPES: p_multi(types),
        B_CHECKED: p_date(today.isoformat()),
    }
    if create:
        props[B_TITLE] = p_title(brand.name or brand.key)
    return strip_human(props)


def ad_title(ad, brand) -> str:
    text = (ad.hook or ad.copy or "").strip()
    if len(text) >= 4:
        return text[:60]
    return f"[{ad.media_type or '소재'}] {brand.name} ({ad.start_date or '레퍼런스'})"


def ad_properties(ad, brand, brand_page_id: str, create: bool, account_type: str = "", title: str = "",
                  status: str = "", appeals: list = None, video_link: str = "", existing_video: str = "",
                  status_type: str = "status") -> dict:
    props = {
        A_BRAND: p_relation([brand_page_id]),
        A_ACCOUNT: p_text(ad.page_name),
        A_ACCOUNT_TYPE: p_select(account_type),
        A_MEDIA: p_select(ad.media_type),
        A_TERMS: p_multi(ad.relevance),
        A_START: p_date(ad.start_date),
        A_META: p_url(ad.library_url),
        A_LANDING: p_url(ad.landing_url),
        A_AD_ID: p_text(ad.ad_id),
        A_COLLATION: p_text(ad.collation_id),
        A_ASSET: p_text(ad.video_asset_id),
        A_FINGERPRINT: p_text(ad.fingerprint),
    }
    if video_link and not existing_video:
        props[A_VIDEO] = p_url(video_link)
    if create:
        props[A_TITLE] = p_title(title or ad_title(ad, brand))
        name = status or STATUS_DEFAULT
        props[A_STATUS] = {"select": {"name": name}} if status_type == "select" else {"status": {"name": name}}
        props[A_APPEAL] = p_multi(appeals or [])
    return strip_human(props)


def ad_body(ad) -> list:
    blocks = []
    if ad.copy:
        blocks.append(callout("광고 카피", "📝", "gray_background", [paragraph(ad.copy)]))
    return blocks


def brand_auto_block(brand, today: date) -> dict:
    """브랜드 본문의 🤖 자동 기록 박스 (매번 통째로 새로 씁니다)"""
    from a_grade_finder import volume_summary, rise_summary
    from naver_datalab import format_rise

    v = brand.volume
    children = [paragraph(f"마지막 확인 {today.isoformat()} · 이 박스 안은 adforge가 저장할 때마다 새로 씁니다.")]
    children.append(heading("검색량", 3))
    children.append(bullet(volume_summary(v)))
    if v and v.rise_end:
        children.append(bullet(rise_summary(v)))
    for m in (v.months if v else [])[-12:]:
        children.append(bullet(f"{m['month']}{' (일부)' if m.get('partial') else ''}: {m['volume']:,}건"))
    audience = getattr(brand, "audience", None) or {}
    if audience.get("ok"):
        g = audience.get("gender") or {}
        ages = " · ".join(f"{k} {val}%" for k, val in (audience.get("age") or {}).items())
        children.append(heading("연령·성별 (네이버 쇼핑인사이트 클릭 비중)", 3))
        children.append(bullet(f"여성 {g.get('여성', 0)}% · 남성 {g.get('남성', 0)}% · 4050 {audience.get('target_4050', 0)}%"))
        children.append(bullet(ages))
    if brand.tracked:
        children.append(heading(f"연결 계정 {len(brand.accounts)}개", 3))
        for a in brand.accounts[:40]:
            label = f"{a.account_type} · {a.page_name} · 이 브랜드 광고 {a.brand_ads}개 · 최장 {a.max_running_days}일 · {a.confidence}"
            if getattr(a, "depth", 0):
                label += f" · 🔁 {a.found_via}에서 찾음"
            children.append(bullet(_rt(label, link=a.library_url) if a.library_url else _rt(label)))
    return callout(AUTO_MARKER, "🤖", "gray_background", children[:95])


# ─────────────────────────────────────────────────────────────────
# 저장소 (찾아서 갱신 / 없으면 생성)
# ─────────────────────────────────────────────────────────────────

def _read(prop: dict):
    if not prop:
        return None
    kind = prop.get("type")
    value = prop.get(kind)
    if kind in ("title", "rich_text"):
        return _plain(value)
    if kind == "url":
        return value or ""
    if kind == "relation":
        return [r.get("id") for r in value or []]
    if kind in ("select", "status"):
        return (value or {}).get("name", "")
    return value


class ReferenceStore:
    """🏢 브랜드 · 🎬 소재 표 읽기/저장"""

    def __init__(self, client: NotionClient, brand_ds: str, ad_ds: str):
        self.client = client
        self.brand_ds = brand_ds
        self.ad_ds = ad_ds
        self.brands: dict = {}         # 브랜드 키 → page
        self.brand_by_id: dict = {}    # page id → 브랜드 키
        self.ads: dict = {}            # 광고 ID → page
        self.ad_schema: dict = {}
        self.brand_schema: dict = {}
        self.loaded = False

    @classmethod
    def from_env(cls, client: NotionClient = None) -> "ReferenceStore":
        ids = configured_ids()
        if not (ids[ENV_BRAND_DS] and ids[ENV_AD_DS]):
            raise RuntimeError("노션 브랜드·소재 표가 설정되지 않았습니다. `python notion_references.py setup`을 먼저 실행하세요.")
        token = os.environ.get("NOTION_TOKEN", "").strip()
        if not token:
            raise RuntimeError("NOTION_TOKEN이 없습니다.")
        return cls(client or NotionClient(token), ids[ENV_BRAND_DS], ids[ENV_AD_DS])

    def load(self) -> "ReferenceStore":
        self.brand_schema = self.client.get(f"data_sources/{self.brand_ds}").get("properties") or {}
        self.ad_schema = self.client.get(f"data_sources/{self.ad_ds}").get("properties") or {}
        missing = [n for n in (B_KEY,) if n not in self.brand_schema] + \
                  [n for n in (A_AD_ID, A_BRAND) if n not in self.ad_schema]
        if missing:
            raise RuntimeError(f"노션 표에 필요한 칸이 없습니다: {', '.join(missing)}")
        self.brands, self.brand_by_id, self.ads = {}, {}, {}
        for page in self.client.query_data_source(self.brand_ds):
            key = _read(page["properties"].get(B_KEY))
            if key:
                self.brands[key] = page
                self.brand_by_id[page["id"]] = key
        for page in self.client.query_data_source(self.ad_ds):
            ad_id = _read(page["properties"].get(A_AD_ID))
            if ad_id:
                self.ads[ad_id] = page
        self.loaded = True
        return self

    def _only_known(self, props: dict, schema: dict) -> dict:
        """표에 없는 칸(사용자가 지운 칸)은 빼고 보냅니다."""
        return {k: v for k, v in strip_human(props).items() if k in schema}

    def recorded_keys(self):
        from a_grade_finder import RecordedKeys

        keys = RecordedKeys(loaded=True)
        for ad_id, page in self.ads.items():
            props = page["properties"]
            keys.ad_ids.add(ad_id)
            for name, target in ((A_COLLATION, keys.collation_ids), (A_ASSET, keys.asset_ids)):
                value = _read(props.get(name))
                if value:
                    target.add(value)
            fp = _read(props.get(A_FINGERPRINT))
            for brand_page in _read(props.get(A_BRAND)) or []:
                brand_key = self.brand_by_id.get(brand_page)
                if fp and brand_key:
                    keys.fingerprints.add((brand_key, fp))
        return keys

    # ── 브랜드 ─────────────────────────────────────────────
    def upsert_brand(self, brand, today: date = None) -> tuple:
        """(page_id, 새로 만들었는지)"""
        today = today or date.today()
        if not self.loaded:
            self.load()
        key = brand_key_of(brand)
        existing = self.brands.get(key)
        props = self._only_known(brand_properties(brand, today, create=existing is None), self.brand_schema)
        if existing is None:
            page = self.client.post("pages", json={
                "parent": {"type": "data_source_id", "data_source_id": self.brand_ds},
                "icon": {"type": "emoji", "emoji": "🏆"},
                "properties": props,
                "children": [brand_auto_block(brand, today)],
            })
            self.brands[key] = {"id": page["id"], "properties": page.get("properties") or {}}
            self.brand_by_id[page["id"]] = key
            return page["id"], True
        page_id = existing["id"]
        self.client.patch(f"pages/{page_id}", json={"properties": props})
        self.replace_auto_block(page_id, brand_auto_block(brand, today))
        return page_id, False

    def replace_auto_block(self, page_id: str, block: dict) -> None:
        """본문에서 🤖 자동 기록 박스만 찾아 같은 자리에 새로 넣습니다. 그 밖의 블록은 건드리지 않습니다."""
        children = self.client.block_children(page_id)
        previous, target = None, None
        for child in children:
            if child.get("type") == "callout" and _plain(child["callout"].get("rich_text")).startswith(AUTO_MARKER):
                target = child
                break
            previous = child
        body = {"children": [block]}
        if target is not None:
            body["position"] = ({"type": "after_block", "after_block": {"id": previous["id"]}}
                                if previous else {"type": "start"})
            self.client.patch(f"blocks/{page_id}/children", json=body)
            self.client.delete(f"blocks/{target['id']}")
        else:
            body["position"] = {"type": "start"}
            self.client.patch(f"blocks/{page_id}/children", json=body)

    # ── 소재 ───────────────────────────────────────────────
    def upsert_ad(self, ad, brand, brand_page_id: str, account_type: str = "", title: str = "", status: str = "",
                  appeals: list = None, video_link: str = "") -> tuple:
        """(page_id, 새로 만들었는지)"""
        if not self.loaded:
            self.load()
        existing = self.ads.get(ad.ad_id) if ad.ad_id else None
        status_type = (self.ad_schema.get(A_STATUS) or {}).get("type", "status")
        existing_video = _read((existing.get("properties") or {}).get(A_VIDEO)) if existing else ""
        props = ad_properties(ad, brand, brand_page_id, create=existing is None, account_type=account_type,
                              title=title, status=status, appeals=appeals, video_link=video_link,
                              existing_video=existing_video, status_type=status_type)
        props = self._only_known(props, self.ad_schema)
        if existing is None:
            page = self.client.post("pages", json={
                "parent": {"type": "data_source_id", "data_source_id": self.ad_ds},
                "properties": props,
                "children": ad_body(ad),
            })
            if ad.ad_id:
                self.ads[ad.ad_id] = {"id": page["id"], "properties": page.get("properties") or {
                    A_VIDEO: {"type": "url", "url": props.get(A_VIDEO, {}).get("url")}}}
            return page["id"], True
        self.client.patch(f"pages/{existing['id']}", json={"properties": props})
        if A_VIDEO in props:
            existing.setdefault("properties", {})[A_VIDEO] = {"type": "url", "url": video_link}
        return existing["id"], False


# ─────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────

def _main(argv=None) -> int:
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH)
    parser = argparse.ArgumentParser(description="노션 A급 소재 레퍼런스 표 만들기")
    sub = parser.add_subparsers(dest="cmd", required=True)
    setup = sub.add_parser("setup", help="브랜드·소재 표 만들기 (기본은 미리보기)")
    setup.add_argument("--apply", action="store_true", help="미리보기 내용대로 실제로 만듭니다")
    setup.add_argument("--out", default="", help="미리보기를 저장할 파일 (UTF-8)")
    args = parser.parse_args(argv)

    token = os.environ.get("NOTION_TOKEN", "").strip()
    if not token:
        print("NOTION_TOKEN이 없습니다.")
        return 2
    client = NotionClient(token)
    plan = plan_setup(client, os.environ.get("NOTION_DATABASE_ID", "").strip())
    text = format_plan(plan)
    if args.apply:
        log = apply_setup(client, plan)
        text += "\n\n## 실행 결과\n" + "\n".join(f"- {line}" for line in log)
    else:
        text += "\n\n(미리보기입니다. 노션에는 아무것도 쓰지 않았습니다. 실제로 만들려면 --apply)"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)
    return 1 if plan.problems else 0


if __name__ == "__main__":
    raise SystemExit(_main())
