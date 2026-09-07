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
    ad_copy: str = "",
    reference_url: str = "",
    account_name: str = "",
    status: str = "검토중",
    date: str = "",
    keyword: str = "",
    page_name: str = "",
    brand: str = "",
    title: str = "",
    media_type: str = "",
) -> dict:
    """
    광고 레퍼런스 데이터를 Notion 데이터베이스에 새 항목으로 저장합니다.

    Args:
        token: Notion Integration Token
        database_id: 대상 데이터베이스 ID
        ad_copy: 광고 카피 원문
        reference_url: 레퍼런스 링크
        account_name: 광고 계정명 (기존 brand도 지원)
        status: 진행 여부 (검토중/진행/보류/완료)
        date: 게재일 / 날짜 (YYYY-MM-DD)
        keyword: 검색 키워드 (선택)
        page_name: 광고 페이지명 (선택)
        brand: 이전 호환용 브랜드명
        title: 페이지 제목 (Title 컬럼용. 없으면 ad_copy 또는 조합형 생성)
        media_type: 소재 유형 (영상, 이미지, 캐러셀 등)

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

    # 1. Title (제목) 컬럼 감지 및 설정
    title_col = None
    if db_props:
        for col_name, col_meta in db_props.items():
            if col_meta.get("type") == "title":
                title_col = col_name
                break
    if not title_col:
        title_col = "제목" if (db_props and "제목" in db_props) else ("광고 카피" if (db_props and "광고 카피" in db_props) else "제목")

    # 제목 결정 (우선순위: title > 정제된 ad_copy > 브랜드/날짜 조합)
    account_val = account_name if account_name else (page_name if page_name else brand)
    final_title = title.strip() if title else ""
    if not final_title:
        if ad_copy and ad_copy.lower() not in ("none", "nan", "null", ""):
            final_title = ad_copy[:100]
        elif account_val:
            prefix = f"[{media_type}] " if media_type else ""
            suffix = f" ({date})" if date else " 레퍼런스"
            final_title = f"{prefix}{account_val}{suffix}"
        else:
            final_title = f"[{media_type or '소재'}] 광고 레퍼런스"

    properties[title_col] = {
        "title": [{"text": {"content": final_title[:2000]}}]
    }

    # 2. 레퍼런스 링크 (URL)
    if reference_url and (not db_props or "레퍼런스 링크" in db_props):
        properties["레퍼런스 링크"] = {"url": reference_url}

    # 3. 광고 계정명 / 브랜드 (Rich Text)
    if account_val:
        if db_props:
            if "광고 계정명" in db_props:
                properties["광고 계정명"] = {"rich_text": [{"text": {"content": account_val}}]}
            elif "브랜드" in db_props:
                properties["브랜드"] = {"rich_text": [{"text": {"content": account_val}}]}
        else:
            properties["광고 계정명"] = {"rich_text": [{"text": {"content": account_val}}]}

    # 4. 진행 여부 (Select)
    if status and (not db_props or "진행 여부" in db_props):
        properties["진행 여부"] = {"select": {"name": status}}

    # 5. 게재일 / 날짜 (Date)
    if date:
        date_col = None
        if db_props:
            if "게재일" in db_props:
                date_col = "게재일"
            elif "날짜" in db_props:
                date_col = "날짜"
            else:
                for c_name, c_meta in db_props.items():
                    if c_meta.get("type") == "date":
                        date_col = c_name
                        break
        else:
            date_col = "게재일"

        if date_col and (not db_props or date_col in db_props):
            properties[date_col] = {"date": {"start": date}}

    # 6. 소재 유형 (Select)
    if media_type:
        type_col = None
        if db_props:
            for candidate in ("소재 유형", "소재형태", "유형", "소재구분", "미디어 타입"):
                if candidate in db_props and db_props[candidate].get("type") == "select":
                    type_col = candidate
                    break
        else:
            type_col = "소재 유형"

        if type_col and (not db_props or type_col in db_props):
            properties[type_col] = {"select": {"name": media_type}}

    # 7. 키워드 (Rich Text)
    if keyword and (not db_props or "키워드" in db_props):
        properties["키워드"] = {"rich_text": [{"text": {"content": keyword}}]}

    # 8. 별도 '광고 카피' rich_text 컬럼이 있는 경우
    if ad_copy and db_props and "광고 카피" in db_props and title_col != "광고 카피":
        if db_props["광고 카피"].get("type") == "rich_text":
            properties["광고 카피"] = {"rich_text": [{"text": {"content": ad_copy[:2000]}}]}

    # 본문 콜아웃 블록 (상세 정보 보존)
    children = []
    info_parts = []
    if account_val:
        info_parts.append(f"📌 광고주: {account_val}")
    if media_type:
        info_parts.append(f"🎬 소재 유형: {media_type}")
    if date:
        info_parts.append(f"📅 게재일: {date}")
    if keyword:
        info_parts.append(f"🔍 검색 키워드: {keyword}")
    if ad_copy and ad_copy.lower() not in ("none", "nan", "null", ""):
        info_parts.append(f"📝 광고 카피:\n{ad_copy}")

    if info_parts:
        children.append({
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": "\n\n".join(info_parts)}}],
                "icon": {"emoji": "🎬" if media_type == "영상" else "📸"},
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
        item_date = item.get("date") or item.get("게재일") or today
        result = save_ad_reference_to_notion(
            token=token,
            database_id=database_id,
            ad_copy=item.get("ad_copy", ""),
            reference_url=item.get("reference_url", ""),
            account_name=item.get("account_name", item.get("brand", "")),
            status=item.get("status", default_status),
            date=str(item_date),
            keyword=item.get("keyword", ""),
            page_name=item.get("page_name", ""),
            title=item.get("title", ""),
            media_type=item.get("media_type", item.get("소재 유형", "")),
        )
        if result["ok"]:
            saved += 1
        else:
            failed += 1

    return {"ok": failed == 0, "saved": saved, "failed": failed}
