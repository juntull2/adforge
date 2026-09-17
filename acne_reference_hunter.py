"""
A급 레퍼런스 탐색기 (여드름 카테고리)
=========================================
- 메타 광고 라이브러리 스크래핑: 60일+ 집행 영상 광고 수집
- 네이버 검색광고 API: 브랜드명 실제 월간 검색량 조회
- 네이버 데이터랩: 1년 트렌드 → 최근 2개월 내 1만↑ 급상승 감지
- 협력광고 / 대기업 / 나레이션 없음 필터
- 숨겨진 연결 계정(페이지) 탐색
"""

import os
import sys
import json
import time
import re
import hmac
import hashlib
import base64
from datetime import datetime
from urllib.parse import urlparse

import pandas as pd

# 로컬 모듈 (c:\adforge 기준)
sys.path.insert(0, os.path.dirname(__file__))

from meta_ad_library import (
    _scrape_ads_public,
    _filter_by_duration,
    detect_media_type,
    _extract_landing_url,
    clean_ad_copy,
)
from naver_datalab import get_datalab_trends
from naver_scraper import get_naver_search_volume

# ─────────────────────────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────────────────────────

ACNE_KEYWORDS = [
    "여드름",
    "여드름 크림",
    "여드름 패치",
    "여드름 앰플",
    "여드름 세럼",
    "여드름 클렌저",
    "여드름 토너",
    "트러블 스킨케어",
    "트러블 크림",
    "여드름 화장품",
]

COLLAB_KEYWORDS = [
    "협력", "협찬", "파트너", "체험단", "공동구매", "제휴", "콜라보", "collab",
]

MAJOR_BRANDS = [
    "아모레퍼시픽", "LG생활건강", "LG", "삼성", "이니스프리", "설화수", "헤라", "라네즈",
    "에뛰드", "토니모리", "네이처리퍼블릭", "더페이스샵", "미샤", "뷰티풀라이프",
    "닥터지", "스킨푸드", "에이프릴스킨", "클리오", "롬앤", "3ce",
    "메디큐브", "에스트라", "동국제약", "한국콜마", "코스맥스",
    "JMsolution", "제이엠솔루션", "CNP", "차앤박",
]

MIN_COPY_LEN_FOR_NARRATION = 15   # 나레이션 추정 최소 카피 글자 수
SPIKE_RECENT_MONTHS = 2           # 최근 N개월 내 급상승 감지
SPIKE_MIN_VOLUME = 10_000         # 실제 월간 검색량 기준 1만
MIN_RUNNING_DAYS = 60             # 메타 최소 집행 기간 (일)
HIDDEN_ACCOUNT_AD_LIMIT = 10      # 숨겨진 계정 탐색 시 수집 광고 수


# ─────────────────────────────────────────────────────────────────
# 환경변수 로드
# ─────────────────────────────────────────────────────────────────

def _load_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())


# ─────────────────────────────────────────────────────────────────
# Step 1: 메타 광고 수집
# ─────────────────────────────────────────────────────────────────

def collect_meta_ads(
    keywords=ACNE_KEYWORDS,
    min_days=MIN_RUNNING_DAYS,
    limit_per_keyword=30,
):
    print(f"\n{'='*60}")
    print("📡 [Step 1] 메타 광고 라이브러리 스크래핑")
    print(f"  키워드 {len(keywords)}개 | 최소 집행 {min_days}일 이상")
    print(f"{'='*60}")

    all_ads = []
    seen_ad_ids = set()

    for kw in keywords:
        print(f"  🔍 '{kw}' 검색 중...")
        try:
            raw = _scrape_ads_public(kw, country="KR", limit=limit_per_keyword)
            filtered = _filter_by_duration(raw, min_days=min_days)
            new_count = 0
            for ad in filtered:
                ad_id = ad.get("ad_archive_id", "") or str(id(ad))
                if ad_id not in seen_ad_ids:
                    seen_ad_ids.add(ad_id)
                    ad["_search_keyword"] = kw
                    all_ads.append(ad)
                    new_count += 1
            print(f"    → {len(raw)}개 수집 / {len(filtered)}개 {min_days}일↑ / {new_count}개 신규")
        except Exception as e:
            print(f"    ⚠️  스크래핑 실패: {e}")
        time.sleep(2.0)

    print(f"\n  ✅ 총 {len(all_ads)}개 광고 수집 완료")
    return all_ads


# ─────────────────────────────────────────────────────────────────
# Step 2: 영상 + 나레이션 추정 필터
# ─────────────────────────────────────────────────────────────────

