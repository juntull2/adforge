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

# -------------------------------------------------------------------
# FFmpeg 환경변수 경로 보정 (Windows 실행 보장)
# -------------------------------------------------------------------
os.environ["PATH"] += os.pathsep + r"C:\Program Files\FFmpeg\bin"

# -------------------------------------------------------------------
# Pretendard Black 실제 윈도우 시스템 폰트 경로 연동
# -------------------------------------------------------------------
PRETENDARD_BLACK_PATH = "C:/Users/5700G/AppData/Local/Microsoft/Windows/Fonts/Pretendard-Black.otf"
PRETENDARD_BLACK_NAME = "Pretendard Black"

class CustomFont:
    def __init__(self, font_name: str, font_path: str):
        self.name = font_name
        self.path = font_path
        self.resource_id = ""
        self.value = EffectMeta(font_name, False, "", "", "", [])

PRETENDARD_BLACK_FONT = CustomFont(PRETENDARD_BLACK_NAME, PRETENDARD_BLACK_PATH)

# TextSegment.export_material Monkey-Patching
_orig_export_material = TextSegment.export_material

def _custom_export_material(self):
    ret = _orig_export_material(self)
    try:
        content_obj = json.loads(ret["content"])
        if "styles" in content_obj and len(content_obj["styles"]) > 0:
            content_obj["styles"][0]["font"] = {
                "id": "",
                "name": PRETENDARD_BLACK_NAME,
                "path": PRETENDARD_BLACK_PATH,
                "title": PRETENDARD_BLACK_NAME
            }
            ret["content"] = json.dumps(content_obj, ensure_ascii=False)
    except Exception:
        pass

    ret["font_name"] = PRETENDARD_BLACK_NAME
    ret["font_title"] = PRETENDARD_BLACK_NAME
    ret["font_path"] = PRETENDARD_BLACK_PATH
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

def split_script_by_sentences_and_phrases(script_text: str, max_chars_per_phrase: int = 12):
    raw_sentences = re.split(r'(?<=[.!?…])|\n', script_text)
    sentence_structures = []

    for raw in raw_sentences:
        sentence = raw.strip()
        if not sentence:
            continue
        
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
            "full_sentence": sentence,
            "phrases": phrases
        })

    return sentence_structures

# -------------------------------------------------------------------
# 5. 스톡 비디오 소스 자동 수급 헬퍼
# -------------------------------------------------------------------
def get_or_download_stock_videos(keywords: list) -> list:
    stock_dir = os.path.join(os.getcwd(), "stock_videos")
    os.makedirs(stock_dir, exist_ok=True)
    
    mp4_files = glob.glob(os.path.join(stock_dir, "*.mp4"))
    if not mp4_files:
        print("💡 저장된 스톡 비디오가 없어 자동으로 8개를 다운로드합니다...")
        for kw in keywords:
            fetch_and_download_mixkit_stock_videos(kw, count=4, output_dir=stock_dir)
        mp4_files = glob.glob(os.path.join(stock_dir, "*.mp4"))
        
    return mp4_files

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
    model_name: str = "nvidia/nemotron-3-ultra-550b-a55b"
):
    """4050 여성을 타겟으로 하는 네이버 클립 대본 생성 (스트리밍)"""
    if not api_key:
        yield "API 키가 설정되지 않았습니다."
        return
        
    try:
        from openai import OpenAI
        client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=api_key
        )
        
        system_prompt = f"""You are an expert content strategist for Naver Clip, targeting 40~50-year-old women.
You write polite, trustworthy, and engaging 'senior format' scripts (using ~해요, ~습니다).

Current Task:
- Category: {topic_category}
- Specific Topic: {sub_topic}
- Product Context: {product_name}
- Selected Format: {video_format}

Format Guidelines:
A (Pure Info): 100% helpful tips. Zero product mention. End with "도움이 되셨다면 좋아요와 저장 부탁드려요!"
B (Indirect Promo): Give tips first, then casually mention "I use a specific device/item for this. I'll leave the one I use in the comments!". DO NOT say the brand name "{product_name}" in the video.
C (Direct Promo): Actively review and recommend "{product_name}" by name in the video, explaining its benefits.

OUTPUT STRUCTURE:
Write ONLY the content requested below, without any extra markdown formatting or conversational text.
Separate the video script, comment CTA, and video description with exactly these delimiters: "====COMMENT====" and "====DESCRIPTION===="

[Video Script]
Write the narration text for a 30-40 second short-form video.
Format: just raw text that a TTS can read nicely. No timestamps, no visual directions.

====COMMENT====
[Comment CTA]
If Format A: Write a polite comment encouraging engagement (no product).
If Format B: Write a comment promoting "{product_name}", e.g., "영상에서 말한 그 제품! 네이버에 '{product_name}'를 검색해 보세요."
If Format C: Write a comment with a link or search CTA for "{product_name}".

====DESCRIPTION====
[Video Description & Hashtags]
Write a catchy video description along with 3-5 relevant hashtags.
MUST BE UNDER 200 CHARACTERS TOTAL.
"""

        kwargs = {
            "model": model_name,
            "messages": [{"role": "user", "content": system_prompt}],
            "stream": True,
            "max_tokens": 4096,
            "temperature": 0.7,
            "top_p": 0.95
        }
        
        if "nemotron-3-ultra-550b" in model_name.lower():
            kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": True}, "reasoning_budget": 4096}
            kwargs["max_tokens"] = 16384
            
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
        yield f"오류 발생: {str(e)}"

