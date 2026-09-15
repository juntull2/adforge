import os
import time
import hmac
import hashlib
import base64
from curl_cffi import requests
import requests as std_requests
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
        res = std_requests.get(BASE_URL + uri, params=params, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            if data and "keywordList" in data:
                clean_target = keyword.replace(" ", "").strip()
                for item in data["keywordList"]:
                    if item.get("relKeyword") == clean_target:
                        pc_val = item.get("monthlyPcQcCnt", 0)
                        mo_val = item.get("monthlyMobileQcCnt", 0)
                        
                        def parse_cnt(v):
                            if isinstance(v, str) and "<" in v:
                                return 5
                            try:
                                return int(v)
                            except:
                                return 0
                                
                        pc_cnt = parse_cnt(pc_val)
                        mo_cnt = parse_cnt(mo_val)
                        return {
                            "pc": pc_cnt,
                            "mobile": mo_cnt,
                            "total": pc_cnt + mo_cnt,
                            "raw_pc": str(pc_val),
                            "raw_mobile": str(mo_val),
                            "exact_match": True,
                            "comp_idx": item.get("compIdx", "-")
                        }
        else:
            print(f"Naver Ads API Error: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"API Request Error: {e}")
        
    return {"pc": 0, "mobile": 0, "total": 0, "raw_pc": "< 10", "raw_mobile": "< 10", "exact_match": False, "comp_idx": "-"}


def get_brand_and_product_volumes(brand_name: str, product_name: str, customer_id: str, access_license: str, secret_key: str):
    """
    브랜드명과 자사몰 주력 제품명을 각각 완전 일치(Exact Match)로 분리 조회하여 반환.
    """
    brand_res = get_naver_search_volume(brand_name, customer_id, access_license, secret_key)
    product_res = get_naver_search_volume(product_name, customer_id, access_license, secret_key) if product_name else None
    
    return {
        "brand": {
            "name": brand_name,
            "metrics": brand_res
        },
        "product": {
            "name": product_name,
            "metrics": product_res
        } if product_res else None
    }



CATEGORY_TOP_BRANDS = {
    # ── [욕구 TOP] 비만 / 다이어트 / 체형 ──
    "비만": ["위고비", "마운자로", "삭센다", "큐시미아", "푸드올로지", "칼로바이", "빨간통", "딥트3일"],
    "다이어트": ["푸드올로지", "칼로바이", "빨간통", "딥트3일", "베이스앤", "스키니랩", "세리박스", "GRN"],
    "뱃살": ["푸드올로지", "빨간통", "딥트3일", "모로실", "칼로바이"],
    "체지방": ["푸드올로지", "빨간통", "모로실", "카테킨", "칼로바이"],
    "붓기": ["달심", "보나수아", "호박즙", "브이단", "이너워터", "기분전환"],
    "식욕": ["삭센다", "위고비", "큐시미아", "디에타민"],

    # ── [욕구 TOP] 탈모 / 두피 / 헤어 ──
    "탈모": ["닥터포헤어", "라보에이치", "모다모다", "판시딜", "미녹시딜", "로게인폼", "알페신"],
    "두피": ["닥터포헤어", "라보에이치", "아로마티카", "헤드앤숄더", "려"],
    "정수리": ["닥터포헤어", "라보에이치", "판시딜", "로게인폼"],
    "새치": ["모다모다", "려", "리엔", "새치샴푸"],
    "샴푸": ["닥터포헤어", "모다모다", "라보에이치", "헤드앤숄더", "려"],

    # ── [욕구 TOP] 여드름 / 피부 / 뷰티 ──
    "여드름": ["노스카나", "애크논", "메디큐브", "아크네스", "클리어틴", "아누아", "닥터지", "파티온", "에스트라"],
    "좁쌀": ["아누아", "넘버즈인", "에스트라", "메디큐브", "토리든"],
    "기미": ["도미나스", "동국제약", "멜라토닝", "트라넥삼산", "참존", "아이오페", "도미나크림"],
    "모공": ["메디큐브", "제로모공", "성분에디터", "바이오던스", "아누아"],
    "주름": ["가히", "메디큐브", "에이지알", "동국제약", "센텔리안24", "아이오페"],
    "색소": ["도미나스", "멜라토닝", "노스카나", "동아제약"],
    "피부": ["메디큐브", "달바", "토리든", "아누아", "에스트라", "가히", "센텔리안24"],
    "탄력": ["듀얼소닉", "메디큐브", "에이지알", "가히"],
    "건조": ["에스트라", "피지오겔", "일리윤", "세타필", "토리든"],
    "패드": ["메디큐브", "아누아", "토리든", "스킨푸드"],
    "앰플": ["토리든", "달바", "메디큐브", "마녀공장"],
    "쿠션": ["클리오", "헤라", "정샘물", "에스쁘아"],
    "선크림": ["달바", "라운드랩", "닥터지"],
    "클렌징": ["마녀공장", "바이오더마", "센카"],

    # ── [욕구 TOP] 관절 / 통증 / 체형교정 ──
    "관절": ["호관원", "관절보궁", "콘드로이친", "종근당", "옵티MSM", "정관장", "천관보"],
    "무릎": ["잠스트", "바우어파인트", "에이더", "호관원", "관절보궁"],
    "허리": ["커블", "미요", "바디럽", "밸런스온", "에르고슬립"],
    "목": ["닥터바르미", "몽제", "바디럽", "템퍼", "슬립랩"],
    "목디스크": ["닥터바르미", "몽제", "바디럽", "경추베개"],
    "거북목": ["닥터바르미", "몽제", "바디럽", "에르고"],
    "손목": ["잠스트", "에이더", "바우어파인트"],
    "족저근막": ["아치패드", "베어풋", "바디럽", "에이더"],
    "보호대": ["잠스트", "바우어파인트", "에이더", "맥데이비드"],
    "찜질": ["오아", "누잠", "닥터웰", "보국", "한일"],
    "온열": ["누잠", "오아", "보국"],
    "마사지": ["풀리오", "클럭", "코지마", "바디프랜드", "제스파"],
    "베개": ["닥터바르미", "몽제", "바디럽", "템퍼", "슬립랩"],

    # ── [욕구 TOP] 수면 / 건강 / 활력 ──
    "불면": ["락티움", "감태추출물", "슬립랩", "수면영양제", "닥터바르미"],
    "수면": ["락티움", "슬립랩", "수면영양제", "닥터바르미", "몽제"],
    "피로": ["오쏘몰", "아로나민", "임팩타민", "정관장", "고려은단"],
    "혈당": ["바나바잎", "여주즙", "혈당엔", "종근당"],
    "유산균": ["락토핏", "덴프스", "종근당", "드시모네"],
    "영양제": ["종근당", "고려은단", "정관장", "오쏘몰"],
    "단백질": ["셀렉스", "하이뮨", "마이프로틴", "칼로바이"],
    "쉐이크": ["셀렉스", "하이뮨", "칼로바이"],
    "치아": ["루치펠로", "덴티스테", "유시몰", "화이트랩"],
    "미백": ["루치펠로", "화이트랩", "덴티스테", "유시몰"],

    # ── 리빙 / 소형가전 ──
    "가습기": ["오아", "미로", "듀플렉스", "조지루시"],
    "제습기": ["위닉스", "LG", "신일"],
    "청소기": ["다이슨", "로보락", "드리미", "삼성"],
    "공기청정기": ["LG", "삼성", "위닉스", "다이슨"],
    "인덕션": ["쿠쿠", "SK매직", "삼성"],
    "밥솥": ["쿠쿠", "쿠첸"],
    "냄비": ["해피콜", "테팔", "스타우브"],
    "프라이팬": ["해피콜", "테팔"],
}

# 역방향 브랜드 -> 카테고리 매핑 구축
BRAND_TO_CATEGORY = {}
ALL_KNOWN_BRANDS = set()
for _cat, _brands in CATEGORY_TOP_BRANDS.items():
    for _b in _brands:
        ALL_KNOWN_BRANDS.add(_b)
        if _b not in BRAND_TO_CATEGORY:
            BRAND_TO_CATEGORY[_b] = []
        BRAND_TO_CATEGORY[_b].append(_cat)

# 브랜드 추천 시 제외할 정보성/비상업성 노이즈 단어
NOISE_WORDS = (
    "계산기", "정의", "뜻", "원인", "초기증상", "치료법", "자가진단",
    "병원", "외과", "내과", "의원", "한의원", "피부과", "사망", "통계",
    "부작용증상", "수술", "진료", "치료"
)


def get_naver_related_keywords_over_10k(keyword: str, customer_id: str, access_license: str, secret_key: str, min_volume: int = 10000, limit: int = 15):
    """
    네이버 검색광고 공식 API (100% 무료, 과금 0원)를 활용하여,
    우리 제품/카테고리와 밀접하게 연관된 브랜드(주요 노출) 및 핵심 연관 검색어를 선별하여 반환합니다.
    """
    import concurrent.futures

    keyword = str(keyword).strip()
    if not keyword or not customer_id or not access_license or not secret_key:
        return []

    BASE_URL = "https://api.naver.com"
    uri = "/keywordstool"
    kw_clean = keyword.replace(" ", "")

    # 1. 연관 카테고리 대표 브랜드 추출 (정방향 + 역방향)
    matched_brands = []
    for cat, brands in CATEGORY_TOP_BRANDS.items():
        if cat in keyword:
            for b in brands:
                if b not in matched_brands:
                    matched_brands.append(b)

    # 검색어 자체가 브랜드인 경우 동종 카테고리 피어 브랜드 매칭
    for b, cats in BRAND_TO_CATEGORY.items():
        if b in keyword:
            for c in cats:
                for peer in CATEGORY_TOP_BRANDS.get(c, []):
                    if peer not in matched_brands:
                        matched_brands.append(peer)

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
            res = std_requests.get(BASE_URL + uri, params=params, headers=headers, timeout=5)
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

        brand_items = []
        product_items = []
        seen = set()

        # 브랜드 키워드는 상업적 구매의도가 높으므로 조금 더 유연한 최소 기준 적용
        brand_min_vol = max(1000, min_volume // 4)

        for item in all_k_list:
            rel_kw = item.get("relKeyword", "")
            if not rel_kw or rel_kw in seen:
                continue

            # 정보성/병원 등 노이즈 단어 필터링
            if any(nw in rel_kw for nw in NOISE_WORDS):
                continue

            try: pc = int(item.get("monthlyPcQcCnt", 0))
            except: pc = 10
            try: mo = int(item.get("monthlyMobileQcCnt", 0))
            except: mo = 10
            tot = pc + mo

            if matched_brands:
                is_brand = any(b in rel_kw for b in matched_brands)
            else:
                is_brand = any(b in rel_kw for b in ALL_KNOWN_BRANDS)

            is_product = any(t in rel_kw for t in tokens)

            if is_brand and tot >= brand_min_vol:
                seen.add(rel_kw)
                brand_items.append({
                    "keyword": rel_kw,
                    "volume": tot,
                    "is_brand": True,
                    "pc": pc,
                    "mobile": mo
                })
            elif not is_brand and is_product and tot >= min_volume:
                seen.add(rel_kw)
                product_items.append({
                    "keyword": rel_kw,
                    "volume": tot,
                    "is_brand": False,
                    "pc": pc,
                    "mobile": mo
                })

        # 브랜드 키워드를 최우선 정렬 (검색량 높은 순)
        brand_items.sort(key=lambda x: -x["volume"])
        product_items.sort(key=lambda x: -x["volume"])

        # 브랜드를 주로 배치하고, 나머지 자리에 일반 제품 연관어 배치
        combined = brand_items + product_items
        return combined[:limit]
    except Exception as e:
        print(f"Related keywords error: {e}")

    return []
