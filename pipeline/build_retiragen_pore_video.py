import os
import sys
import json
import asyncio
import subprocess
from pathlib import Path

# 콘솔 유니코드/이모지 인코딩 보정
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import edge_tts
from pydub import AudioSegment
from pydub.silence import detect_nonsilent

# 폰트 경로 설정
LOCAL_FONTS_DIR = r"C:\Users\5700G\AppData\Local\Microsoft\Windows\Fonts"
FONT_PATH = os.path.join(LOCAL_FONTS_DIR, "Pretendard-Bold.otf").replace("\\", "/")

# 에셋 기본 경로
BASE_MODEL_DIR = r"C:\Users\5700G\Desktop\레티라겐\윤라영님모델_소스"
BASE_XHS_DIR = r"C:\Users\5700G\Desktop\레티라겐\xhs_sources"
BASE_SFX_DIR = r"C:\Users\5700G\Desktop\효과음"

# 10개 씬 구성 정의
SCENES_SPEC = [
    {
        "id": 1,
        "role": "hook",
        "text": "전 피부과 프락셀 안 받아도 모공 요철 제로예요.",
        "caption_l1": "전 피부과 프락셀 안 받아도",
        "caption_l2": "모공 요철 제로예요.",
        "highlight": "모공 요철 제로",
        "asset": os.path.join(BASE_MODEL_DIR, "환하게 웃는 장면 - Trim.mp4"),
        "sfx": os.path.join(BASE_SFX_DIR, "0_오프닝 효과음(가장앞부분에배치)", "HMNMisc_Finger Snap.wav")
    },
    {
        "id": 2,
        "role": "pain_1",
        "text": "유명한 모공 앰플, 레티놀 크림 다 써봐도 개기름 뜨고 화장 밀리고,",
        "caption_l1": "유명한 모공 앰플, 레티놀 크림 써봐도",
        "caption_l2": "개기름 뜨고 화장 밀리고,",
        "highlight": "개기름 뜨고 화장 밀리고",
        "asset": os.path.join(BASE_MODEL_DIR, "거울 보며 짜증내는 장면.mp4"),
        "sfx": os.path.join(BASE_SFX_DIR, "5_화면전환효과", "Whoosh Transition 1.wav")
    },
    {
        "id": 3,
        "role": "pain_2",
        "text": "심할 땐 피부가 아예 뒤집어지더라고요. 결국 나비존 요철만 푹 파였죠.",
        "caption_l1": "심할 땐 피부가 아예 뒤집어지더라고요.",
        "caption_l2": "결국 나비존 요철만 푹 파였죠.",
        "highlight": "나비존 요철만 푹 파였죠",
        "asset": os.path.join(BASE_XHS_DIR, "4_피부_숏폼영상_무자막", "07.mp4"),
        "sfx": os.path.join(BASE_SFX_DIR, "3_특수자막(강조용)", "쨍그랑.mp3")
    },
    {
        "id": 4,
        "role": "reveal_1",
        "text": "근데 귤껍질 같던 볼살 매끈해진 거 보이세요? 전 레티놀 크림을 삼키기 시작했어요.",
        "caption_l1": "근데 귤껍질 같던 볼살 매끈해진 거 보이세요?",
        "caption_l2": "전 레티놀 크림을 삼키기 시작했어요.",
        "highlight": "레티놀 크림을 삼키기",
        "asset": os.path.join(BASE_MODEL_DIR, "이거 비밀인데.. - Trim.mp4"),
        "asset_alt": os.path.join(BASE_MODEL_DIR, "약 손바닥 위에 있는 장면 - Trim.mp4"),
        "sfx": os.path.join(BASE_SFX_DIR, "3_특수자막(강조용)", "Ding Sound Effect.mp3")
    },
    {
        "id": 5,
        "role": "reveal_2",
        "text": "엥? 레티놀 크림을 삼켜요?",
        "caption_l1": "엥? 레티놀 크림을 삼켜요?!",
        "caption_l2": "",
        "highlight": "레티놀 크림을 삼켜요?!",
        "asset": os.path.join(BASE_MODEL_DIR, "폰 보고 놀라는 장면 - Trim.mp4"),
        "sfx": os.path.join(BASE_SFX_DIR, "3_특수자막(강조용)", "뜨링!.wav")
    },
    {
        "id": 6,
        "role": "proof_1",
        "text": "저도 처음엔 안 믿었는데, 아니 땡볕 야구장을 다녀와도 피지가 터지기는커녕 요철이 점점 더 팽팽하게 차오르는 거예요!",
        "caption_l1": "땡볕 야구장 다녀와도 피지 터지기는커녕",
        "caption_l2": "요철이 팽팽하게 차오르는 거예요!",
        "highlight": "요철이 팽팽하게 차오르는 거예요!",
        "asset": os.path.join(BASE_MODEL_DIR, "약 복용 장면 - Trim.mp4"),
        "asset_alt": os.path.join(BASE_XHS_DIR, "4_피부_숏폼영상_무자막", "14.mp4"),
        "sfx": os.path.join(BASE_SFX_DIR, "3_특수자막(강조용)", "뽀로롱.mp3")
    },
    {
        "id": 7,
        "role": "proof_2",
        "text": "그렇게 한 달 정도 꾸준히 먹어보니, 이젠 프라이머 없이도 매끈한 17호 피부가 됐어요.",
        "caption_l1": "그렇게 한 달 정도 꾸준히 먹어보니,",
        "caption_l2": "이젠 프라이머 없이도 매끈한 17호 피부!",
        "highlight": "매끈한 17호 피부!",
        "asset": os.path.join(BASE_MODEL_DIR, "피부 클로즈업 - Trim.mp4"),
        "sfx": os.path.join(BASE_SFX_DIR, "3_특수자막(강조용)", "티딩! 효과음.mp3")
    },
    {
        "id": 8,
        "role": "mechanism",
        "text": "알고 보니 속피지선부터 바짝 말려주고 진피 속엔 초저분자 콜라겐을 메워주는 원리라는데, 와, 피부과 프락셀 레이저가 피부 자체에 이식된 느낌?",
        "caption_l1": "속피지선 바짝 말리고 초저분자 콜라겐 채우는 원리!",
        "caption_l2": "프락셀 레이저가 피부에 이식된 느낌?",
        "highlight": "프락셀 레이저가 피부에 이식된 느낌?",
        "asset": os.path.join(BASE_MODEL_DIR, "제품 얼굴 옆에 들고 찍는 장면(좌우반전됨..) - Trim.mp4"),
        "asset_alt": os.path.join(BASE_MODEL_DIR, "거울 보는 장면 - Trim.mp4"),
        "sfx": os.path.join(BASE_SFX_DIR, "3_특수자막(강조용)", "Ding Sound Effect.mp3")
    },
    {
        "id": 9,
        "role": "maintain",
        "text": "하루 종일 자연광 맞아도 매끈한 깐달걀 피부 톤이 쭈욱 유지돼요!",
        "caption_l1": "하루 종일 자연광 맞아도",
        "caption_l2": "매끈한 깐달걀 피부 톤이 쭈욱 유지돼요!",
        "highlight": "매끈한 깐달걀 피부 톤",
        "asset": os.path.join(BASE_MODEL_DIR, "피부 클로즈업3 - Trim.mp4"),
        "sfx": os.path.join(BASE_SFX_DIR, "3_특수자막(강조용)", "티딩! 효과음.mp3")
    },
    {
        "id": 10,
        "role": "cta",
        "text": "30일 기간 한정 반값 할인도 한다는데, 궁금한 분들은 아래 비밀링크 참고해 보세요.",
        "caption_l1": "30일 기간 한정 반값 할인!",
        "caption_l2": "궁금한 분들은 아래 비밀링크 참고해 보세요 👇",
        "highlight": "30일 기간 한정 반값 할인!",
        "asset": os.path.join(BASE_MODEL_DIR, "화살표 아래로_CTA (손가락 모양이 좀..) - Trim.mp4"),
        "asset_alt": os.path.join(BASE_MODEL_DIR, "따봉.mp4"),
        "sfx": os.path.join(BASE_SFX_DIR, "3_특수자막(강조용)", "Ding Ding Sound Effect.wav")
    }
]

