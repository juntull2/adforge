# AdForge V2 고도화 개발 지시서

## 0. 프로젝트 목표

현재 AdForge는 `몸편한하루` 숏폼 제작을 중심으로 사용되고 있다.

현재 제작 프로세스:

1. 네이버 클립에서 영상 레퍼런스 탐색
2. 카테고리 선택 + 세부 주제 입력
3. AdForge에서 대본 생성
4. 기존 GPTs에서 대본 검수
5. 검수된 대본을 AdForge Step 2에 복사
6. TTS 선택 → CapCut 프로젝트 생성
7. Hailuo용 영상 프롬프트 생성
8. GPTs에서 Hailuo 프롬프트 검수
9. Hailuo 영상 생성
10. CapCut에서 훅 자막/효과 작업
11. Hailuo 영상 소스 삽입 및 편집
12. 최종 검수
13. 업로드

현재 가장 큰 문제는 **콘텐츠 1편을 만들 때 사람이 여러 단계에서 반복적으로 개입한다는 것**이다.

특히:

- 대본 복사/붙여넣기
- Hailuo 프롬프트 생성/복사/검수
- 영상 소스 검색
- Hailuo 생성
- 영상 다운로드
- CapCut 삽입
- 훅 자막/효과 작업

때문에 제작 속도가 느리다.

### 최종 목표

AdForge를 `몸편한하루 전용 툴`에서

> **어떤 주제든 입력하면 콘텐츠 기획 → 대본 → 장면 설계 → 스톡 영상 검색 → 필요한 장면만 AI 영상 생성 → TTS → 자막 → 훅 효과 → CapCut 프로젝트 생성까지 이어지는 회사 전체 숏폼 콘텐츠 제작 플랫폼**

으로 확장한다.

단, 이번 1차 고도화에서는 **대본 생성/검수 시스템은 기존 방식을 최대한 유지한다.**

현재 사용하는 GPTs를 대본 검수에 계속 사용한다.

---

# 1. 개발 원칙

### 원칙 1. 기존 기능을 먼저 보존한다.

현재 정상 작동하는 AdForge의:

- 대본 생성
- Step 2
- TTS
- CapCut 프로젝트 생성
- 기존 영상 제작 기능

을 먼저 유지한다.

기존 코드를 무리하게 전면 재작성하지 않는다.

---

### 원칙 2. 몸편한하루를 하드코딩하지 않는다.

현재는 몸편한하루 중심이지만 향후:

- 몸편한하루
- 오가닉 콘텐츠
- 제품 광고
- 다른 브랜드
- 다른 플랫폼

까지 사용할 수 있어야 한다.

따라서 신규 기능은 가능한 한 `Project` 기반으로 설계한다.

---

### 원칙 3. 사람이 하는 검수는 당장 없애지 않는다.

이번 단계에서는 AI 검수를 AdForge 내부에 새로 구현하는 것보다,

> **현재 사용자가 직접 사용하는 GPTs 검수 프로세스를 유지한다.**

대신 검수 전후의 복사/붙여넣기와 영상 제작 작업을 자동화한다.

---

### 원칙 4. Hailuo 사용량을 최소화한다.

모든 장면을 Hailuo로 생성하지 않는다.

기본 우선순위:

```text
무료 스톡 영상
↓
기존 보유 영상
↓
간단한 이미지/텍스트 기반 장면
↓
Hailuo AI 영상
```

즉, **스톡으로 충분히 표현 가능한 장면은 Hailuo를 사용하지 않는다.**

---

# 2. Phase 1 — Project 구조 도입

## 목표

AdForge가 `몸편한하루 전용` 구조가 아니라 프로젝트별 설정을 가질 수 있도록 만든다.

### Project 데이터

```text
Project
├── project_id
├── project_name
├── target_audience
├── platform
├── content_category
├── tone
├── default_video_ratio
├── default_resolution
├── default_tts
├── subtitle_style
├── hook_style
├── stock_sources
├── ai_video_provider
└── daily_target
```

