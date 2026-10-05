import os
import time
import hmac
import hashlib
import base64
import requests
from dotenv import load_dotenv

load_dotenv('c:/adforge/.env')

customer_id = os.environ.get("NAVER_CUSTOMER_ID")
access_license = os.environ.get("NAVER_ACCESS_LICENSE")
secret_key = os.environ.get("NAVER_SECRET_KEY")

print("Credentials loaded:", bool(customer_id), bool(access_license), bool(secret_key))

def get_naver_search_volume_detail(keyword: str):
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
    
    params = {
        "hintKeywords": keyword,
        "showDetail": 1
    }
    
    res = requests.get(BASE_URL + uri, params=params, headers=headers, timeout=10)
    if res.status_code != 200:
        return {"error": res.status_code, "text": res.text}
        
    data = res.json()
    if not data or "keywordList" not in data:
        return {"error": "no keywordList"}
        
    results = []
    clean_target = keyword.replace(" ", "").strip()
    exact_match = None
    
    for item in data["keywordList"]:
        rel_kwd = item.get("relKeyword", "")
        pc = item.get("monthlyPcQcCnt", 0)
        mo = item.get("monthlyMobileQcCnt", 0)
        comp = item.get("compIdx", "")
        
        def parse_v(v):
            if isinstance(v, str) and "<" in v:
                return 5
            try:
                return int(v)
            except:
                return 0
                
        pc_cnt = parse_v(pc)
        mo_cnt = parse_v(mo)
        tot = pc_cnt + mo_cnt
        
        entry = {
            "keyword": rel_kwd,
            "pc": pc_cnt,
            "mobile": mo_cnt,
            "total": tot,
            "competition": comp
        }
        
        if rel_kwd == clean_target:
            exact_match = entry
        results.append(entry)
        
    return {
        "exact": exact_match,
        "top_related": sorted(results, key=lambda x: x["total"], reverse=True)[:10]
    }

keywords = [
    "노일리", "NOILY",
    "이옴", "EIOM", "이옴마스크팩",
    "디마프", "demaf", "디마프만능기초",
    "델리케어", "델리케어살구팩",
    "메디옥실", "medioxyl",
    "프롬갓", "프롬갓갓크림",
    "넘버즈인",
    "파티온"
]

print("\n" + "="*80)
print(f"{'키워드':<15} | {'PC 검색수':<10} | {'모바일 검색수':<10} | {'월간 총 검색수':<12} | {'경쟁도'}")
print("="*80)

for kw in keywords:
    res = get_naver_search_volume_detail(kw)
    if "error" in res:
        print(f"{kw:<15} | ERROR: {res['error']}")
    else:
        ex = res.get("exact")
        if ex:
            print(f"{ex['keyword']:<15} | {ex['pc']:<10,d} | {ex['mobile']:<10,d} | {ex['total']:<12,d} | {ex['competition']}")
        else:
            # show best match
            top = res["top_related"][0] if res["top_related"] else None
            if top:
                print(f"{kw+' (연관 1위)':<15} | {top['pc']:<10,d} | {top['mobile']:<10,d} | {top['total']:<12,d} | {top['competition']} ({top['keyword']})")
            else:
                print(f"{kw:<15} | 검색 결과 없음")
    time.sleep(0.3)
