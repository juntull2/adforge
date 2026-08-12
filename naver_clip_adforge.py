import os
import re
import csv
import json
import glob
import asyncio
import edge_tts
import pycapcut as cc
from pydub import AudioSegment as PydubAudio
from pydub.silence import detect_nonsilent

from auto_stock_downloader import fetch_and_download_mixkit_stock_videos
from pycapcut import SEC, Timerange, TrackType, TextStyle, TextBorder, TextSegment, AudioMaterial, AudioSegment, VideoMaterial, VideoSegment, ClipSettings
from pycapcut.metadata.effect_meta import EffectMeta
import threading

capcut_draft_lock = threading.Lock()

# -------------------------------------------------------------------
# FFmpeg 환경변수 경로 보정 (Windows 실행 보장)
# -------------------------------------------------------------------
os.environ["PATH"] += os.pathsep + r"C:\Program Files\FFmpeg\bin"

# -------------------------------------------------------------------
# 여기어때 잘난체 실제 윈도우 시스템 폰트 경로 연동
# -------------------------------------------------------------------
JALNAN_PATH = "C:/Users/5700G/AppData/Local/Microsoft/Windows/Fonts/Jalnan2TTF.ttf"
JALNAN_NAME = "Jalnan2"

class CustomFont:
    def __init__(self, font_name: str, font_path: str):
        self.name = font_name
        self.path = font_path
        self.resource_id = ""
        self.value = EffectMeta(font_name, False, "", "", "", [])

JALNAN_FONT = CustomFont(JALNAN_NAME, JALNAN_PATH)

# TextSegment.export_material Monkey-Patching
_orig_export_material = TextSegment.export_material

def _custom_export_material(self):
    ret = _orig_export_material(self)
    try:
        content_obj = json.loads(ret["content"])
        if "styles" in content_obj and len(content_obj["styles"]) > 0:
            content_obj["styles"][0]["font"] = {
                "id": "",
                "name": JALNAN_NAME,
                "path": JALNAN_PATH,
                "title": JALNAN_NAME
            }
            ret["content"] = json.dumps(content_obj, ensure_ascii=False)
    except Exception:
        pass

    ret["font_name"] = JALNAN_NAME
    ret["font_title"] = JALNAN_NAME
    ret["font_path"] = JALNAN_PATH
    ret["font_resource_id"] = ""
    ret["font_id"] = ""
    return ret

TextSegment.export_material = _custom_export_material

# -------------------------------------------------------------------
# 1. 옵시디언 03_제품 DB 동적 파서 및 기본 DB
# -------------------------------------------------------------------
OBSIDIAN_VAULT_PATH = r"C:\Users\5700G\Documents\카카오톡 받은 파일\노리몰_가이드\Obsidian Vault"
PRODUCT_DB_PATH = os.path.join(OBSIDIAN_VAULT_PATH, "03_제품 DB")

DEFAULT_PRODUCTS_DB = {
    "다피다 허리 찜질기": {
        "hub_keyword": "적외선 찜질복대",
        "target": "만성 허리 통증을 겪는 4050 여성 및 남성 / 부모님 효도선물층",
        "usp": "원적외선(방사율 0.902) + 근적외선(3파장) 동시 방출 (시장 유일 듀얼 적외선), 피부 속 3cm 깊은 척추 마디 침투 온열, 300g 초경량 슬림핏, 30일 무상 환불 보증",
        "pain_points": ["파스나 겉만 따뜻한 일반 찜질로는 속근육 통증 안 풀림", "병원/한의원 온열 치료비 부담"],
        "solution": "피부 속 3cm 깊은 척추 마디까지 침투하는 3파장 근적외선 + 원적외선 무선 복대",
        "stock_keywords": ["back pain", "massage"],
        "smartstore_url": "https://smartstore.naver.com/all-envy/products/12566869835",
        "reviews": [
            "한의원에서 근적외선 찜질 치료받던 느낌 그대로라 집에서 매일 차고 있어요.",
            "파스 붙여도 안 풀리던 굳은 허리가 속까지 따뜻해지면서 3분 만에 사르르 풀립니다.",
            "30일 환불 보증이라 반신반의하며 샀는데 부모님이 너무 만족하셔서 추가 구매했어요.",
            "무선에 300g 초경량이라 옷 속에 차고 청소하고 집안일할 수 있는 게 진짜 제일 편합니다."
        ]
    },
    "파우리나 전동재활자전거": {
        "hub_keyword": "노인용 하체회복기구",
        "target": "수술/입원/노화로 하체 근력이 저하되어 부모님이 걱정되는 50대 자녀",
        "usp": "노인생체역학 최적 관절각도 설계, 100W 무소음 고출력 모터, 허리 굽히지 않는 유선 리모컨 조작, 양방향 셀프 페달링",
        "pain_points": ["부모님이 거동 불편해 요양병원 눕게 될까 두려움", "전문 재활 센터 비용 부담 및 무리한 운동 시 관절 손상"],
        "solution": "집에서 리모컨으로 안전하고 편안하게 부모님 하체 근력을 회복시키는 무소음 전동 자전거",
        "stock_keywords": ["exercise", "elderly"],
        "smartstore_url": "https://smartstore.naver.com/martinishop/products/7095386764",
        "reviews": [
            "고관절 수술 후 거동 불편하셨던 어머님이 집에서 안전하게 매일 근력 운동하고 계십니다.",
            "모터 소리가 정말 조용해서 아파트 층간소음 걱정 없이 밤에도 부모님이 편하게 타세요.",
            "리모컨으로 조작하니까 허리 굽힐 필요 없어서 어르신들 쓰기에 딱 좋습니다."
        ]
    }
}

def load_obsidian_products_db() -> dict:
    """옵시디언 03_제품 DB 폴더 내 마크다운 파일들을 동적으로 파싱하여 제품 DB 업데이트"""
    products_db = dict(DEFAULT_PRODUCTS_DB)
    if os.path.exists(PRODUCT_DB_PATH):
        md_files = glob.glob(os.path.join(PRODUCT_DB_PATH, "*.md"))
        for md_file in md_files:
            try:
                prod_name = os.path.basename(md_file).replace(".md", "").strip()
                with open(md_file, "r", encoding="utf-8") as f:
                    content = f.read()

                # 허브키워드 추출
                hub_match = re.search(r"hub_keyword:\s*(.+)", content)
                hub_kw = hub_match.group(1).strip() if hub_match else "추천제품"

                # 리뷰/후기 텍스트 파싱
                reviews = []
                review_matches = re.findall(r"[*•-]\s*(?:\"|\')?([^\"\n\']+고|풀려|만족|좋아|추천|느낌|편해)[^\n]*", content)
                if review_matches:
                    reviews = review_matches[:4]
                else:
                    reviews = ["실제 구매 고객 만족도 4.9점! 100% 무상 환불 보증"]

                # 기존 DB 업데이트 또는 신규 추가
                if prod_name in products_db:
                    products_db[prod_name]["hub_keyword"] = hub_kw
                    products_db[prod_name]["reviews"] = reviews
                else:
                    products_db[prod_name] = {
                        "hub_keyword": hub_kw,
                        "target": "타깃 고객",
                        "usp": f"{prod_name} 핵심가치 및 차별화 포인트",
                        "pain_points": ["불편함 해소", "비용 부담"],
                        "solution": f"{prod_name}으로 빠르고 편리하게 해결",
                        "stock_keywords": ["health", "lifestyle"],
                        "reviews": reviews
                    }
            except Exception as e:
                print(f"Obsidian parsing warning for {md_file}: {e}")
    return products_db

PRODUCTS_DB = load_obsidian_products_db()

