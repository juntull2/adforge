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

def clean_ad_copy(text: str, brand: str = "") -> str:
    """
    광고 카피에서 {{product.brand}} 등 템플릿 변수 및 None, 무의미한 문자를 정제합니다.
    """
    if not text or str(text).lower() in ("none", "nan", "null"):
        return ""
    cleaned = str(text)
    # {{product.brand}} 등 치환
    if brand:
        cleaned = re.sub(r"\{\{\s*product\.brand\s*\}\}", brand, cleaned, flags=re.IGNORECASE)
    # 남은 {{...}} 템플릿 변수 제거
    cleaned = re.sub(r"\{\{[^}]+\}\}", "", cleaned)
    # 줄바꿈 및 다중 공백 정리
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned.lower() in ("none", "nan", "null", ""):
        return ""
    return cleaned


def detect_media_type(ad: dict, snapshot: dict) -> str:
    """
    Meta Ad Library 데이터로부터 미디어 유형('영상', '이미지', '캐러셀')을 정밀하게 판별합니다.
    - 영상: 동영상 재생이 가능한 모든 광고 (릴스, 숏폼, 피드 비디오, 비디오 카드 등)
    - 캐러셀: 2장 이상의 다중 이미지/카드뉴스 슬라이드 광고
    - 이미지: 단일 이미지, 단일 DCO/DPA 카드, 정지 이미지 배너 광고
    """
    if not snapshot and not ad:
        return "이미지"

    # 1. 명시적 비디오 지표 확인 (영상 확정)
    videos = snapshot.get("videos") or []
    if isinstance(videos, list) and len(videos) > 0:
        return "영상"

    extra_videos = snapshot.get("extra_videos") or []
    if isinstance(extra_videos, list) and len(extra_videos) > 0:
        return "영상"

    if snapshot.get("video_hd_url") or snapshot.get("video_sd_url"):
        return "영상"

    display_fmt = str(snapshot.get("display_format") or "").upper()
    media_fmt = str(ad.get("media_type") or "").upper()
    if "VIDEO" in display_fmt or "VIDEO" in media_fmt:
        return "영상"

    # 2. cards (카드/슬라이드) 내부 미디어 정밀 검사
    cards = snapshot.get("cards") or []
    has_card_video = False
    has_card_image = False
    card_count = 0

    if isinstance(cards, list) and len(cards) > 0:
        card_count = len(cards)
        for card in cards:
            if not isinstance(card, dict):
                continue
            # 카드에 실제 비디오 URL이 있는지 확인
            if card.get("video_hd_url") or card.get("video_sd_url"):
                has_card_video = True
                break
            # 카드에 이미지 URL이 있는지 확인
            if (
                card.get("resized_image_url")
                or card.get("original_image_url")
                or card.get("image_url")
                or card.get("watermarked_resized_image_url")
            ):
                has_card_image = True

    # 카드 내에 비디오가 하나라도 있으면 영상
    if has_card_video:
        return "영상"

    # 3. 다중 카드(캐러셀 / 카드뉴스) 검사
    if card_count > 1:
        return "캐러셀"

    # 4. 이미지(단일 이미지 / 단일 카드 / DCO / DPA) 검사
    images = snapshot.get("images") or []
    if isinstance(images, list) and len(images) > 0:
        return "이미지"

    extra_images = snapshot.get("extra_images") or []
    if isinstance(extra_images, list) and len(extra_images) > 0:
        return "이미지"

    if snapshot.get("resized_image_url") or snapshot.get("original_image_url") or snapshot.get("image_url"):
        return "이미지"

    if has_card_image or card_count == 1:
        return "이미지"

    if any(k in display_fmt for k in ["IMAGE", "PHOTO", "DCO", "DPA", "CAROUSEL"]):
        if "CAROUSEL" in display_fmt and card_count > 1:
            return "캐러셀"
        return "이미지"

    if "IMAGE" in media_fmt or "PHOTO" in media_fmt:
        return "이미지"

    # 5. 최종 폴백: 비디오 단서가 전혀 없으면 안전하게 "이미지"
    return "이미지"


def _clean_landing_url(url: str) -> str:
    """페이스북 리다이렉트(l.facebook.com/l.php?u=...) 및 트래킹 파라미터를 정리하여 깨끗한 자사몰 원본 URL 반환"""
    if not url or not isinstance(url, str):
        return ""
    url = url.strip()
    if "l.facebook.com" in url or "lm.facebook.com" in url:
        try:
            from urllib.parse import urlparse, parse_qs, unquote
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            if "u" in qs:
                url = unquote(qs["u"][0])
        except Exception:
            pass
    return url