예:

```text
프로젝트명: 몸편한하루
타겟: 50~70대
플랫폼: Naver Clip
비율: 9:16
해상도: 1080x1920
하루 목표: 10편
```

향후:

```text
프로젝트명: 제품광고 A
프로젝트명: 오가닉 생활정보
프로젝트명: 브랜드 B
```

를 추가할 수 있어야 한다.

---

# 3. Phase 2 — Script → Scene Planner

## 가장 중요한 핵심 기능

최종 대본을 입력하면 AdForge가 자동으로 **영상 장면 단위로 분리**한다.

예:

```text
대본:

혈당 관리가 걱정된다면
식후에 바로 누워있지 마세요.
딱 10분만 이렇게 움직여보세요.
```

↓

```text
Scene 01
구간: 0~3초
내용: 혈당 관리가 걱정되는 상황
화면: 시니어가 걱정스러운 표정
우선 소스: Stock

Scene 02
구간: 3~7초
내용: 식후 바로 눕는 행동
화면: 소파에 눕는 시니어
우선 소스: Stock

Scene 03
구간: 7~12초
내용: 10분 걷기
화면: 시니어가 걷는 모습
우선 소스: Stock

Scene 04
구간: 12~17초
내용: 특정 운동 동작
화면: 정확한 운동 동작
우선 소스: AI Video
```

### Scene 데이터 구조

```text
Scene
├── scene_id
├── order
├── start_time
├── end_time
├── narration
├── visual_description
├── search_keywords
├── preferred_source
├── aspect_ratio
├── minimum_resolution
├── stock_search_status
├── stock_asset_id
├── ai_video_required
├── ai_video_prompt
└── status
```

---

# 4. Phase 3 — Stock Engine 개발

## 목표

대본의 각 Scene에 필요한 영상을 자동으로 검색한다.

1차 지원 사이트:

- Pexels
- Pixabay

향후 확장 가능하도록 Provider 구조로 만든다.

```text
StockProvider
├── PexelsProvider
├── PixabayProvider
└── FutureProvider
```

---

# 5. Stock 검색 방식

Scene마다 AI 또는 규칙 기반으로 검색어를 생성한다.

예:

```text
Scene:
"식후에 10분 정도 가볍게 걷습니다."

검색어:
senior walking after meal
elderly walking park
senior exercise walking
```

검색 결과를 여러 개 가져온다.

---

# 6. Stock 영상 품질 필터

9:16 숏폼에 사용하기 때문에 단순히 검색 결과를 가져오지 않는다.

다음 기준으로 자동 필터링한다.

### 최우선

```text
9:16
4K
고화질
```

### 차선

```text
4K
16:9
피사체가 중앙에 있음
9:16 Crop 가능
```

### 그 다음

```text
1080p
9:16
```

### 제외

```text
저해상도
워터마크
피사체가 너무 가장자리에 있음
세로 크롭 불가능
검색어와 의미적으로 무관
너무 짧아서 사용 불가능
```

---

# 7. Stock Scoring 시스템

검색 결과마다 점수를 계산한다.

예:

```text
Stock Score

해상도        25점
세로 비율     25점
검색어 적합도 20점
피사체 위치   10점
영상 길이     10점
화질          10점
----------------
총점          100점
```

예:

```text
#1
4K / 9:16 / 적합
97점

#2
4K / 16:9 / Crop 가능
91점

#3
1080p / 9:16
83점
```

상위 결과를 자동 선정한다.

---

# 8. Stock Asset 관리

다운로드한 영상은 단순히 파일만 저장하지 않는다.

다음 메타데이터를 저장한다.

```text
Asset
├── asset_id
├── local_path
├── source
├── source_url
├── author
├── license
├── commercial_use
├── attribution_required
├── original_width
├── original_height
├── duration
├── downloaded_at
└── tags
```