# -------------------------------------------------------------------
# 2. 네이버 클립 6탭 이내 상위 노출 황금 키워드 분석 데이터
# -------------------------------------------------------------------
def load_naver_clip_keywords() -> list:
    json_path = os.path.join(os.getcwd(), "extracted_keywords.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return [
        {"keyword": "허리삐끗했을때", "volume": "18,060", "clip_tab_rank": 2, "main_tab": "네이버 클립"},
        {"keyword": "허리아플때", "volume": "2,660", "clip_tab_rank": 3, "main_tab": "네이버 클립"},
        {"keyword": "허리디스크 찜질", "volume": "460", "clip_tab_rank": 4, "main_tab": "네이버 클립"},
        {"keyword": "허리통증운동", "volume": "770", "clip_tab_rank": 4, "main_tab": "네이버 클립"},
        {"keyword": "허리통증 스트레칭", "volume": "3,720", "clip_tab_rank": 4, "main_tab": "네이버 클립"},
        {"keyword": "허리디스크파열", "volume": "1,160", "clip_tab_rank": 4, "main_tab": "네이버 클립"},
        {"keyword": "허리통증완화방법", "volume": "110", "clip_tab_rank": 5, "main_tab": "네이버 클립"},
        {"keyword": "허리파스", "volume": "530", "clip_tab_rank": 5, "main_tab": "네이버 클립"},
        {"keyword": "허리통증파스", "volume": "640", "clip_tab_rank": 6, "main_tab": "네이버 클립"},
        {"keyword": "허리근육통", "volume": "1,700", "clip_tab_rank": 3, "main_tab": "네이버 클립"},
        {"keyword": "임산부 허리통증", "volume": "3,140", "clip_tab_rank": 3, "main_tab": "네이버 클립"},
        {"keyword": "허리통증 주사", "volume": "1,900", "clip_tab_rank": 3, "main_tab": "네이버 클립"},
        {"keyword": "허리통증 타이레놀", "volume": "580", "clip_tab_rank": 4, "main_tab": "네이버 클립"},
        {"keyword": "허리통증원인", "volume": "1,020", "clip_tab_rank": 6, "main_tab": "네이버 클립"},
        {"keyword": "척추신경차단술", "volume": "820", "clip_tab_rank": 4, "main_tab": "네이버 클립"},
        {"keyword": "하지방사통", "volume": "810", "clip_tab_rank": 5, "main_tab": "네이버 클립"},
        {"keyword": "허리근육통증", "volume": "370", "clip_tab_rank": 3, "main_tab": "네이버 클립"},
        {"keyword": "허리디스크재활운동", "volume": "450", "clip_tab_rank": 3, "main_tab": "네이버 클립"},
        {"keyword": "디스크시술", "volume": "330", "clip_tab_rank": 3, "main_tab": "네이버 클립"},
        {"keyword": "70대아빠선물", "volume": "40", "clip_tab_rank": 5, "main_tab": "네이버 클립"},
        {"keyword": "80대할머니선물", "volume": "1,820", "clip_tab_rank": 6, "main_tab": "네이버 클립"},
        {"keyword": "80대할머니생신선물", "volume": "180", "clip_tab_rank": 6, "main_tab": "네이버 클립"}
    ]

NAVER_CLIP_TOP_KEYWORDS = load_naver_clip_keywords()

# -------------------------------------------------------------------
# 3. 오디오 앞/뒤 무음 공백 제거(Silence Trimming)
# -------------------------------------------------------------------
def trim_audio_silence(mp3_path: str, silence_thresh_db: int = -42):
    try:
        audio = PydubAudio.from_file(mp3_path)
        nonsilent = detect_nonsilent(audio, min_silence_len=10, silence_thresh=silence_thresh_db)
        if nonsilent:
            start_trim = max(0, nonsilent[0][0] - 20)
            end_trim = min(len(audio), nonsilent[-1][1] + 20)
            trimmed_audio = audio[start_trim:end_trim]
            trimmed_audio.export(mp3_path, format="mp3")
    except Exception as e:
        print(f"Audio trim warning: {e}")

# -------------------------------------------------------------------
# 4. 한국어 정밀 발음 가중치 및 문장 구조화
# -------------------------------------------------------------------
def calculate_effective_speech_length(text: str) -> float:
    letters_count = len(re.sub(r'[\s.,!?…]', '', text))
    punct_count = len(re.findall(r'[,!?…]', text))
    return letters_count + (punct_count * 1.5)

def split_script_by_sentences_and_phrases(script_text: str, max_chars_per_phrase: int = 10):
    # 1. 문장 단위(오디오 생성 단위)는 구두점(.!?…) 기준으로만 분리 (원본 \n 유지)
    raw_sentences = re.split(r'(?<=[.!?…])', script_text)
    
    sentence_structures = []
    
    for raw in raw_sentences:
        sentence_raw = raw.strip(' \t\r')
        if not sentence_raw.strip():
            continue
            
        # 오디오 생성을 위한 깨끗한 문장 (엔터를 공백으로 치환)
        clean_sentence = sentence_raw.replace('\n', ' ').strip()
        clean_sentence = re.sub(r'\s+', ' ', clean_sentence)
        
        # 2. 자막 쪼개기 (엔터 기준 최우선 적용)
        if '\n' in sentence_raw:
            # 사용자가 직접 엔터로 자막 단위를 명시한 경우
            phrases = [p.strip() for p in sentence_raw.split('\n') if p.strip()]
        else:
            # 엔터가 없는 경우, 기존 글자 수 기반 쪼개기 알고리즘 폴백
            sentence = clean_sentence
            if len(sentence) <= max_chars_per_phrase:
                phrases = [sentence]
            else:
                words = sentence.split(" ")
                phrases = []
                current_phrase = ""
                for word in words:
                    if len(current_phrase) + len(word) + 1 <= max_chars_per_phrase:
                        current_phrase += (" " if current_phrase else "") + word
                    else:
                        if current_phrase:
                            phrases.append(current_phrase)
                        current_phrase = word
                if current_phrase:
                    phrases.append(current_phrase)
                    
        sentence_structures.append({
            "full_sentence": clean_sentence,
            "phrases": phrases
        })
        
    return sentence_structures

# -------------------------------------------------------------------
# 5. 스톡 비디오 소스 자동 수급 헬퍼
# -------------------------------------------------------------------
from auto_stock_downloader import fetch_and_download_mixkit_stock_videos, fetch_pexels_portrait_videos, fetch_pixabay_portrait_videos
import random

def get_or_download_stock_videos(keywords: list, pexels_key: str = "", pixabay_key: str = "") -> list:
    stock_dir = os.path.join(os.getcwd(), "stock_videos")
    os.makedirs(stock_dir, exist_ok=True)
    
    mp4_files = glob.glob(os.path.join(stock_dir, "*.mp4"))
    if not mp4_files:
        print("💡 저장된 스톡 비디오가 없어 자동으로 다운로드합니다...")
        sources = ["mixkit"]
        if pexels_key:
            sources.append("pexels")
        if pixabay_key:
            sources.append("pixabay")
            
        for kw in keywords:
            chosen_source = random.choice(sources)
            if chosen_source == "pexels":
                fetch_pexels_portrait_videos(kw, api_key=pexels_key, count=4, output_dir=stock_dir)
            elif chosen_source == "pixabay":
                fetch_pixabay_portrait_videos(kw, api_key=pixabay_key, count=4, output_dir=stock_dir)
            else:
                fetch_and_download_mixkit_stock_videos(kw, count=4, output_dir=stock_dir)
                
        mp4_files = glob.glob(os.path.join(stock_dir, "*.mp4"))
        
    return mp4_files

