import os
import json
import time
import hmac
import hashlib
import base64
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import meta_ad_library

load_dotenv('c:/adforge/.env')

# 1. NAVER Search Ads (ItemScout Data Source)
customer_id = os.environ.get("NAVER_CUSTOMER_ID")
access_license = os.environ.get("NAVER_ACCESS_LICENSE")
secret_key = os.environ.get("NAVER_SECRET_KEY")

def get_itemscout_volume(keyword: str):
    keyword = str(keyword).replace(" ", "").replace("\n", "").strip()
    BASE_URL = "https://api.naver.com"
    uri = "/keywordstool"
    method = "GET"
    timestamp = str(int(time.time() * 1000))
    
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
    
    params = {"hintKeywords": keyword, "showDetail": 1}
    try:
        res = requests.get(BASE_URL + uri, params=params, headers=headers, timeout=10)
        if res.status_code != 200:
            return {"keyword": keyword, "pc": 0, "mobile": 0, "total": 0, "comp": "-"}
        data = res.json()
        if not data or "keywordList" not in data:
            return {"keyword": keyword, "pc": 0, "mobile": 0, "total": 0, "comp": "-"}
            
        def parse_v(v):
            if isinstance(v, str) and "<" in v:
                return 5
            try:
                return int(v)
            except:
                return 0
                
        clean_target = keyword.replace(" ", "").strip()
        for item in data["keywordList"]:
            rel_kwd = item.get("relKeyword", "")
            if rel_kwd == clean_target:
                pc = parse_v(item.get("monthlyPcQcCnt", 0))
                mo = parse_v(item.get("monthlyMobileQcCnt", 0))
                return {
                    "keyword": rel_kwd,
                    "pc": pc,
                    "mobile": mo,
                    "total": pc + mo,
                    "comp": item.get("compIdx", "-")
                }
        # If not exact match found, return first or zero
        if data["keywordList"]:
            first = data["keywordList"][0]
            pc = parse_v(first.get("monthlyPcQcCnt", 0))
            mo = parse_v(first.get("monthlyMobileQcCnt", 0))
            return {
                "keyword": first.get("relKeyword", keyword),
                "pc": pc,
                "mobile": mo,
                "total": pc + mo,
                "comp": first.get("compIdx", "-")
            }
    except Exception as e:
        print(f"Error querying naver search for {keyword}: {e}")
    return {"keyword": keyword, "pc": 0, "mobile": 0, "total": 0, "comp": "-"}

target_supplements = [
    {
        "category": "피지억제 유산균",
        "brand": "오르엔시아 (ORNCIA)",
        "product": "클리어젠",
        "keywords": ["클리어젠", "오르엔시아", "클리어젠 유산균", "피지억제 유산균"],
        "search_query": "클리어젠"
    },
    {
        "category": "피지선 억제 / 피부 재생 영양제",
        "brand": "리포데이 (Lipoday)",
        "product": "파이토업",
        "keywords": ["리포데이", "파이토업", "리포데이 파이토업", "스위스 레티놀 영양제"],
        "search_query": "리포데이"
    },
    {
        "category": "여드름 / 피지선 / 호르몬 이너케어",
        "brand": "메디온 (THE MEDION)",
        "product": "락토페린 이너케어",
        "keywords": ["메디온", "메디온 락토페린", "락토페린 여드름", "피지 락토페린"],
        "search_query": "메디온"
    },
    {
        "category": "피지선 조절 영양제 (이소티논 대체)",
        "brand": "이소놀 (Isonol)",
        "product": "이소놀정",
        "keywords": ["이소놀정", "이소놀", "피지선 영양제", "이소티논 영양제"],
        "search_query": "이소놀정"
    },
    {
        "category": "피지 억제 판토텐산 영양제",
        "brand": "누오 (NUO)",
        "product": "누오 판토텐산",
        "keywords": ["누오", "누오 판토텐산", "누오킷", "사쿠라블룸티"],
        "search_query": "누오"
    },
    {
        "category": "모낭 / 피지 종합 영양제",
        "brand": "판토모나 (PANTOMONA)",
        "product": "판토모나 비오틴/판토텐산",
        "keywords": ["판토모나", "판토모나 여드름", "온궁민건강프로젝트"],
        "search_query": "판토모나"
    }
]

