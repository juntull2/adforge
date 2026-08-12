# AdForge — CapCut 원클릭 자동 생성 고도화

## 1. 최우선 목표

현재 AdForge의 핵심 기능은 유지한다.

현재 레포에는 이미:

- Edge-TTS
- 문장별 음성 생성
- 음성 길이 기반 자막 싱크
- pycapcut 기반 CapCut Draft 생성
- 1080×1920 / 30fps 프로젝트 생성
- Pexels 세로 스톡 다운로드

기능이 구현되어 있다.

이번 개발의 목적은 이 기능들을 하나의 제작 Pipeline으로 연결하는 것이다.

---

# 2. 최종 사용자 경험

사용자는 다음 정보만 입력한다.

```text
프로젝트
주제
검수 완료 대본
TTS 선택
```

그리고 버튼 하나:

```text
[🎬 CapCut 프로젝트 생성]
```

을 누른다.

이 버튼 하나로 다음 작업을 자동 처리한다.

```text
대본
↓
Scene 분할
↓
Hook 추출
↓
Scene별 검색어 생성
↓
무료 Stock 검색
↓
9:16 / 고화질 필터
↓
Stock 다운로드
↓
영상 길이 자동 조정
↓
TTS 생성
↓
자막 생성
↓
Hook 강조 자막 생성
↓
CapCut Draft 생성
```

사용자는 CapCut을 열어 결과를 확인한다.

---

# 3. 중요한 UX 원칙

## 완벽한 영상 검수 UI를 만들지 않는다.

이번 버전에서는 사용자가 CapCut에서 직접 결과를 확인한다.

마음에 들지 않으면:

```text
CapCut 프로젝트 삭제
↓
AdForge에서 [🔄 다시 생성]
↓
새로운 영상 소스 선택
↓
새로운 CapCut 프로젝트 생성
```

구조로 한다.

---

# 4. "다시 생성" 기능

반드시 구현한다.

버튼:

```text
[🔄 새로운 영상으로 다시 생성]
```

기존 생성 결과와 동일한 Stock Asset을 반복 사용하지 않는다.

DB 또는 JSON에:

```text
generation_id
project_id
scene_id
used_asset_ids
```

를 기록한다.

재생성 시:

```text
기존 used_asset_ids
↓
exclude
↓
새로운 Stock 검색 결과
↓
새로운 영상 선택
```

한다.

---

# 5. 생성 버전 관리

예:

```text
혈당관리_001
혈당관리_002
혈당관리_003
```

각 생성마다 고유한 `generation_id`를 만든다.

예:

```text
GEN-20260812-001
GEN-20260812-002
GEN-20260812-003
```

---

# 6. Hook 자동 강조

대본의 첫 번째 문장을 무조건 Hook으로 취급하지 않는다.

가능하면 현재 대본 구조상 첫 번째 문장을 기본 Hook으로 사용하되, 명확한 Hook 후보가 있으면 우선 선택한다.

예:

```text
혈당 관리가 걱정된다면
식후에 이 운동부터 해보세요.
```

↓

```text
HOOK:
혈당 관리가 걱정된다면
```

또는:

```text
식후에 절대 하지 마세요.
```

↓

```text
HOOK:
식후에 절대 하지 마세요.
```

---

# 7. Hook 자막 스타일

첫 0~3초 구간은 일반 자막과 별도 스타일을 적용한다.

기본값:

```text
1080x1920
대형 폰트
Bold
흰색
검정 Stroke
강조 단어 컬러 변경
화면 중앙 또는 상단
Scale/Pop 효과
```

예:

```text
혈당 관리가
걱정된다면
```

일반 자막보다 크게 표시한다.

---

# 8. Hook 강조 단어

Hook 전체를 같은 색으로 하지 않는다.

예:

```text
혈당 관리가
걱정된다면
```

에서:

```text
혈당
```

또는

```text
걱정된다면
```

을 Accent Color로 강조할 수 있도록 한다.

Project 설정에서:

```text
hook_text_color
hook_accent_color
hook_font_size
hook_position
hook_animation
hook_stroke
```

를 설정 가능하게 만든다.

---

# 9. Hook 영상도 자동으로 맞춘다.

Hook 텍스트만 강조해서는 안 된다.

Hook 문장을 Scene 01의 영상 검색어 생성에 사용한다.

예:

```text
Hook:
"식후에 절대 하지 마세요."
```

검색어:

```text
senior after meal sitting sofa
elderly lying sofa after eating
senior resting after meal
```

등을 생성한다.

첫 번째 영상은 Hook의 의미를 시각적으로 전달하는 것을 최우선으로 한다.

---

# 10. Scene Planner

검수 완료 대본을 Scene 단위로 나눈다.

예:

```text
Scene 01
0~3초
Hook
"식후에 절대 하지 마세요."

Scene 02
3~7초
"대부분 식사 후 바로 앉아버리는데요."

Scene 03
7~12초
"딱 10분만 걸어보세요."

Scene 04
12~17초
운동 방법 설명
```

각 Scene에:

```text
scene_id
order
narration
duration
visual_description
search_keywords
is_hook
```

을 저장한다.

---

# 11. 영상 소스 우선순위

각 Scene에 대해:

```text
1순위: Local Asset
2순위: Pexels
3순위: Pixabay
4순위: 기존 Stock Cache
5순위: Hailuo
```

를 사용한다.

단, 현재 1차 버전에서는 Hailuo 자동 생성은 선택사항으로 두고 먼저 Stock 자동 배치를 완성한다.

---

# 12. Stock 품질

최종 영상은:

```text
1080x1920
9:16
```

을 기본으로 한다.

원본이 9:16이면 우선 사용한다.

원본이 16:9인 경우:

```text
고해상도
+
중앙 Crop 가능
```

한 영상만 사용한다.

가능하면 4K 원본을 우선한다.

---

# 13. Scene 길이와 영상 길이

예:

```text
Scene 01
TTS duration = 3.2초
```

영상도 최소 3.2초 이상 확보한다.

영상이 8초라면:

```text
3.2초만 사용
```

한다.

영상이 너무 짧으면:

```text
다른 Stock 선택
```

한다.

---

# 14. 영상 자동 배치

CapCut 프로젝트에 실제 Video Segment를 생성한다.

기존의:

```text
Text Track
Audio Track
```

만 만드는 구조에서:

```text
Video Track
Audio Track
Subtitle Track
Hook Track
```

구조로 확장한다.

---

# 15. 최종 CapCut Timeline

예:

```text
VIDEO
├── Scene 01 Stock
├── Scene 02 Stock
├── Scene 03 Stock
└── Scene 04 Stock

AUDIO
└── TTS

SUBTITLE
├── Hook
├── Scene 02 subtitle
├── Scene 03 subtitle
└── Scene 04 subtitle

HOOK
└── Scene 01 강조 텍스트
```

모든 타임라인은 TTS duration을 기준으로 정확하게 맞춘다.

---

# 16. 원클릭 생성

UI에는 명확하게:

```text
[🎬 CapCut 프로젝트 생성]
```

버튼을 만든다.

버튼을 누르면 진행률을 표시한다.

```text
대본 분석       ✅
Scene 분할      ✅
Hook 생성       ✅
Stock 검색      ✅
영상 다운로드   ⏳
TTS 생성        ⏳
자막 생성       ⏳
CapCut 생성     ⏳
```

완료:

```text
✅ CapCut 프로젝트 생성 완료

[CapCut 열기]
[🔄 다시 생성]
```

---

# 17. 재생성

사용자가:

```text
[🔄 다시 생성]
```

을 누르면 새 generation_id를 만든다.

기존:

```text
GEN-001
```

↓

새로운:

```text
GEN-002
```

기존 영상 Asset은 기본적으로 제외한다.

---

# 18. 생성 결과 저장

각 생성마다:

```text
Generation
├── generation_id
├── project_id
├── script_hash
├── created_at
├── capcut_project_name
├── scenes
├── used_assets
└── status
```

를 저장한다.

---

# 19. 프로젝트 이름

자동 생성:

```text
{주제}_{날짜}_{generation_number}
```

예:

```text
혈당관리운동_20260812_001
혈당관리운동_20260812_002
```

---

# 20. 실패 처리

Stock 검색 실패:

```text
→ 다른 검색어
→ 다른 Provider
→ Local Asset
```

순서로 fallback.

영상 다운로드 실패:

```text
→ 다음 Asset
```

CapCut 생성 실패:

```text
→ 오류 로그
→ 실패 단계 표시
→ 재시도 버튼
```

---

# 21. 절대 하지 말 것

이번 단계에서는 다음 기능을 우선 개발하지 않는다.

```text
❌ 대본 검수 AI API
❌ 복잡한 내부 영상 편집 UI
❌ 네이버 클립 자동 다운로드
❌ 모든 장면 Hailuo 생성
❌ 자체 영상 생성 모델 개발
❌ 불필요한 Dashboard 확장
```

---

# 22. 이번 개발의 핵심

현재 AdForge는 이미:

```text
TTS
+
자막
+
CapCut Draft
+
1080x1920
+
Pexels Stock
```

기반이 있다.

따라서 기존 기능을 버리고 새로 만들지 않는다.

**현재 기능을 하나의 Pipeline으로 연결한다.**

최종적으로:

```text
대본 붙여넣기
↓
[🎬 CapCut 프로젝트 생성]
↓
기다림
↓
CapCut 열기
↓
영상 확인
```

이 경험을 만드는 것이 이번 작업의 최우선 목표다.

---

# 23. 성공 기준

테스트 대본 하나를 넣었을 때:

### 사람

```text
대본 입력
버튼 클릭
```

만 한다.

### AdForge

```text
Scene 분석
Stock 검색
영상 다운로드
9:16 변환/선택
TTS
자막
Hook
CapCut Draft
```

를 자동 처리한다.

### 최종 결과

CapCut을 열었을 때:

```text
1080x1920
9:16
TTS
자막
Hook 강조
Scene별 영상
```

이 이미 들어가 있어야 한다.

사용자는 필요한 경우만 수정한다.

---

# 24. 가장 중요한 UX

AdForge의 목표는:

> "영상을 만들어주는 도구"

가 아니라

> **"버튼 하나 누르면 CapCut에서 바로 검수할 수 있는 영상이 만들어지는 도구"**

가 되는 것이다.