def find_best_video_for_sentence(sentence: str, stock_videos: list, last_used_video: str = "") -> str:
    if not stock_videos:
        return ""
        
    # 키워드 매핑 (한국어 대본 단어 -> 파일명 키워드)
    keyword_map = {
        "마사지": ["massage"],
        "문지": ["massage"], 
        "비벼": ["massage"],
        "스트레칭": ["stretching", "yoga"],
        "늘려": ["stretching", "yoga"],
        "당겨": ["stretching", "yoga"],
        "허리": ["back_pain"],
        "통증": ["back_pain", "relief"],
        "요가": ["yoga"],
        "명상": ["yoga", "healthy_lifestyle"],
        "운동": ["fitness", "workout", "exercise"],
        "스쿼트": ["fitness", "workout"],
        "다리": ["fitness", "workout"],
        "일어": ["fitness", "workout"],
        "앉아": ["fitness", "workout"]
    }
    
    sentence_lower = sentence.lower()
    matched_videos = []
    
    # 문장에 매핑된 키워드가 포함되어 있는지 확인
    for kr_kw, en_kws in keyword_map.items():
        if kr_kw in sentence_lower:
            for v_file in stock_videos:
                v_name = os.path.basename(v_file).lower()
                if any(en_kw in v_name for en_kw in en_kws):
                    matched_videos.append(v_file)
                    
    # 중복 제거
    matched_videos = list(set(matched_videos))
    
    # 1순위: 매칭된 비디오가 있다면 그 중에서 랜덤 선택
    if matched_videos:
        # 이전에 사용한 영상과 가급적 겹치지 않게 (매칭된게 2개 이상일 때)
        candidates = [v for v in matched_videos if v != last_used_video]
        if candidates:
            return random.choice(candidates)
        return random.choice(matched_videos)
        
    # 2순위: 매칭된 비디오가 없으면 전체에서 랜덤 선택하되, 직전 영상은 피함
    candidates = [v for v in stock_videos if v != last_used_video]
    if candidates:
        return random.choice(candidates)
    return random.choice(stock_videos)

# -------------------------------------------------------------------
# 6. 스마트스토어 상세페이지 결합 6가지+2가지 신규 대본 포맷 생성 엔진
# -------------------------------------------------------------------

import google.generativeai as genai

def generate_naver_clip_script(product_name: str, topic: str, api_key: str):
    """AI 대본 기획 (4050 여성 건강 타깃 맞춤형)"""
    if not api_key:
        return f"[{topic}] 건강 정보", "API 키가 설정되지 않았습니다. 대시보드 설정에서 API 키를 입력해주세요."
        
    genai.configure(api_key=api_key)
    prod = PRODUCTS_DB.get(product_name, DEFAULT_PRODUCTS_DB.get("다피다 허리 찜질기", {}))
    usp = prod.get("usp", "")
    reviews = " ".join(prod.get("reviews", []))
    
    prompt = f"""
    당신은 4050 여성 대상 네이버 클립(숏폼) 전문 건강 콘텐츠 기획자입니다.
    주제(키워드): {topic}
    제품명: {product_name}
    제품 강점(USP): {usp}
    고객 후기 요약: {reviews}
    
    [필수 가이드라인]
    1. 대상: 40대~50대 여성 (본인 건강 관리, 부모님 건강 걱정, 집안일 등 일상 통증)
    2. 형식: 숏폼 영상용 내레이션 대본 (약 20~30초 분량, 3~5문장 내외)
    3. 구성: [초반 3초 후킹 및 공감] -> [건강/정보 제공] -> [자연스러운 해결책/제품 언급]
    4. 가드레일 (매우 중요): 
       - 의료적 효능을 확정하거나 단정하는 표현 절대 금지 (예: "완치됩니다", "치료됩니다" ❌).
       - 과도한 공포 조성 금지 (예: "방치하면 큰일 납니다", "평생 고생합니다" ❌).
       - 일상에서 느끼는 불편함을 부드럽게 공감하는 어조 사용 (예: "뻐근하시죠?", "집에서 간편하게 관리해보세요" ⭕).
    5. 출력 형식:
       첫 줄은 반드시 SEO 제목 (예: [{topic}] 집에서 쉽게 따라하는 건강 관리법)
       두 번째 줄부터는 내레이션 대본만 순수하게 작성. (행동 지시문, 음악, 효과음 등 불필요한 텍스트 기재 금지)
    
    위 가이드라인에 맞춰 자연스럽고 유익한 건강 정보 숏폼 대본을 작성해주세요.
    """
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        content_lines = response.text.strip().split('\\n', 1)
        if len(content_lines) > 1:
            seo_title = content_lines[0].strip()
            script_text = content_lines[1].strip()
        else:
            seo_title = f"[{topic}] 건강 정보"
            script_text = content_lines[0].strip()
            
        # 간단한 정제
        seo_title = seo_title.replace("**", "")
        script_text = script_text.replace("**", "").replace("-", "")
        
        return seo_title, script_text
    except Exception as e:
        return f"[{topic}] 건강 꿀팁", f"대본 생성 중 오류가 발생했습니다: {str(e)}"

def generate_seo_recommendation(script_text: str, api_key: str):
    """AI SEO 추천 (제목/키워드/해시태그/Hook/CTA)"""
    if not api_key:
        return "API 키가 설정되지 않아 SEO 추천을 생성할 수 없습니다."
        
    genai.configure(api_key=api_key)
    prompt = f"""
    다음은 네이버 클립 숏폼 대본입니다:
    {script_text}
    
    이 대본을 바탕으로 4050 여성 타깃에 최적화된 네이버 클립용 SEO 추천안을 작성해주세요.
    
    [출력 형식 - 반드시 이 양식을 지켜주세요]
    - 추천 제목: (어그로가 아닌 정보성 제목)
    - 추천 해시태그: (5개 내외)
    - 추천 Hook: (영상 첫 3초 시선 끌기용 화면 텍스트)
    - 추천 CTA: (고정 댓글이나 영상 마지막에 들어갈 행동 유도 문구)
    """
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"SEO 추천 생성 중 오류가 발생했습니다: {str(e)}"

# -------------------------------------------------------------------