def generate_hailuo_prompts_stream(script_text: str, api_key: str, model_name: str = "nvidia/nemotron-3-ultra-550b-a55b"):
    """Hailuo AI (MiniMax) 영상 생성용 영문 프롬프트 추출기 (NVIDIA API 스트리밍)"""
    if not api_key:
        yield "API 키가 설정되지 않았습니다."
        return
        
    try:
        from openai import OpenAI
        client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=api_key
        )
        prompt = f"""
        You are an expert AI video prompt engineer for MiniMax Hailuo AI.
        Below is a Korean short-form video script.
        I need you to break down this script into logical visual scenes (approx 3-5 scenes).
        For each scene, provide a concise but highly detailed English prompt to generate a cinematic, realistic video clip that matches the context.
        
        CRITICAL RULES FOR HAILUO AI PROMPTS:
        1. Sequence: Always write in the order of "Subject -> Place -> Action". (e.g., A 40-year-old woman in a bright living room stretching her back).
        2. Movements & Camera: Specify directions precisely (e.g., "moving from left to right"). Always specify camera height/movement (e.g., "eye-level camera", "smooth tracking shot").
        3. Negative Prompts: Explicitly exclude unwanted elements (e.g., "no distorted faces, no blurry motion, no text overlays").
        4. Character Consistency: If the same character appears across scenes, repeat phrases like "same woman, consistent face, same character, same hairstyle".
        5. Transitions: Describe transitions as physical actions, not magical effects (e.g., "lighting gradually shifts", "during the spin the background changes").
        6. Continuous Shots: To prevent unwanted camera cuts, add "eye-level camera, same distance, centered composition, smooth tracking shot, continuous single take, no cuts".
        7. Conciseness: Keep the prompt concise and focus only on the core visual elements. Do NOT use overly complex sentences.

        Script:
        {script_text}
        
        Output Format:
        [Scene 1] <Korean summary of the scene>
        Prompt: <English Prompt for Hailuo AI>
        
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
        
        if "nemotron-3-ultra-550b" in model_name.lower():
            kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": True}, "reasoning_budget": 4096}
            kwargs["max_tokens"] = 16384
            
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
    if isinstance(voice_config, dict):
        voice = voice_config.get("voice", "ko-KR-SunHiNeural")
        rate = voice_config.get("rate", "+0%")
        pitch = voice_config.get("pitch", "+0Hz")
    elif isinstance(voice_config, str) and voice_config.startswith("{"):
        try:
            cfg = json.loads(voice_config)
            voice = cfg.get("voice", "ko-KR-SunHiNeural")
            rate = cfg.get("rate", "+0%")
            pitch = cfg.get("pitch", "+0Hz")
        except Exception:
            voice, rate, pitch = voice_config, "+0%", "+0Hz"
    else:
        voice = voice_config
        rate = "+0%"
        pitch = "+0Hz"

    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)

def build_capcut_project_for_naver_clip(script_text: str, voice="ko-KR-SunHiNeural"):
    import time
    project_name = f"AutoProject_{int(time.time())}"
    
    # 캡컷 프로젝트용 스톡 비디오 (임시 더미용)
    stock_videos = get_or_download_stock_videos(["abstract background"])

    draft_folder_path = "C:/Users/5700G/AppData/Local/CapCut/User Data/Projects/com.lveditor.draft"
    draft_folder = cc.DraftFolder(draft_folder_path)

    try:
        script_file = draft_folder.create_draft(project_name, width=1080, height=1920, fps=30, allow_replace=True)
    except PermissionError:
        project_name = f"{project_name}_v11"
        script_file = draft_folder.create_draft(project_name, width=1080, height=1920, fps=30, allow_replace=True)

    # 9:16 세로 숏폼 캔버스 비율 명시적 고정
    script_file.content["canvas_config"] = {"width": 1080, "height": 1920, "ratio": "9:16"}

    # 🎬 트랙 3개 준비 (비디오 트랙 + 자막 트랙 + 오디오 트랙)
    script_file.add_track(TrackType.video, track_name="메인_비디오_트랙")
    script_file.add_track(TrackType.text, track_name="자막_트랙")
    script_file.add_track(TrackType.audio, track_name="더빙_트랙")

    temp_dir = os.path.join(os.getcwd(), "temp_audio")
    os.makedirs(temp_dir, exist_ok=True)

    sentence_structures = split_script_by_sentences_and_phrases(script_text, max_chars_per_phrase=12)

    print(f"\n========================================================")
    print(f"[네이버 클립 프로젝트 생성 시작] {project_name}")
    
    print(f"[자동 비디오 교차 배치] 보유 스톡 비디오 {len(stock_videos)}개 교차 연동")
    print(f"========================================================")

    current_time_us = 0

    for s_idx, struct in enumerate(sentence_structures, 1):
        full_sentence = struct["full_sentence"]
        phrases = struct["phrases"]

        mp3_path = os.path.join(temp_dir, f"{project_name}_s{s_idx}.mp3")
        asyncio.run(generate_tts_audio(full_sentence, mp3_path, voice_config=voice))

        # 오디오 무음 정밀 트림
        trim_audio_silence(mp3_path)

        audio_mat = AudioMaterial(mp3_path)
        sentence_duration_us = audio_mat.duration

        # 오디오 트랙 추가
        audio_timerange = Timerange(current_time_us, sentence_duration_us)
        script_file.add_segment(AudioSegment(audio_mat, audio_timerange), track_name="더빙_트랙")

        # 🎬 1. 배경 비디오 소스 2~3초 단위 교차 자동 배치!
        if stock_videos:
            v_file = stock_videos[(s_idx - 1) % len(stock_videos)]
            try:
                v_mat = VideoMaterial(v_file)
                clip_dur = min(v_mat.duration, sentence_duration_us)
                src_timerange = Timerange(0, clip_dur)
                tgt_timerange = Timerange(current_time_us, clip_dur)
                
                v_seg = VideoSegment(v_mat, tgt_timerange, source_timerange=src_timerange)
                script_file.add_segment(v_seg, track_name="메인_비디오_트랙")
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

            style = TextStyle(
                size=14.5,
                color=(1.0, 1.0, 1.0),
                bold=True,
                align=1
            )
            border = TextBorder(color=(0.0, 0.0, 0.0), width=45.0)
            clip_settings = ClipSettings(transform_x=0.0, transform_y=-0.48)

            text_seg = TextSegment(
                text=phrase,
                timerange=phrase_timerange,
                font=PRETENDARD_BLACK_FONT,
                style=style,
                border=border,
                clip_settings=clip_settings
            )

            script_file.add_segment(text_seg, track_name="자막_트랙")
            phrase_start_us += phrase_duration_us

        sec_val = sentence_duration_us / SEC
        print(f"  [문장 {s_idx}] 오디오 ({sec_val:.2f}s) + 비디오 소스 배치 완료: '{full_sentence}'")

        current_time_us += sentence_duration_us

    script_file.save()
    print(f"\n[완료] [AI더빙 + 비디오 컷 + Pretendard 자막] 100% 자동 완성! 초안: '{project_name}'")
    return project_name

if __name__ == "__main__":
    build_capcut_project_for_naver_clip("다피다 허리 찜질기", "허리아플때")
    build_capcut_project_for_naver_clip("파우리나 전동재활자전거", "노인용 하체회복기구")