회사에서 광고 콘텐츠까지 사용할 가능성이 있으므로 **출처/라이선스 정보를 반드시 저장한다.**

---

# 9. Phase 4 — 9:16 자동 변환 Pipeline

모든 소스를 최종적으로:

```text
1080 x 1920
9:16
```

으로 맞춘다.

### 변환 규칙

#### 원본 9:16

그대로 사용.

#### 4K 16:9

중앙 크롭 또는 피사체 중심 Crop.

#### 1080p 16:9

품질이 충분하면 사용하되 우선순위를 낮춘다.

#### 세로 피사체가 Crop 과정에서 잘리는 경우

해당 Asset을 자동 제외하고 다음 결과를 사용한다.

---

# 10. Phase 5 — Stock vs Hailuo 자동 판단

Scene Planner에서 모든 장면에 대해 다음 판단을 한다.

```text
이 장면은 무료 스톡으로 충분히 표현 가능한가?
```

### YES

```text
Stock 사용
```

### NO

```text
Hailuo 생성
```

예:

```text
걷는 시니어
→ Stock

물 마시는 시니어
→ Stock

공원에서 스트레칭
→ Stock

정확한 특정 운동 자세
→ Hailuo

현실적으로 구하기 어려운 장면
→ Hailuo
```

---

# 11. Hailuo Prompt 자동 생성

Hailuo가 필요한 Scene만 Prompt를 생성한다.

기존처럼 모든 장면에 Hailuo Prompt를 만들지 않는다.

Prompt는 Scene 정보를 기반으로 생성한다.

```text
Scene 정보
+
인물
+
행동
+
장소
+
카메라
+
조명
+
스타일
+
세로 영상 조건
```

예:

```text
9:16 vertical video,
Korean elderly woman,
performing a gentle indoor exercise,
natural movement,
realistic Korean apartment,
soft daylight,
static medium shot,
realistic documentary style,
no text,
no subtitles,
no distortion
```

---

# 12. Hailuo Prompt 실패 방지 규칙

Hailuo용 Prompt에는 다음을 기본적으로 포함한다.

- 9:16 vertical
- realistic
- natural human movement
- single clear action
- stable camera
- no text
- no subtitles
- no watermark
- no extra limbs
- no duplicated person
- no unnatural movement

특히 **한 장면에 너무 많은 행동을 넣지 않는다.**

나쁜 예:

```text
걷다가 앉아서 물을 마시고 스트레칭하면서 카메라를 바라본다.
```

좋은 예:

```text
A Korean elderly woman slowly walking in a park.
Natural walking motion.
Stable camera.
```

---

# 13. Phase 6 — Hook 자동화

현재 CapCut에서 사람이 직접 만드는 훅 강조 작업을 자동화한다.

대본에서 Hook을 별도로 추출한다.

예:

```text
전체 대본:
혈당 관리가 걱정된다면
식후에 바로 누워있지 마세요.
...
```

Hook:

```text
혈당 관리가 걱정된다면
```

또는

```text
식후에 절대 하지 마세요.
```

프로젝트별 Hook Style을 적용한다.

예:

```text
Hook Style
├── 강조 색상
├── 폰트
├── 크기
├── 등장 시점
├── 확대 효과
├── 흔들림 효과
└── 강조 단어
```

---

# 14. Phase 7 — CapCut 자동 구성

최종 결과물은:

```text
TTS
+
Stock Video
+
Hailuo Video
+
Subtitle
+
Hook Effect
+
Background
```

를 자동으로 배치한 CapCut 프로젝트가 되어야 한다.

목표:

> 사람이 CapCut을 열었을 때 처음부터 영상이 거의 완성되어 있어야 한다.

사람이 하는 것은:

```text
최종 검수
↓
필요하면 일부 수정
↓
Export
```

정도로 줄인다.

---

# 15. Phase 8 — Batch Production