def generate_strategic_script_stream(
    topic_category: str,
    sub_topic: str,
    video_format: str,
    product_name: str,
    api_key: str,
    model_name: str = "mistralai/mistral-nemotron",
    custom_system_prompt: str = "",
    benchmark_script: str = "",
    reference_document: str = "",
    hook_type: str = "DESIRE",
    visual_hook: str = "BODY",
    expert_present: bool = True
):
    """4050 여성을 타겟으로 하는 네이버 클립 대본 생성 (스트리밍)"""
    if not api_key:
        yield "API 키가 설정되지 않았습니다."
        return
        
    try:
        from openai import OpenAI
        _base_url = "https://openrouter.ai/api/v1" if api_key.startswith("sk-or-") else "https://integrate.api.nvidia.com/v1"
        client = OpenAI(base_url=_base_url, api_key=api_key)
        
        base_prompt = custom_system_prompt.strip()
        if not base_prompt:
            base_prompt = """당신은 '몸편한하루' 채널의 전문 콘텐츠 전략가 겸 숏폼 대본 작가입니다.

[채널 정체성]
몸편한하루는 50~70대 시청자를 핵심 타겟으로 하는 시니어 건강·운동 숏폼 채널입니다.
핵심 가치: "나이가 들어서 몸이 예전 같지 않은 사람들이, 오늘 당장 따라 할 수 있는 작고 쉬운 건강 습관을 알려주는 채널"

[콘텐츠 핵심 철학]
- 정보는 신뢰성 있게 / 표현은 쉽게 / Hook은 강하게 / 운동은 쉽게
- "어렵게 설명하지 말고, 지금 당장 따라 하게 만든다."
- 전문용어 최소화. 나쁜 예: "슬관절 주변의 근육을 활성화하여" → 좋은 예: "무릎이 예전 같지 않다면 이 동작부터"
- 과도한 공포 조장 금지: "이거 안 하면 무조건 큰일납니다", "이 운동만 하면 당뇨가 치료됩니다" 등 확정적·치료 보장형 표현 절대 사용 금지
- 올바른 표현: "도움이 될 수 있습니다", "관리에 도움이 되는 방법입니다", "전문가들이 흔히 권하는 방법 중 하나입니다"

[시청자 감정 흐름]
공감("어? 나도 그런데?") → 호기심("이건 몰랐는데?") → 긴장감("이거 안 하면 안 되겠는데?") → 낮은 진입장벽("이 정도면 나도 할 수 있겠다") → 행동 유도("일단 한번 해봐야겠다")

[시니어 친화 운동 기준]
- 의자, 벽 등 집에서 도구 없이 가능
- 10초/30초/1분 등 짧게 시작
- 동작 단순하고 설명 직관적
- 고강도·전문 장비 필요·복잡한 루틴 절대 지양

[언어 규칙]
SCRIPT 영역에는 영어나 알파벳을 단 한 글자도 사용하지 마세요. TTS 엔진이 고장납니다. 100% 순한국어로 작성."""

        system_prompt = f"""{base_prompt}

[현재 작업 설정]
- 카테고리: {topic_category}
- 세부 주제: {sub_topic}
- 제품 정보: {product_name}
- 선택 포맷: {video_format}
"""
        
        if benchmark_script.strip():
            system_prompt += f"\n[벤치마킹 대본 원문 — 후킹 방식, 톤앤매너, 구조만 참고해서 새 대본 작성]\n{benchmark_script.strip()}\n"

        if reference_document.strip():
            system_prompt += f"""
[참고 전문 지식]
{reference_document.strip()}

→ 위 자료에서 의학적 팩트/인사이트를 추출하되, 전문용어를 쉽고 친근하게 변환하여 대본에 반영하세요.
"""

        system_prompt += f"""
[대본 작성 규칙]

1. Hook 유형: {hook_type}
첫 1~3초에 시청자가 "어? 이거 나한테 하는 말인데?" 라고 느끼게 만드세요. 아래 Hook 유형 중 선택된 유형({hook_type})을 반드시 적용하세요:
- 경고형: "무릎 아프다고 이 동작부터 하지 마세요."
- 금지형: "식후에 바로 이 행동은 하지 마세요."
- 숫자형: "딱 10초만 이렇게 해보세요."
- 연령형: "50대부터는 이 근육이 정말 중요합니다." (⚠️ 연령형 Hook일 때만 첫 문장에서 "50대부터" 허용. 이후 본문은 반드시 간접 표현 사용)
- 공감형: "계단 몇 층만 올라가도 숨차시죠?"
- 궁금증형: "왜 아침마다 허리가 뻣뻣할까요?"
- 반전형: "걷기만 열심히 한다고 해결되지 않습니다."
- 비교형: "10분 걷는 것과 30분 걷는 것, 뭐가 다를까요?"
- 체크리스트형: "이 중 2개 이상 해당된다면 꼭 보세요."
- 행동유도형: "지금 의자에서 일어나서 이것부터 해보세요."

2. 대본 구조 (PASTOR):
- P (Hook): 위 Hook 유형 적용. 첫 문장은 강하게.
- A (Amplify) [{'전문가 인용 포함' if expert_present else '전문가 인용 제외'}]: {'의사나 트레이너의 관점을 1~2문장으로 인용하여 신뢰감을 높이세요.' if expert_present else '전문가 없이 핵심 원인만 1문장으로 빠르게 전달하고 해결책으로 넘어가세요.'}
- S (Solution + 미드롤 CTA): 해결책 공개 전 "좋아요 먼저 누르고 따라하세요!" 등 CTA 삽입 후 쉽고 구체적인 해결법 제시.
- T (Transformation): 1단계, 2단계로 매우 짧게 행동 지시. 감각적 단어 필수("시원하다" 대신 "막힌 혈류가 뚫리는 느낌").
- O (Offer): 마지막 문장은 반드시 특정 키워드 댓글 유도. "도움이 되셨다면 좋아요" 절대 금지. Sunk Cost 심리 자극.

3. 나이 표현 규칙:
- Hook 첫 문장에서 연령형({hook_type})일 때만 "50대부터" 허용
- 본문 전체에서 "시니어", "중년", "4050", "노년" 등 직접 나이 지칭 금지
- 대신 간접 표현 사용: "예전 같지 않은 몸", "요즘 부쩍", "나잇살", "젊을 때와 다르게"

4. 언어·형식:
- 대본(SCRIPT)에 영어 알파벳 단 한 글자도 금지 (TTS 오류 발생)
- 문장 수: 10~15문장 (약 45~60초 분량)
- 각 문장은 짧게. 2~4 단어 단위로 Enter를 쳐서 세로 자막에 최적화
- 밋밋한 정보 전달 금지. "오늘은 혈당 관리에 좋은 운동을 알려드리겠습니다" 같은 아나운서 말투 금지.
- "내용은 신뢰할 수 있게, 포장은 강하게" 유지

5. 포맷 규칙:
   - 포맷 A (순수 정보형): 제품 언급 0%. 꿀팁만. 마지막은 댓글 CTA.
   - 포맷 B (간접 홍보): 꿀팁(80%) + "제가 쓰는 기구는 댓글에!" (20%). 영상 내 브랜드명 "{product_name}" 절대 언급 금지.
   - 포맷 C (직접 홍보): "{product_name}" 이름으로 직접 리뷰 및 추천. 나쁜 대안과 비교.
   - 포맷 D (Q&A): 시청자 사연을 읽어주고 속 시원한 해결책 제시.
   - 포맷 E (팩트체크): 흔한 오해를 반박하며 올바른 정보 제공.
   - 포맷 F (스토리텔링): 본인/지인의 생생한 경험담(고생담)으로 공감 유도 후 팁 제공.

OUTPUT STRUCTURE:
You MUST output exactly FIVE sections (Visual Hook, Script, Comment, DM Message, Description), separated by exactly these delimiters: "====VISUAL_HOOK====", "====SCRIPT====", "====COMMENT====", "====DM_MESSAGE====", and "====DESCRIPTION====".
[CRITICAL RULE]: DO NOT output any thinking process, chain-of-thought, or internal monologue. DO NOT write "Let's think" or any other conversational text. You MUST start your response IMMEDIATELY with the "====VISUAL_HOOK====" delimiter.

====VISUAL_HOOK====
Write a 1-sentence direction for the video editor or AI video generator for the FIRST 3 SECONDS of the video.
This visual must match the selected Visual Hook type: [{visual_hook}]
Types: BODY(탄탄한 하체/몸매 노출), MOVEMENT(안정적 한발서기 등 움직임), BEFORE_AFTER(자세 교정 전후), PROBLEM_SITUATION(허리 부여잡는 모습), EXPERT(전문가 진찰 모습), EXERCISE_RESULT(운동 후 땀흘리는 모습)

====SCRIPT====
Write the narration text for a 45-60 second short-form video (10-15 sentences).
Format: just raw text that a TTS can read nicely. No timestamps, no visual directions.
CRITICAL FORMATTING RULE: You MUST break the text into very short lines (2~4 words per line) by hitting Enter frequently. This is for easy reading as vertical subtitles.
[CRITICAL RULE]: DO NOT include any word counts, reasoning, calculations, or numbering (e.g. "Sentence 1", "Words: 5") inside the script. ONLY write the actual Korean narration text itself.
Example format:
허리 깊숙이 박힌
얼음장 같은 냉기,
겉만 데워선
절대 안 빠집니다.

====COMMENT====
[Comment CTA for DM Automation]
Write a pinned comment designed for DM (Direct Message) automation.
Encourage viewers to leave a specific keyword in the comments to receive a DM with the secret tips, full video, or product link.
Structure it briefly and engagingly.
- Example: "영상 속 000 운동법 풀영상이 궁금하시다면 댓글에 '비법'이라고 남겨주세요! DM으로 바로 보내드릴게요💌"
- If Format B or C, the DM promise should be about the product link.
CRITICAL: The entire comment MUST BE UNDER 300 CHARACTERS.

====DM_MESSAGE====
[Direct Message Content]
Write the actual message to be sent via DM to users who commented the keyword.
- FIRST LINE (후킹 오프닝): MUST be 15 characters or less. Make it feel personal, warm, and surprising — NOT generic like "댓글 달아주셔서 감사합니다". Instead use something that feels like a friend reaching out (e.g., "드디어 기다리셨죠!💌", "오셨군요! 기다렸어요✨", "여기 왔어요! 반가워요😊", "도착했어요! 꼭 보세요🌿").
- REST OF MESSAGE: Friendly, conversational Korean. Include a placeholder for the link: [LINK].
CRITICAL: The entire DM message MUST BE UNDER 300 CHARACTERS.

====DESCRIPTION====
[Video Title, Description & Hashtags]
Write the Title, Description, and Hashtags optimized for Naver SEO.
- TITLE: MUST BE UNDER 24 CHARACTERS. Make it highly clickable.
- DESCRIPTION & HASHTAGS: Write a brief description followed by 3-5 hashtags.
CRITICAL: The Description and Hashtags combined MUST BE UNDER 200 CHARACTERS. Do not exceed this limit.
Format exactly like this:
TITLE: [Your Title Here]
BODY: [Your Description and Hashtags Here]
"""

        kwargs = {
            "model": model_name,
            "messages": [{"role": "user", "content": system_prompt}],
            "stream": True,
            "max_tokens": 4096,
            "temperature": 0.7,
            "top_p": 0.95
        }
        
        completion = client.chat.completions.create(**kwargs)
        
        for chunk in completion:
            if not chunk.choices:
                continue
                
            reasoning = getattr(chunk.choices[0].delta, "reasoning_content", None)
            if reasoning:
                yield reasoning
                
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content
                
    except Exception as e:
        raise Exception(f"AI 대본 생성 실패: {str(e)}")

