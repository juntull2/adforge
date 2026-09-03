import os
import re
import csv
import json
import glob
import asyncio
import edge_tts
import pycapcut as cc

# Monkey patch pycapcut SegmentAnimations to fix video animation export bug
_original_export_json = cc.animation.SegmentAnimations.export_json
def _patched_export_json(self):
    data = _original_export_json(self)
    if any(a.export_json().get("material_type") == "video" for a in self.animations):
        data["type"] = "video_animation"
    return data
cc.animation.SegmentAnimations.export_json = _patched_export_json

from pydub import AudioSegment as PydubAudio
from pydub.silence import detect_nonsilent

from auto_stock_downloader import fetch_and_download_mixkit_stock_videos
from pycapcut import SEC, Timerange, TrackType, TextStyle, TextBorder, TextSegment, AudioMaterial, AudioSegment, VideoMaterial, VideoSegment, ClipSettings
from pycapcut.metadata.text_intro import TextIntro
from pycapcut.metadata.text_outro import TextOutro
from pycapcut.metadata.text_loop import TextLoopAnim
from pycapcut.metadata.effect_meta import EffectMeta
import threading

capcut_draft_lock = threading.Lock()

# -------------------------------------------------------------------
# FFmpeg 환경변수 경로 보정 (Windows 실행 보장)
# -------------------------------------------------------------------
os.environ["PATH"] += os.pathsep + r"C:\Program Files\FFmpeg\bin"

import os
_local_app_data = os.environ.get('LOCALAPPDATA', 'C:/Users/Default/AppData/Local').replace("\\", "/")
PRETENDARD_NAME = "Pretendard"
_font_paths = [
    f"{_local_app_data}/Microsoft/Windows/Fonts/Pretendard-Bold.otf",
    f"{_local_app_data}/Microsoft/Windows/Fonts/Pretendard-Medium.otf",
    "C:/Windows/Fonts/Pretendard-Bold.otf"
]

PRETENDARD_PATH = next((p for p in _font_paths if os.path.exists(p)), _font_paths[0] if _font_paths else "")

class CustomFont:
    def __init__(self, font_name: str, font_path: str):
        self.name = font_name
        self.path = font_path
        self.resource_id = ""
        self.value = EffectMeta(font_name, False, "", "", "", [])

PRETENDARD_FONT = CustomFont(PRETENDARD_NAME, PRETENDARD_PATH)

BLACK_HAN_SANS_NAME = "Black Han Sans"
_bhs_paths = [
    f"{_local_app_data}/Microsoft/Windows/Fonts/BlackHanSans-Regular.ttf",
    "C:/Windows/Fonts/BlackHanSans-Regular.ttf",
]
BLACK_HAN_SANS_PATH = next((p for p in _bhs_paths if os.path.exists(p)), _bhs_paths[0])
BLACK_HAN_SANS_FONT = CustomFont(BLACK_HAN_SANS_NAME, BLACK_HAN_SANS_PATH)

# TextSegment.export_material Monkey-Patching
_orig_export_material = TextSegment.export_material

def _custom_export_material(self):
    ret = _orig_export_material(self)
    # 이 세그먼트에 설정된 폰트를 동적으로 읽음
    seg_font = getattr(self, 'font', None)
    if seg_font is not None:
        font_name = getattr(seg_font, 'name', PRETENDARD_NAME)
        font_path = getattr(seg_font, 'path', PRETENDARD_PATH)
    else:
        font_name = PRETENDARD_NAME
        font_path = PRETENDARD_PATH

    try:
        content_obj = json.loads(ret["content"])
        if "styles" in content_obj and len(content_obj["styles"]) > 0:
            content_obj["styles"][0]["font"] = {
                "id": "",
                "name": font_name,
                "path": font_path,
                "title": font_name
            }
            ret["content"] = json.dumps(content_obj, ensure_ascii=False)
    except Exception:
        pass

    ret["font_name"] = font_name
    ret["font_title"] = font_name
    ret["font_path"] = font_path
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

# 단독으로 줄 끝에 오면 안 되는 수식어/관형사/부사/접두사
_NO_LINE_END_WORDS = {
    '몇', '이', '그', '저', '온갖', '모든', '새', '헌', '옛', '첫', '한', '두', '세', '네', '단',
    '더', '덜', '꼭', '잘', '못', '안', '속', '겉', '겉만', '다', '막', '늘', '참', '갓', '또', '약',
    '큰', '작은', '긴', '짧은', '좋은', '나쁜', '특허', '무선', '30일', '100%', '3cm', '매번', '가끔',
    '티가', '옷', '물리치료', '병원', '원적외선', '듀얼', '속근육까지', '심부열을'
}

