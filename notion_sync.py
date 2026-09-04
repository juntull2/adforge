"""
Notion API 연동 모듈
- 광고 레퍼런스 데이터를 Notion 데이터베이스에 저장
"""

import requests
from datetime import datetime


NOTION_API_VERSION = "2022-06-28"
NOTION_API_BASE = "https://api.notion.com/v1"


def get_notion_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_API_VERSION,
    }


def test_notion_connection(token: str, database_id: str) -> dict:
    """노션 연결 상태를 확인합니다."""
    db_id = database_id.replace("-", "")
    url = f"{NOTION_API_BASE}/databases/{db_id}"
    resp = requests.get(url, headers=get_notion_headers(token), timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        return {"ok": True, "title": _get_db_title(data)}
    else:
        return {"ok": False, "error": resp.json().get("message", f"HTTP {resp.status_code}")}


def _get_db_title(db_data: dict) -> str:
    title_arr = db_data.get("title", [])
    if title_arr:
        return title_arr[0].get("plain_text", "Untitled")
    return "Untitled"


_DB_PROPS_CACHE = {}


def get_database_properties(token: str, database_id: str) -> dict:
    """데이터베이스 프로퍼티(컬럼) 정보를 조회합니다 (캐시 적용)."""
    db_id = database_id.replace("-", "")
    if db_id in _DB_PROPS_CACHE:
        return _DB_PROPS_CACHE[db_id]
    url = f"{NOTION_API_BASE}/databases/{db_id}"
    try:
        resp = requests.get(url, headers=get_notion_headers(token), timeout=10)
        if resp.status_code == 200:
            props = resp.json().get("properties", {})
            _DB_PROPS_CACHE[db_id] = props
            return props
    except Exception:
        pass
    return {}


def save_ad_reference_to_notion(
    token: str,
    database_id: str,
    ad_copy: str,
    reference_url: str,
    account_name: str = "",
    status: str = "검토중",
    date: str = "",
    keyword: str = "",
    page_name: str = "",
    brand: str = "",
) -> dict:
    """
    광고 레퍼런스 데이터를 Notion 데이터베이스에 새 항목으로 저장합니다.

    Args:
        token: Notion Integration Token
        database_id: 대상 데이터베이스 ID
        ad_copy: 광고 카피 (Title 컬럼)
        reference_url: 레퍼런스 링크
        account_name: 광고 계정명 (기존 brand도 지원)
        status: 진행 여부 (검토중/진행/보류/완료)
        date: 날짜 (YYYY-MM-DD)
        keyword: 검색 키워드 (선택)
        page_name: 광고 페이지명 (선택)
        brand: 이전 호환용 브랜드명

    Returns:
        {"ok": True, "url": 노션페이지URL} or {"ok": False, "error": 메시지}
    """
    db_id = database_id.replace("-", "")
    url = f"{NOTION_API_BASE}/pages"

    # 유효하지 않은 URL 문자열 처리 (pandas에서 str() 변환 시 "None" 이나 "nan"이 될 수 있음)
    if reference_url in ("None", "nan", "", "NaN"):
        reference_url = None

    # 대상 DB 프로퍼티 스키마 조회
    db_props = get_database_properties(token, database_id)

    properties = {}

    # 1. 광고 카피 (Title 컬럼 감지)
    title_col = "광고 카피"
    if db_props:
        for col_name, col_meta in db_props.items():
            if col_meta.get("type") == "title":
                title_col = col_name
                break
    properties[title_col] = {
        "title": [{"text": {"content": ad_copy[:2000] if ad_copy else "광고 레퍼런스"}}]
    }

    # 2. 레퍼런스 링크 (URL)
    if reference_url and (not db_props or "레퍼런스 링크" in db_props):
        properties["레퍼런스 링크"] = {"url": reference_url}

    # 3. 광고 계정명 / 브랜드 (Rich Text)
    account_val = account_name if account_name else brand
    if account_val:
        if db_props:
            if "광고 계정명" in db_props:
                properties["광고 계정명"] = {"rich_text": [{"text": {"content": account_val}}]}
            elif "브랜드" in db_props:
                properties["브랜드"] = {"rich_text": [{"text": {"content": account_val}}]}
            else:
                properties["광고 계정명"] = {"rich_text": [{"text": {"content": account_val}}]}
        else:
            properties["광고 계정명"] = {"rich_text": [{"text": {"content": account_val}}]}

    # 4. 진행 여부 (Select)
    if status and (not db_props or "진행 여부" in db_props):
        properties["진행 여부"] = {"select": {"name": status}}

    # 5. 날짜 (Date)
    if date and (not db_props or "날짜" in db_props):
        properties["날짜"] = {"date": {"start": date}}

    # 6. 키워드 (Rich Text)
    if keyword and (not db_props or "키워드" in db_props):
        properties["키워드"] = {"rich_text": [{"text": {"content": keyword}}]}

    # 키워드와 페이지명을 content에 추가 (있으면)
    children = []
    if keyword or page_name:
        info_parts = []
        if page_name:
            info_parts.append(f"📌 광고주: {page_name}")
        if keyword:
            info_parts.append(f"🔍 검색 키워드: {keyword}")
        children.append({
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": "\n".join(info_parts)}}],
                "icon": {"emoji": "📸"},
                "color": "blue_background",
            }
        })

    payload = {
        "parent": {"database_id": db_id},
        "properties": properties,
        "children": children,
    }

    resp = requests.post(url, headers=get_notion_headers(token), json=payload, timeout=15)

    if resp.status_code == 200:
        page_url = resp.json().get("url", "")
        return {"ok": True, "url": page_url}
    else:
        err = resp.json()
        return {
            "ok": False,
            "error": err.get("message", f"HTTP {resp.status_code}"),
            "details": err,
        }


def batch_save_to_notion(
    token: str,
    database_id: str,
    items: list,
    default_status: str = "검토중",
) -> dict:
    """
    여러 광고를 한번에 Notion에 저장합니다.

    Args:
        items: [{"ad_copy", "reference_url", "account_name" or "brand", "keyword", "page_name"}, ...]
    Returns:
        {"ok": True, "saved": N, "failed": M}
    """
    saved = 0
    failed = 0
    today = datetime.now().strftime("%Y-%m-%d")

    for item in items:
        result = save_ad_reference_to_notion(
            token=token,
            database_id=database_id,
            ad_copy=item.get("ad_copy", ""),
            reference_url=item.get("reference_url", ""),
            account_name=item.get("account_name", item.get("brand", "")),
            status=default_status,
            date=today,
            keyword=item.get("keyword", ""),
            page_name=item.get("page_name", ""),
        )
        if result["ok"]:
            saved += 1
        else:
            failed += 1

    return {"ok": failed == 0, "saved": saved, "failed": failed}
