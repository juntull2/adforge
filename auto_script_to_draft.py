import pycapcut as cc
from pycapcut import SEC, tim, Timerange, TrackType, TextStyle, TextBorder, TextSegment

def create_capcut_from_script(script_text: str, project_name: str = "대본_자동생성_프로젝트", duration_per_line: float = 3.5):
    """
    대본(텍스트)을 입력받아 CapCut 초안 프로젝트로 자막 및 컷 구간을 자동 생성합니다.
    
    :param script_text:줄바꿈(\n)으로 구분된 대본 텍스트
    :param project_name: 생성할 CapCut 초안 프로젝트 이름
    :param duration_per_line: 자막 1줄당 표시할 시간(초)
    """
    # 1. CapCut 초안 폴더 경로
    draft_folder_path = "C:/Users/임준모/AppData/Local/CapCut/User Data/Projects/com.lveditor.draft"
    draft_folder = cc.DraftFolder(draft_folder_path)

    # 2. 새 초안 프로젝트 생성 (FHD 1080x1920 세로 숏폼 기준, 30fps)
    script_file = draft_folder.create_draft(project_name, width=1080, height=1920, fps=30, allow_replace=True)

    # 3. 자막 트랙 추가
    script_file.add_track(TrackType.text, track_name="자동_자막_트랙")

    # 4. 대본 파싱 (빈 줄 제외)
    lines = [line.strip() for line in script_text.strip().split("\n") if line.strip()]

    print(f"총 {len(lines)}개의 대본 문장을 자막으로 변환합니다...")

    current_time_us = 0  # 시작 시간 (미세초 단위)

    # 5. 문장별 자막 클립 생성 및 배치
    for i, line in enumerate(lines, 1):
        # 글자 수에 맞춰 표시 시간 동적 계산 (최소 2초 ~ 최대 6초)
        line_duration_sec = max(2.0, min(6.0, len(line) * 0.18))
        duration_us = int(line_duration_sec * SEC)

        # 자막 스타일 지정 (흰색 글씨 + 검은색 테두리)
        style = TextStyle(
            size=7.5,
            color=(1.0, 1.0, 1.0),  # RGB (1, 1, 1) = 흰색
            bold=True
        )
        border = TextBorder(
            color=(0.0, 0.0, 0.0),  # 검은색 테두리
            width=30.0
        )

        # 자막 세그먼트 생성
        timerange = Timerange(current_time_us, duration_us)
        text_seg = TextSegment(
            text=line,
            timerange=timerange,
            style=style,
            border=border
        )

        # 자막 트랙에 추가
        script_file.add_segment(text_seg, track_name="자동_자막_트랙")

        print(f"[{i}/{len(lines)}] '{line}' ({line_duration_sec:.1f}초)")
        
        # 다음 자막 위치로 이동
        current_time_us += duration_us

    # 6. 초안 저장
    script_file.save()
    print(f"\n성공! CapCut 초안 '{project_name}'이 생성되었습니다.")
    print(f"CapCut 앱을 열어 '{project_name}' 프로젝트를 바로 확인해 보세요!")

if __name__ == "__main__":
    # 사용자가 제출한 숏폼 대본
    user_script = """
    허리 삐끗했을 때 파스 붙이고 누워만 계셨다면 당장 멈추세요!
    갑자기 굳은 척추 속근육은 겉만 따뜻하게 해선 절대 풀리지 않습니다.
    핵심은 3파장 근적외선으로 피부 속 3cm 깊은 척추 마디까지 열을 전달하는 것인데요.
    한의원 치료에 쓰이는 원적외선과 근적외선이 동시에 나오는 복대를 차주면…
    굳어있던 척추가 사르르 풀리면서 3초 만에 일상생활 가능! 무선이라 차고 집안일도 OK
    30일 써보고 마음에 안 들면 100% 환불!
    """

    create_capcut_from_script(user_script, project_name="허리_근적외선_복대_광고")
