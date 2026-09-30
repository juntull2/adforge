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

def get_naver_search_volume(keyword: str):
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
        return None
        
    data = res.json()
    if not data or "keywordList" not in data:
        return None
        
    clean_target = keyword.replace(" ", "").strip()
    def parse_v(v):
        if isinstance(v, str) and "<" in v:
            return 5
        try:
            return int(v)
        except:
            return 0

    for item in data["keywordList"]:
        if item.get("relKeyword") == clean_target:
            pc = parse_v(item.get("monthlyPcQcCnt", 0))
            mo = parse_v(item.get("monthlyMobileQcCnt", 0))
            return {
                "keyword": clean_target,
                "pc": pc,
                "mobile": mo,
                "total": pc + mo,
                "competition": item.get("compIdx", "")
            }
    return None

targets = [
    # 이옴 스타일 피지/모공/여드름 팩 & 클렌저 브랜드들
    "풀리", "풀리돌피지크림", "돌피지크림",
    "새살", "새살모공팩",
    "에이프릴스킨", "에이프릴스킨당근클렌징밤", "당근클렌징밤", "에이프릴스킨필오프팩",
    "메디큐브", "메디큐브제로모공패드", "제로모공패드",
    "피캄", "피캄모공실종팩", "모공실종팩",
    "셀올로지", "셀올로지포어샷",
    "쏘내추럴", "쏘내추럴피지흡착팩"
]

print("Fetching search volumes...")
results = []
for t in targets:
    res = get_naver_search_volume(t)
    if res:
        results.append(res)
    else:
        results.append({"keyword": t, "pc": 0, "mobile": 0, "total": 0, "competition": "-"})
    time.sleep(0.2)

with open('eiom_alternatives_stats.txt', 'w', encoding='utf-8') as f:
    f.write(f"{'키워드':<25} | {'PC':<8} | {'모바일':<8} | {'총합':<10} | {'경쟁도'}\n")
    f.write("="*65 + "\n")
    for r in results:
        f.write(f"{r['keyword']:<25} | {r['pc']:<8,d} | {r['mobile']:<8,d} | {r['total']:<10,d} | {r['competition']}\n")

print("Done writing eiom_alternatives_stats.txt")
