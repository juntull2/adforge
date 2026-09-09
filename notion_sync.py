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
    landing_url: str = "",
    account_url: str = "",
) -> dict:
    """
    광고 레퍼런스 데이터를 Notion 데이터베이스에 새 항목으로 저장합니다.

    Args:
        token: Notion Integration Token
        database_id: 대상 데이터베이스 ID
        ad_copy: 광고 카피 원문
        reference_url: 레퍼런스 링크 (구글 드라이브 또는 메타 광고 링크)
        account_name: 광고 계정명 (기존 brand도 지원)
        status: 진행 여부 (검토중/진행/보류/완료)
        date: 게재일 / 날짜 (YYYY-MM-DD)
        keyword: 검색 키워드 (선택)
        page_name: 광고 페이지명 (선택)
        brand: 이전 호환용 브랜드명
        title: 페이지 제목 (Title 컬럼용. 없으면 ad_copy 또는 조합형 생성)
        media_type: 소재 유형 (영상, 이미지, 캐러셀 등)
        landing_url: 자사몰 / 랜딩페이지 URL (연결링크)
        account_url: 광고 계정 메타 라이브러리 URL (클릭 시 이동할 링크)

    Returns:
        {"ok": True, "url": 노션페이지URL} or {"ok": False, "error": 메시지}
    """
    db_id = database_id.replace("-", "")
    url = f"{NOTION_API_BASE}/pages"

    # 유효하지 않은 URL 문자열 처리
    if reference_url in ("None", "nan", "", "NaN"):
        reference_url = None
    if landing_url in ("None", "nan", "", "NaN"):
        landing_url = None
    if account_url in ("None", "nan", "", "NaN"):
        account_url = None

    # 대상 DB 프로퍼티 스키마 조회
    db_props = get_database_properties(token, database_id)

    properties = {}

    # 1. Title (제목 / 광고 카피) 컬럼 감지 및 설정
    title_col = None
    if db_props:
        for col_name, col_meta in db_props.items():
            if col_meta.get("type") == "title":
                title_col = col_name
                break
    if not title_col:
        title_col = "광고 카피" if (db_props and "광고 카피" in db_props) else ("제목" if (db_props and "제목" in db_props) else "광고 카피")

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

    # 2. 레퍼런스링크 (구글 드라이브 또는 메타 광고 URL)
    ref_col = None
    if db_props:
        for cand in ("레퍼런스링크", "레퍼런스 링크", "레퍼런스"):
            if cand in db_props and db_props[cand].get("type") == "url":
                ref_col = cand
                break
    else:
        ref_col = "레퍼런스링크"

    if reference_url and (not db_props or (ref_col and ref_col in db_props)):
        properties[ref_col] = {"url": reference_url}

    # 3. 연결링크 (자사몰 / 랜딩페이지 URL)
    landing_col = None
    if db_props:
        for cand in ("연결링크", "연결 링크", "자사몰", "랜딩페이지", "사이트 링크", "링크"):
            if cand in db_props and db_props[cand].get("type") == "url":
                landing_col = cand
                break
    else:
        landing_col = "연결링크"

    if landing_url and (not db_props or (landing_col and landing_col in db_props)):
        properties[landing_col] = {"url": landing_url}

    # 4. 광고 계정명 / 브랜드 (Rich Text - 클릭 가능한 하이퍼링크 지원)
    if account_val:
        acc_col = None
        if db_props:
            for cand in ("광고 계정명", "광고계정명", "브랜드"):
                if cand in db_props:
                    acc_col = cand
                    break
        else:
            acc_col = "광고 계정명"
        if acc_col:
            final_account_url = account_url
            if not final_account_url or not str(final_account_url).startswith("http"):
                from urllib.parse import quote_plus
                final_account_url = f"https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=KR&q={quote_plus(account_val)}&search_type=keyword_unordered"

            text_payload = {
                "content": account_val,
                "link": {"url": final_account_url}
            }
            properties[acc_col] = {"rich_text": [{"type": "text", "text": text_payload}]}

    # 5. 진행 여부 (Select)
    status_col = None
    if db_props:
        for cand in ("진행 여부", "진행여부", "상태"):
            if cand in db_props and db_props[cand].get("type") == "select":
                status_col = cand
                break
    else:
        status_col = "진행 여부"

    if status and (not db_props or (status_col and status_col in db_props)):
        properties[status_col] = {"select": {"name": status}}

    # 6. 날짜 / 게재일 / 개제일 (Date)
    if date:
        date_col = None
        if db_props:
            for cand in ("날짜", "개제일", "게재일", "집행일"):
                if cand in db_props and db_props[cand].get("type") == "date":
                    date_col = cand
                    break
            if not date_col:
                for c_name, c_meta in db_props.items():
                    if c_meta.get("type") == "date":
                        date_col = c_name
                        break
        else:
            date_col = "날짜"

        if date_col and (not db_props or date_col in db_props):
            properties[date_col] = {"date": {"start": date}}

    # 7. 소재 유형 (Select) - 만약 DB에 존재하면 설정
    if media_type and db_props:
        type_col = None
        for candidate in ("소재 유형", "소재형태", "유형", "소재구분", "미디어 타입"):
            if candidate in db_props and db_props[candidate].get("type") == "select":
                type_col = candidate
                break
        if type_col and type_col in db_props:
            properties[type_col] = {"select": {"name": media_type}}

    # 8. 키워드 (Rich Text)
    kw_col = None
    if db_props:
        for cand in ("키워드", "검색 키워드", "검색어"):
            if cand in db_props:
                kw_col = cand
                break
    else:
        kw_col = "키워드"

    if keyword and (not db_props or (kw_col and kw_col in db_props)):
        properties[kw_col] = {"rich_text": [{"text": {"content": keyword}}]}

    # 본문 콜아웃 블록 (상세 정보 보존)
    children = []
    info_parts = []
    if account_val:
        info_parts.append(f"📌 광고주: {account_val}")
    if media_type:
        info_parts.append(f"🎬 소재 유형: {media_type}")
    if date:
        info_parts.append(f"📅 날짜: {date}")
    if landing_url:
        info_parts.append(f"🔗 연결링크(자사몰): {landing_url}")
    if reference_url:
        info_parts.append(f"📁 레퍼런스링크: {reference_url}")
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
    }
    if children:
        payload["children"] = children

    resp = requests.post(url, headers=get_notion_headers(token), json=payload, timeout=15)

    if resp.status_code in (200, 201):
        data = resp.json()
        return {"ok": True, "url": data.get("url", "")}
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
        items: [{"ad_copy", "reference_url", "account_name", "landing_url", "keyword", "page_name"}, ...]
    Returns:
        {"ok": True, "saved": N, "failed": M}
    """
    saved = 0
    failed = 0
    today = datetime.now().strftime("%Y-%m-%d")

    for item in items:
        item_date = item.get("date") or item.get("날짜") or item.get("게재일") or item.get("개제일") or today
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
            landing_url=item.get("landing_url", item.get("연결링크", "")),
            account_url=item.get("account_url", item.get("_page_library_url", "")),
        )
        if result["ok"]:
            saved += 1
        else:
            failed += 1

    return {"ok": failed == 0, "saved": saved, "failed": failed}
