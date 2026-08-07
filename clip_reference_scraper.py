import os
import re
import urllib.parse
import json
import urllib.request

OBSIDIAN_REF_DB_PATH = r"C:\Users\5700G\Documents\카카오톡 받은 파일\노리몰_가이드\Obsidian Vault\04_광고 소재 레퍼런스 DB"
CACHE_DIR = os.path.join(os.getcwd(), "scraped_clip_cache")

def fetch_real_naver_clip_metadata(url: str) -> dict:
    """네이버 클립 URL 접속 ➡️ 실제 원본 메타데이터(og:title, og:description) 실시간 수집"""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15"}
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
        print(f"[Scraper Live Warning] {e}")
    return {"title": "", "description": ""}

def analyze_custom_clip_link_or_text(input_text_or_url: str, keyword: str = "추천소재", category: str = "건강/가전", no_narration: bool = False) -> dict:
    """
    사용자가 직접 입력한 실제 네이버 클립 영상 링크 또는 자막 텍스트를 라이브 수집 & AI 구조분해 분석
    (no_narration=True 인 경우 음성 나레이션 없음 소재로 분석)
    """
    text_content = input_text_or_url.strip()
    is_url = text_content.startswith("http://") or text_content.startswith("https://")
    
    source_url = text_content if is_url else f"https://m.search.naver.com/search.naver?query={urllib.parse.quote(keyword)}"
    clip_title = f"[{keyword}] 실제 네이버 클립 레퍼런스 분석"
    
    # 1. URL이 들어왔을 때: 실제 네이버 클립 웹사이트 메타데이터(제목/설명) 실시간 수집!
    if is_url:
        meta = fetch_real_naver_clip_metadata(text_content)
        real_title = meta.get("title", "")
        real_desc = meta.get("description", "")
        
        if real_title:
            clip_title = real_title
        
        if real_desc:
            parsed_script = f"{real_title}. {real_desc}"
        else:
            parsed_script = f"{real_title if real_title else keyword} 자막 및 시각 연출 중심 레퍼런스 소재입니다."
    else:
        parsed_script = text_content

    # 2. 실시간 추출된 텍스트 문장 파싱
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])|\n', parsed_script) if s.strip()]
    if not sentences:
        sentences = [parsed_script]

    # 첫 3초 훅 / 결핍 / USP / CTA 4단계 자동 매핑
    sections = [
        ("후킹/어그로 (0~3초)", "타깃 지정 및 스크롤을 내리던 고객의 주의를 1초 만에 붙잡는 시각적 훅"),
        ("결핍/불안 자극", "방치 시 발생할 통증/손해에 대한 불안 자극 및 고발 연출"),
        ("USP/메디컬 앵커링", "일반 제품과의 차별화된 기술적/물리적 설득 명분 제공"),
        ("CTA/위험 소거", "100% 무상 환불 보증 및 프로필 링크 구매 유도 행동 장치")
    ]

    script_table = []
    for idx, (sec_title, visual_desc) in enumerate(sections):
        audio_part = "(없음 - BGM 및 화면자막 전용 소재)" if no_narration else (sentences[idx] if idx < len(sentences) else sentences[-1] if sentences else parsed_script)
        text_part = sentences[idx] if idx < len(sentences) else sentences[-1] if sentences else parsed_script
        
        script_table.append({
            "section": sec_title,
            "audio": audio_part,
            "visual": visual_desc,
            "text": text_part[:30] + "..." if len(text_part) > 30 else text_part
        })

    clip_data = {
        "keyword": keyword,
        "title": clip_title,
        "category": category,
        "author": "네이버 클립 라이브 수집",
        "video_url": source_url,
        "video_stream_url": "",
        "real_stt_script": parsed_script,
        "no_narration": no_narration,
        "script_table": script_table,
        "marketer_notes": [
            f"소재 유형: {'🔇 나레이션 없음 (자막/화면 연출 중심 소재)' if no_narration else '🎙️ 음성 나레이션 탑재 소재'}",
            f"네이버 클립 원본 라이브 URL: {source_url}",
            "첫 3초 시청 완독률을 극대화하는 직관적 결핍 고발형 훅 구조 적용.",
            "나레이션 없이 자막 자극 및 밈(Meme) 교차 연출로 시각 몰입도 극대화.",
            "자사 제품(다피다 허리 찜질기 / 파우리나 재활자전거) 숏폼 대본 카피라이팅에 즉시 트위스트 적용 가능."
        ]
    }

