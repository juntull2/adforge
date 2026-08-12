# AdForge 신규 아키텍처 개정 최종 구현 지시서

## 0. 목적

현재 `implementation_plan.md`를 기준으로 하되, 이번 문서를 **New Architecture의 최종 개정본**으로 사용한다.

현재 프로젝트에는 이미 다음 두 시스템 모드가 존재한다.

```text
Legacy Mode
New Architecture
```

이번 작업은 전체 프로젝트를 재작성하는 것이 아니다.

### 절대 원칙

```text
Legacy Mode
→ 변경하지 않는다.

New Architecture
→ 이번 문서 기준으로 개정한다.
```

첫 번째 실제 운영 대상은:

```text
Brand: 몸편한하루
Platform: Naver Clip
Domain: 건강/생활/운동/신체 불편 콘텐츠
```

이다.

최우선 해결 문제는:

1. 대본 품질
2. 대본과 영상의 맥락 불일치
3. 9:16 영상 품질 저하
4. Naver Clip용 콘텐츠 전략 부재

이다.

---

# 1. Legacy Mode 동결

Legacy Mode의 다음 기능은 변경하지 않는다.

- 현재 TTS
- 영상 합성
- Stock Download
- CapCut Draft
- 기존 UI 흐름
- 기존 동작 로직

Legacy Mode는 **회귀 테스트 대상**으로만 사용한다.

기존 파일을 정리한다는 이유로 삭제하지 않는다.

---

# 2. New Architecture 방향

기존 신규 아키텍처의 기본 구조는 유지하되, `Benchmark Intelligence`와 `BodyComfort First`를 핵심 축으로 추가한다.

최종 구조:

```text
New Architecture
│
├── Brand Profile
│   └── 몸편한하루
│
├── Product Intelligence
│
├── Benchmark Intelligence ★
│
├── Hook Strategy Engine
│
├── Script Intelligence
│
├── Scene Intelligence
│
├── Asset Intelligence
│
├── Video Production
│
├── Naver Clip Optimization
│
└── Performance Learning
```

최종 파이프라인:

```text
Product / Product URL
        ↓
Brand Context
        ↓
Product Intelligence
        ↓
Audience Intelligence
        ↓
Benchmark Intelligence
        ↓
Content Strategy
        ↓
Hook Strategy Selection
        ↓
Hook Candidates
        ↓
Script Generation
        ↓
Script Quality Gate
        ↓
Scene Planner
        ↓
Semantic Asset Matching
        ↓
Asset Quality Gate
        ↓
9:16 Quality Gate
        ↓
TTS / Caption / Video Composition
        ↓
CapCut Draft
        ↓
Naver Clip Metadata
        ↓
Performance Logging
```

---

# 3. BodyComfort First

첫 번째 Brand Profile은 `몸편한하루`로 만든다.

```json
{
  "brand_id": "bodycomfort",
  "brand_name": "몸편한하루",
  "platform": "naver_clip",
  "domain": "health_lifestyle",
  "target_profile": [],
  "tone": "쉽고 명확하며 신뢰감 있는 정보 전달",
  "benchmark_dataset": "bodycomfort_benchmark_v0.1"
}
```

확인되지 않은 브랜드 세부 정보를 임의로 생성하지 않는다.

코드 구조는 브랜드 독립적으로 유지하여 이후 Brand Profile만 교체할 수 있게 한다.

---

# 4. Benchmark Intelligence 추가

현재 확보한 벤치마크 영상을 New Architecture의 핵심 지식 소스로 사용한다.

중요:

```text
벤치마크 영상 자체를 AI 모델에 직접 학습시키는 것
≠
이번 목표
```

목표는:

```text
Benchmark Video
→ 분석
→ 반복 패턴 추출
→ Benchmark DNA
→ Script / Scene 전략에 활용
```

이다.

벤치마크는 **복제 데이터가 아니라 전략 데이터**다.

---

# 5. Benchmark Dataset v0.1

