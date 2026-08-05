# 🚀 AdForge (adforge)

**CapCut + AI TTS 기반의 숏폼/네이버 클립 광고 마케팅 영상 자동화 툴**

AdForge는 마케팅 대본을 입력하면 **AI 성우 더빙(TTS)과 자막, 컷 타임라인**을 자동으로 생성하여 **CapCut 프로젝트 초안(.draft)**으로 변환해 주는 자동화 툴입니다.

---

## 🌟 주요 기능 (Key Features)

- **AI 더빙 음성 자동 생성**: Edge-TTS를 연동하여 고품질 한국어 성우(여성/남성) 음성 MP3 자동 생성
- **1:1 자막-음성 타임라인 싱크**: 음성의 길이를 밀리초 단위로 측정하여 자막 타임라인 자동 동기화
- **CapCut 프로젝트 초안 자동 생성**: 별도의 편집 과정 없이 CapCut 앱에서 바로 열어볼 수 있는 초안 프로젝트 생성
- **네이버 클립 / 숏폼 / 릴스 규격 최적화**: 1080x1920 세로 숏폼 규격 및 가독성 높은 자막 스타일 기본 제공

---

## 🛠️ 설치 및 환경 설정 (Setup)

### 1. 레포지토리 클론 및 이동
```bash
git clone https://github.com/juntull2/adforge.git
cd adforge
```

### 2. 가상환경 생성 및 패키지 설치
```bash
# 가상환경 생성
python -m venv .venv

# 가상환경 활성화 (Windows)
.\.venv\Scripts\Activate.ps1

# 패키지 설치
pip install -r requirements.txt
```

---

## 🚀 사용 방법 (Usage)

### AI 더빙 + 자막 자동 생성 스크립트 실행
`auto_tts_script_to_draft.py` 파일 내에 대본 텍스트를 작성한 후 아래 명령어를 실행합니다.

```bash
python auto_tts_script_to_draft.py
```

실행 완료 후 **CapCut 앱**을 열면 새로 생성된 프로젝트를 바로 확인하실 수 있습니다.

---

## 📁 프로젝트 구조

```text
adforge/
├── auto_tts_script_to_draft.py  # AI 더빙 + 자막 싱크 CapCut 프로젝트 생성 메인 스크립트
├── auto_script_to_draft.py      # 대본 기반 자막 타임라인 생성 스크립트
├── main.py                      # CapCut 템플릿 복사 및 기본 수정 스크립트
├── requirements.txt             # 파이썬 의존성 패키지 목록
└── README.md                    # 프로젝트 설명 문서
```
