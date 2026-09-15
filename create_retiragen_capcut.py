import os
import sys
import re
import json
import uuid
import time
import shutil
from pathlib import Path

# AdForge 환경 세팅
sys.stdout.reconfigure(encoding='utf-8')
import pycapcut as cc
from pycapcut import (
    TrackType, AudioMaterial, AudioSegment, VideoMaterial, VideoSegment,
    TextSegment, TextStyle, TextBorder, ClipSettings, Timerange, SEC
)
from naver_clip_adforge import (
    PRETENDARD_FONT, BLACK_HAN_SANS_FONT,
    generate_single_sentence_tts, trim_audio_silence,
    calculate_effective_speech_length, split_sentence_naturally,
    apply_context_aware_keyframes, DEFAULT_FISH_VOICE
)

def create_retiragen_project():
    print("=" * 60)
    print("🎬 [AdForge] 레티라겐 레퍼런스 1:1 미러링 캡컷 프로젝트 생성 시작")
    print("=" * 60)

    local_media_folder = r"C:\Users\5700G\Desktop\레티라겐"
    sfx_folder = os.path.abspath("local_assets/sfx")
    temp_dir = os.path.abspath("temp_audio")
    os.makedirs(temp_dir, exist_ok=True)

    # 1. 레퍼런스 기반 8개 씬 구성
    scenes = [
        {
            "role": "hook",
            "text": "딱 한 달 먹기만 했는데, 푹 패인 흉터 어디 가고 깐달걀 피부만 남아있어.",
            "video": "여드름 비포 1.mp4",
            "sfx": "whoosh.mp3",
            "is_hook": True
        },
        {
            "role": "proof",
            "text": "나 진짜 한 달 딱 먹었거든? 이거 봐봐, 진짜 대박이야.",
            "video": "여드름 애프터 1.mp4",
            "sfx": "ding.mp3",
            "is_hook": True
        },
        {
            "role": "discovery",
            "text": "피부과 원장들도 몰래 챙겨 먹는다는 여드름 재생 캡슐이거든?",
            "video": "Hailuo_Video_약국 한바퀴 돌아보는 장면 UGC 스마트폰 브이로그 _553642253490466819.mp4",
            "sfx": "pop.mp3",
            "is_hook": False
        },
        {
            "role": "usp",
            "text": "울긋불긋 여드름에 패인 흉터까지 싹 메워주는 인생 꿀템!",
            "video": "제품 확대샷 2.mp4",
            "sfx": "whoosh.mp3",
            "is_hook": False
        },
        {
            "role": "mechanism",
            "text": "피지 말려주는 스위스산 레티놀에 살 채워주는 300달톤 콜라겐까지 피부에 좋은 건 다 들었는데,",
            "video": "Collagen_fibers_repairing_skin_t…_202609041426.mp4",
            "sfx": "pop.mp3",
            "is_hook": False
        },
        {
            "role": "intake",
            "text": "하루 딱 한 알 꿀꺽 삼키면 끝!",
            "video": "약 먹기 2.mp4",
            "sfx": "ding.mp3",
            "is_hook": False
        },
        {
            "role": "result",
            "text": "처음엔 기름질까 봐 걱정했는데, 피지는 싹 마르고 속살만 차오르니까 화장이 진짜 찰떡같이 먹어요.",
            "video": "볼콕콕.mp4",
            "sfx": "whoosh.mp3",
            "is_hook": False
        },
        {
            "role": "cta",
            "text": "피부 흉터는 시간 지나면 굳어버리는 거 아시죠? 지금 100% 환불 보장에 특가 할인 중이니까 품절 전에 얼른 겟하세요!",
            "video": "Hailuo_Video_이 여자가 용돈받아서 신나하는 모습 UGC 스마트폰 _553631647555211265.mp4",
            "sfx": "ding.mp3",
            "is_hook": False
        }
    ]

    # 2. 캡컷 프로젝트 생성
    project_name = f"AutoProject_레티라겐_레퍼런스_{int(time.time())}"
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        local_app_data = os.path.expanduser("~\\AppData\\Local")
    draft_folder_path = os.path.join(local_app_data, "CapCut", "User Data", "Projects", "com.lveditor.draft")

    draft_folder = cc.DraftFolder(draft_folder_path)
    script_file = draft_folder.create_draft(project_name, width=1080, height=1920, fps=30, allow_replace=True)
    script_file.content["canvas_config"] = {"width": 1080, "height": 1920, "ratio": "9:16"}

    # 트랙 구성
    script_file.add_track(TrackType.video, track_name="메인_비디오_트랙")
    script_file.add_track(TrackType.text, track_name="자막_트랙")
    script_file.add_track(TrackType.audio, track_name="더빙_트랙")
    script_file.add_track(TrackType.audio, track_name="효과음_트랙")

    current_time_us = 0
    voice = DEFAULT_FISH_VOICE

    print(f"\n[1] 프로젝트명: {project_name}")
    print(f"[2] 총 {len(scenes)}개 씬 TTS 음성 생성 및 타임라인 배치 중...")

    for idx, sc in enumerate(scenes):
        s_idx = idx + 1
        clean_text = sc["text"].strip()
        v_name = sc["video"]
        sfx_name = sc["sfx"]
        is_hook = sc["is_hook"]

        # 2-1. TTS 음성 생성
        mp3_path = os.path.join(temp_dir, f"{project_name}_s{s_idx}.mp3")
        clean_audio_text = re.sub(r'[*#\[\]_=\-]', '', clean_text).strip()
        generate_single_sentence_tts(clean_audio_text, mp3_path, voice=voice, speed=1.05)
        trim_audio_silence(mp3_path)

        audio_mat = AudioMaterial(mp3_path)
        sentence_duration_us = audio_mat.duration

        # 더빙 트랙 추가
        audio_timerange = Timerange(current_time_us, sentence_duration_us)
        script_file.add_segment(AudioSegment(audio_mat, audio_timerange), track_name="더빙_트랙")

        # 2-2. 효과음(SFX) 트랙 추가
        if sfx_name:
            sfx_path = os.path.join(sfx_folder, sfx_name)
            if os.path.exists(sfx_path):
                try:
                    sfx_mat = AudioMaterial(sfx_path)
                    sfx_dur = min(sfx_mat.duration, int(1.2 * SEC))
                    sfx_timerange = Timerange(current_time_us, sfx_dur)
                    script_file.add_segment(AudioSegment(sfx_mat, sfx_timerange), track_name="효과음_트랙")
                except Exception as e:
                    print(f"  (효과음 삽입 오류 {sfx_name}: {e})")

        # 2-3. 비디오 소스 매칭 및 트랙 추가
        v_file_path = os.path.join(local_media_folder, v_name)
        if os.path.exists(v_file_path):
            try:
                v_mat = VideoMaterial(v_file_path)
                ext = os.path.splitext(v_file_path)[1].lower()
                if ext in ['.jpg', '.jpeg', '.png']:
                    clip_dur = sentence_duration_us
                    src_timerange = Timerange(0, clip_dur)
                else:
                    clip_dur = min(v_mat.duration, sentence_duration_us)
                    src_timerange = Timerange(0, clip_dur)

                tgt_timerange = Timerange(current_time_us, sentence_duration_us)
                v_width = getattr(v_mat, 'width', 0)
                v_height = getattr(v_mat, 'height', 0)
                scale_factor = max(1080.0 / v_width, 1920.0 / v_height) if v_width and v_height else 1.0

                clip_settings = ClipSettings(scale_x=scale_factor, scale_y=scale_factor)
                v_seg = VideoSegment(v_mat, tgt_timerange, source_timerange=src_timerange, clip_settings=clip_settings)
                
                try:
                    apply_context_aware_keyframes(v_seg, clean_text, scale_factor, duration_us=tgt_timerange.duration)
                except Exception:
                    pass

                script_file.add_segment(v_seg, track_name="메인_비디오_트랙")
            except Exception as ve:
                print(f"  (비디오 클립 연동 경고 {v_name}: {ve})")
        else:
            print(f"  [주의] 비디오 파일을 찾을 수 없음: {v_name}")

        # 2-4. 자막 트랙 추가 (구문 단위 분할 및 스타일링)
        phrases = split_sentence_naturally(clean_text, max_chars=18)
        if not phrases:
            phrases = [clean_text]

        phrase_lens = [calculate_effective_speech_length(p) for p in phrases]
        total_p_len = sum(phrase_lens) or 1.0
        p_start_us = current_time_us

        for p_idx, (phrase, eff_len) in enumerate(zip(phrases, phrase_lens)):
            if p_idx == len(phrases) - 1:
                p_dur_us = (current_time_us + sentence_duration_us) - p_start_us
            else:
                p_dur_us = int(sentence_duration_us * (eff_len / total_p_len))

            p_timerange = Timerange(p_start_us, p_dur_us)

            # 스타일 설정: 훅/강조는 노란색 큰 글씨, 일반은 흰색 깔끔한 글씨
            text_color = (1.0, 0.9, 0.0) if is_hook else (1.0, 1.0, 1.0)
            text_size = 18.0 if is_hook else 14.5
            font = BLACK_HAN_SANS_FONT if is_hook else PRETENDARD_FONT

            style = TextStyle(size=text_size, color=text_color, bold=True, align=1)
            border = TextBorder(color=(0.0, 0.0, 0.0), width=55.0 if is_hook else 25.0)
            clip_settings = ClipSettings(transform_x=0.0, transform_y=0.0)

            text_seg = TextSegment(
                text=phrase,
                timerange=p_timerange,
                font=font,
                style=style,
                border=border,
                clip_settings=clip_settings
            )
            script_file.add_segment(text_seg, track_name="자막_트랙")
            p_start_us += p_dur_us

        dur_sec = sentence_duration_us / SEC
        print(f"  ✅ [씬 {s_idx}] ({dur_sec:.1f}s) 소스: {v_name[:20]}... | SFX: {sfx_name} | 대사: {clean_text[:25]}...")

        current_time_us += sentence_duration_us

    # 3. 프로젝트 저장
    script_file.save()
    total_sec = current_time_us / SEC
    print("\n" + "=" * 60)
    print(f"🎉 [성공] 캡컷 프로젝트 생성 완료!")
    print(f"📁 프로젝트명: {project_name}")
    print(f"⏱️ 총 영상 길이: {total_sec:.1f}초")
    print(f"📍 캡컷 경로: {os.path.join(draft_folder_path, project_name)}")
    print("👉 캡컷(CapCut)을 실행하시면 메인 홈 화면에 프로젝트가 바로 표시됩니다!")
    print("=" * 60)
    return project_name

if __name__ == "__main__":
    create_retiragen_project()