## 하루 10편 생산을 위해 반드시 필요한 기능

현재:

```text
1편 제작
↓
완료
↓
2편 제작
```

이 아니라:

```text
주제 10개
↓
10개 대본
↓
10개 Scene Planner
↓
Stock 검색 병렬 실행
↓
Hailuo 필요한 Scene만 병렬 생성
↓
TTS 병렬 생성
↓
CapCut 프로젝트 10개
```

로 만든다.

---

# 16. Batch Dashboard

화면에 현재 제작 상태를 보여준다.

```text
오늘 목표: 10편

① 혈당 관리 운동
   대본 ✅
   Stock ✅
   Hailuo ⏳
   CapCut ⏳

② 무릎 통증 운동
   대본 ✅
   Stock ✅
   Hailuo ✅
   CapCut ✅

③ 식후 걷기
   대본 검수 대기

④ 허리 스트레칭
   대본 생성 중
```

상태:

```text
Draft
Script Review
Scene Planning
Stock Searching
AI Video Generating
Composing
QA
Completed
```

---

# 17. 제작 시간을 측정한다.

각 단계의 소요시간을 기록한다.

```text
script_generation_time
stock_search_time
stock_download_time
hailuo_generation_time
tts_generation_time
capcut_generation_time
human_review_time
total_production_time
```

목표는 단순히 기능을 많이 만드는 것이 아니다.

### 최종 KPI

```text
1편 평균 제작 시간
현재 대비 50% 이상 단축

사람의 실제 작업 시간
현재 대비 70% 이상 단축

Hailuo 사용 장면
전체 장면의 30~40% 이하

하루 생산 가능량
10편 이상
```

---

# 18. Phase 9 — Project 확장

1차 목표가 `몸편한하루`에서 안정화되면 같은 엔진을 다른 프로젝트에 적용한다.

### 프로젝트 A

```text
몸편한하루
정보형 건강 콘텐츠
```

### 프로젝트 B

```text
오가닉 콘텐츠
정보 / 공감 / 생활꿀팁
```

### 프로젝트 C

```text
제품 광고
제품 정보 → 광고 소재 → 영상
```

중요한 점은 **제작 엔진을 다시 개발하지 않는 것**이다.

Project 설정만 변경해서 사용한다.

---

# 19. 향후 2차 고도화

1차 고도화가 안정화된 후 추가한다.

## Reference Engine

네이버 클립 레퍼런스 수집:

```text
레퍼런스 검색
↓
인기 콘텐츠 수집
↓
제목/후킹 분석
↓
영상 구조 분석
↓
주제 추출
↓
콘텐츠 소재화
```

---

# 20. 향후 3차 고도화

## Performance Engine

게시된 콘텐츠 성과를 저장한다.

```text
조회수
좋아요
댓글
공유
저장
완주율
클릭
전환
```

그리고:

```text
어떤 Hook이 잘 터졌는가?
어떤 주제가 잘 터졌는가?
어떤 영상 길이가 좋은가?
어떤 레시피가 좋은가?
```

를 분석한다.

최종적으로는:

```text
성과 데이터
↓
콘텐츠 패턴 분석
↓
다음 콘텐츠 소재 추천
↓
다음 10편 자동 제작
```

까지 연결한다.

---

# 21. 최종 Architecture

최종적으로 AdForge는 다음 구조를 목표로 한다.

```text
                    AD FORGE
                       │
             ┌─────────┴─────────┐
             │      PROJECT      │
             └─────────┬─────────┘
                       ↓
                CONTENT INPUT
                       ↓
                 SCRIPT ENGINE
                       ↓
              [현재 GPTs 검수]
                       ↓
                  SCENE PLANNER
                       ↓
              ┌────────┴────────┐
              ↓                 ↓
        STOCK ENGINE        AI VIDEO ENGINE
              ↓                 ↓
         Pexels/Pixabay       Hailuo
              ↓                 ↓
              └────────┬────────┘
                       ↓
                    TTS
                       ↓
              VIDEO COMPOSER
                       ↓
             HOOK/SUBTITLE
                       ↓
                 CAPCUT DRAFT
                       ↓
                    QA
                       ↓
                 HUMAN REVIEW
                       ↓
                   EXPORT
                       ↓
                   UPLOAD
                       ↓
             PERFORMANCE ENGINE
                       ↓
                DATA / LEARNING
```

