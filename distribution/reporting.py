from typing import List
from distribution.models import UploadResult

def generate_report(title: str, results: List[UploadResult]) -> str:
    """
    Generates a markdown report from the upload results.
    """
    lines = []
    lines.append("📝 [일일 숏폼 업로드 보고]")
    lines.append("")
    lines.append(f"주제: {title}")
    lines.append("")
    
    # Define human-readable names
    platform_names = {
        "youtube": "유튜브 쇼츠",
        "instagram": "인스타그램 릴스",
        "facebook": "페이스북 릴스",
        "tiktok": "틱톡",
        "naver_clip": "네이버 클립"
    }
    
    for res in results:
        kr_name = platform_names.get(res.platform, res.platform)
        if res.status == "url_verified" and res.url:
            lines.append(f"✅ {kr_name}: {res.url}")
        elif res.status == "failed" or res.error:
            lines.append(f"❌ {kr_name}: {res.error or '알 수 없는 오류'}")
        else:
            # Handle cases where it was published but URL wasn't verified
            msg = "게시 완료는 확인했지만 최종 URL을 확보하지 못함" if res.status == "published" else f"상태: {res.status}"
            lines.append(f"⚠️ {kr_name}: {msg}")
            
    return "\n".join(lines)
