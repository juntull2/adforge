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