현재 확보한 벤치마크 영상들을:

```text
Benchmark Dataset v0.1
```

로 관리한다.

중복 파일은 제거한다.

현재 상태는:

```text
BENCHMARK_OBSERVED
```

이다.

다음 상태를 반드시 구분한다.

```text
BENCHMARK_OBSERVED
PERFORMANCE_VALIDATED
MODEL_INFERRED
```

현재 벤치마크에서 발견한 패턴을 Naver의 공식 알고리즘 규칙이라고 표현하지 않는다.

---

# 6. Benchmark 디렉터리

```text
benchmark/
│
├── raw/
│   └── *.mp4
│
├── analyzed/
│   └── *.json
│
├── benchmark_dna.json
└── benchmark_index.json
```

추가 모듈:

```text
models/benchmark.py
intelligence/benchmark_intelligence.py
agents/benchmark_agent.py
```

---

# 7. Benchmark Video Schema

각 영상은 최소 다음 구조로 저장한다.

```json
{
  "video_id": "benchmark_001",
  "source_type": "benchmark_clip",
  "status": "BENCHMARK_OBSERVED",
  "duration_sec": 63.4,
  "aspect_ratio": "9:16",
  "resolution": "480x854",

  "hook": {
    "text": "...",
    "duration_sec": 3.0,
    "pattern_ids": [
      "micro_commitment",
      "specific_body_problem"
    ]
  },

  "target": [],
  "topic": [],
  "body_parts": [],
  "script_structure": [],
  "visual_patterns": [],
  "caption_patterns": [],
  "cta_patterns": [],
  "scenes": []
}
```

Scene은:

```json
{
  "scene_id": "scene_01",
  "start_sec": 0.0,
  "end_sec": 3.0,
  "purpose": "hook",
  "visual_description": "...",
  "caption_text": "...",
  "subject": "...",
  "action": "...",
  "body_part": "...",
  "environment": "..."
}
```

수준으로 구조화한다.

---

# 8. Benchmark DNA

여러 벤치마크 영상에서 반복되는 패턴을 집계한다.

```json
{
  "dataset_id": "bodycomfort_benchmark_v0.1",
  "source_count": 0,
  "status": "BENCHMARK_OBSERVED",

  "hook_patterns": [],
  "target_patterns": [],
  "topic_clusters": [],
  "script_structures": [],
  "visual_patterns": [],
  "caption_patterns": [],
  "cta_patterns": []
}
```

각 패턴에는:

```text
pattern_id
name
description
observed_count
confidence
generation_policy
source_video_ids
```

를 저장한다.

`generation_policy` 예:

```text
style_only
strategy_only
safe_to_generate
requires_evidence
```

---

# 9. Benchmark에서 추출할 것

추출 대상:

- Hook 구조
- 정보 전달 순서
- 타겟 지정 방식
- 숫자/시간/횟수 사용 패턴
- 신체 부위/문제 구체화 방식
- 문제 → 해결 구조
- 시각적 증명 방식
- 자막 밀도/구성
- 장면 전환 패턴
- CTA 유형
- 시각적 구성 패턴
- 특정 연령대/상황 표현 방식

---

# 10. Benchmark에서 복제하지 않을 것

다음은 그대로 생성에 사용하지 않는다.

- 원문 대본
- 원문 제목
- 원문 CTA 문구
- 원본 영상
- 원본 자막
- 특정 창작자의 고유 표현

Benchmark는 **구조와 전략을 추출하는 용도**다.

---

# 11. Benchmark → Script

Script 생성은 다음 순서로 변경한다.

```text
Product
↓
Audience
↓
Benchmark Retrieval
↓
Relevant Benchmark Patterns
↓
Hook Strategy Selection
↓
Hook Candidates
↓
Script Generation
↓
Script Quality Gate
↓
Approved Script
```

LLM에게:

> "이 영상을 참고해서 비슷하게 써라."

라고 지시하지 않는다.

대신:

> "해당 콘텐츠 유형에서 관찰된 구조적 패턴을 활용하되, 새로운 제품/타겟/문맥으로 독자적인 콘텐츠를 생성하라."

라는 방식으로 사용한다.

---

# 12. Hook Strategy Engine

기존 8개 Hook 전략을 유지한다.

```text
LOSS_AVERSION
CURIOSITY_GAP
PATTERN_INTERRUPT
SPECIFIC_EMPATHY
AUTHORITY
SOCIAL_PROOF_FOMO
SIMPLE_LIST
EXPERIENCE_STORY
```

추가:

```text
MICRO_COMMITMENT
```

Benchmark에서 반복적으로 관찰되는:

```text
딱 5번
1분
10초
하루 한 번
```

같은 작은 실행 단위의 전략을 별도 패턴으로 지원한다.

단, 숫자를 근거 없이 만들어내지 않는다.

---

# 13. Hook 후보 경쟁

하나의 Hook만 생성하지 않는다.

```text
Product
+
Audience
+
Benchmark Patterns
↓
2~3 Hook Strategies
↓
3~5 Hook Candidates
↓
Hook Scoring
↓
Best Hook
```

평가:

```text
Hook Strength
Target Specificity
Curiosity
Product Relevance
Credibility
Factual Safety
```

---

# 14. Script Quality Gate

다음 항목을 0~100으로 평가한다.

```text
Hook Strength
Target Specificity
Clarity
Curiosity
Credibility
Emotional Relevance
Product Relevance
Pacing
CTA Strength
Factual Safety
```

그리고 hard gate:

```text
MEDICAL_CLAIM_RISK
UNSUPPORTED_EFFICACY
FAKE_TESTIMONIAL
FAKE_AUTHORITY
UNSUPPORTED_NUMERICAL_CLAIM
```

Hard gate에 걸리면 총점과 관계없이 재생성한다.

---

# 15. 건강 콘텐츠 표현 안전성

Benchmark 영상에서 강한 표현이 등장하더라도 이를 사실로 학습하지 않는다.

예:

```text
기적
병이 뚫린다
통증이 싹 사라진다
```

등은:

```text
BENCHMARK STYLE
```

로만 저장한다.

실제 몸편한하루 광고 생성에서는 제품 근거와 확인 가능한 정보 범위 안에서 표현한다.

---

# 16. Scene Intelligence 개정

현재 가장 큰 기술적 문제인:

> "대본의 맥락과 상관없는 영상이 선택되는 문제"

를 해결하기 위해 단순 keyword search를 사용하지 않는다.

다음 구조를 사용한다.

```text
Narration
↓
Scene Understanding
↓
Visual Intent
↓
Visual Requirements
↓
Search Queries
↓
Candidate Retrieval
↓
Semantic Ranking
```

---

# 17. Scene Intent Schema

```json
{
  "subject": "...",
  "age_group": "...",
  "action": "...",
  "location": "...",
  "object": "...",
  "body_part": "...",
  "symptom": "...",
  "emotion": "...",
  "context": "...",
  "visual_goal": "...",
  "avoid": []
}
```

---

# 18. Benchmark Visual Pattern → Scene Planner

Benchmark의 시각적 반복 패턴은 Scene Planner의 **보조 신호**로 사용한다.

예:

```text
middle_aged_person
+
body_part_closeup
+
exercise_demo
```

→

```json
{
  "subject": "middle_aged_person",
  "body_part": "knee",
  "action": "exercise",
  "shot": "medium",
  "purpose": "demonstration"
}
```

형태의 Visual Requirements로 변환한다.

단, Benchmark pattern이 실제 대본 의미보다 우선하지 않는다.

---

# 19. Semantic Asset Matching

각 Scene마다 3~5개의 검색 query를 만든다.

query에는 가능한 한:

```text
who
+
action
+
where
+
body part / object
+
emotion / context
+
portrait preference
```

를 포함한다.

예:

```text
older woman chair knee exercise home portrait
middle aged woman knee pain stretching at home
senior woman exercising with chair vertical
```

다음과 같은 지나치게 넓은 검색은 피한다.

```text
health woman
exercise
summer
```

---

# 20. Reject → Re-search Loop

필수 구현한다.

```text
Scene Intent
↓
Search
↓
Candidates
↓
Hard Filter
↓
Semantic Score
↓
Pass?
├─ YES → Select
└─ NO
    ↓
Query Refinement
    ↓
Second Search
    ↓
Re-score
    ↓
Pass?
├─ YES → Select
└─ NO
    ↓
Third Search / Scene Reinterpretation
    ↓
Still fail → Reject
```

권장 최대 3라운드.

무관한 영상을 억지로 사용하지 않는다.

---

# 21. Asset Quality Gate

최종 광고용 자산은 다음을 검사한다.

```text
resolution
aspect_ratio
codec
duration
corruption
blur/compression
watermark
crop feasibility
```

---

# 22. 9:16 Quality Gate

최종 목표:

```text
1080 × 1920
9:16
```

우선순위:

```text
1. Native portrait high-resolution
2. Native portrait acceptable resolution
3. High-resolution 4K landscape → safe reframe/crop
4. High-resolution landscape → safe crop
5. Reject → re-search
```

가로 영상을 무조건 확대해 세로로 만들지 않는다.

---

# 23. Crop Quality

가로 영상을 crop하는 경우:

```text
source resolution
→ crop region
→ effective crop resolution
→ target resolution
→ required upscale factor
```

를 계산한다.

필요한 확대 배율이 과도하면 Reject한다.

Smart Crop은 fallback으로만 사용한다.

AI Reframe은 구현 난이도가 과도하지 않은 경우 지원한다.

Benchmark 원본처럼 저해상도인 480×854 영상은 **최종 광고 소재로 사용하지 않는다.**

---

# 24. Naver Clip Intelligence

Benchmark 데이터는 Naver의 비공개 알고리즘을 의미하지 않는다.

사용 가능한 표현:

```text
Observed Pattern
Estimated Optimization
AdForge Recommendation
```

사용 금지:

```text
Naver Ranking Formula
Guaranteed Exposure
Official Ranking Score
```

---

# 25. Performance Learning

현재 Benchmark는:

```text
BENCHMARK_OBSERVED
```

몸편한하루의 실제 게시물 성과가 쌓이면:

```text
PERFORMANCE_VALIDATED
```

로 별도 저장한다.

예:

```json
{
  "pattern_id": "micro_commitment",
  "benchmark_occurrences": 11,
  "bodycomfort_occurrences": 8,
  "views": 18400,
  "ctr": 0.027,
  "validation_status": "PERFORMANCE_VALIDATED"
}
```

Benchmark에서 자주 보였다는 이유만으로 성공 패턴으로 승격하지 않는다.

---

# 26. Debug Mode

New Architecture에 Debug Mode를 추가한다.

다음을 확인할 수 있어야 한다.

```text
Brand Profile
Benchmark Patterns Used
Hook Strategy
Hook Candidates
Selected Hook
Script Score
Scene Intent
Search Queries
Rejected Assets
Selected Asset
Semantic Score
Quality Score
9:16 Decision
Final Optimization Score
```

특히:

```text
Rejected Assets
Re-search reason
```

은 반드시 기록한다.

---

# 27. Output Package

최종 결과:

```text
final_video.mp4
capcut_draft/
script.json
script.txt
title.txt
hashtags.txt
keywords.json
optimization_score.json
generation_report.json
benchmark_usage.json
```

`benchmark_usage.json`에는 어떤 benchmark pattern이 사용됐는지 저장한다.

---

# 28. Performance 데이터와 Benchmark 데이터 분리

반드시 다음 세 상태를 구분한다.

```text
BENCHMARK_OBSERVED
PERFORMANCE_VALIDATED
MODEL_INFERRED
```