print("=== 1. Starting Meta Ad Library Scraping ===")
results = []

for item in target_supplements:
    q = item["search_query"]
    print(f"\n[Scraping Meta Ad Library for query: {q} ({item['brand']})]")
    
    # 1. Meta Scrape
    meta_res = meta_ad_library.search_meta_ads(keyword=q, country="KR", min_days_running=0, limit=30)
    ads = meta_res.get("ads", [])
    print(f"-> Found {len(ads)} ads in Meta Ad Library")
    
    # 2. Volumes
    vol_results = []
    for kw in item["keywords"]:
        v = get_itemscout_volume(kw)
        vol_results.append(v)
        time.sleep(0.15)
        
    # 3. Process Ads
    parsed_ads = []
    for ad in ads:
        snapshot = ad.get("snapshot", {})
        page_name = ad.get("page_name") or snapshot.get("page_name", "")
        page_id = str(ad.get("page_id") or snapshot.get("page_id", "")).strip()
        ad_id = str(ad.get("ad_archive_id") or ad.get("id") or snapshot.get("ad_id", "")).strip()
        
        # Start date
        start_val = ad.get("start_date") or snapshot.get("creation_time")
        if isinstance(start_val, (int, float)):
            start_date = datetime.fromtimestamp(int(start_val)).strftime("%Y-%m-%d")
        elif start_val:
            start_date = str(start_val)[:10]
        else:
            start_date = ""
            
        running_days = ad.get("_running_days", 0)
        
        # Body text
        body = snapshot.get("body", {})
        body_text = body.get("text", "") if isinstance(body, dict) else str(body or "")
        cleaned_body = meta_ad_library.clean_ad_copy(body_text, brand=page_name)
        
        # Links
        meta_library_link = f"https://www.facebook.com/ads/library/?id={ad_id}" if ad_id else ""
        landing_url = meta_ad_library._extract_landing_url(snapshot)
        video_download_url = meta_ad_library._extract_video_download_url(ad, snapshot)
        media_type = meta_ad_library.detect_media_type(ad, snapshot)
        
        page_lib_url = f"https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=KR&view_all_page_id={page_id}" if page_id else ""
        
        # Determine if hidden subaccount
        is_subaccount = False
        brand_clean = item["brand"].replace(" ", "").lower()
        pn_clean = page_name.replace(" ", "").lower()
        
        # If page name doesn't contain brand name directly, it is very likely a subaccount / viral page
        if not any(token in pn_clean for token in ["orncia", "오르엔시아", "오른시아", "lipoday", "리포데이", "themedion", "메디온", "isonol", "이소놀", "nuo", "누오", "pantomon", "판토모나"]):
            is_subaccount = True
            
        parsed_ads.append({
            "ad_id": ad_id,
            "meta_library_link": meta_library_link,
            "page_name": page_name,
            "page_id": page_id,
            "page_library_url": page_lib_url,
            "is_subaccount": is_subaccount,
            "start_date": start_date,
            "running_days": running_days,
            "media_type": media_type,
            "ad_copy": cleaned_body,
            "landing_url": landing_url,
            "video_download_url": video_download_url
        })
        
    # Sort ads by running days descending
    parsed_ads.sort(key=lambda x: x["running_days"], reverse=True)
    
    results.append({
        "info": item,
        "search_volumes": vol_results,
        "ads": parsed_ads
    })
    time.sleep(1)

# Write output to json
with open("c:/adforge/supplements_investigation_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print("\n=== Finished and saved to c:/adforge/supplements_investigation_results.json ===")