def trim_silence(path: str) -> AudioSegment:
    sound = AudioSegment.from_file(path)
    ns = detect_nonsilent(sound, min_silence_len=80, silence_thresh=-38)
    if ns:
        start = max(0, ns[0][0] - 50)
        end = min(len(sound), ns[-1][1] + 80)
        return sound[start:end]
    return sound

async def generate_all_tts(scenes):
    audio_dir = os.path.abspath("temp_audio/retiragen_pore_v2")
    os.makedirs(audio_dir, exist_ok=True)
    voice = "ko-KR-SunHiNeural"
    rate = "+16%"

    print("🎙️ 1. Edge-TTS 오디오 생성 및 무음 트리밍 시작...")
    for s in scenes:
        raw_mp3 = os.path.join(audio_dir, f"raw_scene_{s['id']:02d}.mp3")
        clean_mp3 = os.path.join(audio_dir, f"scene_{s['id']:02d}.wav")
        comm = edge_tts.Communicate(s["text"], voice, rate=rate)
        await comm.save(raw_mp3)
        trimmed = trim_silence(raw_mp3)
        trimmed.export(clean_mp3, format="wav")
        dur = len(trimmed) / 1000.0
        s["audio_path"] = clean_mp3
        s["duration"] = round(dur, 2)
        print(f"  [Scene {s['id']:02d}] {dur:.2f}s | {s['text'][:25]}...")
    
    total_dur = sum(s["duration"] for s in scenes)
    print(f"✅ 총 음성 길이: {total_dur:.2f}초\n")
    return scenes