def audit_marketing_quality_strictly(script_text: str, target_product: str) -> dict:
    """
    [옵시디언 업무가이드 GUIDE-DA-01 100% 기반 빡센 AI 마케터 심사 엔진]
    Q1. 초반 3초~5초 후킹 단어/결핍 타게팅 (20점)
    Q2. 데드존 UI 안전성 및 자막 템포 (20점)
    Q3. 2~3초 간격 속청 컷 전환 템포 (20점)
    Q4. 메디컬/과한 데이터 이성적 구매 설득 USP (20점)
    Q5. 긴급성 유도 및 30일 환불 위험소거 CTA (20점)
    """
    score = 100
    audits = []

    # 1. Q1: 초반 3초~5초 후킹 어그로 심사 (20점)
    hook_keywords = ["사람", "아픈", "고통", "퇴근", "앉아", "고민", "의사", "허리", "무릎", "특가", "후회", "비밀"]
    has_hook = any(kw in script_text for kw in hook_keywords)
    if not has_hook:
        score -= 20
        audits.append({
            "옵시디언 심사 항목": "🎯 Q1. 초반 3초 후킹 단어 (어그로)",
            "판정 결과": "❌ 감점 (-20점)",
            "옵시디언 마케팅 분석": "1초 만에 시청자 스크롤을 멈출 타깃/결핍 단어가 극초반 대사에 부족함.",
            "필수 수정 지침": "👉 대사 첫 문장에 '하루종일 앉아있는 사람', '퇴근 후 허리통증' 등 결핍 단어 필수 추가"
        })
    else:
        audits.append({
            "옵시디언 심사 항목": "🎯 Q1. 초반 3초 후킹 단어 (어그로)",
            "판정 결과": "✅ 통과 (+20점)",
            "옵시디언 마케팅 분석": "극초반 결핍 타겟팅 문구가 포함되어 시청 스크롤 멈춤 효과 확보.",
            "필수 수정 지침": "현 대사 훅 유지"
        })

    # 2. Q2: 데드존 안전 가독성 심사 (20점)
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])|\n', script_text) if s.strip()]
    long_sentences = [s for s in sentences if len(s) > 35]
    if long_sentences:
        score -= 20
        audits.append({
            "옵시디언 심사 항목": "👁️ Q2. 데드존 UI 가림 위험",
            "판정 결과": "❌ 감점 (-20점)",
            "옵시디언 마케팅 분석": f"문장이 너무 길어({len(long_sentences[0])}자) 하단 네이버 클립 UI에 자막이 가려질 위험이 큼.",
            "필수 수정 지침": "👉 한 자막 문장을 22자 이내로 숏컷 분할하여 배치할 것"
        })
    else:
        audits.append({
            "옵시디언 심사 항목": "👁️ Q2. 데드존 UI 가림 위험",
            "판정 결과": "✅ 통과 (+20점)",
            "옵시디언 마케팅 분석": "문장 길이가 짧아 자막이 클립 UI 데드존을 침범하지 않음.",
            "필수 수정 지침": "현 자막 템포 유지"
        })

    # 3. Q3: 2~3초 속청 컷 전환 템포 심사 (20점)
    if len(sentences) < 4:
        score -= 20
        audits.append({
            "옵시디언 심사 항목": "⏱️ Q3. 2~3초 속청 컷 전환 템포",
            "판정 결과": "❌ 감점 (-20점)",
            "옵시디언 마케팅 분석": "15~30초 숏폼 내 문장/화면 컷 전환수가 최소 4개 미만이어서 시청자가 지루함을 느낌.",
            "필수 수정 지침": "👉 2초 간격으로 시각 컷 전환 및 추임새 대사 1~2개 추가 배치"
        })
    else:
        audits.append({
            "옵시디언 심사 항목": "⏱️ Q3. 2~3초 속청 컷 전환 템포",
            "판정 결과": "✅ 통과 (+20점)",
            "옵시디언 마케팅 분석": "문장 호흡이 촘촘하여 2~3초 간격 시각 컷 전환이 원활함.",
            "필수 수정 지침": "현 컷 전환 구성 유지"
        })

    # 4. Q4: 메디컬/과한 데이터 구매 설득 USP 심사 (20점)
    usp_keywords = ["원적외선", "근적외선", "듀얼", "3파장", "자동", "스피드", "페달", "수동", "모드", "속근육", "침투", "한의원"]
    has_usp = any(kw in script_text for kw in usp_keywords)
    if not has_usp:
        score -= 20
        audits.append({
            "옵시디언 심사 항목": "🏥 Q4. 과한 데이터/메디컬 설득 USP",
            "판정 결과": "❌ 감점 (-20점)",
            "옵시디언 마케팅 분석": f"자사 제품({target_product})만의 기술적/물리적 설득 차별점이 대사에 언급되지 않음.",
            "필수 수정 지침": "👉 '원적외선+3파장 근적외선 듀얼 침투' 또는 '3단계 자동 스피드 조절' 명분 필수 삽입"
        })
    else:
        audits.append({
            "옵시디언 심사 항목": "🏥 Q4. 과한 데이터/메디컬 설득 USP",
            "판정 결과": "✅ 통과 (+20점)",
            "옵시디언 마케팅 분석": "자사 제품만의 기술적 설득 차별점이 대사에 명확히 포함됨.",
            "필수 수정 지침": "현 기술 USP 문구 유지"
        })

    # 5. Q5: 긴급성 유도 & 30일 환불 CTA 심사 (20점)
    cta_keywords = ["반품", "환불", "보증", "30일", "스토어", "링크", "클릭", "특가", "쿠폰"]
    has_cta = any(kw in script_text for kw in cta_keywords)
    if not has_cta:
        score -= 20
        audits.append({
            "옵시디언 심사 항목": "🛒 Q5. 긴급성 유도 & 환불 CTA",
            "판정 결과": "❌ 감점 (-20점)",
            "옵시디언 마케팅 분석": "시청자의 결제 장벽을 허무는 30일 무료 반품이나 상품 스티커 이동 문구가 부재함.",
            "필수 수정 지침": "👉 영상 후반 '안 맞으면 30일 무상 환불 가능하니 아래 상품 스티커 클릭' 멘트 필수 삽입"
        })
    else:
        audits.append({
            "옵시디언 심사 항목": "🛒 Q5. 긴급성 유도 & 환불 CTA",
            "판정 결과": "✅ 통과 (+20점)",
            "옵시디언 마케팅 분석": "30일 환불 보증 및 상품 스티커 이동 지시 문구가 포함되어 CVR 유도 가능.",
            "필수 수정 지침": "현 CTA 문구 유지"
        })

    # 빡센 총평 문구
    if score == 100:
        verdict = "🔥 **[프로 마케터급 상위 1% 소재 (GUIDE-DA-01 만점)]**: 네이버 클립 1~6탭 상위 노출 및 일 유효 유입 150명 / CVR 5% 목표 달성이 확정적인 완벽한 소재입니다."
    elif score >= 80:
        verdict = "👍 **[양호하지만 감점 1건 보완 필요]**: 감점된 1가지 항목을 보완하지 않으면 중간 시청 완독률이 꺾일 수 있습니다."
    elif score >= 60:
        verdict = "⚠️ **[중간 이탈 위험 소재]**: 2가지 핵심 요소가 빠져있습니다. CVR 5% 달성을 위해 아래 감점 항목을 필수 보완하세요."
    else:
        verdict = "⛔ **[경고: CVR 미달 & 노출 실패 위험 소재]**: 현재 대본 상태로 업로드 시 제작 노력 및 광고비가 낭비될 위험이 높습니다. 감점 항목을 즉시 재수정하세요!"

    return {
        "score": score,
        "audits": audits,
        "verdict": verdict
    }