def filter_narration_video(ads):
    print(f"\n{'='*60}")
    print("🎬 [Step 2] 영상 + 나레이션 추정 필터")
    print(f"{'='*60}")

    result = []
    for ad in ads:
        snapshot = ad.get("snapshot", {})
        media_type = detect_media_type(ad, snapshot)
        if media_type != "영상":
            continue

        body = snapshot.get("body", {})
        body_text = body.get("text", "") if isinstance(body, dict) else str(body)
        clean_text = re.sub(r"\{\{[^}]+\}\}", "", body_text).strip()

        if len(clean_text) >= MIN_COPY_LEN_FOR_NARRATION:
            ad["_media_type"] = "영상"
            ad["_body_text"] = clean_text
            result.append(ad)

    print(f"  ✅ {len(result)}개 통과 (영상 + 나레이션 추정)")
    return result


# ─────────────────────────────────────────────────────────────────
# Step 3: 협력광고 / 대기업 필터
# ─────────────────────────────────────────────────────────────────

def filter_collab_and_major(ads):
    print(f"\n{'='*60}")
    print("🚫 [Step 3] 협력광고 / 대기업 필터")
    print(f"{'='*60}")

    result = []
    excluded_collab = 0
    excluded_major = 0

    for ad in ads:
        snapshot = ad.get("snapshot", {})
        page_name = (ad.get("page_name") or snapshot.get("page_name", "")).lower()
        body_text = ad.get("_body_text", "").lower()
        combined = page_name + " " + body_text

        if any(kw in combined for kw in COLLAB_KEYWORDS):
            excluded_collab += 1
            continue

        page_name_orig = (ad.get("page_name") or snapshot.get("page_name", ""))
        if any(brand.lower() in page_name_orig.lower() for brand in MAJOR_BRANDS):
            excluded_major += 1
            continue

        result.append(ad)

    print(f"  제외: 협력광고 {excluded_collab}개 / 대기업 {excluded_major}개")
    print(f"  ✅ {len(result)}개 통과")
    return result


# ─────────────────────────────────────────────────────────────────
# Step 4: 네이버 검색량 + 데이터랩 급상승 판정
# ─────────────────────────────────────────────────────────────────

def _get_monthly_volume(brand_name):
    customer_id    = os.environ.get("NAVER_CUSTOMER_ID", "")
    access_license = os.environ.get("NAVER_ACCESS_LICENSE", "")
    secret_key     = os.environ.get("NAVER_SECRET_KEY", "")

    if not all([customer_id, access_license, secret_key]):
        return {"pc": 0, "mobile": 0, "total": 0}

    names_to_try = [brand_name]
    korean_only = re.sub(r"[^\uAC00-\uD7A3\u3131-\u318E\s]", "", brand_name).strip()
    if korean_only and korean_only != brand_name:
        names_to_try.append(korean_only)

    best = {"pc": 0, "mobile": 0, "total": 0}
    for name in names_to_try:
        if not name:
            continue
        res = get_naver_search_volume(name, customer_id, access_license, secret_key)
        if res["total"] > best["total"]:
            best = res
        time.sleep(0.3)

    return best


def _detect_spike_from_datalab(brand_name, current_volume):
    result = {
        "spike_detected": False,
        "spike_month": None,
        "spike_volume_est": 0,
        "max_1y_index": 0.0,
        "recent_2m_max_index": 0.0,
    }

    try:
        dl = get_datalab_trends(brand_name, total_volume=current_volume)
        if not dl.get("ok"):
            return result

        df_1y = dl.get("df_1y")
        if df_1y is None or df_1y.empty:
            return result

        recent_index = float(df_1y.iloc[-1]["검색지수"])

        if recent_index <= 0 or current_volume <= 0:
            scale = 1.0
            threshold_index = 70.0
        else:
            scale = current_volume / recent_index
            threshold_index = SPIKE_MIN_VOLUME / scale

        result["max_1y_index"] = float(df_1y["검색지수"].max())

        recent_rows = df_1y.tail(SPIKE_RECENT_MONTHS)
        result["recent_2m_max_index"] = float(recent_rows["검색지수"].max())

        for _, row in recent_rows.iterrows():
            idx_val = float(row["검색지수"])
            estimated_vol = int(idx_val * scale) if scale > 0 else 0

            if idx_val >= threshold_index or estimated_vol >= SPIKE_MIN_VOLUME:
                result["spike_detected"] = True
                result["spike_month"] = row["월"]
                result["spike_volume_est"] = max(result["spike_volume_est"], estimated_vol or int(idx_val))

    except Exception as e:
        print(f"    ⚠️  데이터랩 조회 실패 ({brand_name}): {e}")

    return result


