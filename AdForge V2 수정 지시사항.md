# AdForge V2 수정 지시사항
## 네이버 클립 레퍼런스 처리 방식

### 1. 네이버 클립은 자동 다운로드하지 않는다.

AdForge에서 네이버 클립을 영상 파일로 다운로드하는 기능은 구현하지 않는다.

사용자가 직접 영상을 다운로드할 수 있도록 한다.

AdForge의 역할은:

```text
네이버 클립 레퍼런스 발견
        ↓
AdForge에 링크 입력
        ↓
레퍼런스 정보 저장
        ↓
필요하면 사용자가 직접 다운로드
```

까지만 담당한다.

---

# 2. Reference URL 관리 기능

AdForge에 `Reference` 개념을 추가한다.

### Reference 데이터

```text
Reference
├── reference_id
├── project_id
├── platform
├── url
├── title
├── category
├── topic
├── memo
├── thumbnail_url (optional)
├── created_at
└── tags
```

예:

```text
플랫폼:
Naver Clip

URL:
사용자가 입력한 네이버 클립 링크

카테고리:
건강 운동

주제:
혈당 관리

메모:
식후 운동 훅 참고

태그:
혈당, 걷기, 시니어, 훅
```

---

# 3. UI

사용자가 네이버 클립에서 마음에 드는 영상을 발견하면:

```text
[+ 레퍼런스 추가]
```

버튼을 누른다.

입력:

```text
플랫폼:
Naver Clip

URL:
https://...

카테고리:
[건강 운동 ▼]

세부 주제:
혈당 관리 운동

메모:
첫 3초 훅 참고
```

저장한다.

---

# 4. Reference Library

저장된 레퍼런스를 한 화면에서 볼 수 있도록 한다.

```text
Reference Library

┌─────────────────────────────────┐
│ 몸편한하루 - 혈당 운동            │
│ Naver Clip                       │
│ https://...                      │
│                                  │
│ [클립 열기] [메모] [태그]        │
└─────────────────────────────────┘
```

### `[클립 열기]`

사용자의 브라우저에서 해당 네이버 클립 URL을 연다.

AdForge가 영상을 다운로드하거나 저장하지 않는다.

---

# 5. 레퍼런스와 콘텐츠 연결

레퍼런스는 향후 콘텐츠 제작에 연결할 수 있어야 한다.

예:

```text
Reference
   ↓
[이 레퍼런스로 콘텐츠 만들기]
   ↓
새 Content Job 생성
   ↓
주제 / 구조 / 훅 참고
```

단, 레퍼런스 영상 자체를 자동으로 복제하지 않는다.

---

# 6. 레퍼런스 분석

향후 AI 분석 기능을 추가할 수 있도록 구조만 만들어 둔다.

예:

```text
Reference Analysis

Hook:
"식후에 절대 하지 마세요"

Estimated Length:
28 sec

Structure:
Hook
↓
Problem
↓
Solution
↓
CTA

Tone:
경고형

Target:
시니어

Topic:
혈당 관리
```

이 분석 결과는 **레퍼런스의 구조와 패턴을 파악하기 위한 것**으로 사용한다.

---

# 7. 중요: 원본 영상 파일을 AdForge에 자동 저장하지 않는다.

다음 기능은 구현하지 않는다.

```text
❌ 네이버 클립 자동 다운로드
❌ 네이버 클립 영상 자동 저장
❌ 네이버 클립 영상 자동 편집 소스로 사용
❌ 네이버 클립 영상 재배포
```

대신:

```text
✅ URL 저장
✅ 제목/메모/태그 저장
✅ 링크 클릭으로 원본 확인
✅ 프로젝트와 연결
✅ 레퍼런스 분석 데이터 저장
```

으로 한다.

---

# 8. Stock Engine과 완전히 분리한다.

네이버 클립 Reference와 무료 Stock은 서로 다른 개념이다.

```text
Reference Engine
├── Naver Clip
├── YouTube
└── 기타 참고 링크

Stock Engine
├── Pexels
├── Pixabay
└── Company Asset
```

Reference는 **참고용**.

Stock은 **실제 영상 제작 소스**.

이 둘을 절대 섞지 않는다.

---

# 9. 최종 제작 흐름

최종적으로 다음 구조를 목표로 한다.

```text
[1] 네이버 클립에서 레퍼런스 발견
              ↓
[2] AdForge에 링크 저장
              ↓
[3] 카테고리 / 주제 / 메모 입력
              ↓
[4] 기존 GPTs로 대본 생성/검수
              ↓
[5] 검수된 대본 AdForge 입력
              ↓
[6] Scene Planner
              ↓
       ┌──────┴──────┐
       ↓             ↓
   Free Stock      Hailuo
       ↓             ↓
       └──────┬──────┘
              ↓
          FFmpeg
              ↓
       TTS + Subtitle
              ↓
         Hook Effect
              ↓
         Preview
              ↓
       최종 사람 검수
              ↓
           Export
```

---

# 10. 개발 우선순위 수정

이번 버전에서는 다음 순서로 개발한다.

### Phase 1

```text
Project 구조
+
Reference Library
+
Naver Clip URL 저장
```

### Phase 2

```text
Script
→
Scene Planner
```

### Phase 3

```text
Pexels
+
Pixabay
+
Stock Search
+
Cache
```

### Phase 4

```text
9:16
+
FFmpeg
+
Smart Crop
```

### Phase 5

```text
Stock vs Hailuo
```

### Phase 6

```text
Hailuo Prompt
```

### Phase 7

```text
TTS
+
Subtitle
+
Hook
```

### Phase 8

```text
Preview
+
Export
```

### Phase 9

```text
Batch Production
+
Dashboard
```

---

# 최종 원칙

AdForge는 네이버 클립을 **다운로드하는 도구가 아니라 레퍼런스를 관리하는 도구**로 만든다.

사용자가 직접 다운로드한 파일이 필요한 경우에는 사용자가 직접 다운로드해서 AdForge의 `Local Asset Library`에 추가할 수 있도록 한다.

```text
Naver Clip
   ↓
링크만 저장
   ↓
사람이 필요하면 직접 다운로드
   ↓
Local Asset Library에 직접 추가
```

이 구조로 구현한다.