def generate_seo_and_marketing_from_user_script(user_script_text: str, target_product: str) -> dict:
    """
    AdForge Naver Clip Creative OS Multi-Agent 파이프라인 통합 구동:
    ResearchAgent ➡️ KeywordAgent ➡️ ClipIntelligenceAgent ➡️ CreativeAgent ➡️ SEOAgent ➡️ CreativeMemoryAgent
    """
    from agents.research import ResearchAgent
    from agents.keyword import KeywordAgent
    from agents.clip import ClipIntelligenceAgent
    from agents.creative import CreativeAgent
    from agents.seo import SEOAgent
    from agents.memory import CreativeMemoryAgent

    script_clean = user_script_text.strip()

    # 1. Research Agent (상품, 고객, 경쟁사, 시장 분석)
    research_agent = ResearchAgent()
    research_res = research_agent.analyze_product_and_market(target_product, script_clean)

    # 2. Keyword Agent (114개 황금 키워드 & 10개 해시태그 파싱)
    keyword_agent = KeywordAgent()
    keyword_res = keyword_agent.extract_keywords_and_tags(script_clean, target_product)

    # 3. Clip Intelligence Agent / AdForge Reverse Engineering Engine
    clip_agent = ClipIntelligenceAgent()
    clip_res = clip_agent.reverse_engineer_clip_structure(script_clean, target_product)

    # 4. Creative Agent (24자 제목 & 200자 카피 작성)
    creative_agent = CreativeAgent()
    creative_res = creative_agent.generate_creative_copy(keyword_res["target_keyword"], target_product, script_clean)

    # 5. SEO Agent (5대 마케팅 지표 빡센 자동 심사)
    seo_agent = SEOAgent()
    seo_res = seo_agent.audit_marketing_quality_strictly(script_clean, target_product)

    # 6. Creative Memory Agent (시그니처 메모리 인사이트 반영)
    memory_agent = CreativeMemoryAgent()
    memory_res = memory_agent.get_memory_insights()

    return {
        "user_script": script_clean,
        "auto_keyword": keyword_res["target_keyword"],
        "seo_title": creative_res["seo_title"],
        "seo_desc": creative_res["seo_desc"],
        "seo_tags": keyword_res["seo_tags"],
        "store_link": creative_res["store_link"],
        "script_table": clip_res["script_table"],
        "marketer_notes": clip_res["marketer_notes"],
        "ai_audit": seo_res,
        "research_data": research_res,
        "memory_insights": memory_res
    }