def filter_search_spike(ads):
    print(f"\n{'='*60}")
    print("📊 [Step 4] 네이버 검색량 급상승 판정")
    print(f"  기준: 최근 {SPIKE_RECENT_MONTHS}개월 내 월간 검색량 {SPIKE_MIN_VOLUME:,} 이상")
    print(f"{'='*60}")

    brand_cache = {}

    def _get_brand_result(page_name):
        if page_name not in brand_cache:
            print(f"  🔎 '{page_name}' 검색량 조회 중...")
            vol = _get_monthly_volume(page_name)
            spike = _detect_spike_from_datalab(page_name, vol["total"])
            brand_cache[page_name] = {**vol, **spike}
            status = "✅ 급상승" if spike["spike_detected"] else "❌ 미충족"
            print(
                f"    현재 검색량: {vol['total']:,} | "
                f"최근2개월 지수MAX: {spike['recent_2m_max_index']:.1f} | "
                f"급상승 추정: {spike['spike_volume_est']:,} → {status}"
            )
            time.sleep(0.5)
        return brand_cache[page_name]

    result = []
    for ad in ads:
        snapshot = ad.get("snapshot", {})
        page_name = (ad.get("page_name") or snapshot.get("page_name", "")).strip()
        if not page_name:
            continue

        brand_res = _get_brand_result(page_name)
        ad["_naver_volume"] = brand_res.get("total", 0)
        ad["_spike_detected"] = brand_res.get("spike_detected", False)
        ad["_spike_month"] = brand_res.get("spike_month")
        ad["_spike_volume_est"] = brand_res.get("spike_volume_est", 0)

        if brand_res.get("spike_detected"):
            result.append(ad)

    print(f"\n  ✅ {len(result)}개 통과 (검색량 급상승 확인)")
    return result


# ─────────────────────────────────────────────────────────────────
# Step 5: 숨겨진 연결 계정 탐색
# ─────────────────────────────────────────────────────────────────

def find_hidden_accounts(ads):
    print(f"\n{'='*60}")
    print("🕵️  [Step 5] 숨겨진 연결 계정 탐색")
    print(f"{'='*60}")

    hidden = {}
    processed_pages = set()

    for ad in ads:
        snapshot = ad.get("snapshot", {})
        page_name = (ad.get("page_name") or snapshot.get("page_name", "")).strip()
        page_id = str(ad.get("page_id") or snapshot.get("page_id", "")).strip()

        if not page_name or page_name in processed_pages:
            continue
        processed_pages.add(page_name)

        connected = []
        print(f"  🔗 '{page_name}' 연결 계정 탐색...")

        # 방법 1: 브랜드명 키워드 교차 탐색 → 다른 페이지명 발견
        try:
            related_ads = _scrape_ads_public(page_name, country="KR", limit=HIDDEN_ACCOUNT_AD_LIMIT)
            other_pages = {}
            for r_ad in related_ads:
                r_snap = r_ad.get("snapshot", {})
                r_page = (r_ad.get("page_name") or r_snap.get("page_name", "")).strip()
                r_pid = str(r_ad.get("page_id") or r_snap.get("page_id", "")).strip()
                if r_page and r_page != page_name:
                    other_pages[r_page] = r_pid
            for p, pid in other_pages.items():
                connected.append({"page_name": p, "page_id": pid, "method": "키워드 교차 발견"})
            time.sleep(1.5)
        except Exception as e:
            print(f"    ⚠️  키워드 교차 탐색 오류: {e}")

        # 방법 2: 도메인 기반 크로스 탐색
        landing = _extract_landing_url(snapshot)
        if landing:
            try:
                parsed = urlparse(landing)
                domain = parsed.netloc.replace("www.", "")
                if domain:
                    domain_kw = domain.split(".")[0]
                    domain_ads = _scrape_ads_public(domain_kw, country="KR", limit=10)
                    for d_ad in domain_ads:
                        d_snap = d_ad.get("snapshot", {})
                        d_page = (d_ad.get("page_name") or d_snap.get("page_name", "")).strip()
                        d_pid = str(d_ad.get("page_id") or d_snap.get("page_id", "")).strip()
                        d_landing = _extract_landing_url(d_snap)
                        if d_landing and domain in d_landing and d_page != page_name:
                            if not any(c["page_name"] == d_page for c in connected):
                                connected.append({
                                    "page_name": d_page,
                                    "page_id": d_pid,
                                    "method": f"동일 도메인 ({domain})",
                                })
                    time.sleep(1.5)
            except Exception as e:
                print(f"    ⚠️  도메인 탐색 오류: {e}")

        # 방법 3: 브랜드명 파생 키워드 검색
        core = re.sub(r"[\s\(\)\[\]공식몰스토어샵]", "", page_name)
        derived_keywords = []
        if core and core != page_name:
            derived_keywords.append(core)
        for suffix in ["공식", "공식몰"]:
            derived_keywords.append(page_name + " " + suffix)

        for dk in derived_keywords[:2]:
            try:
                dk_ads = _scrape_ads_public(dk, country="KR", limit=5)
                for dk_ad in dk_ads:
                    dk_snap = dk_ad.get("snapshot", {})
                    dk_page = (dk_ad.get("page_name") or dk_snap.get("page_name", "")).strip()
                    dk_pid = str(dk_ad.get("page_id") or dk_snap.get("page_id", "")).strip()
                    if dk_page and dk_page != page_name and core and core in dk_page:
                        if not any(c["page_name"] == dk_page for c in connected):
                            connected.append({
                                "page_name": dk_page,
                                "page_id": dk_pid,
                                "method": f"브랜드 파생 키워드 ({dk})",
                            })
                time.sleep(1.0)
            except Exception:
                pass

        if connected:
            print(f"    🎯 {len(connected)}개 연결 계정 발견: {[c['page_name'] for c in connected]}")
        else:
            print(f"    - 연결 계정 없음")

        hidden[page_name] = connected
        time.sleep(1.5)

    return hidden