def generate_cta_from_script_stream(script_text: str, api_key: str, model_name: str = "mistralai/mistral-nemotron"):
    """기존 대본으로부터 고정댓글(CTA) + DM 메세지 + 영상 설명 & 해시태그 생성 (스트리밍)"""
    if not api_key:
        yield "API 키가 설정되지 않았습니다."
        return

    try:
        from openai import OpenAI
        _base_url = "https://openrouter.ai/api/v1" if api_key.startswith("sk-or-") else "https://integrate.api.nvidia.com/v1"
        client = OpenAI(base_url=_base_url, api_key=api_key)

        system_prompt = f"""You are a Korean short-form content marketing expert specializing in Naver Clip.
Based on the provided video script, generate THREE sections in Korean.

[영상 대본]
{script_text.strip()}

OUTPUT STRUCTURE:
You MUST output exactly THREE sections separated by these exact delimiters: "====COMMENT====", "====DM_MESSAGE====", and "====DESCRIPTION====".
[CRITICAL RULE]: DO NOT output any thinking process, chain-of-thought, or internal monologue. DO NOT write "Let's think" or any other conversational text. You MUST start your response IMMEDIATELY with the "====COMMENT====" delimiter.

====COMMENT====
[Comment CTA for DM Automation]
영상 내용을 보고 시청자가 DM 자동화에 참여하도록 유도하는 고정 댓글을 한국어로 작성하세요.
대본의 핵심 운동/행동을 키워드로 삼아 댓글을 유도하세요.
예시: "이 운동법 전체 영상이 궁금하시면 댓글에 '복근 탄력'이라고 남겨주세요! DM으로 바로 보내드릴게요💌"
CRITICAL: 전체 댓글 300자 이내.

====DM_MESSAGE====
[Direct Message Content]
댓글 키워드를 남긴 사람에게 실제로 보낼 DM 메세지를 한국어로 작성하세요.
- 첫 줄 (후킹 오프닝): 반드시 15자 이내. 식상한 "댓글 달아주셔서 감사합니다" 절대 금지. 친구가 먼저 연락한 것처럼 따뜻하고 놀라운 느낌으로 시작하세요.
  예시: "드디어 기다리셨죠!💌", "오셨군요! 기다렸어요✨", "여기 왔어요! 반가워요😊", "도착했어요! 꼭 보세요🌿", "발견하셨군요!🎉"
  대본 주제와 자연스럽게 어울리는 표현으로 창의적으로 작성하세요.
- 나머지: 친근하고 따뜻한 톤으로, 링크 자리에는 [LINK] 표시.
CRITICAL: 전체 DM 메세지 300자 이내.

====DESCRIPTION====
[Video Title, Description & Hashtags]
영상 제목, 설명, 해시태그를 네이버 SEO에 최적화해서 한국어로 작성하세요.
- TITLE: 24자 이내. 클릭을 유도하는 제목.
- DESCRIPTION & HASHTAGS: 간단한 설명 + 해시태그 3~5개.
CRITICAL: 설명과 해시태그 합산 200자 이내.
Format:
TITLE: [제목]
BODY: [설명 + 해시태그]
"""

        kwargs = {
            "model": model_name,
            "messages": [{"role": "user", "content": system_prompt}],
            "stream": True,
            "max_tokens": 1024,
            "temperature": 0.7,
            "top_p": 0.95
        }

        completion = client.chat.completions.create(**kwargs)

        for chunk in completion:
            if not chunk.choices:
                continue

            reasoning = getattr(chunk.choices[0].delta, "reasoning_content", None)
            if reasoning:
                yield reasoning

            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content

    except Exception as e:
        yield f"\n\nCTA 생성 중 오류가 발생했습니다: {str(e)}"

def generate_image_prompts_stream(script_text: str, api_key: str, model_name: str = "mistralai/mistral-nemotron"):
    """이미지 생성(Hailuo AI)을 위한 영문 프롬프트 추출기 (NVIDIA API 스트리밍)"""
    if not api_key:
        yield "API 키가 설정되지 않았습니다."
        return
        
    try:
        from openai import OpenAI
        _base_url = "https://openrouter.ai/api/v1" if api_key.startswith("sk-or-") else "https://integrate.api.nvidia.com/v1"
        client = OpenAI(base_url=_base_url, api_key=api_key)
        prompt = f"""
        You are an expert AI image prompt engineer for MiniMax Hailuo AI (Image Generation).
        Below is a short-form video script.
        I need you to break down this script into logical visual scenes (approx 3-5 scenes) to be used as a storyboard or thumbnail reference.
        For each scene, provide a concise but highly detailed English prompt to generate a cinematic, realistic image using Hailuo AI.
        
        CRITICAL RULES FOR HAILUO IMAGE PROMPTS:
        1. Aspect Ratio: Every prompt MUST begin with "Vertical 9:16 portrait framing," to specify a vertical image format. Do NOT use tags like --ar.
        2. Modular Formula: Every prompt MUST strictly follow this sequence:
           [9:16 Portrait Frame] + [Subject + Description] + [Action/Pose] + [Environment/Background] + [Lighting & Mood] + [Camera Shot/Style]
        3. Subject Details: Be extremely precise about appearance and textures (e.g., "A 40-year-old Korean woman wearing a cozy white knit sweater").
        4. Scene & Mood: Provide atmospheric cues for cinematic polish (e.g., "golden hour, cinematic lighting, photorealistic, highly detailed, sharp focus").
        5. Intro Scene Rule: For the first scene (the initial explanation/narration), you MUST feature a "professional doctor in a white lab coat looking directly at the camera" to build viewer trust.
        6. Conciseness: Keep it focused. Do not write paragraphs. Use sequential modular descriptors separated by commas.
        
        Script:
        {script_text}
        
        Output Format (strictly follow this for EVERY scene):
        [Scene N] <Korean summary of the scene>
        Prompt: <English Prompt for Image Generation>
        """
        
        kwargs = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "max_tokens": 4096,
            "temperature": 0.8,
            "top_p": 0.95
        }
        
        completion = client.chat.completions.create(**kwargs)
        
        for chunk in completion:
            if not chunk.choices:
                continue
                
            reasoning = getattr(chunk.choices[0].delta, "reasoning_content", None)
            if reasoning:
                yield reasoning
                
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content
                
    except Exception as e:
        yield f"\n\n이미지 프롬프트 생성 중 오류가 발생했습니다: {str(e)}"

