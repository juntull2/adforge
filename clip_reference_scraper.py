import os
import re
import urllib.parse
import urllib.request

def fetch_real_naver_clip_metadata(url: str) -> dict:
    """네이버 클립 URL 접속 ➡️ 실제 원본 메타데이터(og:title, og:description) 수집"""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            html = response.read().decode('utf-8', errors='ignore')
            title_match = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']', html, re.IGNORECASE)
            desc_match = re.search(r'<meta[^>]*property=["\']og:description["\'][^>]*content=["\']([^"\']+)["\']', html, re.IGNORECASE)
            
            title = title_match.group(1).strip() if title_match else ""
            desc = desc_match.group(1).strip() if desc_match else ""
            return {"title": title, "description": desc}
    except Exception as e:
        print(f"[Scraper Warning] {e}")
    return {"title": "", "description": ""}

def analyze_custom_clip_link(url_or_text: str, keyword: str = "추천소재") -> dict:
    """네이버 클립 링크 또는 텍스트 입력 시 메타데이터 및 단순 구조 분석"""
    text_content = url_or_text.strip()
    is_url = text_content.startswith("http://") or text_content.startswith("https://")
    
    source_url = text_content if is_url else f"https://m.search.naver.com/search.naver?query={urllib.parse.quote(keyword)}"
    clip_title = f"[{keyword}] 레퍼런스 분석"
    
    if is_url:
        meta = fetch_real_naver_clip_metadata(text_content)
        real_title = meta.get("title", "")
        real_desc = meta.get("description", "")
        if real_title: clip_title = real_title
        parsed_script = f"{real_title}. {real_desc}" if real_desc else real_title
    else:
        parsed_script = text_content

    sentences = [s.strip() for s in re.split(r'(?<=[.!?])|\n', parsed_script) if s.strip()]
    if not sentences: sentences = [parsed_script]

    # 단순화된 4단계 구조 매핑 (가벼운 분석)
    sections = [
        ("후킹/어그로 (0~3초)", "초반 시선 끌기"),
        ("결핍/불안 자극", "문제 제기"),
        ("해결책/정보", "제품/정보 제공"),
        ("CTA (행동 유도)", "행동 유도 텍스트")
    ]
    if is_url and len(sentences) <= 2:
        script_table.append({
            "section": "제목/메타데이터",
            "visual": "URL 자동 수집",
            "text": parsed_script
        })
        script_table.append({
            "section": "안내",
            "visual": "전체 대본 분석 불가",
            "text": "(네이버 클립 URL 방식으로는 시스템상 전체 대본을 가져올 수 없습니다. 상세 구조 분석을 원하시면 영상 대본 텍스트를 직접 붙여넣어 주세요.)"
        })
    else:
        for idx, (sec_title, visual_desc) in enumerate(sections):
            text_part = sentences[idx] if idx < len(sentences) else (sentences[-1] if sentences else parsed_script)
            script_table.append({
                "section": sec_title,
                "visual": visual_desc,
                "text": text_part[:50] + "..." if len(text_part) > 50 else text_part
            })

    return {
        "title": clip_title,
        "video_url": source_url,
        "real_stt_script": parsed_script,
        "script_table": script_table,
    }