# ─────────────────────────────────────────────────────────────────
# Step 6: 결과 정리 및 저장
# ─────────────────────────────────────────────────────────────────

def build_result(ads, hidden_accounts):
    rows = []
    for ad in ads:
        snapshot = ad.get("snapshot", {})
        page_name = (ad.get("page_name") or snapshot.get("page_name", "")).strip()
        page_id = str(ad.get("page_id") or snapshot.get("page_id", "")).strip()

        ad_id = ad.get("ad_archive_id", "")
        ad_url = f"https://www.facebook.com/ads/library/?id={ad_id}" if ad_id else ""
        page_lib_url = (
            f"https://www.facebook.com/ads/library/?active_status=all&ad_type=all"
            f"&country=KR&view_all_page_id={page_id}" if page_id else ""
        )

        start_val = ad.get("start_date") or snapshot.get("creation_time")
        if isinstance(start_val, (int, float)):
            start_date = datetime.fromtimestamp(int(start_val)).strftime("%Y-%m-%d")
        elif start_val:
            start_date = str(start_val)[:10]
        else:
            start_date = ""

        running_days = ad.get("_running_days", 0)
        body_text = ad.get("_body_text", "")[:120]

        connected = hidden_accounts.get(page_name, [])
        hidden_str = " / ".join([c["page_name"] for c in connected]) if connected else "-"

        rows.append({
            "브랜드(페이지명)": page_name,
            "page_id": page_id,
            "집행 시작일": start_date,
            "집행 기간(일)": running_days,
            "네이버 검색량(현재)": ad.get("_naver_volume", 0),
            "급상승 월": ad.get("_spike_month", ""),
            "급상승 추정 검색량": ad.get("_spike_volume_est", 0),
            "광고 카피 미리보기": body_text,
            "광고 보기 URL": ad_url,
            "페이지 전체 광고": page_lib_url,
            "숨겨진 연결 계정": hidden_str,
            "검색 키워드": ad.get("_search_keyword", ""),
            "랜딩 URL": _extract_landing_url(snapshot),
        })

    df = pd.DataFrame(rows).drop_duplicates(subset=["브랜드(페이지명)", "집행 시작일"])
    df = df.sort_values("집행 기간(일)", ascending=False).reset_index(drop=True)
    return df


