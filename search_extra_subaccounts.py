import json
import time
from datetime import datetime
import meta_ad_library

queries = [
    "건강ㅎŁ 삶 되찾ブl",
    "파이토업",
    "이소놀",
    "피지조절",
    "피지억제",
    "꿀팁저장해바라"
]

all_extra = []
for q in queries:
    print(f"Searching: {q}")
    res = meta_ad_library.search_meta_ads(keyword=q, country="KR", min_days_running=0, limit=20)
    ads = res.get("ads", [])
    print(f"-> Found {len(ads)} ads")
    for ad in ads:
        snapshot = ad.get("snapshot", {})
        page_name = ad.get("page_name") or snapshot.get("page_name", "")
        page_id = str(ad.get("page_id") or snapshot.get("page_id", "")).strip()
        ad_id = str(ad.get("ad_archive_id") or ad.get("id") or snapshot.get("ad_id", "")).strip()
        
        start_val = ad.get("start_date") or snapshot.get("creation_time")
        if isinstance(start_val, (int, float)):
            start_date = datetime.fromtimestamp(int(start_val)).strftime("%Y-%m-%d")
        elif start_val:
            start_date = str(start_val)[:10]
        else:
            start_date = ""
            
        running_days = ad.get("_running_days", 0)
        body = snapshot.get("body", {})
        body_text = body.get("text", "") if isinstance(body, dict) else str(body or "")
        cleaned_body = meta_ad_library.clean_ad_copy(body_text, brand=page_name)
        meta_library_link = f"https://www.facebook.com/ads/library/?id={ad_id}" if ad_id else ""
        landing_url = meta_ad_library._extract_landing_url(snapshot)
        video_download_url = meta_ad_library._extract_video_download_url(ad, snapshot)
        media_type = meta_ad_library.detect_media_type(ad, snapshot)
        
        all_extra.append({
            "search_query": q,
            "ad_id": ad_id,
            "meta_library_link": meta_library_link,
            "page_name": page_name,
            "page_id": page_id,
            "start_date": start_date,
            "running_days": running_days,
            "media_type": media_type,
            "ad_copy": cleaned_body,
            "landing_url": landing_url,
            "video_download_url": video_download_url
        })
    time.sleep(1)

with open("c:/adforge/supplements_extra_subaccounts.json", "w", encoding="utf-8") as f:
    json.dump(all_extra, f, ensure_ascii=False, indent=2)

print("Saved c:/adforge/supplements_extra_subaccounts.json")