def build_ass_subtitles(scenes, ass_path):
    """ASS 규격 가독성 극대화 숏폼 자막 생성"""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Pretendard-Bold,68,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,5.5,2.5,2,40,40,340,1
Style: Highlight,Pretendard-Bold,72,&H0000FFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,6.0,3.0,2,40,40,340,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    curr_time = 0.0

    def fmt_time(t):
        hrs = int(t // 3600)
        mins = int((t % 3600) // 60)
        secs = int(t % 60)
        cs = int(round((t - int(t)) * 100))
        if cs >= 100:
            cs = 99
        return f"{hrs:01d}:{mins:02d}:{secs:02d}.{cs:02d}"

    for s in scenes:
        start_str = fmt_time(curr_time)
        end_str = fmt_time(curr_time + s["duration"])
        l1 = s["caption_l1"]
        l2 = s["caption_l2"]
        hl = s["highlight"]

        text_lines = []
        for line in [l1, l2]:
            if not line:
                continue
            if hl in line:
                # 하이라이트 단어 형광 노랑 컬러 태그
                line = line.replace(hl, f"{{\\c&H003BFF&\\b1\\fscx108\\fscy108}}{hl}{{\\c&H00FFFFFF&\\fscx100\\fscy100}}")
            text_lines.append(line)
        full_text = "\\N".join(text_lines)

        events.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{full_text}")
        curr_time += s["duration"]

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events) + "\n")
    print(f"📝 자막 파일 생성 완료: {ass_path}")

def render_scene_clip(s, out_path):
    """각 씬의 비디오를 1080x1920 9:16으로 맞추고 정확한 오디오 길이에 동기화"""
    dur = s["duration"]
    asset = s["asset"]
    alt_asset = s.get("asset_alt")

    # 멀티 컷 분할 (asset_alt가 있는 경우 절반씩 사용)
    if alt_asset and os.path.exists(alt_asset):
        half_dur = dur / 2.0
        part1 = out_path.replace(".mp4", "_p1.mp4")
        part2 = out_path.replace(".mp4", "_p2.mp4")

        cmd1 = [
            "ffmpeg", "-y", "-ss", "0.2", "-t", f"{half_dur:.3f}",
            "-i", asset,
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-an", part1
        ]
        cmd2 = [
            "ffmpeg", "-y", "-ss", "0.2", "-t", f"{half_dur:.3f}",
            "-i", alt_asset,
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-an", part2
        ]
        subprocess.run(cmd1, capture_output=True, check=True)
        subprocess.run(cmd2, capture_output=True, check=True)

        concat_list = out_path.replace(".mp4", "_concat.txt")
        with open(concat_list, "w", encoding="utf-8") as f:
            f.write(f"file '{part1.replace(chr(92), '/')}'\nfile '{part2.replace(chr(92), '/')}'\n")

        cmd_cat = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
            "-c", "copy", out_path
        ]
        subprocess.run(cmd_cat, capture_output=True, check=True)
    else:
        # 단일 컷
        cmd = [
            "ffmpeg", "-y", "-ss", "0.2", "-t", f"{dur:.3f}",
            "-stream_loop", "-1", "-i", asset,
            "-t", f"{dur:.3f}",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-an", out_path
        ]
        subprocess.run(cmd, capture_output=True, check=True)