def _extract_landing_url(snapshot: dict) -> str:
    """광고 스냅샷에서 자사몰 / 랜딩페이지 URL을 추출합니다."""
    if not snapshot:
        return ""

    candidates = [
        snapshot.get("link_url"),
        snapshot.get("cta_url"),
    ]

    cards = snapshot.get("cards") or []
    if isinstance(cards, list):
        for card in cards:
            if isinstance(card, dict) and card.get("link_url"):
                candidates.append(card.get("link_url"))
            if isinstance(card, dict) and card.get("cta_url"):
                candidates.append(card.get("cta_url"))

    for c in candidates:
        if c and isinstance(c, str) and c.startswith("http"):
            return _clean_landing_url(c)

    # fallback: caption이 URL 형태인 경우
    caption = snapshot.get("caption")
    if caption and isinstance(caption, str) and ("http://" in caption or "https://" in caption):
        return _clean_landing_url(caption)

    return ""


def _extract_video_download_url(ad: dict, snapshot: dict) -> str:
    """광고 데이터에서 원본 비디오 mp4 다운로드 URL을 추출합니다."""
    if not snapshot and not ad:
        return ""

    # 1. snapshot 직접 비디오 URL (HD 우선)
    if snapshot.get("video_hd_url"):
        return snapshot["video_hd_url"]
    if snapshot.get("video_sd_url"):
        return snapshot["video_sd_url"]

    # 2. snapshot.videos 리스트
    videos = snapshot.get("videos") or []
    if isinstance(videos, list):
        for v in videos:
            if isinstance(v, dict):
                if v.get("video_hd_url"):
                    return v["video_hd_url"]
                if v.get("video_sd_url"):
                    return v["video_sd_url"]

    # 3. cards 내부 비디오
    cards = snapshot.get("cards") or []
    if isinstance(cards, list):
        for card in cards:
            if isinstance(card, dict):
                if card.get("video_hd_url"):
                    return card["video_hd_url"]
                if card.get("video_sd_url"):
                    return card["video_sd_url"]

    # 4. extra_videos
    extra_videos = snapshot.get("extra_videos") or []
    if isinstance(extra_videos, list):
        for v in extra_videos:
            if isinstance(v, dict):
                if v.get("video_hd_url"):
                    return v["video_hd_url"]
                if v.get("video_sd_url"):
                    return v["video_sd_url"]

    return ""


def _ads_to_dataframe(ads: list) -> pd.DataFrame:
    """스크래핑 결과 또는 API 결과를 통일된 DataFrame으로 변환합니다."""
    rows = []
    for ad in ads:
        snapshot = ad.get("snapshot", {})

        # page_name: 루트 레벨 우선, 없으면 snapshot에서
        page_name = ad.get("page_name") or snapshot.get("page_name", "")

        body = snapshot.get("body", {})
        body_text = body.get("text", "") if isinstance(body, dict) else str(body)
        cleaned_body = clean_ad_copy(body_text, brand=page_name)
        body_preview = cleaned_body[:80] + "..." if len(cleaned_body) > 80 else cleaned_body

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

        # 미디어 유형 감지
        media_type = detect_media_type(ad, snapshot)

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

        landing_url = _extract_landing_url(snapshot)
        video_download_url = _extract_video_download_url(ad, snapshot)

        page_id = str(ad.get("page_id") or snapshot.get("page_id", "")).strip()
        if page_id:
            page_library_url = f"https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=KR&view_all_page_id={page_id}"
        elif page_name:
            page_library_url = f"https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=KR&q={quote_plus(page_name)}&search_type=keyword_unordered"
        else:
            page_library_url = ""

        rows.append({
            "페이지명": page_name,
            "page_id": page_id,
            "_page_library_url": page_library_url,
            "소재 유형": media_type,
            "광고 카피": body_preview,
            "광고 카피 원문": cleaned_body,
            "CTA": cta,
            "집행 시작일": start_date,
            "집행 기간": f"{running_days}일째" if running_days > 0 else "알 수 없음",
            "게시 플랫폼": platform_str,
            "광고 보기": snapshot_url,
            "연결링크": landing_url,
            "_video_url": video_download_url,
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
