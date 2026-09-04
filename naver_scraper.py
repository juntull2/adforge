import os
import time
import hmac
import hashlib
import base64
from curl_cffi import requests
from bs4 import BeautifulSoup

def get_naver_clip_rank(keyword: str) -> int:
    """
    네이버 모바일 통합검색에서 '클립' 영역이 몇 번째(탭 순위가 아닌 본문 영역 순위)인지 파악.
    반환값: 1~N (몇 번째인지), 없으면 -1
    """
    url = "https://m.search.naver.com/search.naver"
    
    try:
        # curl_cffi의 impersonate 옵션으로 TLS 핑거프린트 우회 (모바일 브라우저 환경 모방)
        response = requests.get(url, params={"query": keyword}, impersonate="chrome110", timeout=8)
        soup = BeautifulSoup(response.text, "html.parser")
        
        # 모바일 통합검색 본문 수직 섹션 랭킹 탐색 (h2 태그 또는 api_title 클래스)
        # 상단 탭(a.tab)이 아니라 실제 본문에서 몇 번째 블록으로 노출되는지 찾습니다.
        titles = soup.select("h2, .api_title")
        
        valid_titles = []
        for t in titles:
            text = t.get_text(strip=True)
            if text and text not in valid_titles:
                valid_titles.append(text)
                
        for idx, text in enumerate(valid_titles, 1):
            if "클립" in text:
                return idx

                    
        return -1
    except Exception as e:
        print(f"Clip rank error: {e}")
        return -1

