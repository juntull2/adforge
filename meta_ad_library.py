"""
Meta Ad Library 조회 모듈 (v2 - 공개 GraphQL 방식)
- Meta 공개 GraphQL 엔드포인트를 활용하여 API 승인 없이 모든 상업 광고 조회
- Graph API 모드 (Access Token 있을 때) / 공개 스크래핑 모드 하이브리드
"""

import re
import json
import time
import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from urllib.parse import quote_plus

# curl_cffi를 이용한 브라우저 핑거프린트 우회
try:
    from curl_cffi import requests as cf_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False

# AdLibrarySearchPaginationQuery의 고정 doc_id (JS 번들에서 추출)
_AD_LIB_DOC_ID = "24922295957467452"


# ─────────────────────────────────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────────────────────────────────

def search_meta_ads(
    keyword: str,
    access_token: str = "",
    country: str = "KR",
    min_days_running: int = 90,
    limit: int = 30,
) -> dict:
    """
    Meta Ad Library에서 키워드로 광고를 검색합니다.

    Returns:
        {
            mode: "scrape" | "api" | "link",
            ads: [...],
            df: DataFrame,
            url: 웹 검색 URL,
            error: 에러 메시지 or None,
        }
    """
    search_url = _build_search_url(keyword, country)

    # 1. 공개 GraphQL 스크래핑 시도 (curl_cffi 필요)
    if CURL_CFFI_AVAILABLE:
        try:
            raw_ads = _scrape_ads_public(keyword, country, limit)
            if raw_ads:
                filtered = _filter_by_duration(raw_ads, min_days_running)
                df = _ads_to_dataframe(filtered)
                return {
                    "mode": "scrape",
                    "ads": filtered,
                    "df": df,
                    "url": search_url,
                    "error": None,
                }
        except Exception as e:
            pass  # 스크래핑 실패 시 아래로 계속

    # 2. Graph API 시도 (Access Token 있을 때)
    if access_token:
        try:
            ads = _fetch_ads_from_api(keyword, access_token, country, min_days_running, limit)
            df = _ads_to_dataframe(ads) if ads else pd.DataFrame()
            return {
                "mode": "api",
                "ads": ads,
                "df": df,
                "url": search_url,
                "error": None,
            }
        except PermissionError as e:
            return {
                "mode": "link",
                "ads": [],
                "df": pd.DataFrame(),
                "url": search_url,
                "error": None,
                "permission_note": str(e),
            }
        except Exception as e:
            pass

    # 3. 링크 모드 (폴백)
    return {
        "mode": "link",
        "ads": [],
        "df": pd.DataFrame(),
        "url": search_url,
        "error": None,
    }


# ─────────────────────────────────────────────────────────────────────
# 공개 GraphQL 스크래핑
# ─────────────────────────────────────────────────────────────────────

def _make_session():
    """브라우저 핑거프린트가 적용된 세션 생성"""
    return cf_requests.Session(impersonate="chrome124")


def _get_page(sess, url, max_retry: int = 2):
    """페이지 GET + /__rd_verify 챌린지 자동 처리"""
    hdrs = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Upgrade-Insecure-Requests": "1",
    }
    for _ in range(max_retry):
        r = sess.get(url, headers=hdrs, timeout=30)
        if "rd_verify" in r.text or "executeChallenge" in r.text:
            m = re.search(r"fetch\('([^']+)'", r.text)
            if m:
                sess.post(
                    f"https://www.facebook.com{m.group(1)}",
                    headers={"Origin": "https://www.facebook.com", "Content-Length": "0"},
                    timeout=15,
                )
                time.sleep(1.5)
                continue
        if r.status_code == 200:
            return r
        time.sleep(1)
    return r


def _extract_lsd(html: str) -> str:
    """HTML에서 LSD 토큰 추출"""
    for pat in [
        r'"LSD",\[\],\{"token":"([^"]+)"',
        r'"lsd"\s*:\s*"([^"]{6,})"',
        r'"token":"([a-zA-Z0-9_\-]{8,})"',
    ]:
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return ""