---

# 22. 개발 순서

절대 한 번에 전체를 만들지 않는다.

### Phase 1
**Project 구조**

↓

### Phase 2
**Script → Scene Planner**

↓

### Phase 3
**Pexels/Pixabay Stock Engine**

↓

### Phase 4
**9:16 / 고화질 자동 필터 + Crop**

↓

### Phase 5
**Stock vs Hailuo 자동 분류**

↓

### Phase 6
**Hailuo Prompt 자동 생성**

↓

### Phase 7
**Hook / Subtitle 자동화**

↓

### Phase 8
**CapCut 자동 구성**

↓

### Phase 9
**10편 Batch Production**

↓

### Phase 10
**Production Dashboard**

↓

### Phase 11
**Reference Engine**

↓

### Phase 12
**Performance Engine**

---

# 23. 이번 개발에서 하지 말아야 할 것

### ❌ 하지 말 것

1. 기존 AdForge 전체 재작성
2. 대본 GPT 검수 시스템을 당장 API로 변경
3. 모든 Scene을 Hailuo로 생성
4. 특정 사이트 하나에 Stock Engine을 하드코딩
5. 몸편한하루 전용 코드 추가
6. 처음부터 광고/오가닉/몸편한하루를 동시에 완성하려고 하기
7. UI부터 예쁘게 만드는 것
8. 실제 제작 속도 측정 없이 기능만 추가하기

---

# 24. 첫 번째 완료 기준

이번 1차 개발은 다음 테스트를 통과하면 성공이다.

### Input

```text
프로젝트:
몸편한하루

카테고리:
건강 운동

주제:
혈당 관리 운동

대본:
기존 GPTs에서 검수 완료된 대본
```

### Output

AdForge가 자동으로:

```text
1. Scene 분할
2. 각 Scene 검색어 생성
3. Pexels/Pixabay 검색
4. 고화질/9:16 필터
5. 적합한 Stock 다운로드
6. Stock으로 부족한 Scene 식별
7. 부족한 Scene만 Hailuo Prompt 생성
8. Hailuo 생성 결과 관리
9. TTS 생성
10. Hook 추출
11. Subtitle 생성
12. CapCut 프로젝트 구성
```

까지 처리해야 한다.

최종적으로 사람이 해야 하는 것은:

```text
최종 영상 확인
↓
수정이 필요한 경우 수정
↓
업로드
```

정도로 줄이는 것을 목표로 한다.

---

# 25. 가장 중요한 개발 철학

이번 고도화의 목적은

> **"AI 기능을 많이 넣는 것"**

이 아니다.

목적은:

> **"사람이 영상 하나를 만드는 데 필요한 클릭, 복사, 검색, 다운로드, 붙여넣기, 반복 작업을 없애는 것"**

이다.

특히 현재 가장 큰 병목인

```text
Hailuo Prompt 작성
→ GPT 검수
→ Hailuo 생성
→ 다운로드
→ CapCut 삽입
```

과

```text
무료 영상 소스 검색
→ 다운로드
→ 9:16 변환
→ CapCut 삽입
```

을 자동화하는 것을 최우선으로 한다.

### 최종 목표:

**사람 1명 + AdForge = 하루 숏폼 10편 이상 안정적으로 생산**

그리고 이후:

**사람 1명 + AdForge = 하루 30편 이상 생산 가능한 구조**

까지 확장할 수 있도록 설계한다.