def _get_break_score(word: str) -> int:
    """단어 끝의 줄바꿈 적합도 (높을수록 호흡하기 자연스러움)"""
    clean_w = re.sub(r'[\'\"\[\]\(\)]', '', word)
    if clean_w.endswith(',') or clean_w.endswith('~'):
        return 10
    if re.search(r'[.!?…]+$', clean_w):
        return 10
    high_priority_endings = [
        '때마다', '때문에', '것보다', '보다도', '대신', '대신에',
        '환불되니', '그만하시고', '끊고', '풀어줘요', '계시나요?',
        '안착했습니다', '가벼워집니다', '치료하세요', '하셔야 해요',
        '필수거든요', '필수라거든요', '정석이거든요', '핵심입니다',
        '나고,', '녹아내려', '풀어줘요.', '가벼워집니다.', '풀리고'
    ]
    for h in high_priority_endings:
        if clean_w.endswith(h):
            return 8
    conn_patterns = [
        r'(고|며|며는)$',
        r'(면|으면)$',
        r'(니|으니|니까|으니까|거든요|라거든요|다구요)$',
        r'(아서|어서|여서|해|내려|올려|되어)$',
        r'(는데|은데|텐데)$',
        r'(듯이|수록|도록|게)$',
        r'(지만|으나|더라도)$'
    ]
    for p in conn_patterns:
        if re.search(p, clean_w):
            return 6
    if re.search(r'(은|는|이|가|을|를|으로|로|에서|에게)$', clean_w):
        return 3
    return 0

def split_sentence_naturally(sentence: str, max_chars: int = 18, min_chars: int = 7) -> list:
    """한 문장을 문맥과 의미 단위에 맞게 자연스럽게 줄바꿈하여 리스트 반환"""
    sentence = sentence.strip()
    if not sentence:
        return []
    if len(sentence) <= max_chars:
        return [sentence]
    words = sentence.split(' ')
    if not words:
        return []
    chunks = []
    current_chunk = []
    for i, w in enumerate(words):
        current_chunk.append(w)
        current_text = " ".join(current_chunk)
        current_len = len(current_text)
        if i == len(words) - 1:
            chunks.append(current_text)
            current_chunk = []
            break
        next_w = words[i+1]
        next_len = current_len + 1 + len(next_w)
        is_next_conj = next_w in ['왜냐하면', '그래서', '하지만', '그러니', '따라서', '그런데', '차기만', '30일']
        clean_w = re.sub(r'[\'\"\,]', '', w)
        is_no_end = clean_w in _NO_LINE_END_WORDS
        score = _get_break_score(w)
        must_break = False
        good_break = False
        if next_len > max_chars:
            must_break = True
            if is_no_end and len(current_chunk) > 1:
                current_chunk.pop()
                chunks.append(" ".join(current_chunk))
                current_chunk = [w]
                continue
        elif current_len >= min_chars and not is_no_end:
            if is_next_conj:
                good_break = True
            elif score >= 6:
                rem_len = len(" ".join(words[i+1:]))
                if rem_len >= 5:
                    good_break = True
        if must_break or good_break:
            chunks.append(" ".join(current_chunk))
            current_chunk = []
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    return chunks

def split_script_by_sentences_and_phrases(script_text: str, max_chars_per_phrase: int = 40):
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
            # 엔터가 없는 경우, 문맥/호흡 단위 지능형 분할 알고리즘 적용
            phrases = split_sentence_naturally(clean_sentence, max_chars=max_chars_per_phrase)
                    
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
    
    sentence_structures = split_script_by_sentences_and_phrases(script_text, max_chars_per_phrase=40)
    
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

def apply_context_aware_keyframes(v_seg, text, scale_factor, duration_us):
    import pycapcut as cc
    text = text.replace(" ", "")
    base_s = scale_factor
    
    if any(w in text for w in ["갑자기", "충격", "놀라운", "하지만", "그러나", "그런데", "반전", "비밀"]):
        # 다이나믹 줌인
        try:
            v_seg.add_keyframe(cc.KeyframeProperty.scale_x, 0, base_s)
            v_seg.add_keyframe(cc.KeyframeProperty.scale_y, 0, base_s)
            v_seg.add_keyframe(cc.KeyframeProperty.scale_x, min(1000000, duration_us), base_s * 1.25)
            v_seg.add_keyframe(cc.KeyframeProperty.scale_y, min(1000000, duration_us), base_s * 1.25)
            v_seg.add_keyframe(cc.KeyframeProperty.scale_x, duration_us, base_s * 1.3)
            v_seg.add_keyframe(cc.KeyframeProperty.scale_y, duration_us, base_s * 1.3)
        except Exception as e: print('KF ERROR:', e)
    elif any(w in text for w in ["결국", "그래서", "시간이지나", "부드러운", "편안한", "마침내", "자연스럽게"]):
        # 페이드인 + 느린 줌아웃
        try:
            v_seg.add_keyframe(cc.KeyframeProperty.alpha, 0, 0.0)
            v_seg.add_keyframe(cc.KeyframeProperty.alpha, min(800000, duration_us), 1.0)
            v_seg.add_keyframe(cc.KeyframeProperty.scale_x, 0, base_s * 1.1)
            v_seg.add_keyframe(cc.KeyframeProperty.scale_y, 0, base_s * 1.1)
            v_seg.add_keyframe(cc.KeyframeProperty.scale_x, duration_us, base_s)
            v_seg.add_keyframe(cc.KeyframeProperty.scale_y, duration_us, base_s)
        except Exception as e: print('KF ERROR:', e)
    elif any(w in text for w in ["첫째", "둘째", "셋째", "다음으로", "그리고", "또한", "게다가"]):
        # 크기 1.15배 확대 후 좌에서 우로 무빙
        try:
            v_seg.add_keyframe(cc.KeyframeProperty.scale_x, 0, base_s * 1.15)
            v_seg.add_keyframe(cc.KeyframeProperty.scale_y, 0, base_s * 1.15)
            v_seg.add_keyframe(cc.KeyframeProperty.position_x, 0, -100)
            v_seg.add_keyframe(cc.KeyframeProperty.position_x, duration_us, 100)
        except Exception as e: print('KF ERROR:', e)
    else:
        # 잔잔한 줌인
        try:
            v_seg.add_keyframe(cc.KeyframeProperty.scale_x, 0, base_s)
            v_seg.add_keyframe(cc.KeyframeProperty.scale_y, 0, base_s)
            v_seg.add_keyframe(cc.KeyframeProperty.scale_x, duration_us, base_s * 1.1)
            v_seg.add_keyframe(cc.KeyframeProperty.scale_y, duration_us, base_s * 1.1)
        except Exception as e: print('KF ERROR:', e)