이는 향후 AdForge가:

```text
벤치마크에서 많이 관찰된 패턴
+
몸편한하루에서 실제 성과가 난 패턴
```

을 구분하는 기반이 된다.

---

# 29. 구현 순서

한 번에 전부 구현하지 않는다.

### Step 1 — Foundation

- Brand Profile
- Benchmark schema
- directory
- config
- logging

### Step 2 — Benchmark Intelligence

- benchmark analyzer interface
- benchmark JSON
- DNA aggregator
- retrieval

### Step 3 — Script Intelligence

- 8 Hook Strategies
- MICRO_COMMITMENT
- Hook candidates
- script scoring
- safety gate

### Step 4 — Scene Intelligence

- Scene Intent
- Visual Requirements
- benchmark visual retrieval
- semantic queries
- Reject / Re-search

### Step 5 — Asset Quality

- portrait-first retrieval
- resolution gate
- crop feasibility
- 9:16 validation

### Step 6 — Production Integration

기존의 정상 작동하는:

- TTS
- Video Composition
- CapCut Draft

기능을 최대한 재사용한다.

### Step 7 — Naver Clip Optimization

- title
- hashtags
- keywords
- optimization score

### Step 8 — Performance Learning

- performance log
- pattern validation
- feedback loop

---

# 30. MVP의 성공 기준

범용 SaaS를 먼저 완성하는 것이 목표가 아니다.

첫 번째 목표:

```text
몸편한하루 제품
↓
Naver Clip 콘텐츠 전략
↓
강한 Hook
↓
품질 높은 대본
↓
맥락에 맞는 영상
↓
9:16 고화질
↓
TTS
↓
CapCut Draft
↓
제목 / 해시태그
```

가 하나의 pipeline으로 작동하는 것이다.

---

# 31. 완료 기준

다음 조건을 모두 만족해야 한다.

1. Legacy Mode가 기존과 동일하게 실행된다.
2. BodyComfort Brand Profile이 작동한다.
3. Benchmark DNA가 조회된다.
4. Benchmark pattern을 사용한 Hook 후보가 생성된다.
5. Script Quality Gate가 작동한다.
6. Scene Intent가 생성된다.
7. 무관한 stock footage가 Hard Reject된다.
8. 실패 시 재검색된다.
9. 9:16 Quality Gate가 동작한다.
10. CapCut Draft가 생성된다.
11. Naver Clip metadata가 생성된다.
12. Debug Mode에서 생성 과정을 추적할 수 있다.
13. Benchmark 원본을 그대로 복제하지 않는다.
14. Unsupported medical/efficacy claims가 차단된다.

---

# 32. Antigravity 작업 방식

코드 변경 전에 현재 repository를 분석하고:

```text
KEEP
REFACTOR
REPLACE
DEPRECATE
```

로 분류한다.

Legacy 관련 파일은 삭제하지 않는다.

New Architecture는 기존 구현 중 재사용 가능한 기능을 최대한 재사용한다.

각 단계 완료 시:

```text
Implemented
Changed Files
Tests
Test Results
Known Limitations
Next Step
```

를 보고한다.

---

# 33. 최종 지시

이 문서를 현재 `implementation_plan.md`의 **New Architecture 개정본**으로 사용한다.

다시 강조한다.

```text
Legacy Mode
→ 절대 변경하지 않는다.

New Architecture
→ BodyComfort First + Benchmark Intelligence 중심으로 개정한다.
```

현재 확보된 벤치마크 영상은 전략 패턴 추출용으로만 사용한다.

최우선 목표는:

```text
대본 품질
+
대본-영상 의미 일치
+
9:16 고화질
+
Naver Clip용 콘텐츠 전략
```

이다.

그 위에 Performance Learning을 단계적으로 추가한다.

무조건 범용화부터 하지 말고 **몸편한하루의 실제 광고 제작 성공을 첫 번째 검증 기준**으로 삼는다.