def _scrape_ads_public(keyword: str, country: str = "KR", limit: int = 30) -> list:
    """
    Meta Ad Library 공개 GraphQL로 광고를 스크래핑합니다.
    API 승인 없이 모든 상업 광고 접근 가능.
    """
    sess = _make_session()

    # 홈 방문 (쿠키 획득)
    _get_page(sess, "https://www.facebook.com/")
    time.sleep(1.5)

    # Ad Library 페이지 방문 (LSD 토큰 + 쿠키)
    lib_url = (
        f"https://www.facebook.com/ads/library/"
        f"?active_status=active&ad_type=all&country={country}"
        f"&q={quote_plus(keyword)}&media_type=all&search_type=keyword_unordered"
    )
    lib_resp = _get_page(sess, lib_url)

    lsd = _extract_lsd(lib_resp.text)
    if not lsd:
        return []

    # GraphQL 쿼리
    gql_url = "https://www.facebook.com/api/graphql/"
    gql_hdrs = {
        "Accept": "*/*",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://www.facebook.com",
        "Referer": lib_url,
        "X-FB-LSD": lsd,
        "X-ASBD-ID": "198387",
        "X-FB-Friendly-Name": "AdLibrarySearchPaginationQuery",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }

    variables = {
        "activeStatus": "active",
        "adType": "all",
        "bylines": [],
        "collationToken": None,
        "contentLanguages": [],
        "countries": [country],
        "cursor": None,
        "excludedIDs": [],
        "first": min(limit, 30),
        "isTargetedCountry": False,
        "location": None,
        "mediaType": "all",
        "multiCountryFilterMode": None,
        "pageIDs": [],
        "potentialReachInput": None,
        "publisherPlatforms": [],
        "queryString": keyword,
        "regions": [],
        "searchType": "keyword_unordered",
        "sessionID": None,
        "sortData": None,
        "source": None,
        "startDate": None,
        "v": "ed3774",
        "viewAllPageID": None,
    }

    form = {
        "lsd": lsd,
        "variables": json.dumps(variables),
        "doc_id": _AD_LIB_DOC_ID,
        "__comet_req": "15",
        "__a": "1",
    }

    r = sess.post(gql_url, data=form, headers=gql_hdrs, timeout=25)
    if r.status_code != 200:
        return []

    try:
        data = r.json()
    except Exception:
        return []

    # 응답 파싱
    connection = (
        data.get("data", {})
        .get("ad_library_main", {})
        .get("search_results_connection", {})
    )
    if not connection:
        return []

    edges = connection.get("edges", [])
    ads = []
    for edge in edges:
        node = edge.get("node", {})
        collated = node.get("collated_results", [])
        for ad in collated:
            ads.append(ad)

    return ads


# ─────────────────────────────────────────────────────────────────────
# 장기 집행 필터링
# ─────────────────────────────────────────────────────────────────────

def _filter_by_duration(ads: list, min_days: int) -> list:
    """광고 시작일 기준으로 min_days 이상 집행된 광고만 필터링합니다."""
    today = datetime.now()
    result = []

    for ad in ads:
        snapshot = ad.get("snapshot", {})

        # start_date는 Unix timestamp(정수)로 옴
        start_val = ad.get("start_date") or snapshot.get("creation_time")

        if start_val is None:
            ad["_running_days"] = 0
            if min_days == 0:
                result.append(ad)
            continue

        try:
            if isinstance(start_val, (int, float)):
                start_dt = datetime.fromtimestamp(int(start_val))
            else:
                start_dt = datetime.strptime(str(start_val)[:10], "%Y-%m-%d")

            running_days = (today - start_dt).days
            ad["_running_days"] = running_days

            if running_days >= min_days:
                result.append(ad)
        except Exception:
            ad["_running_days"] = 0
            if min_days == 0:
                result.append(ad)

    # 오래된 순 정렬
    result.sort(key=lambda x: x.get("_running_days", 0), reverse=True)
    return result


# ─────────────────────────────────────────────────────────────────────
# DataFrame 변환
# ─────────────────────────────────────────────────────────────────────