def build_capcut_project_for_naver_clip(script_text: str, voice="ko-KR-SunHiNeural", el_api_key="", template_folder=None, keyword="", pexels_api_key="", pixabay_api_key="", local_media_folder="", media_mapping=None, creative_direction=None, manual_style=None):
    if template_folder and template_folder != "none":
        return build_from_template(script_text, voice, el_api_key, template_folder)
    
    import time
    import uuid
    project_name = f"AutoProject_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    
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
    
    stock_videos = []

    with capcut_draft_lock:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            local_app_data = os.path.expanduser("~\\AppData\\Local")
        draft_folder_path = os.path.join(local_app_data, "CapCut", "User Data", "Projects", "com.lveditor.draft")
        os.makedirs(draft_folder_path, exist_ok=True)
        draft_folder = cc.DraftFolder(draft_folder_path)
    
        try:
            script_file = draft_folder.create_draft(project_name, width=1080, height=1920, fps=30, allow_replace=True)
        except (PermissionError, OSError) as e:
            project_name = f"{project_name}_r{uuid.uuid4().hex[:4]}"
            script_file = draft_folder.create_draft(project_name, width=1080, height=1920, fps=30, allow_replace=True)
    
        script_file.content["canvas_config"] = {"width": 1080, "height": 1920, "ratio": "9:16"}
    
        script_file.add_track(TrackType.video, track_name="메인_비디오_트랙")
        script_file.add_track(TrackType.text, track_name="자막_트랙")
        script_file.add_track(TrackType.audio, track_name="더빙_트랙")

    temp_dir = os.path.join(os.getcwd(), "temp_audio")
    os.makedirs(temp_dir, exist_ok=True)

    sentence_structures = split_script_by_sentences_and_phrases(script_text, max_chars_per_phrase=40)

    print(f"\n========================================================")
    print(f"[네이버 클립 프로젝트 생성 시작] {project_name}")
    
    current_time_us = 0
    video_usage_tracker = {v_file: 0 for v_file in stock_videos}
    last_used_video = ""

    if media_mapping is None:
        media_mapping = {}

    for s_idx, struct in enumerate(sentence_structures, 1):
        full_sentence = struct["full_sentence"]
        phrases = struct["phrases"]
        mapping_idx = s_idx - 1

        target_media_filename = media_mapping.get(mapping_idx)
        clean_sentence = full_sentence.strip()
        cleaned_phrases = [p.strip() for p in phrases if p.strip()]

        clean_audio_text = re.sub(r'[*#\[\]_=\-]', '', clean_sentence).strip()
        if not clean_audio_text:
            continue

        mp3_path = os.path.join(temp_dir, f"{project_name}_s{s_idx}.mp3")
        try:
            if voice.startswith("el_"):
                real_voice_id = voice.replace("el_", "")
                if not el_api_key:
                    raise Exception("ElevenLabs API Key가 없습니다.")
                generate_elevenlabs_tts(clean_audio_text, mp3_path, voice_id=real_voice_id, api_key=el_api_key)
            elif voice.startswith("fish_"):
                fish_reference_id = voice.replace("fish_", "")
                fish_api_key = os.environ.get("FISH_API_KEY", "")
                if not fish_api_key:
                    raise Exception("Fish Audio API Key가 없습니다.")
                generate_fish_audio_tts(clean_audio_text, mp3_path, reference_id=fish_reference_id, api_key=fish_api_key)
            else:
                asyncio.run(generate_tts_audio(clean_audio_text, mp3_path, voice_config=voice))
        except Exception as e:
            print(f"  [오디오 생성 실패, 무료 TTS로 대체] {e}")
            try:
                import asyncio
                asyncio.run(generate_tts_audio(clean_audio_text, mp3_path, voice_config="ko-KR-SunHiNeural"))
            except Exception as e2:
                raise Exception(f"오디오 생성 완전 실패: {e}")

        trim_audio_silence(mp3_path)

        audio_mat = AudioMaterial(mp3_path)
        sentence_duration_us = audio_mat.duration

        audio_timerange = Timerange(current_time_us, sentence_duration_us)
        script_file.add_segment(AudioSegment(audio_mat, audio_timerange), track_name="더빙_트랙")

        v_file_to_use = None
        is_local_media = False

        if target_media_filename and local_media_folder:
            potential_path = os.path.join(local_media_folder, target_media_filename)
            if os.path.exists(potential_path):
                v_file_to_use = potential_path
                is_local_media = True

        if not v_file_to_use and stock_videos:
            v_file_to_use = find_best_video_for_sentence(clean_sentence, stock_videos, last_used_video=last_used_video)
            last_used_video = v_file_to_use

        if v_file_to_use:
            try:
                v_mat = VideoMaterial(v_file_to_use)
                
                if is_local_media:
                    ext = os.path.splitext(v_file_to_use)[1].lower()
                    if ext in ['.jpg', '.jpeg', '.png']:
                        clip_dur = sentence_duration_us
                        start_offset = 0
                    else:
                        clip_dur = min(v_mat.duration, sentence_duration_us)
                        start_offset = 0
                else:
                    clip_dur = min(v_mat.duration, sentence_duration_us)
                    start_offset = video_usage_tracker.get(v_file_to_use, 0)
                    if start_offset + clip_dur > v_mat.duration:
                        start_offset = 0
                        clip_dur = min(v_mat.duration, sentence_duration_us)
                    video_usage_tracker[v_file_to_use] = start_offset + clip_dur
                    
                src_timerange = Timerange(start_offset, clip_dur)
                tgt_timerange = Timerange(current_time_us, clip_dur)
                
                v_width = getattr(v_mat, 'width', 0)
                v_height = getattr(v_mat, 'height', 0)
                if v_width and v_height:
                    scale_factor = max(1080.0 / v_width, 1920.0 / v_height)
                else:
                    scale_factor = 1.0
                    
                clip_settings = ClipSettings(scale_x=scale_factor, scale_y=scale_factor)
                
                v_seg = VideoSegment(v_mat, tgt_timerange, source_timerange=src_timerange, clip_settings=clip_settings)
                try:
                    apply_context_aware_keyframes(v_seg, clean_sentence, scale_factor, duration_us=tgt_timerange.duration)
                except Exception as e:
                    print(f"  (키프레임 애니메이션 적용 오류: {e})")

                script_file.add_segment(v_seg, track_name="메인_비디오_트랙")
            except Exception as ve:
                print(f"  (비디오 소스 연동 알림: {ve})")

        phrase_effective_lens = [calculate_effective_speech_length(p) for p in cleaned_phrases]
        total_effective_len = sum(phrase_effective_lens) or 1.0
        phrase_start_us = current_time_us

        for p_idx, (phrase, eff_len) in enumerate(zip(cleaned_phrases, phrase_effective_lens)):
            if p_idx == len(cleaned_phrases) - 1:
                phrase_duration_us = (current_time_us + sentence_duration_us) - phrase_start_us
            else:
                phrase_duration_us = int(sentence_duration_us * (eff_len / total_effective_len))

            phrase_timerange = Timerange(phrase_start_us, phrase_duration_us)

            # 훅 여부: 시간 기준 OR creative_direction role
            cd_role = None
            if creative_direction and "sentences" in creative_direction:
                for _s in creative_direction["sentences"]:
                    if _s.get("index") == mapping_idx:
                        cd_role = _s.get("role")
                        break
            is_hook = (current_time_us < 3000000) or (cd_role == "hook")

            style = TextStyle(
                size=18.0 if is_hook else 14.5,
                color=(1.0, 0.9, 0.0) if is_hook else (1.0, 1.0, 1.0),
                bold=True,
                align=1
            )
            border = TextBorder(color=(0.0, 0.0, 0.0), width=55.0 if is_hook else 25.0)
            clip_settings = ClipSettings(transform_x=0.0, transform_y=0.0)
            active_font = BLACK_HAN_SANS_FONT if is_hook else PRETENDARD_FONT

            text_seg = TextSegment(
                text=phrase,
                timerange=phrase_timerange,
                font=active_font,
                style=style,
                border=border,
                clip_settings=clip_settings
            )

            # ── 역할 결정 ─────────────────────────────────────────────
            # creative_direction이 있으면 AI가 분류한 role 사용,
            # 없으면 시간 기준 is_hook으로 fallback
            effective_role = cd_role or ("hook" if is_hook else "normal")

            # ── 모드 1: 템플릿(manual_style) + AI 역할 분류 ─────────────
            # manual_style이 있으면 → AI가 분류한 role로 템플릿에서 스타일 조회
            if manual_style:
                ms = (manual_style.get(effective_role)
                      or manual_style.get("normal")
                      or {})

                # 폰트 오버라이드
                ms_font_name = ms.get("font_name")
                ms_font_path = ms.get("font_path")
                if ms_font_name and ms_font_path:
                    text_seg.font = CustomFont(ms_font_name, ms_font_path)

                # 크기 오버라이드
                ms_size = ms.get("size")
                if ms_size:
                    current_color = (1.0, 0.9, 0.0) if (effective_role == "hook") else (1.0, 1.0, 1.0)
                    text_seg.style = TextStyle(size=ms_size, color=current_color, bold=True, align=1)

                # ── pycapcut enum 기반 애니메이션 ──
                for anim_val, anim_cls in [
                    (ms.get("intro"), TextIntro),
                    (ms.get("loop"),  TextLoopAnim),
                    (ms.get("outro"), TextOutro),
                ]:
                    if anim_val and anim_val in anim_cls.__members__:
                        try: text_seg.add_animation(anim_cls[anim_val])
                        except Exception: pass

                # ── raw_anim: 로컬 캐시 기반 직접 주입 (놓기 등 enum 없는 효과) ──
                # 형식: [{"resource_id": "...", "path": "...", "type": "in/loop/out", "name": "..."}]
                raw_anims = ms.get("raw_anims", [])
                if raw_anims:
                    text_seg._raw_anims = raw_anims  # 나중에 _inject_raw_anims()에서 처리


            # ── 모드 2: AI 크리에이티브 연출 단독 (템플릿 없을 때) ──────
            elif creative_direction and "sentences" in creative_direction:
                sentence_info = None
                for s in creative_direction["sentences"]:
                    if s.get("index") == mapping_idx:
                        sentence_info = s
                        break

                if sentence_info:
                    intro_name = sentence_info.get("text_intro")
                    loop_name  = sentence_info.get("text_loop_anim")
                    outro_name = sentence_info.get("text_outro")

                    if intro_name:
                        try:
                            anim_enum = TextIntro[intro_name] if intro_name in TextIntro.__members__ else None
                            if anim_enum: text_seg.add_animation(anim_enum)
                        except Exception: pass

                    if loop_name:
                        try:
                            anim_enum = TextLoopAnim[loop_name] if loop_name in TextLoopAnim.__members__ else None
                            if anim_enum: text_seg.add_animation(anim_enum)
                        except Exception: pass

                    if outro_name:
                        try:
                            anim_enum = TextOutro[outro_name] if outro_name in TextOutro.__members__ else None
                            if anim_enum: text_seg.add_animation(anim_enum)
                        except Exception: pass

                    c_style = sentence_info.get("subtitle_style")
                    if c_style:
                        try:
                            size = c_style.get("size", 14.5)
                            color_list = c_style.get("color", [1.0, 1.0, 1.0])
                            color = tuple(color_list) if isinstance(color_list, list) else color_list
                            bold = c_style.get("bold", True)
                            text_seg.style = TextStyle(size=size, color=color, bold=bold, align=1)
                            border_color_list = c_style.get("border_color", [0.0, 0.0, 0.0])
                            border_color = tuple(border_color_list) if isinstance(border_color_list, list) else border_color_list
                            border_width = c_style.get("border_width", 25.0)
                            text_seg.border = TextBorder(color=border_color, width=border_width)
                        except Exception: pass

            script_file.add_segment(text_seg, track_name="자막_트랙")
            phrase_start_us += phrase_duration_us

        sec_val = sentence_duration_us / SEC
        phrases_str = " -> ".join(cleaned_phrases)
        print(f"  [문장 {s_idx}] 오디오 ({sec_val:.2f}s) 생성 완료 | 자막 싱크(10자): {phrases_str}")

        current_time_us += sentence_duration_us

    script_file.save()

    # ── raw_anim 후처리: draft_content.json 직접 패치 ─────────────────
    # TextSegment에 _raw_anims가 있으면 sticker_animation으로 주입
    try:
        # text_segments 수집 (script_file 내부 트랙에서)
        segs_with_raw = []
        for track in script_file.tracks:
            for seg in getattr(track, 'segments', []):
                if hasattr(seg, '_raw_anims') and seg._raw_anims:
                    segs_with_raw.append(seg)

        if segs_with_raw:
            import uuid
            content_file = os.path.join(script_file.project_path, "draft_content.json")
            with open(content_file, encoding='utf-8') as f:
                draft = json.load(f)

            if 'material_animations' not in draft['materials']:
                draft['materials']['material_animations'] = []

            # text 트랙에서 material_id 기준으로 segment 찾기
            text_segs_in_draft = []
            for track in draft.get('tracks', []):
                if track.get('type') == 'text':
                    text_segs_in_draft = track.get('segments', [])
                    break

            mat_id_map = {s.material_id: s for s in segs_with_raw}

            for draft_seg in text_segs_in_draft:
                mat_id = draft_seg.get('material_id')
                src_seg = mat_id_map.get(mat_id)
                if not src_seg:
                    continue

                # raw_anim별로 material_animation 생성 및 참조 추가
                for raw in src_seg._raw_anims:
                    ma_id = str(uuid.uuid4()).upper()
                    anim_duration = draft_seg.get('target_timerange', {}).get('duration', 500000)
                    anim_entry = {
                        "id": raw.get('id', raw['resource_id']),
                        "type": raw.get('anim_type', 'in'),
                        "start": 0,
                        "duration": 500000 if raw.get('anim_type', 'in') == 'in' else anim_duration,
                        "path": raw['path'],
                        "platform": "all",
                        "resource_id": raw['resource_id'],
                        "third_resource_id": raw.get('third_resource_id', ''),
                        "source_platform": raw.get('source_platform', 1),
                        "name": raw['name'],
                        "category_id": raw.get('category_id', ''),
                        "category_name": raw.get('category_name', ''),
                        "panel": "",
                        "material_type": "sticker",
                        "anim_adjust_params": None,
                        "request_id": raw.get('request_id', ''),
                    }
                    ma_block = {
                        "id": ma_id,
                        "type": "sticker_animation",
                        "animations": [anim_entry],
                        "multi_language_current": "none",
                    }
                    draft['materials']['material_animations'].append(ma_block)
                    if 'extra_material_refs' not in draft_seg:
                        draft_seg['extra_material_refs'] = []
                    draft_seg['extra_material_refs'].append(ma_id)

            with open(content_file, 'w', encoding='utf-8') as f:
                json.dump(draft, f, ensure_ascii=False)
            print(f"  [raw_anim] {len(segs_with_raw)}개 세그먼트에 직접 애니메이션 주입 완료")
    except Exception as e:
        print(f"  [raw_anim 경고] 직접 주입 실패 (무시): {e}")

    print(f"\n[완료] [AI더빙 + 비디오 컷 + 잘난체 자막] 100% 자동 완성! 초안: '{project_name}'")
    return project_name

