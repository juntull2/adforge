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
# 1. 제품 DB 정보 (옵시디언 03_제품 DB 노트 기반)
# -------------------------------------------------------------------
PRODUCTS_DB = {
    "다피다 허리 찜질기": {
        "hub_keyword": "적외선 찜질복대",
        "target": "만성 허리 통증을 겪는 4050 여성 및 남성",
        "usp": "원적외선(방사율 0.902) + 근적외선(3파장) 동시 방출 (시장 유일), 300g 초경량 슬림핏, 30일 무상 환불 보증",
        "pain_points": ["파스나 겉만 따뜻한 찜질로는 속근육 통증 안 풀림", "병원/한의원 치료비 부담"],
        "solution": "피부 속 3cm 깊은 척추 마디까지 침투하는 3파장 근적외선 + 원적외선 복대",
        "stock_keywords": ["back pain", "massage"]
    },
    "파우리나 전동재활자전거": {
        "hub_keyword": "노인용 하체회복기구",
        "target": "수술/입원/노화로 하체 근력이 저하되어 부모님이 걱정되는 50대 자녀",
        "usp": "노인생체역학 최적각도, 100W 고출력 저소음 모터, 리모컨 간편 조작, 양방향 셀프 페달링",
        "pain_points": ["부모님이 자리를 보전하게 될까 봐 두려움", "병원 재활 치료비용 부담"],
        "solution": "집에서 안전하고 편안하게 부모님 하체 근력을 회복시키는 재활 자전거",
        "stock_keywords": ["exercise", "elderly"]
    }
}

# -------------------------------------------------------------------
# 2. 오디오 앞/뒤 무음 공백 제거(Silence Trimming)
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
# 3. 한국어 정밀 발음 가중치 및 문장 구조화
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
# 4. 스톡 비디오 소스 자동 수급 헬퍼
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
# 5. 네이버 클립 SEO & 오메클 대본 생성기
# -------------------------------------------------------------------
def generate_naver_clip_script(product_name: str, keyword: str):
    prod = PRODUCTS_DB.get(product_name, PRODUCTS_DB["다피다 허리 찜질기"])
    seo_title = f"[{keyword}] {prod['pain_points'][0]}? {prod['hub_keyword']} 활용 3초 통증 완화법"

    if product_name == "다피다 허리 찜질기":
        script_text = f"""
        {keyword}로 고생할 때 파스 붙이고 누워만 계셨다면 당장 멈추세요!
        갑자기 굳은 척추 속근육은 겉만 따뜻하게 해선 절대 풀리지 않습니다.
        핵심은 3파장 근적외선으로 피부 속 3cm 깊은 척추 마디까지 열을 전달하는 건데요.
        원적외선과 근적외선이 동시에 나오는 전용 복대를 차주시면 굳어있던 척추 속근육이 사르르 풀리면서 순식간에 편안해집니다.
        무선이라 차고 집안일할 때도 OK!
        30일간 써보고 마음에 안 들면 100% 환불 보증까지 있으니 안심하고 확인해 보세요.
        """
    else:
        script_text = f"""
        부모님 하체 근력이 줄어들어 제대로 걷기 힘들어하신다면 이 영상 꼭 보세요.
        무작정 무리해서 걷게 하시면 관절과 척추에 큰 부담이 됩니다.
        핵심은 노인생체역학 각도로 부드럽게 하체 근육을 재활시키는 건데요.
        100W 고출력 저소음 모터와 리모컨으로 집에서도 부모님이 안전하게 운동하실 수 있습니다.
        부모님 하체 건강, 늦기 전에 미리 챙겨드리세요!
        """

    return seo_title, script_text.strip()

# -------------------------------------------------------------------
# 6. AI TTS + 배경 비디오 소스 + Pretendard 자막 100% 자동 제작
# -------------------------------------------------------------------
async def generate_tts_audio(text: str, output_path: str, voice: str = "ko-KR-SunHiNeural"):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

def build_capcut_project_for_naver_clip(product_name: str, keyword: str, voice: str = "ko-KR-SunHiNeural"):
    seo_title, script_text = generate_naver_clip_script(product_name, keyword)
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
        asyncio.run(generate_tts_audio(full_sentence, mp3_path, voice=voice))

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
