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
        
    clean_target = keyword.replace(" ", "").strip()
    exact_match = None
    related = []
    
    def parse_v(v):
        if isinstance(v, str) and "<" in v:
            return 5
        try:
            return int(v)
        except:
            return 0

    for item in data["keywordList"]:
        rel_kwd = item.get("relKeyword", "")
        pc_cnt = parse_v(item.get("monthlyPcQcCnt", 0))
        mo_cnt = parse_v(item.get("monthlyMobileQcCnt", 0))
        comp = item.get("compIdx", "")
        pl_avg_cnt = item.get("plAvgDepth", 0)
        
        entry = {
            "keyword": rel_kwd,
            "pc": pc_cnt,
            "mobile": mo_cnt,
            "total": pc_cnt + mo_cnt,
            "competition": comp
        }
        
        if rel_kwd == clean_target:
            exact_match = entry
        else:
            related.append(entry)
            
    related_sorted = sorted(related, key=lambda x: x["total"], reverse=True)
    return {
        "exact": exact_match,
        "related": related_sorted[:5]
    }

brand_keywords = [
    ("노일리", ["노일리", "NOILY", "노일리클렌저"]),
    ("이옴", ["이옴", "EIOM", "이옴마스크팩", "이옴피지팩"]),
    ("디마프", ["디마프", "demaf", "디마프만능기초"]),
    ("델리케어", ["델리케어", "DELICARE", "델리케어살구팩"]),
    ("메디옥실", ["메디옥실", "medioxyl", "메디옥실레드스팟"]),
    ("프롬갓", ["프롬갓", "FROMGOD", "프롬갓갓크림"]),
    ("넘버즈인", ["넘버즈인", "numbuzin", "넘버즈인패드"]),
    ("파티온", ["파티온", "fation", "파티온노스카나인"])
]

out_lines = []
out_lines.append("# 📊 네이버 검색광고 공식 데이터 (아이템스카우트 데이터 소스)")
out_lines.append("> 기준: 최근 30일(월간) 네이버 PC/모바일 공식 검색수 (Naver Search Ads relKwdStat API)\n")

for brand, kw_list in brand_keywords:
    out_lines.append(f"## 🏷️ {brand}")
    out_lines.append("| 키워드 | PC 검색수 | 모바일 검색수 | 월간 총 검색수 | 경쟁도 |")
    out_lines.append("|---|---|---|---|---|")
    
    brand_total = 0
    for kw in kw_list:
        data = get_naver_search_volume_detail(kw)
        ex = data.get("exact")
        if ex:
            out_lines.append(f"| **{ex['keyword']}** | {ex['pc']:,}회 | {ex['mobile']:,}회 | **{ex['total']:,}회** | {ex['competition']} |")
            brand_total += ex["total"]
        else:
            out_lines.append(f"| {kw} | 0회 | 0회 | 0회 | - |")
        time.sleep(0.2)
        
    out_lines.append(f"\n> 💡 **{brand} 브랜드 관련 월간 검색 합산**: **{brand_total:,}회**\n")
    
    # Check top related
    sample_data = get_naver_search_volume_detail(kw_list[0])
    if sample_data.get("related"):
        out_lines.append("연관 키워드 TOP 5:")
        for r in sample_data["related"]:
            out_lines.append(f"- {r['keyword']}: 월 {r['total']:,}회 (PC {r['pc']:,} / 모바일 {r['mobile']:,})")
        out_lines.append("")
    out_lines.append("---\n")

with open('c:/adforge/naver_search_volume_results.txt', 'w', encoding='utf-8') as f:
    f.write("\n".join(out_lines))

print("Successfully written naver_search_volume_results.txt")