from caption_engine import generate_plan_json, render_caption_frames, composite_final_video

def build_final_video_with_caption_os(script_text, keyword, pexels_api_key, pixabay_api_key, voice, el_api_key, local_media_folder, media_mapping, mood="professional", style="karaoke"):
    import time
    import uuid
    import os
    import re
    import asyncio
    import subprocess
    from pydub import AudioSegment as PydubAudio
    
    project_name = f"AutoRender_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    
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
    
    stock_videos = []

    temp_dir = os.path.join(os.getcwd(), "temp_videos", project_name)
    os.makedirs(temp_dir, exist_ok=True)
    
    temp_audio_dir = os.path.join(os.getcwd(), "temp_audio")
    os.makedirs(temp_audio_dir, exist_ok=True)

    sentence_structures = split_script_by_sentences_and_phrases(script_text, max_chars_per_phrase=40)
    
    current_time_us = 0
    video_usage_tracker = {v_file: 0 for v_file in stock_videos}
    last_used_video = ""
    if media_mapping is None:
        media_mapping = {}

    phrases_data = []
    clip_list_path = os.path.join(temp_dir, "clips.txt")
    clip_list = []
    
    import subprocess
    from pydub import AudioSegment as PydubAudio

    for s_idx, struct in enumerate(sentence_structures, 1):
        full_sentence = struct["full_sentence"]
        phrases = struct["phrases"]
        mapping_idx = s_idx - 1

        target_media_filename = media_mapping.get(mapping_idx)
        clean_sentence = full_sentence.strip()
        cleaned_phrases = [p.strip() for p in phrases if p.strip()]

        clean_audio_text = re.sub(r'[*#\[\]_=\-]', '', clean_sentence).strip()
        if not clean_audio_text:
            continue

        mp3_path = os.path.join(temp_audio_dir, f"{project_name}_s{s_idx}.mp3")
        try:
            if voice.startswith("el_"):
                real_voice_id = voice.replace("el_", "")
                if not el_api_key:
                    raise Exception("ElevenLabs API Key가 없습니다.")
                generate_elevenlabs_tts(clean_audio_text, mp3_path, voice_id=real_voice_id, api_key=el_api_key)
            elif voice.startswith("fish_"):
                fish_reference_id = voice.replace("fish_", "")
                fish_api_key = os.environ.get("FISH_API_KEY", "")
                if not fish_api_key:
                    raise Exception("Fish Audio API Key가 없습니다.")
                generate_fish_audio_tts(clean_audio_text, mp3_path, reference_id=fish_reference_id, api_key=fish_api_key)
            else:
                asyncio.run(generate_tts_audio(clean_audio_text, mp3_path, voice_config=voice))
        except Exception as e:
            print(f"  [오디오 생성 실패, 무료 TTS로 대체] {e}")
            try:
                asyncio.run(generate_tts_audio(clean_audio_text, mp3_path, voice_config="ko-KR-SunHiNeural"))
            except Exception as e2:
                raise Exception(f"오디오 생성 완전 실패: {e2}")

        trim_audio_silence(mp3_path)
        
        audio = PydubAudio.from_file(mp3_path)
        sentence_duration_us = len(audio) * 1000  # ms to us

        v_file_to_use = None
        is_local_media = False

        if target_media_filename and local_media_folder:
            potential_path = os.path.join(local_media_folder, target_media_filename)
            if os.path.exists(potential_path):
                v_file_to_use = potential_path
                is_local_media = True

        if not v_file_to_use and stock_videos:
            v_file_to_use = find_best_video_for_sentence(clean_sentence, stock_videos, last_used_video=last_used_video)
            last_used_video = v_file_to_use

        sentence_dur_sec = sentence_duration_us / 1000000.0
        out_clip_path = os.path.join(temp_dir, f"clip_{s_idx}.mp4")

        if v_file_to_use:
            ext = os.path.splitext(v_file_to_use)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png']:
                cmd_ffmpeg = [
                    "ffmpeg", "-loop", "1", "-i", v_file_to_use, "-i", mp3_path,
                    "-c:v", "libx264", "-t", str(sentence_dur_sec), "-c:a", "aac",
                    "-b:a", "192k", "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1",
                    "-pix_fmt", "yuv420p", "-shortest", "-y", out_clip_path
                ]
            else:
                cmd_ffmpeg = [
                    "ffmpeg", "-stream_loop", "-1", "-i", v_file_to_use, "-i", mp3_path,
                    "-c:v", "libx264", "-t", str(sentence_dur_sec), "-c:a", "aac",
                    "-b:a", "192k", "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1",
                    "-pix_fmt", "yuv420p", "-y", out_clip_path
                ]
            subprocess.run(cmd_ffmpeg, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            cmd_ffmpeg = [
                "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=1080x1920", "-i", mp3_path,
                "-c:v", "libx264", "-t", str(sentence_dur_sec), "-c:a", "aac",
                "-b:a", "192k", "-pix_fmt", "yuv420p", "-y", out_clip_path
            ]
            subprocess.run(cmd_ffmpeg, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        clip_list.append(f"file 'clip_{s_idx}.mp4'\n")
        
        phrase_effective_lens = [calculate_effective_speech_length(p) for p in cleaned_phrases]
        total_effective_len = sum(phrase_effective_lens) or 1.0
        phrase_start_us = current_time_us

        line_phrases = []
        for p_idx, (phrase, eff_len) in enumerate(zip(cleaned_phrases, phrase_effective_lens)):
            if p_idx == len(cleaned_phrases) - 1:
                phrase_duration_us = (current_time_us + sentence_duration_us) - phrase_start_us
            else:
                phrase_duration_us = int(sentence_duration_us * (eff_len / total_effective_len))
            
            line_phrases.append({
                "text": phrase,
                "start_us": phrase_start_us,
                "end_us": phrase_start_us + phrase_duration_us
            })
            phrase_start_us += phrase_duration_us

        phrases_data.append({
            "start_us": current_time_us,
            "end_us": current_time_us + sentence_duration_us,
            "phrases": line_phrases
        })

        current_time_us += sentence_duration_us

    with open(clip_list_path, "w", encoding="utf-8") as f:
        f.writelines(clip_list)
        
    base_video_path = os.path.join(temp_dir, "base_video.mp4")
    concat_cmd = [
        "ffmpeg", "-f", "concat", "-safe", "0", "-i", clip_list_path,
        "-c", "copy", "-y", base_video_path
    ]
    subprocess.run(concat_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    plan_path = os.path.join(temp_dir, "plan.json")
    generate_plan_json(phrases_data, current_time_us, style=style, mood=mood, plan_out_path=plan_path)
    
    frames_dir = render_caption_frames(plan_path, current_time_us / 1000000.0, fps=30)
    
    outputs_dir = os.path.join(os.getcwd(), "outputs")
    os.makedirs(outputs_dir, exist_ok=True)
    final_output_path = os.path.join(outputs_dir, f"{project_name}_final.mp4")
    
    composite_final_video(base_video_path, frames_dir, final_output_path, fps=30)
    return final_output_path

import os
import re
import time
import uuid
import asyncio
import subprocess
from pydub import AudioSegment as PydubAudio

import pycapcut as cc
from pycapcut import Timerange, TrackType, AudioMaterial, AudioSegment, VideoMaterial, VideoSegment, ClipSettings
from caption_engine import generate_plan_json, render_caption_frames, render_transparent_video

def build_capcut_project_with_caption_os_overlay(script_text, keyword, pexels_api_key, pixabay_api_key, voice, el_api_key, local_media_folder, media_mapping, mood="professional", style="karaoke"):
    project_name = f"AutoDraft_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    
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
    
    stock_videos = []
    
    with capcut_draft_lock:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            local_app_data = os.path.expanduser("~\\AppData\\Local")
        draft_folder_path = os.path.join(local_app_data, "CapCut", "User Data", "Projects", "com.lveditor.draft")
        os.makedirs(draft_folder_path, exist_ok=True)
        draft_folder = cc.DraftFolder(draft_folder_path)
    
        try:
            script_file = draft_folder.create_draft(project_name, width=1080, height=1920, fps=30, allow_replace=True)
        except (PermissionError, OSError) as e:
            project_name = f"{project_name}_r{uuid.uuid4().hex[:4]}"
            script_file = draft_folder.create_draft(project_name, width=1080, height=1920, fps=30, allow_replace=True)
    
        script_file.content["canvas_config"] = {"width": 1080, "height": 1920, "ratio": "9:16"}
    
        script_file.add_track(TrackType.video, track_name="메인_비디오_트랙")
        script_file.add_track(TrackType.video, track_name="자막_오버레이_트랙")
        script_file.add_track(TrackType.audio, track_name="더빙_트랙")

    temp_dir = os.path.join(os.getcwd(), "temp_videos", project_name)
    os.makedirs(temp_dir, exist_ok=True)
    
    temp_audio_dir = os.path.join(os.getcwd(), "temp_audio")
    os.makedirs(temp_audio_dir, exist_ok=True)

    sentence_structures = split_script_by_sentences_and_phrases(script_text, max_chars_per_phrase=40)
    
    current_time_us = 0
    video_usage_tracker = {v_file: 0 for v_file in stock_videos}
    last_used_video = ""
    if media_mapping is None:
        media_mapping = {}

    phrases_data = []

    for s_idx, struct in enumerate(sentence_structures, 1):
        full_sentence = struct["full_sentence"]
        phrases = struct["phrases"]
        mapping_idx = s_idx - 1

        target_media_filename = media_mapping.get(mapping_idx)
        clean_sentence = full_sentence.strip()
        cleaned_phrases = [p.strip() for p in phrases if p.strip()]

        clean_audio_text = re.sub(r'[*#\[\]_=\-]', '', clean_sentence).strip()
        if not clean_audio_text:
            continue

        mp3_path = os.path.join(temp_audio_dir, f"{project_name}_s{s_idx}.mp3")
        try:
            if voice.startswith("el_"):
                real_voice_id = voice.replace("el_", "")
                if not el_api_key:
                    raise Exception("ElevenLabs API Key가 없습니다.")
                generate_elevenlabs_tts(clean_audio_text, mp3_path, voice_id=real_voice_id, api_key=el_api_key)
            elif voice.startswith("fish_"):
                fish_reference_id = voice.replace("fish_", "")
                fish_api_key = os.environ.get("FISH_API_KEY", "")
                if not fish_api_key:
                    raise Exception("Fish Audio API Key가 없습니다.")
                generate_fish_audio_tts(clean_audio_text, mp3_path, reference_id=fish_reference_id, api_key=fish_api_key)
            else:
                asyncio.run(generate_tts_audio(clean_audio_text, mp3_path, voice_config=voice))
        except Exception as e:
            print(f"  [오디오 생성 실패, 무료 TTS로 대체] {e}")
            try:
                asyncio.run(generate_tts_audio(clean_audio_text, mp3_path, voice_config="ko-KR-SunHiNeural"))
            except Exception as e2:
                raise Exception(f"오디오 생성 완전 실패: {e2}")

        trim_audio_silence(mp3_path)
        
        audio = PydubAudio.from_file(mp3_path)
        sentence_duration_us = len(audio) * 1000

        audio_mat = AudioMaterial(mp3_path)
        audio_timerange = Timerange(current_time_us, sentence_duration_us)
        script_file.add_segment(AudioSegment(audio_mat, audio_timerange), track_name="더빙_트랙")

        v_file_to_use = None
        is_local_media = False

        if target_media_filename and local_media_folder:
            potential_path = os.path.join(local_media_folder, target_media_filename)
            if os.path.exists(potential_path):
                v_file_to_use = potential_path
                is_local_media = True

        if not v_file_to_use and stock_videos:
            v_file_to_use = find_best_video_for_sentence(clean_sentence, stock_videos, last_used_video=last_used_video)
            last_used_video = v_file_to_use

        if v_file_to_use:
            try:
                v_mat = VideoMaterial(v_file_to_use)
                
                if is_local_media:
                    ext = os.path.splitext(v_file_to_use)[1].lower()
                    if ext in ['.jpg', '.jpeg', '.png']:
                        clip_dur = sentence_duration_us
                        start_offset = 0
                    else:
                        clip_dur = min(v_mat.duration, sentence_duration_us)
                        start_offset = 0
                else:
                    clip_dur = min(v_mat.duration, sentence_duration_us)
                    start_offset = video_usage_tracker.get(v_file_to_use, 0)
                    if start_offset + clip_dur > v_mat.duration:
                        start_offset = 0
                        clip_dur = min(v_mat.duration, sentence_duration_us)
                    video_usage_tracker[v_file_to_use] = start_offset + clip_dur
                    
                src_timerange = Timerange(start_offset, clip_dur)
                tgt_timerange = Timerange(current_time_us, clip_dur)
                
                v_width = getattr(v_mat, 'width', 0)
                v_height = getattr(v_mat, 'height', 0)
                if v_width and v_height:
                    scale_factor = max(1080.0 / v_width, 1920.0 / v_height)
                else:
                    scale_factor = 1.0
                    
                clip_settings = ClipSettings(scale_x=scale_factor, scale_y=scale_factor)
                
                v_seg = VideoSegment(v_mat, tgt_timerange, source_timerange=src_timerange, clip_settings=clip_settings)
                try:
                    apply_context_aware_keyframes(v_seg, clean_sentence, scale_factor, duration_us=tgt_timerange.duration)
                except Exception as e:
                    print(f"  (키프레임 애니메이션 적용 오류: {e})")

                script_file.add_segment(v_seg, track_name="메인_비디오_트랙")
            except Exception as ve:
                print(f"  (비디오 소스 연동 알림: {ve})")

        phrase_effective_lens = [calculate_effective_speech_length(p) for p in cleaned_phrases]
        total_effective_len = sum(phrase_effective_lens) or 1.0
        phrase_start_us = current_time_us

        line_phrases = []
        for p_idx, (phrase, eff_len) in enumerate(zip(cleaned_phrases, phrase_effective_lens)):
            if p_idx == len(cleaned_phrases) - 1:
                phrase_duration_us = (current_time_us + sentence_duration_us) - phrase_start_us
            else:
                phrase_duration_us = int(sentence_duration_us * (eff_len / total_effective_len))
            
            line_phrases.append({
                "text": phrase,
                "start_us": phrase_start_us,
                "end_us": phrase_start_us + phrase_duration_us
            })
            phrase_start_us += phrase_duration_us

        phrases_data.append({
            "start_us": current_time_us,
            "end_us": current_time_us + sentence_duration_us,
            "phrases": line_phrases
        })

        current_time_us += sentence_duration_us

    # caption-os 렌더링 시작
    plan_path = os.path.join(temp_dir, "plan.json")
    generate_plan_json(phrases_data, current_time_us, style=style, mood=mood, plan_out_path=plan_path)
    
    frames_dir = render_caption_frames(plan_path, current_time_us / 1000000.0, fps=30)
    
    mov_path = os.path.join(temp_dir, "caption_overlay.mov")
    render_transparent_video(frames_dir, mov_path, fps=30)
    
    # 생성된 투명 비디오를 캡컷 오버레이 트랙에 추가
    cap_mat = VideoMaterial(mov_path)
    cap_tgt_timerange = Timerange(0, cap_mat.duration)
    cap_src_timerange = Timerange(0, cap_mat.duration)
    # 크기 조절 (화면 꽉 차게)
    cap_v_seg = VideoSegment(cap_mat, cap_tgt_timerange, source_timerange=cap_src_timerange)
    script_file.add_segment(cap_v_seg, track_name="자막_오버레이_트랙")

    script_file.save()
    print(f"\n[완료] 투명 자막 오버레이가 포함된 캡컷 프로젝트 초안: '{project_name}'")
    return project_name


if __name__ == "__main__":
    build_capcut_project_for_naver_clip("다피다 허리 찜질기", "허리아플때")
    build_capcut_project_for_naver_clip("파우리나 전동재활자전거", "노인용 하체회복기구")