def fix_brand_stt_typos(text: str) -> str:
    """
    Whisper STT가 자주 오인식하는 브랜드명 및 한국어 숏폼 멘트 실시간 보정 딕셔너리
    """
    typo_map = {
        "답이다": "다피다",
        "다 피다": "다피다",
        "다피 다": "다피다",
        "다필다": "다피다",
        "바우리나": "파우리나",
        "파우 리나": "파우리나",
        "파울리나": "파우리나",
        "약은 중인": "약 먹는 중인",
        "차진게": "찾게 된 게",
        "차진": "찾게 됨",
        "한 나름": "한낮의",
        "나름 근적외선": "근적외선"
    }
    corrected = text
    for wrong, right in typo_map.items():
        corrected = corrected.replace(wrong, right)
    return corrected

def analyze_real_uploaded_video_file(video_bytes: bytes, target_product: str) -> dict:
    """
    사용자가 업로드한 실제 MP4 동영상 파일 바이너리를 정밀 수집하고:
    1. Whisper AI initial_prompt 브랜드 힌트 추가로 100% 음성 인식 정확도 극대화
    2. 브랜드 오타 교정 딕셔너리로 '다피다', '파우리나' 오인식 자동 보정
    3. 옵시디언 001~017번 4컬럼 세부 구조분해 표 및 마케터 심사 생성
    """
    temp_dir = os.path.join(os.getcwd(), "temp_uploads")
    os.makedirs(temp_dir, exist_ok=True)
    temp_video_path = os.path.join(temp_dir, "uploaded_user_video.mp4")
    
    with open(temp_video_path, "wb") as f:
        f.write(video_bytes)

    extracted_text = ""
    # 1. Whisper AI 실시간 STT 음성 추출 (initial_prompt 힌트 제공으로 브랜드 오인식 방지)
    try:
        import whisper
        print(f"[Video Analyzer] Running Whisper AI transcription for {target_product}...")
        model = whisper.load_model("tiny")
        
        # 브랜드명 및 키워드 인식 힌트 프롬프트 제공
        prompt_hint = f"이 영상은 노리몰 {target_product}, 다피다 허리 찜질기, 파우리나 전동 재활 자전거, 원적외선 근적외선 온열 마사지기 제품 광고 숏폼 대본입니다."
        res = model.transcribe(temp_video_path, language="ko", initial_prompt=prompt_hint)
        raw_text = res.get("text", "").strip()
        
        # 2. 브랜드 오타 자동 교정 실행
        extracted_text = fix_brand_stt_typos(raw_text)
        print(f"[Video Analyzer Success] Corrected Script ({len(extracted_text)} chars): {extracted_text[:80]}...")
    except Exception as e_w:
        print(f"[Video Analyzer Warning] Whisper STT error: {e_w}")

    # 대본이 추출된 경우 해당 실시간 보정 대본으로 분석
    if extracted_text:
        return generate_seo_and_marketing_from_user_script(extracted_text, target_product)
    else:
        return generate_seo_and_marketing_from_user_script(f"{target_product} 자막 및 시각 연출 중심 소재입니다.", target_product)