def generate_hailuo_prompts_stream(script_text: str, api_key: str, model_name: str = "mistralai/mistral-nemotron"):
    """Hailuo 텍스트-투-비디오 프롬프트 생성용 영문 프롬프트 추출기 (NVIDIA API 스트리밍)"""
    if not api_key:
        yield "API 키가 설정되지 않았습니다."
        return
        
    try:
        from openai import OpenAI
        _base_url = "https://openrouter.ai/api/v1" if api_key.startswith("sk-or-") else "https://integrate.api.nvidia.com/v1"
        client = OpenAI(base_url=_base_url, api_key=api_key)
        prompt = f"""
        You are an expert AI video prompt engineer for MiniMax Hailuo AI.
        Below is a short-form video script.
        I need you to break down this script into logical visual scenes (approx 3-5 scenes).
        For each scene, provide a concise but highly detailed English prompt to generate a cinematic, realistic video clip.
        
        CRITICAL RULES FOR HAILUO AI PROMPTS:
        0. ASPECT RATIO (MANDATORY — ALWAYS FIRST): Every single prompt MUST begin with "Vertical 9:16 portrait framing, smartphone short-form video format," — this is non-negotiable and applies to ALL scenes without exception.
        1. Modular Formula: Every prompt MUST strictly follow this sequence:
           [9:16 Portrait Frame] + [Camera Shot + Motion] + [Subject + Description] + [Action Constraint] + [Scene + Environment] + [Lighting & Mood]
        2. Camera & Motion: Use only portrait-friendly shots (e.g., "Close-up shot, tilt-up", "Medium shot, eye-level", "Low angle looking up"). Avoid wide landscape shots that break vertical framing.
        3. Subject Details: Be extremely precise about appearance and textures to avoid distortion. The primary character MUST be a "young Korean female trainer wearing leggings and a tight sports top" (e.g., "A young attractive Korean female fitness trainer wearing black leggings and a white sports bra, ponytail hair").
        4. Action Constraints: Avoid vague descriptions. Define physical behavior accurately to prevent motion chaos (e.g., "gently massaging her lower back with a warm smile").
        5. Scene & Mood: Provide atmospheric cues for cinematic polish (e.g., "golden hour, cinematic rim lighting, volumetric lighting, shallow depth of field, bokeh, Arri Alexa").
        6. INTRO SCENE RULE (MANDATORY): For the first 1-2 scenes (the initial explanation/narration), you MUST feature this "young Korean female trainer explaining to the camera" to immediately grab attention and build visual interest.
        7. Negative Constraints: Exclude artifacts by adding anti-prompts at the end (e.g., "no plastic texture, no distorted faces, no text overlays, no horizontal landscape composition").
        8. Conciseness: Keep it focused. Do not write paragraphs. Use sequential modular descriptors separated by commas.

        Script:
        {script_text}
        
        Output Format (strictly follow this for EVERY scene):
        [Scene N] <Korean summary of the scene>
        소스 유형: [📦 스톡 영상] OR [🤖 Hailuo 생성]
        판단 근거: <1줄 이유>
        Prompt: <English Prompt for Hailuo AI — only if 🤖 Hailuo 생성. If 📦 스톡 영상, write a Pexels search keyword instead>
        
        SOURCE TYPE DECISION RULES:
        - Use [📦 스톡 영상] when the scene shows: generic lifestyle footage, nature, city, product close-ups, abstract background, simple walking/moving shots that don't require a specific character or branded action.
        - Use [🤖 Hailuo 생성] when the scene requires: a specific character (doctor, specific person), branded product demonstration, unique medical/health explanation gesture, or any scene where stock footage would look generic and unconvincing.
        
        [Scene 2] ...
        """
        
        kwargs = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "max_tokens": 4096,
            "temperature": 1,
            "top_p": 0.95
        }
        
        completion = client.chat.completions.create(**kwargs)
        
        for chunk in completion:
            if not chunk.choices:
                continue
                
            reasoning = getattr(chunk.choices[0].delta, "reasoning_content", None)
            if reasoning:
                yield reasoning
                
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content
                
    except Exception as e:
        yield f"\n\n프롬프트 생성 중 오류가 발생했습니다: {str(e)}"

# -------------------------------------------------------------------
# 6. AI TTS + 배경 비디오 소스 + Pretendard 자막 100% 자동 제작
# -------------------------------------------------------------------
async def generate_tts_audio(text: str, output_path: str, voice_config="ko-KR-SunHiNeural"):
    """
    Microsoft Edge TTS 엔진을 사용하여 텍스트를 음성(mp3)으로 변환
    """
    communicate = edge_tts.Communicate(text, voice_config)
    await communicate.save(output_path)

import requests

def generate_elevenlabs_tts(text: str, output_path: str, voice_id: str, api_key: str):
    """
    ElevenLabs API를 사용하여 텍스트를 음성(mp3)으로 변환
    """
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key
    }
    
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75
        }
    }
    
    response = requests.post(url, json=data, headers=headers)
    if response.status_code != 200:
        raise Exception(f"ElevenLabs API Error: {response.status_code} - {response.text}")
        
    with open(output_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)