def save_results(df, ads, hidden_accounts):
    out_dir = os.path.join(os.path.dirname(__file__), "outputs")
    os.makedirs(out_dir, exist_ok=True)

    date_str = datetime.now().strftime("%Y%m%d_%H%M")
    csv_path = os.path.join(out_dir, f"acne_references_{date_str}.csv")
    json_path = os.path.join(out_dir, f"acne_references_{date_str}.json")

    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    json_data = {
        "generated_at": datetime.now().isoformat(),
        "total_count": len(df),
        "results": df.to_dict(orient="records"),
        "hidden_accounts_detail": hidden_accounts,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    print(f"\n  💾 CSV 저장: {csv_path}")
    print(f"  💾 JSON 저장: {json_path}")
    return csv_path, json_path


def print_final_report(df, hidden_accounts):
    print(f"\n{'='*60}")
    print(f"🏆 A급 레퍼런스 최종 결과: {len(df)}개 발견")
    print(f"{'='*60}")

    if df.empty:
        print("  결과 없음. 조건을 완화하거나 키워드를 추가해 보세요.")
        return

    for i, row in df.iterrows():
        brand = row["브랜드(페이지명)"]
        hidden = hidden_accounts.get(brand, [])
        print(f"\n  [{i+1}] {brand}")
        print(f"    ├ 집행: {row['집행 시작일']} ~ ({row['집행 기간(일)']}일)")
        print(f"    ├ 급상승: {row['급상승 월']} | 추정 검색량: {row['급상승 추정 검색량']:,}")
        print(f"    ├ 현재 네이버 검색량: {row['네이버 검색량(현재)']:,}")
        print(f"    ├ 카피: {str(row['광고 카피 미리보기'])[:60]}...")
        print(f"    ├ 광고: {row['광고 보기 URL']}")
        if hidden:
            print(f"    └ 숨겨진 계정: {', '.join([c['page_name'] for c in hidden])}")
        else:
            print(f"    └ 숨겨진 계정: 없음")


# ─────────────────────────────────────────────────────────────────
# 메인 파이프라인
# ─────────────────────────────────────────────────────────────────

def run_pipeline(
    keywords=None,
    min_running_days=MIN_RUNNING_DAYS,
    skip_spike_check=False,
    skip_hidden_accounts=False,
):
    _load_env()
    if keywords is None:
        keywords = ACNE_KEYWORDS

    print(f"\n{'#'*60}")
    print(f"  🎯 A급 레퍼런스 탐색기 | 여드름 카테고리")
    print(f"  시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*60}")

    # Step 1
    ads = collect_meta_ads(keywords=keywords, min_days=min_running_days)
    if not ads:
        print("\n  ⚠️  수집된 광고 없음. 종료.")
        return pd.DataFrame(), {}

    # Step 2
    ads = filter_narration_video(ads)
    if not ads:
        print("\n  ⚠️  나레이션 영상 광고 없음. 종료.")
        return pd.DataFrame(), {}

    # Step 3
    ads = filter_collab_and_major(ads)
    if not ads:
        print("\n  ⚠️  협력/대기업 필터 후 결과 없음. 종료.")
        return pd.DataFrame(), {}

    # Step 4
    if not skip_spike_check:
        ads = filter_search_spike(ads)
        if not ads:
            print("\n  ⚠️  검색량 급상승 조건 충족 브랜드 없음. 종료.")
            return pd.DataFrame(), {}
    else:
        print("\n  ⏭️  [Step 4] 검색량 급상승 체크 건너뜀")
        for ad in ads:
            ad.setdefault("_naver_volume", 0)
            ad.setdefault("_spike_detected", False)
            ad.setdefault("_spike_month", "")
            ad.setdefault("_spike_volume_est", 0)

    # Step 5
    if not skip_hidden_accounts:
        hidden_accounts = find_hidden_accounts(ads)
    else:
        print("\n  ⏭️  [Step 5] 숨겨진 계정 탐색 건너뜀")
        hidden_accounts = {}

    # Step 6
    df = build_result(ads, hidden_accounts)
    print_final_report(df, hidden_accounts)
    save_results(df, ads, hidden_accounts)

    print(f"\n{'#'*60}")
    print(f"  ✅ 파이프라인 완료! 총 {len(df)}개 A급 레퍼런스 발견")
    print(f"{'#'*60}\n")

    return df, hidden_accounts


# ─────────────────────────────────────────────────────────────────
# CLI 진입점
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="A급 레퍼런스 탐색기 (여드름 카테고리)")
    parser.add_argument("--keywords", nargs="+", default=None, help="커스텀 키워드 리스트")
    parser.add_argument("--min-days", type=int, default=MIN_RUNNING_DAYS, help="최소 집행 일수 (기본 60)")
    parser.add_argument("--skip-spike", action="store_true", help="검색량 급상승 체크 건너뜀")
    parser.add_argument("--skip-hidden", action="store_true", help="숨겨진 계정 탐색 건너뜀")

    args = parser.parse_args()
    run_pipeline(
        keywords=args.keywords,
        min_running_days=args.min_days,
        skip_spike_check=args.skip_spike,
        skip_hidden_accounts=args.skip_hidden,
    )
