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

def clean_obsidian_review_text(raw_text: str) -> str:
    """마크다운 기호(##, *, -, 💬), 따옴표, 이모지 및 YAML 키워드를 완벽히 클리닝하는 함수"""
    # 불필요한 마크다운 기호 및 이모지 전면 제거
    cleaned = re.sub(r'[#*\-•💬\s"\']+', ' ', raw_text).strip()
    cleaned = re.sub(r'^(실제 구매|구매 고객|후기|리뷰|대표 카테고리|허브키워드|네이밍|카테고리)[^\n]*', '', cleaned).strip()
    # 메타데이터 라인 제거
    if any(cleaned.startswith(k) for k in ["product_name:", "hub_keyword:", "category:", "target:", "usp:", "pain_points:", "solution:", "stock_keywords:", "reviews:"]):
        return ""
    return cleaned

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

                raw_lines = content.splitlines()

                # 허브키워드 추출
                hub_match = re.search(r"hub_keyword:\s*(.+)", content)
                hub_kw = hub_match.group(1).strip() if hub_match else "추천제품"

                # 리뷰/후기 섹션(## 실제 구매 고객 후기)만 정밀 조준 추출
                reviews = []
                review_section = False
                for line in raw_lines:
                    if "구매" in line and "후기" in line:
                        review_section = True
                        continue
                    if review_section and line.strip().startswith("##"):
                        review_section = False
                        break
                    if review_section:
                        line_clean = clean_obsidian_review_text(line)
                        # 20자 이상의 완전한 실제 구매 후기 문장만 수용
                        if len(line_clean) >= 20 and not any(junk in line_clean for junk in ["##", "카테고", "*", "\""]):
                            if line_clean not in reviews:
                                reviews.append(line_clean)

                # 기존 DB 업데이트 (파싱된 클린 후기가 1개 이상 있을 때만 덮어쓰기)
                if prod_name in products_db:
                    products_db[prod_name]["hub_keyword"] = hub_kw
                    if reviews:
                        products_db[prod_name]["reviews"] = reviews[:4]
                else:
                    products_db[prod_name] = {
                        "hub_keyword": hub_kw,
                        "target": "타깃 고객",
                        "usp": f"{prod_name} 핵심가치 및 차별화 포인트",
                        "pain_points": ["불편함 해소", "비용 부담"],
                        "solution": f"{prod_name}으로 빠르고 편리하게 해결",
                        "stock_keywords": ["health", "lifestyle"],
                        "reviews": reviews[:4] if reviews else DEFAULT_PRODUCTS_DB.get(prod_name, {}).get("reviews", [])
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
SCRIPT_FORMAT_NAMES = {
    "phase1": "🟢 1단계: 순수 정보성 (쇼핑 태그 ❌, 정보/공감 100%)",
    "phase2": "🟡 2단계: 해결책 인식 (찜질/온열 카테고리 브릿지)",
    "phase3": "🟠 3단계: 자연스러운 제품 연결 (간접 판매/댓글 CTA)",
    "phase4": "🔴 4단계: 판매 전환 콘텐츠 (직접 판매/쇼핑 태그 ✅)"
}

def generate_naver_clip_script(product_name: str, keyword: str, format_type: str = "phase1"):
    if format_type == "phase1":
        seo_title = f"[{keyword}] 50대 허리가 아픈 진짜 이유, 나이 탓 아닙니다."
        script_text = f"""
{keyword} 때문에 고생이시라면 주목! 50대부터 허리가 아픈데, 무작정 나이 탓이라고 넘기면 안 됩니다!
문제는 오래 앉아있는 습관과 무너진 코어 근육 때문인데요.
앉아만 있으면 척추가 무너지고 허리 근육이 더 굳어버립니다.
오늘부터 1시간에 한 번씩 일어나서 가볍게 기지개만 켜보세요!
여러분은 평소 허리 건강 어떻게 관리하시나요? 나만의 꿀팁이 있다면 댓글로 남겨주세요!
        """
    elif format_type == "phase2":
        seo_title = f"[{keyword}] 허리 아플 때 냉찜질? 온찜질? 헷갈리신다면"
        script_text = f"""
{keyword}로 허리 아프다고 무조건 파스 붙이거나 냉찜질부터 하시면 안 됩니다!
일반적인 뻐근함이나 만성적인 고통에는 근육을 이완시키는 온열이 훨씬 좋은데요.
허리가 뻐근할 때 따뜻하게 해주면 굳은 근육이 사르르 풀리고 편안해집니다.
다만 너무 뜨겁게 하지 말고 적절한 온도를 유지하는 게 핵심이에요.
온찜질 방법 더 궁금하시면 댓글에 '온찜질' 남겨주세요!
        """
    elif format_type == "phase3":
        seo_title = f"[{keyword}] 찜질팩 매번 데우기 번거로울 때 꿀팁"
        script_text = f"""
아직도 찜질팩 들고 허리에 대고 계시거나, 매번 전자레인지에 데우시나요?
이런 분들은 거추장스러운 찜질팩보다 밀착형 허리찜질기가 훨씬 편할 수 있습니다.
집안일 할 때나 골프 끝나고 소파에 앉아있을 때, 그냥 차기만 하면 되거든요.
잠들기 전 딱 이것만 챙겨도 허리 관리가 두 배는 더 편해집니다.
제가 쓰는 허리찜질기 궁금하시면 댓글에서 '{keyword} 찜질기' 검색해보세요!
        """
    else:  # phase4
        seo_title = f"[{keyword}] 50대 허리 건강 관리, 제가 다피다 정착한 이유"
        script_text = f"""
허리찜질기 아무거나 사지 마세요. 제가 결국 이걸 쓰게 된 이유는 딱 하나였습니다.
피부 겉만 뜨거운 게 아니라, 원적외선과 근적외선이 동시에 나와서 속근육까지 사르르 풀리거든요!
저녁 8시만 되면 소파에 앉아서 이거 하나 차는 게 제 완벽한 일상 루틴이 되었습니다.
30일 써보고 100% 환불도 되니까, 오래 앉아계시거나 집안일 많이 하시는 분들께 강력 추천해요.
제가 사용하는 다피다 허리찜질기는 하단 쇼핑 태그 클릭해서 확인하세요!
        """
    return seo_title, script_text.strip()

def apply_user_feedback_to_script(current_script: str, user_feedback: str, product_name: str) -> tuple:
    """사용자가 입력한 마케터 피드백(예: 부모님 선물 톤, 30일 환불 강조, 직장인 훅 등)을 반영하여 대본 재작성"""
    fb_clean = user_feedback.strip()
    if not fb_clean or not current_script.strip():
        return f"[{product_name}] 피드백 반영 대본", current_script
    
    lines = [l.strip() for l in current_script.splitlines() if l.strip()]
    if not lines:
        lines = [current_script]
        
    updated_lines = list(lines)
    
    # 1. 훅/초반 연출 변경 피드백
    if any(k in fb_clean for k in ["훅", "3초", "어그로", "시작"]):
        updated_lines[0] = f"🔥 {fb_clean}! " + updated_lines[0]
        
    # 2. 부모님/효도선물 톤 전환
    if any(k in fb_clean for k in ["부모님", "효도", "선물", "어르신", "아빠"]):
        updated_lines[0] = f"부모님 {product_name} 선물로 고민 중이셨다면 딱 15초만 집중해 보세요!"
        if len(updated_lines) > 1:
            updated_lines[-1] = "부모님 건강, 안 맞으면 30일 100% 무료 반품 가능하니 부담 없이 미리 선물해 보세요!"
            
    # 3. 30일 환불/보증 강조
    if any(k in fb_clean for k in ["환불", "반품", "보증", "30일"]):
        updated_lines[-1] = "💡 안 맞으면 30일 내 100% 무상 환불 보증제 적용! 실패 없는 직접 체험으로 결정하세요."

    # 4. 직장인/퇴근 톤 강조
    if any(k in fb_clean for k in ["직장인", "퇴근", "앉아"]):
        updated_lines[0] = "🔥 퇴근 후 허리가 아픈 게 아니라 접히는 고통을 느끼는 직장인이라면 집중!"

    new_script = "\n".join(updated_lines)
    new_title = f"[{fb_clean[:6]}] {product_name} 피드백 반영"
    return new_title[:24], new_script

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

def generate_voice_sample_audio_sync(voice_config, output_path: str = "sample_voice.mp3") -> str:
    """선택한 AI 성우 보이스의 1초 미리듣기 오디오 MP3 파일 생성"""
    import asyncio
    sample_text = "안녕하세요! AdForge 릴스 숏폼 전용 AI 성우 보이스 미리듣기 샘플입니다."
    asyncio.run(generate_tts_audio(sample_text, output_path, voice_config))
    return output_path

def build_capcut_project_for_naver_clip(product_name: str, keyword: str, voice="ko-KR-SunHiNeural", format_type: str = "fear"):
    seo_title, script_text = generate_naver_clip_script(product_name, keyword, format_type=format_type)
    project_name = f"네이버클립_{keyword.replace(' ', '_')}"
    
    prod_data = PRODUCTS_DB.get(product_name, PRODUCTS_DB["다피다 허리 찜질기"])
    stock_videos = get_or_download_stock_videos(prod_data.get("stock_keywords", ["back pain"]))

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
    print(f"[SEO 제목] {seo_title}")
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
    return project_name, seo_title

if __name__ == "__main__":
    build_capcut_project_for_naver_clip("다피다 허리 찜질기", "허리아플때")
    build_capcut_project_for_naver_clip("파우리나 전동재활자전거", "노인용 하체회복기구")