def get_naver_search_volume(keyword: str, customer_id: str, access_license: str, secret_key: str):
    """
    네이버 검색광고 API를 사용하여 PC/모바일 검색량을 반환.
    """
    keyword = str(keyword).replace(" ", "").replace("\n", "").strip()
    if not keyword or not customer_id or not access_license or not secret_key:
        return {"pc": 0, "mobile": 0, "total": 0}
        
    BASE_URL = "https://api.naver.com"
    uri = "/keywordstool"
    method = "GET"
    timestamp = str(int(time.time() * 1000))
    
    # 서명 생성
    message = timestamp + "." + method + "." + uri
    signature = hmac.new(
        secret_key.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).digest()
    signature_base64 = base64.b64encode(signature).decode('utf-8')
    
    headers = {
        "X-Timestamp": timestamp,
        "X-API-KEY": access_license,
        "X-Customer": str(customer_id),
        "X-Signature": signature_base64
    }
    
    params = {
        "hintKeywords": keyword,
        "showDetail": 1
    }
    
    try:
        res = requests.get(BASE_URL + uri, params=params, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            if data and "keywordList" in data and len(data["keywordList"]) > 0:
                item = data["keywordList"][0]
                pc_vol = item.get("monthlyPcQcCnt", 0)
                mo_vol = item.get("monthlyMobileQcCnt", 0)
                
                try: pc_vol = int(pc_vol)
                except: pc_vol = 10
                
                try: mo_vol = int(mo_vol)
                except: mo_vol = 10
                
                return {
                    "pc": pc_vol,
                    "mobile": mo_vol,
                    "total": pc_vol + mo_vol
                }
        else:
            print(f"Naver Ads API Error: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"API Request Error: {e}")
        
    return {"pc": 0, "mobile": 0, "total": 0}


CATEGORY_TOP_BRANDS = {
    # 주요 제품 카테고리 (우선순위 높음)
    "찜질": ["오아", "누잠", "닥터웰", "보국", "한일"],
    "온열": ["누잠", "오아", "보국"],
    "보호대": ["잠스트", "바우어파인트", "에이더", "맥데이비드"],
    "마사지": ["풀리오", "클럭", "코지마", "바디프랜드", "제스파"],
    "다이어트": ["푸드올로지", "칼로바이", "스키니랩", "세리박스", "빨간통"],
    "베개": ["닥터바르미", "몽제", "바디럽", "템퍼", "슬립랩"],
    "단백질": ["셀렉스", "하이뮨", "마이프로틴", "칼로바이"],
    "쉐이크": ["셀렉스", "하이뮨", "칼로바이"],
    "유산균": ["락토핏", "덴프스", "종근당", "드시모네"],
    "영양제": ["종근당", "고려은단", "정관장", "오쏘몰"],
    "패드": ["메디큐브", "아누아", "토리든", "스킨푸드"],
    "앰플": ["토리든", "달바", "메디큐브", "마녀공장"],
    "쿠션": ["클리오", "헤라", "정샘물", "에스쁘아"],
    "선크림": ["달바", "라운드랩", "닥터지"],
    "클렌징": ["마녀공장", "바이오더마", "센카"],
    "샴푸": ["닥터포헤어", "모다모다", "려", "헤드앤숄더", "라보에이치"],
    "탈모": ["닥터포헤어", "모다모다", "려", "라보에이치"],
    # 소형가전 / 리빙
    "가습기": ["오아", "미로", "듀플렉스", "조지루시"],
    "제습기": ["위닉스", "LG", "신일"],
    "청소기": ["다이슨", "로보락", "드리미", "삼성"],
    "공기청정기": ["LG", "삼성", "위닉스", "다이슨"],
    "인덕션": ["쿠쿠", "SK매직", "삼성"],
    "밥솥": ["쿠쿠", "쿠첸"],
    "냄비": ["해피콜", "테팔", "스타우브"],
    "프라이팬": ["해피콜", "테팔"],
    # 부위 및 수식어
    "무릎": ["잠스트", "바우어파인트", "에이더"],
    "손목": ["잠스트", "에이더"],
    "허리": ["커블", "미요", "바디럽"],
}


def get_naver_related_keywords_over_10k(keyword: str, customer_id: str, access_license: str, secret_key: str, min_volume: int = 10000, limit: int = 15):
    """
    네이버 검색광고 공식 API (100% 무료, 과금 0원)를 활용하여,
    우리 제품/카테고리와 밀접하게 연관된 검색어 중 월간 검색량 min_volume(기본 10,000) 이상인 연관어 및 브랜드를 선별하여 반환합니다.
    """
    import concurrent.futures

    keyword = str(keyword).strip()
    if not keyword or not customer_id or not access_license or not secret_key:
        return []

    BASE_URL = "https://api.naver.com"
    uri = "/keywordstool"
    kw_clean = keyword.replace(" ", "")

    # 1. 연관 카테고리 대표 브랜드 추출
    matched_brands = []
    for cat, brands in CATEGORY_TOP_BRANDS.items():
        if cat in keyword:
            for b in brands:
                if b not in matched_brands:
                    matched_brands.append(b)

    # 2. 힌트 키워드 배치 구성 (1회 호출당 최대 5개이므로, 최대 2개 배치로 나누어 병렬 호출)
    batches = []
    if matched_brands:
        batches.append([kw_clean] + matched_brands[:4])
        if len(matched_brands) > 4:
            batches.append(matched_brands[4:9])
    else:
        batches.append([kw_clean])

    def _call_api(hints):
        timestamp = str(int(time.time() * 1000))
        message = timestamp + ".GET." + uri
        signature = hmac.new(
            secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
        signature_base64 = base64.b64encode(signature).decode('utf-8')

        headers = {
            "X-Timestamp": timestamp,
            "X-API-KEY": access_license,
            "X-Customer": str(customer_id),
            "X-Signature": signature_base64
        }
        params = {
            "hintKeywords": ",".join(hints),
            "showDetail": 1
        }
        try:
            res = requests.get(BASE_URL + uri, params=params, headers=headers, timeout=4)
            if res.status_code == 200:
                return res.json().get("keywordList", [])
        except Exception as ex:
            print(f"Naver hint query error: {ex}")
        return []

    all_k_list = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(batches)) as ex:
            futures = [ex.submit(_call_api, b) for b in batches]
            for f in futures:
                all_k_list.extend(f.result())

        # 관련도 판별을 위한 핵심 토큰 구성
        tokens = [t for t in [kw_clean, keyword] if len(t) >= 2]
        if len(kw_clean) >= 4:
            tokens.append(kw_clean[:2])
            tokens.append(kw_clean[2:])
            if len(kw_clean) >= 5:
                tokens.append(kw_clean[:3])
                tokens.append(kw_clean[-3:])
        tokens.extend(matched_brands)
        tokens = list(dict.fromkeys(tokens))

        matched = []
        seen = set()
        for item in all_k_list:
            rel_kw = item.get("relKeyword", "")
            if not rel_kw or rel_kw in seen:
                continue

            try: pc = int(item.get("monthlyPcQcCnt", 0))
            except: pc = 0
            try: mo = int(item.get("monthlyMobileQcCnt", 0))
            except: mo = 0
            tot = pc + mo

            if tot >= min_volume:
                is_brand = any(b in rel_kw for b in matched_brands)
                is_product = any(t in rel_kw for t in tokens)

                if is_brand or is_product:
                    seen.add(rel_kw)
                    matched.append({
                        "keyword": rel_kw,
                        "volume": tot,
                        "is_brand": is_brand,
                        "pc": pc,
                        "mobile": mo
                    })

        # 브랜드 키워드를 앞쪽에, 그 다음 검색량 높은 순으로 정렬
        matched.sort(key=lambda x: (not x["is_brand"], -x["volume"]))
        return matched[:limit]
    except Exception as e:
        print(f"Related keywords error: {e}")

    return []