def assemble_master_video(scenes, ass_path, output_mp4):
    """모든 씬 클립, 오디오, SFX, BGM, 자막을 1080x1920 마스터 MP4로 합성"""
    temp_dir = os.path.abspath("temp_videos/retiragen_pore_v2")
    os.makedirs(temp_dir, exist_ok=True)

    print("🎬 2. 개별 씬 9:16 비디오 클립 렌더링...")
    clip_paths = []
    for s in scenes:
        cp = os.path.join(temp_dir, f"clip_scene_{s['id']:02d}.mp4")
        render_scene_clip(s, cp)
        clip_paths.append(cp)
        print(f"  [Clip {s['id']:02d}] 완료 ({s['duration']:.2f}s)")

    # 1) 비디오 트랙 Concat
    raw_video = os.path.join(temp_dir, "master_raw_video.mp4")
    concat_txt = os.path.join(temp_dir, "video_list.txt")
    with open(concat_txt, "w", encoding="utf-8") as f:
        for cp in clip_paths:
            f.write(f"file '{cp.replace(chr(92), '/')}'\n")

    cmd_vcat = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt,
        "-c", "copy", raw_video
    ]
    subprocess.run(cmd_vcat, capture_output=True, check=True)

    # 2) 오디오 마스터 트랙 믹싱 (Voiceover + SFX + BGM)
    print("🔊 3. 오디오 마스터 트랙 믹싱 (보이스 + 효과음 + 배경음악)...")
    master_voice = AudioSegment.empty()
    curr_ms = 0
    sfx_segments = []

    for s in scenes:
        seg = AudioSegment.from_file(s["audio_path"])
        master_voice += seg
        
        # SFX 믹싱
        if s.get("sfx") and os.path.exists(s["sfx"]):
            sfx_sound = AudioSegment.from_file(s["sfx"]) - 10 # -10dB 볼륨 조절
            sfx_segments.append((curr_ms, sfx_sound))
        curr_ms += len(seg)

    total_len_ms = len(master_voice)

    # 마스터 오디오에 SFX 오버레이
    full_audio = master_voice
    for pos_ms, sfx_seg in sfx_segments:
        full_audio = full_audio.overlay(sfx_seg, position=pos_ms)

    # BGM 오버레이 (Its Jazz -25dB 잔잔하게 깔기)
    bgm_path = os.path.join(BASE_SFX_DIR, "1_BGM(일반)", "Its Jazz 30 sec.wav")
    if os.path.exists(bgm_path):
        bgm = AudioSegment.from_file(bgm_path) - 26 # -26dB 배경음
        bgm_looped = bgm * (int(total_len_ms / len(bgm)) + 2)
        bgm_trimmed = bgm_looped[:total_len_ms].fade_in(500).fade_out(1500)
        full_audio = full_audio.overlay(bgm_trimmed)

    master_audio_path = os.path.join(temp_dir, "master_audio.wav")
    full_audio.export(master_audio_path, format="wav")

    # 3) 최종 MP4 합성 + ASS 자막 버닝
    print(f"🔥 4. 최종 마스터 MP4 렌더링 & 고품질 자막 하드서브 합성 -> {output_mp4}")
    os.makedirs(os.path.dirname(output_mp4), exist_ok=True)

    # 자막 경로 escape 처리 (Windows FFmpeg 규격)
    escaped_ass = ass_path.replace("\\", "/").replace(":", "\\:")

    final_cmd = [
        "ffmpeg", "-y",
        "-i", raw_video,
        "-i", master_audio_path,
        "-vf", f"subtitles='{escaped_ass}'",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_mp4
    ]
    subprocess.run(final_cmd, capture_output=True, check=True)
    print(f"🎉 최종 완성본 생성 완료: {output_mp4}")

async def main():
    print("=" * 65)
    print("🚀 [AdForge x Hypit] 레티라겐 모공/프락셀 레퍼런스 비디오 빌더 가동")
    print("=" * 65)

    scenes = await generate_all_tts(SCENES_SPEC)

    ass_path = os.path.abspath("temp_videos/retiragen_pore_v2/subtitles.ass")
    os.makedirs(os.path.dirname(ass_path), exist_ok=True)
    build_ass_subtitles(scenes, ass_path)

    output_mp4 = os.path.abspath("outputs/retiragen_pore_clone.mp4")
    assemble_master_video(scenes, ass_path, output_mp4)

    # 검증용 16컷 타일 생성
    tile_jpg = os.path.abspath("outputs/retiragen_pore_tile16.jpg")
    print(f"\n📸 5. Hypit media tile 16컷 검증 그리드 추출 -> {tile_jpg}")
    cmd_tile = [
        "hypit", "media", "tile", output_mp4,
        "--frames", "16", "--columns", "4",
        "--to", tile_jpg
    ]
    subprocess.run(cmd_tile, capture_output=True, check=True, shell=True)
    print(f"✅ 검증 그리드 완성: {tile_jpg}")

if __name__ == "__main__":
    asyncio.run(main())
