# 레퍼런스 기반 CapCut 편집기

기존 영상 제작 페이지의 **레퍼런스 기반 편집**에서 레퍼런스 영상, 새 대본, 보유 소스 폴더를 입력합니다. Vision API 키는 화면의 비밀번호 입력란 또는 OPENAI_API_KEY / OPENROUTER_API_KEY 환경 변수로 설정합니다. 영상의 표본 프레임과 대본이 선택한 API로 전송됩니다.

PySceneDetect로 실제 컷을 나누고, 화면 분석으로 소스를 선택하며, 원문을 유지한 음성과 측정된 길이에 맞춰 타임라인을 만듭니다. 부족한 소스는 대체 여부를 보고합니다. 자막 위치, 컷 리듬, 줌 움직임을 반영합니다. 네이티브 효과는 기존 로컬 프로젝트에서 읽은 리소스를 사용합니다. 이름이 확인되지 않는 효과와 폰트를 레퍼런스에서 정확히 식별했다고 주장하지 않습니다. 설정에서 직접 선택할 수 있습니다.

프로젝트, 분석 캐시, 계획, 검수 기록은 `outputs/reference_editor/`에 저장됩니다. 기존 프로젝트를 수정하거나 덮어쓰지 않습니다. CapCut 등록 전에 앱을 정상 종료해야 합니다. 생성과 실제 검수는 별도 상태로 기록됩니다.

## 현재 검증 범위

단위·통합 테스트는 장면 경계, 대본 보존, 자막 시간, 소스 구간, 편집 가능한 트랙 생성, 복사 시 경로 변경, 원본 보존을 검사합니다. 실제 레퍼런스와 API 키를 사용한 품질 검수는 별도로 필요합니다.

2026-10-06 로컬 CapCut 9.5에서는 Windows 접근성 API가 홈 창만 반환했습니다. 따라서 이 설치에서 자동 프로젝트 열기와 내보내기는 검증되지 않았습니다. 지원되는 접근성 컨트롤이 없으면 진단 결과를 기록하며, 직접 내보낸 MP4를 화면에서 업로드해 검사할 수 있습니다. 애니메이션·효과의 정확한 재현은 재생 비교가 필요하므로 정지 프레임 검사만으로 전체 검수 완료로 표시하지 않습니다. Pro 리소스는 실제 계정 권한과 앱에서의 적용 확인이 필요합니다.

## 명령줄

```powershell
.\.venv\Scripts\python.exe scripts/reference_editor.py inspect
.\.venv\Scripts\python.exe scripts/reference_editor.py create --reference reference.mp4 --script script.txt --sources C:\media
.\.venv\Scripts\python.exe scripts/reference_editor.py native outputs/reference_editor/run_x/result.json
```

WhisperX는 별도 Python 환경에 `requirements-reference-alignment.txt`로 설치한 후 설정에서 해당 Python 경로를 지정합니다. 기본 음성은 Edge TTS의 단어 경계 정보를 사용합니다.

설계 참고: [capcut-mcp](https://github.com/LHenri88/capcut-mcp), [PySceneDetect](https://github.com/Breakthrough/PySceneDetect), [pyCapCut](https://github.com/GuanYixuan/pyCapCut). 상위 코드를 복사하지 않고 새 파이프라인을 작성했습니다. pyCapCut은 기존 의존성을 사용합니다. WhisperX는 선택적 의존성입니다.