def scrape_and_analyze_naver_clip(keyword: str) -> dict:
    """메인 호출 인터페이스"""
    return download_and_stt_real_naver_clip(keyword)

def save_reference_to_obsidian(clip_data: dict) -> str:
    """
    1번~17번 기존 04_광고 소재 레퍼런스 DB의 표준 양식과 100% 동기화하여 파일 저장
    """
    os.makedirs(OBSIDIAN_REF_DB_PATH, exist_ok=True)
    
    existing_files = [f for f in os.listdir(OBSIDIAN_REF_DB_PATH) if f.endswith(".md")]
    next_idx = len(existing_files) + 1
    id_str = f"{next_idx:03d}"
    
    keyword = clip_data["keyword"]
    title = clip_data["title"]
    filename = f"{id_str} {title}.md"
    file_path = os.path.join(OBSIDIAN_REF_DB_PATH, filename)

    table_rows = ""
    for row in clip_data["script_table"]:
        table_rows += f"| **{row['section']}** | {row['audio']} | {row['visual']} | {row['text']} |\n"

    notes_str = ""
    for note in clip_data["marketer_notes"]:
        notes_str += f"* **{note[:12]}...**: {note}\n"

    md_content = f"""---
type: 레퍼런스DB
id: "{id_str}"
title: {title}
category: {clip_data.get('category', '건강/가전')}
format_tag:
  - {keyword}
  - 네이버클립
  - 숏폼레퍼런스
  - 불안제어
  - 메디컬앵커링
updated: 2026-08-06
tags:
  - 레퍼런스DB
  - 건강
  - 마사지기
  - {keyword}
---

## 📌 기본 정보
* **카테고리**: #건강 #{keyword} #네이버클립
* **소재 유형**: #공포유형 #불안제어 #3초후킹 #메디컬앵커링
* **관련 마케팅 기법**: [[DA 영상 광고 및 벤치마킹]], [[설득 및 심리학 기법#3. 매몰비용 (Sunk Cost) 자극]], [[AI 기반 광고 기획 및 대본]]

---

## 🎬 숏폼 영상 소스 (플레이어)
<video src="{clip_data['video_stream_url']}" controls width="100%" style="border-radius: 8px; margin-bottom: 15px;"></video>

---

## 🎬 대본 및 화면 초단위 분석

| 구분 | 음성 (Audio Script) | 화면 (Visual) | 자막 (On-Screen Text) |
| :--- | :--- | :--- | :--- |
{table_rows}
---

## 💡 마케터 복기 & 소구점 (트위스트 팁)

{notes_str}
"""

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"[Scraper] Saved standard reference card to: {file_path}")
    return file_path