def generate_fish_audio_tts(text: str, output_path: str, reference_id: str, api_key: str):
    """
    Fish Audio API를 사용하여 텍스트를 음성(mp3)으로 변환
    """
    url = "https://api.fish.audio/v1/tts"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "model": "s2.1-pro-free"  # Fish Audio 공식 무료 API 적용
    }
    
    data = {
        "text": text,
        "format": "mp3",
    }
    
    if reference_id:
        data["reference_id"] = reference_id
        
    response = requests.post(url, json=data, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Fish Audio API Error: {response.status_code} - {response.text}")
        
    with open(output_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)

def get_capcut_projects():
    import os
    import json
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        local_app_data = os.path.expanduser("~\\AppData\\Local")
    base_path = os.path.join(local_app_data, "CapCut", "User Data", "Projects", "com.lveditor.draft")
    projects = []
    if os.path.exists(base_path):
        for folder in os.listdir(base_path):
            info_file = os.path.join(base_path, folder, "draft_meta_info.json")
            if os.path.exists(info_file):
                try:
                    with open(info_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        name = data.get("draft_name", folder)
                        projects.append((name, folder))
                except:
                    pass
    return sorted(projects, key=lambda x: x[0])

def build_from_template(script_text: str, voice: str, api_key: str, template_folder_name: str):
    import time, shutil, uuid, copy
    from pydub import AudioSegment as PydubAudio
    
    project_name = f"AutoProject_{int(time.time())}"
    temp_dir = os.path.join(os.getcwd(), "temp_audio")
    os.makedirs(temp_dir, exist_ok=True)
    
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        local_app_data = os.path.expanduser("~\\AppData\\Local")
    base_path = os.path.join(local_app_data, "CapCut", "User Data", "Projects", "com.lveditor.draft")
    
    src_folder = os.path.join(base_path, template_folder_name)
    dst_folder = os.path.join(base_path, project_name)
    if not os.path.exists(src_folder):
        raise Exception(f"템플릿 폴더를 찾을 수 없습니다: {src_folder}")
    
    shutil.copytree(src_folder, dst_folder)
    
    sentence_structures = split_script_by_sentences_and_phrases(script_text, max_chars_per_phrase=10)
    
    combined_audio = PydubAudio.empty()
    phrase_timings = []
    current_us = 0
    
    for s_idx, struct in enumerate(sentence_structures, 1):
        full_sentence = struct["full_sentence"]
        phrases = struct["phrases"]
        clean_audio_text = re.sub(r'[*#\[\]_=\-]', '', full_sentence).strip()
        if not clean_audio_text:
            continue
            
        mp3_path = os.path.join(temp_dir, f"{project_name}_s{s_idx}.mp3")
        try:
            if voice.startswith("el_"):
                generate_elevenlabs_tts(clean_audio_text, mp3_path, voice_id=voice.replace("el_", ""), api_key=api_key)
            elif voice.startswith("fish_"):
                fish_api_key = os.environ.get("FISH_API_KEY", "")
                generate_fish_audio_tts(clean_audio_text, mp3_path, reference_id=voice.replace("fish_", ""), api_key=fish_api_key)
            else:
                import asyncio
                asyncio.run(generate_tts_audio(clean_audio_text, mp3_path, voice_config=voice))
        except Exception as e:
            print(f"오디오 생성 실패, 무료 TTS로 대체: {e}")
            try:
                import asyncio
                asyncio.run(generate_tts_audio(clean_audio_text, mp3_path, voice_config="ko-KR-SunHiNeural"))
            except Exception as e2:
                raise Exception(f"오디오 생성 완전 실패: {e}")
            
        trim_audio_silence(mp3_path)
        seg = PydubAudio.from_mp3(mp3_path)
        sentence_duration_us = int(len(seg) * 1000)
        combined_audio += seg
        
        phrase_effective_lens = [calculate_effective_speech_length(p) for p in phrases]
        total_effective_len = sum(phrase_effective_lens) or 1.0
        phrase_start_us = current_us
        
        for p_idx, (phrase, eff_len) in enumerate(zip(phrases, phrase_effective_lens)):
            if p_idx == len(phrases) - 1:
                phrase_dur = (current_us + sentence_duration_us) - phrase_start_us
            else:
                phrase_dur = int(sentence_duration_us * (eff_len / total_effective_len))
            
            phrase_timings.append({
                "text": phrase,
                "start": phrase_start_us,
                "duration": phrase_dur
            })
            phrase_start_us += phrase_dur
            
        current_us += sentence_duration_us
        
    final_audio_path = os.path.join(temp_dir, f"{project_name}_merged.mp3")
    combined_audio.export(final_audio_path, format="mp3")
    total_audio_dur_us = current_us
    
    meta_file = os.path.join(dst_folder, "draft_meta_info.json")
    with open(meta_file, 'r', encoding='utf-8') as f:
        meta = json.load(f)
    meta["draft_name"] = project_name
    with open(meta_file, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False)
        
    content_file = os.path.join(dst_folder, "draft_content.json")
    with open(content_file, 'r', encoding='utf-8') as f:
        content = json.load(f)
        
    if "audios" in content["materials"] and len(content["materials"]["audios"]) > 0:
        main_audio = content["materials"]["audios"][0]
        local_audio_path = os.path.join(dst_folder, "merged.mp3")
        shutil.copy2(final_audio_path, local_audio_path)
        main_audio["path"] = local_audio_path
        main_audio["duration"] = total_audio_dur_us
        
        for track in content["tracks"]:
            if track["type"] == "audio":
                for seg in track["segments"]:
                    if seg["material_id"] == main_audio["id"]:
                        seg["source_timerange"]["duration"] = total_audio_dur_us
                        seg["target_timerange"]["duration"] = total_audio_dur_us

    if "videos" in content["materials"] and len(content["materials"]["videos"]) > 0:
        for track in content.get("tracks", []):
            if track["type"] == "video" and not track.get("is_sub_video", False):
                if len(track["segments"]) > 0:
                    last_seg = track["segments"][-1]
                    last_seg["target_timerange"]["duration"] = total_audio_dur_us - last_seg["target_timerange"]["start"]

    if "texts" in content["materials"] and len(content["materials"]["texts"]) > 0:
        text_materials = content["materials"]["texts"]
        # 템플릿의 1번 텍스트는 후킹(강조), 2번 텍스트는 기본 자막으로 파싱
        tmpl_text_mat_hook = text_materials[0]
        tmpl_text_mat_default = text_materials[1] if len(text_materials) > 1 else text_materials[0]
        
        tmpl_text_seg_hook = None
        tmpl_text_seg_default = None
        text_track = None
        for track in content.get("tracks", []):
            if track["type"] == "text":
                if len(track["segments"]) > 0:
                    text_track = track
                    tmpl_text_seg_hook = track["segments"][0]
                    tmpl_text_seg_default = track["segments"][1] if len(track["segments"]) > 1 else track["segments"][0]
                    break
                    
        if text_track and tmpl_text_seg_hook:
            text_track["segments"] = []
            content["materials"]["texts"] = []
            def _gen_id(): return str(uuid.uuid4()).upper()
            
            for idx, pt in enumerate(phrase_timings):
                is_hook = (idx == 0)
                base_mat = tmpl_text_mat_hook if is_hook else tmpl_text_mat_default
                base_seg = tmpl_text_seg_hook if is_hook else tmpl_text_seg_default
                
                new_mat = copy.deepcopy(base_mat)
                new_mat["id"] = _gen_id()
                try:
                    c_obj = json.loads(new_mat["content"])
                    c_obj["text"] = pt["text"]
                    new_mat["content"] = json.dumps(c_obj, ensure_ascii=False)
                except:
                    pass
                content["materials"]["texts"].append(new_mat)
                
                new_seg = copy.deepcopy(base_seg)
                new_seg["id"] = _gen_id()
                new_seg["material_id"] = new_mat["id"]
                new_seg["target_timerange"]["start"] = pt["start"]
                new_seg["target_timerange"]["duration"] = pt["duration"]
                text_track["segments"].append(new_seg)

    with open(content_file, 'w', encoding='utf-8') as f:
        json.dump(content, f, ensure_ascii=False)
        
    print(f"\n[완료] 템플릿 기반 초안: '{project_name}'")
    return project_name

def build_capcut_project_for_naver_clip(script_text: str, voice="ko-KR-SunHiNeural", el_api_key="", template_folder=None, keyword="", pexels_api_key="", pixabay_api_key=""):
    if template_folder and template_folder != "none":
        return build_from_template(script_text, voice, el_api_key, template_folder)
    """
    순수 자동화 로직:
    1. 대본 텍스트를 문장/구절(Phrases) 단위로 분리
    2. TTS 오디오 생성 및 무음 제거 (Edge TTS or ElevenLabs)
    3. 오디오 길이에 맞춰 스톡 비디오 컷 편집
    4. 구절(Phrase) 단위로 100% 정밀 캡컷 자막(TextSegment) 싱크 배치
    5. 캡컷 draft_content.json 파일 빌드 (포팅)
    """
    import time
    import uuid
    # 동시 실행 시 timestamp가 겹치지 않도록 uuid 추가
    project_name = f"AutoProject_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    
    # 채널 방향성 문서 11항: 시니어 타겟과 어울리는 영상 키워드 우선 사용
    # keyword가 있으면 해당 주제 + senior 컨텍스트로 검색
    SENIOR_VIDEO_CONTEXTS = [
        "senior exercise", "elderly gentle exercise", "older adult workout",
        "senior fitness", "elderly stretching", "senior healthy lifestyle",
        "older woman exercise home", "gentle senior movement"
    ]
    import random
    senior_ctx = random.choice(SENIOR_VIDEO_CONTEXTS)
    if keyword:
        stock_search_keywords = [keyword, senior_ctx]
    else:
        stock_search_keywords = [senior_ctx, "abstract background"]
    stock_videos = get_or_download_stock_videos(stock_search_keywords, pexels_key=pexels_api_key, pixabay_key=pixabay_api_key)

    # 캡컷 DraftFolder 접근은 순차적으로 (Lock으로 보호)
    with capcut_draft_lock:
        draft_folder_path = "C:/Users/임준모/AppData/Local/CapCut/User Data/Projects/com.lveditor.draft"
        # 폴더가 없으면 직접 생성
        os.makedirs(draft_folder_path, exist_ok=True)
        draft_folder = cc.DraftFolder(draft_folder_path)
    
        try:
            script_file = draft_folder.create_draft(project_name, width=1080, height=1920, fps=30, allow_replace=True)
        except (PermissionError, OSError) as e:
            project_name = f"{project_name}_r{uuid.uuid4().hex[:4]}"
            script_file = draft_folder.create_draft(project_name, width=1080, height=1920, fps=30, allow_replace=True)
    
        # 9:16 세로 숏폼 캔버스 비율 명시적 고정
        script_file.content["canvas_config"] = {"width": 1080, "height": 1920, "ratio": "9:16"}
    
        # 🎬 트랙 3개 준비
        script_file.add_track(TrackType.video, track_name="메인_비디오_트랙")
        script_file.add_track(TrackType.text, track_name="자막_트랙")
        script_file.add_track(TrackType.audio, track_name="더빙_트랙")

    temp_dir = os.path.join(os.getcwd(), "temp_audio")
    os.makedirs(temp_dir, exist_ok=True)

    # 2~3줄 형태로 꽉 차게 보이기 위해 max_chars_per_phrase=18 적용
    sentence_structures = split_script_by_sentences_and_phrases(script_text, max_chars_per_phrase=18)

    print(f"\n========================================================")
    print(f"[네이버 클립 프로젝트 생성 시작] {project_name}")
    
    print(f"[자동 비디오 교차 배치] 보유 스톡 비디오 {len(stock_videos)}개 교차 연동")
    print(f"========================================================")

    current_time_us = 0
    video_usage_tracker = {v_file: 0 for v_file in stock_videos}
    last_used_video = ""

    for s_idx, struct in enumerate(sentence_structures, 1):
        full_sentence = struct["full_sentence"]
        phrases = struct["phrases"]

        clean_audio_text = re.sub(r'[*#\[\]_=\-]', '', full_sentence).strip()
        if not clean_audio_text:
            continue

        mp3_path = os.path.join(temp_dir, f"{project_name}_s{s_idx}.mp3")
        try:
            if voice.startswith("el_"):
                # ElevenLabs TTS
                real_voice_id = voice.replace("el_", "")
                if not el_api_key:
                    raise Exception("ElevenLabs API Key가 없습니다.")
                generate_elevenlabs_tts(clean_audio_text, mp3_path, voice_id=real_voice_id, api_key=el_api_key)
            elif voice.startswith("fish_"):
                # Fish Audio TTS
                fish_reference_id = voice.replace("fish_", "")
                fish_api_key = os.environ.get("FISH_API_KEY", "")
                if not fish_api_key:
                    raise Exception("Fish Audio API Key가 없습니다.")
                generate_fish_audio_tts(clean_audio_text, mp3_path, reference_id=fish_reference_id, api_key=fish_api_key)
            else:
                # Edge TTS
                asyncio.run(generate_tts_audio(clean_audio_text, mp3_path, voice_config=voice))
        except Exception as e:
            print(f"  [오디오 생성 실패, 무료 TTS로 대체] {e}")
            try:
                import asyncio
                asyncio.run(generate_tts_audio(clean_audio_text, mp3_path, voice_config="ko-KR-SunHiNeural"))
            except Exception as e2:
                raise Exception(f"오디오 생성 완전 실패: {e}")

        # 오디오 무음 정밀 트림
        trim_audio_silence(mp3_path)

        audio_mat = AudioMaterial(mp3_path)
        sentence_duration_us = audio_mat.duration

        # 오디오 트랙 추가
        audio_timerange = Timerange(current_time_us, sentence_duration_us)
        script_file.add_segment(AudioSegment(audio_mat, audio_timerange), track_name="더빙_트랙")

        # 🎬 1. 배경 비디오 소스 2~3초 단위 교차 자동 배치!
        if stock_videos:
            v_file = find_best_video_for_sentence(full_sentence, stock_videos, last_used_video=last_used_video)
            last_used_video = v_file
            try:
                v_mat = VideoMaterial(v_file)
                clip_dur = min(v_mat.duration, sentence_duration_us)
                
                start_offset = video_usage_tracker.get(v_file, 0)
                if start_offset + clip_dur > v_mat.duration:
                    start_offset = 0
                    clip_dur = min(v_mat.duration, sentence_duration_us)
                    
                src_timerange = Timerange(start_offset, clip_dur)
                tgt_timerange = Timerange(current_time_us, clip_dur)
                
                # 9:16 (1080x1920) 캔버스에 맞게 자동 스케일링(크롭)
                scale_factor = max(1080.0 / v_mat.width, 1920.0 / v_mat.height) if getattr(v_mat, 'width', 0) and getattr(v_mat, 'height', 0) else 1.0
                clip_settings = ClipSettings(scale_x=scale_factor, scale_y=scale_factor)
                
                v_seg = VideoSegment(v_mat, tgt_timerange, source_timerange=src_timerange, clip_settings=clip_settings)
                script_file.add_segment(v_seg, track_name="메인_비디오_트랙")
                video_usage_tracker[v_file] = start_offset + clip_dur
            except Exception as ve:
                print(f"  (비디오 소스 연동 알림: {ve})")

        # 🎯 2. 자막 구절별 100% 정밀 싱크 배치
        phrase_effective_lens = [calculate_effective_speech_length(p) for p in phrases]
        total_effective_len = sum(phrase_effective_lens) or 1.0
        phrase_start_us = current_time_us

        for p_idx, (phrase, eff_len) in enumerate(zip(phrases, phrase_effective_lens)):
            if p_idx == len(phrases) - 1:
                phrase_duration_us = (current_time_us + sentence_duration_us) - phrase_start_us
            else:
                phrase_duration_us = int(sentence_duration_us * (eff_len / total_effective_len))

            phrase_timerange = Timerange(phrase_start_us, phrase_duration_us)

            # 3초(3,000,000 us) 이전 구간은 후킹 강조 스타일, 이후는 일반 스타일
            is_hook = current_time_us < 3000000

            style = TextStyle(
                size=14.5,
                color=(1.0, 0.9, 0.0) if is_hook else (1.0, 1.0, 1.0),
                bold=True,
                align=1
            )
            border = TextBorder(color=(0.0, 0.0, 0.0), width=45.0 if is_hook else 25.0)
            clip_settings = ClipSettings(transform_x=0.0, transform_y=0.0)

            text_seg = TextSegment(
                text=phrase,
                timerange=phrase_timerange,
                font=JALNAN_FONT,
                style=style,
                border=border,
                clip_settings=clip_settings
            )

            script_file.add_segment(text_seg, track_name="자막_트랙")
            phrase_start_us += phrase_duration_us

        sec_val = sentence_duration_us / SEC
        phrases_str = " -> ".join(phrases)
        print(f"  [문장 {s_idx}] 오디오 ({sec_val:.2f}s) 생성 완료 | 자막 싱크(10자): {phrases_str}")

        current_time_us += sentence_duration_us

    script_file.save()
    print(f"\n[완료] [AI더빙 + 비디오 컷 + 잘난체 자막] 100% 자동 완성! 초안: '{project_name}'")
    return project_name

if __name__ == "__main__":
    build_capcut_project_for_naver_clip("다피다 허리 찜질기", "허리아플때")
    build_capcut_project_for_naver_clip("파우리나 전동재활자전거", "노인용 하체회복기구")