def _ads_to_dataframe(ads: list) -> pd.DataFrame:
    """스크래핑 결과 또는 API 결과를 통일된 DataFrame으로 변환합니다."""
    rows = []
    for ad in ads:
        snapshot = ad.get("snapshot", {})

        # page_name: 루트 레벨 우선, 없으면 snapshot에서
        page_name = ad.get("page_name") or snapshot.get("page_name", "")

        body = snapshot.get("body", {})
        body_text = body.get("text", "") if isinstance(body, dict) else str(body)
        body_text = body_text.replace("\n", " ").strip()
        body_preview = body_text[:80] + "..." if len(body_text) > 80 else body_text

        cta = snapshot.get("cta_text", "")

        # 시작일: Unix timestamp → 날짜 문자열 변환
        start_val = ad.get("start_date") or snapshot.get("creation_time")
        if isinstance(start_val, (int, float)):
            start_date = datetime.fromtimestamp(int(start_val)).strftime("%Y-%m-%d")
        elif start_val:
            start_date = str(start_val)[:10]
        else:
            start_date = ""

        running_days = ad.get("_running_days", 0)

        # 광고 보기 URL (Meta 광고 라이브러리 직접 링크)
        ad_id = ad.get("ad_archive_id", "")
        if ad_id:
            snapshot_url = f"https://www.facebook.com/ads/library/?id={ad_id}"
        else:
            snapshot_url = ad.get("ad_snapshot_url", "")

        # 게시 플랫폼
        platforms = ad.get("publisher_platform", [])
        if isinstance(platforms, list):
            platform_str = ", ".join(platforms)
        else:
            platform_str = str(platforms) if platforms else ""

        rows.append({
            "페이지명": page_name,
            "광고 카피": body_preview,
            "CTA": cta,
            "집행 시작일": start_date,
            "집행 기간": f"{running_days}일째" if running_days > 0 else "알 수 없음",
            "게시 플랫폼": platform_str,
            "광고 보기": snapshot_url,
        })

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────
# URL 헬퍼
# ─────────────────────────────────────────────────────────────────────

def _build_search_url(keyword: str, country: str = "KR") -> str:
    encoded_kw = quote_plus(keyword)
    return (
        f"https://www.facebook.com/ads/library/"
        f"?active_status=active&ad_type=all&country={country}"
        f"&q={encoded_kw}&media_type=all&search_type=keyword_unordered"
    )


def _build_search_url_sorted(keyword: str, country: str = "KR") -> str:
    encoded_kw = quote_plus(keyword)
    return (
        f"https://www.facebook.com/ads/library/"
        f"?active_status=active&ad_type=all&country={country}"
        f"&q={encoded_kw}&media_type=all&search_type=keyword_unordered"
        f"&sort_data[direction]=asc&sort_data[mode]=relevancy_monthly_grouped"
    )


# ─────────────────────────────────────────────────────────────────────
# Graph API (fallback)
# ─────────────────────────────────────────────────────────────────────

def _fetch_ads_from_api(
    keyword: str,
    access_token: str,
    country: str = "KR",
    min_days_running: int = 90,
    limit: int = 50,
) -> list:
    base_url = "https://graph.facebook.com/v20.0/ads_archive"
    cutoff_date = (datetime.now() - timedelta(days=min_days_running)).strftime("%Y-%m-%d")

    params = {
        "search_terms": keyword,
        "ad_reached_countries": f'["{country}"]',
        "ad_active_status": "ACTIVE",
        "ad_delivery_date_min": cutoff_date,
        "fields": "id,page_name,ad_delivery_start_time,ad_creative_bodies,ad_creative_link_titles,ad_snapshot_url,publisher_platforms",
        "limit": min(limit, 50),
        "access_token": access_token,
    }

    resp = requests.get(base_url, params=params, timeout=30)

    if resp.status_code == 400:
        error_data = resp.json().get("error", {})
        error_msg = error_data.get("message", "")
        if "permission" in error_msg.lower():
            raise PermissionError("Meta Ad Library API 권한 부족")
        raise Exception(f"API 오류: {error_msg}")

    resp.raise_for_status()
    data = resp.json()

    # API 응답을 공통 형식으로 변환
    ads = []
    for item in data.get("data", []):
        start_str = item.get("ad_delivery_start_time", "")[:10]
        try:
            start_dt = datetime.strptime(start_str, "%Y-%m-%d")
            running = (datetime.now() - start_dt).days
        except Exception:
            running = 0

        if running < min_days_running:
            continue

        bodies = item.get("ad_creative_bodies", [])
        body_text = bodies[0] if bodies else ""
        item["_running_days"] = running
        item["snapshot"] = {
            "page_name": item.get("page_name", ""),
            "body": {"text": body_text},
            "creation_time": start_str,
        }
        item["ad_archive_id"] = item.get("id", "")
        ads.append(item)

    ads.sort(key=lambda x: x.get("_running_days", 0), reverse=True)
    return ads
