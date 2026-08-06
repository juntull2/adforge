import os
import asyncio
import edge_tts
import pycapcut as cc
from pycapcut import SEC, Timerange, TrackType, TextStyle, TextBorder, TextSegment, AudioMaterial, AudioSegment

async def generate_tts_audio(text: str, output_path: str, voice_config="ko-KR-SunHiNeural"):
    """Edge-TTS를 사용하여 텍스트를 한국어 MP3 오디오로 변환합니다."""
    if isinstance(voice_config, dict):
        voice = voice_config.get("voice", "ko-KR-SunHiNeural")
        rate = voice_config.get("rate", "+0%")
        pitch = voice_config.get("pitch", "+0Hz")
    else:
        voice = voice_config
        rate = "+0%"
        pitch = "+0Hz"

    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)

def create_capcut_with_tts(script_text: str, project_name: str = "허리_복대_음성더빙_광고", voice="ko-KR-SunHiNeural"):
    """
    대본(텍스트)을 읽어:
    1. Edge-TTS로 문장별 음성(MP3) 파일 생성
    2. 생성된 음성의 실제 길이를 측정
    3. 자막과 음성을 1:1로 완벽하게 싱크 맞춰 CapCut 초안 프로젝트로 생성
    """
    draft_folder_path = "C:/Users/5700G/AppData/Local/CapCut/User Data/Projects/com.lveditor.draft"
    draft_folder = cc.DraftFolder(draft_folder_path)

    # 1. 새 CapCut 초안 프로젝트 생성 (1080x1920 세로 숏폼 규격, 30fps)
    script_file = draft_folder.create_draft(project_name, width=1080, height=1920, fps=30, allow_replace=True)

    # 2. 트랙 생성 (자막 트랙 + 음성 더빙 트랙)
    script_file.add_track(TrackType.text, track_name="자동_자막_트랙")
    script_file.add_track(TrackType.audio, track_name="음성_더빙_트랙")

    # 임시 오디오 저장 디렉토리
    audio_dir = os.path.join(os.getcwd(), "temp_audio")
    os.makedirs(audio_dir, exist_ok=True)

    lines = [line.strip() for line in script_text.strip().split("\n") if line.strip()]
    print(f"총 {len(lines)}개 문장에 대해 AI 음성 변환 및 자막 싱크 생성을 시작합니다...\n")

    current_time_us = 0

    for i, line in enumerate(lines, 1):
        mp3_path = os.path.join(audio_dir, f"voice_{i}.mp3")

        # 3. AI 음성(TTS) 파일 생성
        asyncio.run(generate_tts_audio(line, mp3_path, voice_config=voice))

        # 4. 생성된 음성 소재 분석 (길이 추출)
        audio_mat = AudioMaterial(mp3_path)
        audio_duration_us = audio_mat.duration

        timerange = Timerange(current_time_us, audio_duration_us)

        # 5. 오디오 세그먼트 생성 및 오디오 트랙 추가
        audio_seg = AudioSegment(audio_mat, timerange)
        script_file.add_segment(audio_seg, track_name="음성_더빙_트랙")

        # 6. 자막 세그먼트 생성 (음성 길이와 100% 동일하게 싱크)
        style = TextStyle(size=7.5, color=(1.0, 1.0, 1.0), bold=True)
        border = TextBorder(color=(0.0, 0.0, 0.0), width=30.0)
        text_seg = TextSegment(text=line, timerange=timerange, style=style, border=border)

        script_file.add_segment(text_seg, track_name="자동_자막_트랙")

        sec_val = audio_duration_us / SEC
        print(f"[{i}/{len(lines)}] Voice: {sec_val:.2f}초 | 문장: '{line}'")

        # 다음 문장의 시작 시간 업데이트
        current_time_us += audio_duration_us

    # 7. 프로젝트 저장
    script_file.save()
    print(f"\n성공! 음성 더빙과 자막이 싱크된 CapCut 프로젝트 '{project_name}'이 생성되었습니다.")
    print("CapCut 앱을 열어 들어보세요!")

if __name__ == "__main__":
    script = """
    허리 삐끗했을 때 파스 붙이고 누워만 계셨다면 당장 멈추세요!
    갑자기 굳은 척추 속근육은 겉만 따뜻하게 해선 절대 풀리지 않습니다.
    핵심은 3파장 근적외선으로 피부 속 3cm 깊은 척추 마디까지 열을 전달하는 것인데요.
    한의원 치료에 쓰이는 원적외선과 근적외선이 동시에 나오는 복대를 차주면…
    굳어있던 척추가 사르르 풀리면서 3초 만에 일상생활 가능! 무선이라 차고 집안일도 OK
    30일 써보고 마음에 안 들면 100% 환불!
    """

    # 여성 음성: ko-KR-SunHiNeural
    # 남성 음성: ko-KR-InJoonNeural
    create_capcut_with_tts(script, project_name="허리_복대_음성더빙_광고", voice="ko-KR-SunHiNeural")
