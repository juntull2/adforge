# AdForge v2 구현 지시서
## AI Creative OS for Naver Clip Advertising

당신은 현재 `juntull2/adforge` 저장소를 기반으로 **AdForge v2**를 구현해야 한다.

이 작업의 목표는 기존의 "대본 → TTS → 스톡 영상 → CapCut Draft" 자동화 기능을 버리는 것이 아니다.

**현재 정상적으로 작동하는 기능은 최대한 보존하면서**, 다음 4가지 핵심 문제를 해결하고 제품을 다음 단계로 발전시킨다.

1. 대본 품질이 낮고 Hook/전개/CTA가 약함
2. 대본의 의미와 맥락을 제대로 이해하지 못한 채 부적절한 스톡 영상을 선택함
3. 16:9 등 가로 영상이 선택되어 9:16 변환 과정에서 화질이 크게 저하됨
4. Naver Clip용 광고라는 목적에 맞는 제목/키워드/해시태그/콘텐츠 전략이 없음

최종 목표는 단순한 영상 생성기가 아니라:

> **"상품과 대본의 맥락을 이해하고, Naver Clip에 적합한 광고 크리에이티브를 전략적으로 생성하는 AI Creative OS"**

를 만드는 것이다.

---

# 0. 최우선 원칙

## 절대로 현재 작동하는 기능을 무작정 삭제하거나 전면 재작성하지 마라.

먼저 현재 프로젝트를 분석하고 다음을 수행한다.

### 분석 대상

- `README.md`
- `app.py`
- `main.py`
- `auto_script_to_draft.py`
- `auto_stock_downloader.py`
- `auto_tts_script_to_draft.py`
- `stock_downloader.py`
- `clip_reference_scraper.py`
- `naver_clip_adforge.py`
- `parse_sheet_keywords.py`
- `requirements.txt`
- 현재 테스트 코드
- 현재 생성되는 영상 및 CapCut Draft 출력 구조

현재 구현되어 있는 기능 중 실제로 잘 작동하는 부분은 그대로 유지하고, 필요한 부분만 추상화/교체한다.

먼저 현재 데이터 흐름을 문서화한다.

```text
현재 입력
→ 현재 대본 처리
→ 현재 키워드 추출
→ 현재 영상 검색
→ 현재 영상 다운로드
→ 현재 TTS
→ 현재 영상 합성
→ 현재 CapCut Draft
```

이 흐름을 먼저 파악한 후 아래 v2 구조로 점진적으로 개선한다.

---

# 1. AdForge v2 전체 아키텍처

다음 계층 구조로 재설계한다.

```text
AdForge
│
├── Input Layer
│   ├── Product URL
│   ├── Product Information
│   └── User Script(optional)
│
├── Intelligence Layer
│   ├── Product Analyzer
│   ├── Audience Analyzer
│   ├── Content Goal Analyzer
│   ├── Hook Strategy Engine
│   ├── Naver Clip Intelligence
│   └── Keyword Intelligence
│
├── Script Layer
│   ├── Hook Generator
│   ├── Body Generator
│   ├── Curiosity Engine
│   ├── Proof Generator
│   ├── CTA Generator
│   └── Script Quality Evaluator
│
├── Visual Intelligence Layer
│   ├── Scene Planner
│   ├── Semantic Scene Matcher
│   ├── Stock Search Query Generator
│   ├── Asset Quality Filter
│   ├── Aspect Ratio Filter
│   └── Smart Reframe
│
├── Production Layer
│   ├── TTS
│   ├── Caption
│   ├── Video Composition
│   ├── 9:16 Rendering
│   └── CapCut Draft Export
│
├── Optimization Layer
│   ├── Naver Clip SEO
│   ├── Title Generator
│   ├── Hashtag Generator
│   ├── Information Tag Recommendation
│   └── Creative Score
│
└── Learning Layer
    ├── Performance Data
    ├── Creative Memory
    └── Winning Pattern Detection
```

---

# 2. 폴더 구조 리팩터링

현재 파일을 무작정 하나의 폴더에 계속 추가하지 말고 아래와 같은 구조로 점진적으로 이동한다.

```text
adforge/
│
├── app.py
├── main.py
├── requirements.txt
├── .env.example
│
├── core/
│   ├── config.py
│   ├── logging.py
│   └── schemas.py
│
├── agents/
│   ├── product_agent.py
│   ├── audience_agent.py
│   ├── hook_agent.py
│   ├── script_agent.py
│   ├── scene_agent.py
│   ├── clip_seo_agent.py
│   └── quality_agent.py
│
├── services/
│   ├── script_service.py
│   ├── tts_service.py
│   ├── stock_service.py
│   ├── video_service.py
│   ├── capcut_service.py
│   ├── naver_clip_service.py
│   └── keyword_service.py
│
├── intelligence/
│   ├── hook_engine.py
│   ├── semantic_matcher.py
│   ├── asset_quality.py
│   ├── keyword_intelligence.py
│   └── clip_intelligence.py
│
├── pipelines/
│   ├── script_pipeline.py
│   ├── asset_pipeline.py
│   ├── video_pipeline.py
│   └── full_pipeline.py
│
├── prompts/
│   ├── hooks/
│   ├── scripts/
│   ├── scenes/
│   ├── clip/
│   └── quality/
│
├── models/
│   ├── product.py
│   ├── script.py
│   ├── scene.py
│   ├── asset.py
│   └── clip.py
│
├── tests/
│
└── stock_videos/
```

기존 파일은 기능이 안정화되기 전까지 삭제하지 말고 compatibility layer 또는 wrapper를 만들어 점진적으로 이전한다.

---

# 3. 핵심 기능 1: Script Intelligence Engine

가장 먼저 구현해야 한다.

현재 대본 생성 시스템을 단순한 "AI에게 광고 대본을 써달라" 수준에서 벗어나게 한다.

대본 생성 전에 다음을 결정한다.

```text
Product
+
Target Audience
+
Content Goal
+
Platform
+
Hook Strategy
+
Tone
+
Duration
```

---

# 4. Hook Strategy Library

다음 8가지 전략을 시스템에 명시적으로 등록한다.

## HOOK_01_LOSS_AVERSION

손실회피 전략.

예:

```text
"이걸 몰라서 당신은 돈을 잃고 있을지도 모릅니다."
```

규칙:

- 얻는 것보다 잃는 것을 강조
- 금전적 손실뿐 아니라 시간/기회/불편함 손실도 가능
- 과장 또는 허위 손실 금지

---

## HOOK_02_CURIOSITY_GAP

정보 일부를 의도적으로 남겨 궁금증을 만든다.

예:

```text
"이 방법에는 3가지가 있는데, 대부분은 마지막 한 가지를 모릅니다."
```

규칙:

- 처음부터 모든 정보를 공개하지 않는다.
- 반드시 후속 정보에 대한 이유를 만든다.
- 낚시성 제목 금지

---

## HOOK_03_PATTERN_INTERRUPT

상식/기대와 반대되는 관점을 제시한다.

예:

```text
"비싸야 좋은 제품이라는 생각, 꼭 맞는 건 아닙니다."
```

규칙:

- 독자의 기존 예상과 다른 방향을 제시
- 이후 본문에서 논리적으로 설명
- 근거 없이 "당신이 알고 있는 건 틀렸다"라고 단정하지 않는다.

---

## HOOK_04_SPECIFIC_EMPATHY

명확한 타겟과 실제 상황을 지정한다.

예:

```text
"아침마다 아이 깨우는 것부터 전쟁인 초등학생 부모님이라면..."
```

규칙:

- 구체적인 인물
- 구체적인 상황
- 실제 생활에서 발생할 법한 문제
- "모두에게 해당되는 이야기"보다 "내 이야기"처럼 느끼게 한다.

---

## HOOK_05_AUTHORITY

신뢰 가능한 전문성/경험을 이용한다.

예:

```text
"10년차 마케터들이 가장 먼저 보는 부분입니다."
```

규칙:

- 실제 확인 가능한 근거만 사용
- 존재하지 않는 경력/기관/자격증 생성 금지
- 제품 자체의 신뢰 근거도 활용 가능

---

## HOOK_06_SOCIAL_PROOF_FOMO

"나만 모르고 있다"는 심리를 활용한다.

예:

```text
"이미 많은 사람들이 사용하고 있는데 아직 모르셨나요?"
```

규칙:

- 검증되지 않은 숫자 생성 금지
- 실제 리뷰/판매량/사용자 데이터가 있으면 활용
- 허위 사회적 증거 금지

---

## HOOK_07_SIMPLE_LIST

복잡한 정보를 간단한 숫자 구조로 제공한다.

예:

```text
"이 제품의 장점은 딱 3가지만 보면 됩니다."
```

규칙:

- 3~5개 핵심 포인트
- 문장 짧게
- 정보량을 과도하게 늘리지 않는다.

---

## HOOK_08_EXPERIENCE_STORY

개인의 경험과 변화 중심.

예:

```text
"저도 처음에는 별 차이 없다고 생각했는데, 직접 써보고 생각이 바뀌었습니다."
```

규칙:

- 실제 제공된 경험만 사용
- 허구의 후기 생성 금지
- Before → Discovery → After 구조 활용

---

# 5. Hook 전략 자동 선택

대본을 생성할 때 항상 8개 중 하나 이상을 선택한다.

예:

```json
{
  "primary_hook": "HOOK_01_LOSS_AVERSION",
  "secondary_hook": "HOOK_07_SIMPLE_LIST",
  "reason": "가격 대비 효용을 강조하는 상품이며 구매 전 손실 회피가 적합"
}
```

모델에게 무작정 대본을 생성시키지 말고:

```text
STEP 1
상품 분석

STEP 2
타겟 분석

STEP 3
콘텐츠 목적 분석

STEP 4
Hook 전략 선택

STEP 5
Hook 생성

STEP 6
Body 생성

STEP 7
CTA 생성

STEP 8
품질 평가

STEP 9
문제 있으면 재생성
```

순서로 처리한다.

---

# 6. Script Quality Evaluator

생성된 대본을 그대로 사용하지 않는다.

다음 항목을 각각 0~100점으로 평가한다.

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

총점도 계산한다.

예:

```json
{
  "score": 86,
  "hook": 91,
  "target": 88,
  "clarity": 90,
  "curiosity": 82,
  "credibility": 79,
  "product_relevance": 94,
  "cta": 77
}
```

총점이 기준 이하라면 자동 재작성한다.

권장 기준:

```text
< 75 → regenerate
75~84 → improve
85+ → approve
```

---

# 7. Script 출력 포맷

최종 대본을 단순 문자열 하나로 저장하지 말고 구조화한다.

예:

```json
{
  "title": "...",
  "hook_strategy": "HOOK_01_LOSS_AVERSION",
  "hook": "...",
  "body": [
    {
      "id": "scene_01",
      "narration": "...",
      "purpose": "...",
      "emotion": "...",
      "visual_intent": "...",
      "search_intent": "..."
    }
  ],
  "cta": "...",
  "duration_target": 25,
  "score": 89
}
```

이 구조가 이후 **영상 검색 문제를 해결하는 핵심**이다.

---

# 8. 핵심 기능 2: Semantic Scene Planner

현재 가장 심각한 문제 중 하나는:

> 대본 내용과 관계없는 스톡 영상을 가져오는 것

이다.

이를 단순 keyword matching으로 해결하지 않는다.

현재:

```text
대본 문장
→ keyword 추출
→ stock search
```

방식을 폐기하고 다음 구조를 사용한다.

```text
Narration
↓
Scene Understanding
↓
Visual Intent
↓
Search Query
↓
Candidate Assets
↓
Semantic Scoring
↓
Best Asset
```

---

# 9. Scene Understanding Schema

각 문장을 다음 구조로 변환한다.

```json
{
  "subject": "...",
  "action": "...",
  "location": "...",
  "object": "...",
  "emotion": "...",
  "context": "...",
  "visual_goal": "...",
  "avoid": [
    "..."
  ]
}
```

예:

```text
대본:
"출근길 지하철에서 더위 때문에 땀을 흘리는 직장인이라면 이 제품을 보세요."
```

결과:

```json
{
  "subject": "office worker",
  "action": "commuting",
  "location": "subway",
  "object": "handheld fan",
  "emotion": "hot/uncomfortable",
  "context": "summer commute",
  "visual_goal": "show office worker suffering from heat during commute",
  "avoid": [
    "beach",
    "vacation",
    "generic summer landscape"
  ]
}
```

---

# 10. Search Query Generator

Visual Intent를 기반으로 검색어를 생성한다.

단순 키워드 한 개가 아니라 최대 5개 후보를 만든다.

예:

```text
portrait office worker commuting subway summer
vertical office worker hot subway
portrait person using handheld fan subway
office worker sweating commute
vertical summer commute portable fan
```

영어 검색을 지원하는 스톡 API에서는 영어 중심으로 생성한다.

검색어는 반드시 다음 정보를 포함하도록 한다.

```text
who
+
doing what
+
where
+
emotion
+
important object
+
vertical/portrait preference
```

---

# 11. Candidate Asset Ranking

검색된 영상은 모두 사용하지 않는다.

다음 점수로 평가한다.

```text
Semantic Relevance       40%
Action Match             20%
Object Match             15%
Emotion Match            10%
Context Match             10%
Video Quality             5%
```

단, 영상 품질이 심각하게 낮으면 relevance가 높더라도 탈락시킨다.

---

# 12. Semantic Matching 방법

사용 가능한 경우 embedding 기반 유사도 평가를 구현한다.

권장:

- CLIP 계열
- sentence embedding
- multimodal embedding
- 또는 현재 사용 중인 API에서 제공하는 semantic search

구현 난이도와 비용을 고려하여 단계적으로 구현한다.

MVP에서는:

```text
LLM Scene Analysis
+
keyword matching
+
metadata matching
```

으로 시작해도 된다.

그 다음 embedding 기반 scoring을 추가한다.

---

# 13. "이상한 영상" 방지 시스템

각 Scene에 `avoid` 조건을 만든다.

예:

```text
대본:
"목이 뻐근한 직장인을 위한 마사지기"

허용:
office worker
neck pain
desk
massage
neck massage

금지:
beach
gym
running
healthy lifestyle
vacation
food
landscape
```

검색 결과가 금지 의미와 강하게 일치하면 점수를 크게 감점한다.

---

# 14. 핵심 기능 3: 9:16 High Quality Asset Pipeline

중요:

**가로 영상을 억지로 9:16으로 확대하는 것을 기본 전략으로 사용하지 마라.**

최우선순위:

```text
1. Native 9:16 high-resolution
2. Native portrait high-resolution
3. 4K landscape → intelligent reframe
4. High-resolution landscape → smart crop
5. Low-resolution asset → reject
```

---

# 15. Asset Quality Gate

최종 영상으로 들어가기 전에 다음 조건을 검증한다.

```text
minimum width
minimum height
aspect ratio
resolution
duration
codec
corruption
frame readability
```

기본 정책:

```text
1080p 미만 → 가능하면 reject
720p 이하 → 기본 reject
세로 원본 우선
4K 원본 우선
```

단, API가 실제 제공 가능한 해상도를 먼저 확인하고 현실적인 threshold를 적용한다.

---

# 16. 9:16 처리 방식

## 절대 금지

```text
16:9 1080p
→ 무조건 확대
→ 9:16
```

이렇게 처리하지 않는다.

## 권장

```text
Search
→ portrait 우선
→ high-res 우선
→ quality filter
→ semantic matching
→ selected asset
```

가장 먼저 좋은 원본을 가져온다.

---

# 17. Smart Crop은 마지막 수단

Smart Crop이 필요한 경우:

```text
원본이 고해상도이고
중요 객체가 중앙/한쪽에 존재하고
세로 crop이 충분히 가능한 경우
```

에만 사용한다.

Smart Crop을 적용하기 전에:

```text
face detection
object detection
saliency detection
```

등으로 crop 영역을 결정한다.

---

# 18. AI Reframe

움직이는 인물/제품이 있는 경우에는 static crop보다 AI Reframe을 우선 고려한다.

예:

```text
사람이 화면 왼쪽
→ 이동
→ 중앙
→ 오른쪽
```

이면

```text
9:16 viewport가 인물을 따라 움직인다.
```

기능을 넣는다.

단, 품질보다 구현 복잡도가 지나치게 커지면 v2.1로 분리한다.

---

# 19. 핵심 기능 4: Naver Clip Intelligence

Naver Clip용 광고가 주요 목적이므로 플랫폼 분석 모듈을 만든다.

중요:

**네이버의 비공개 알고리즘을 안다고 주장하지 않는다.**

공개 데이터와 실측 데이터를 이용해 "최적화 점수"를 만든다.

---

# 20. Naver Clip 분석 대상

가능한 공개 데이터와 사용자가 제공하는 성과 데이터를 수집/저장한다.

예:

```text
title
description
hashtags
information tags
category
upload time
views
likes
comments
engagement rate
traffic source
```

사용자 계정에서 제공되는 실제 성과 데이터가 있다면:

```text
impressions
clicks
CTR
views
traffic source
audience age
audience gender
```

등을 저장할 수 있도록 데이터 모델을 설계한다.

---

# 21. Keyword Intelligence

상품을 기준으로 다음 키워드를 만든다.

```text
Primary Keyword
Secondary Keyword
Long-tail Keyword
Problem Keyword
Solution Keyword
Intent Keyword
Commercial Keyword
```

예:

```text
제품: 휴대용 선풍기

Primary:
휴대용 선풍기

Secondary:
손선풍기
미니 선풍기
무선 선풍기

Long-tail:
출퇴근 휴대용 선풍기
여름 손선풍기 추천
```

---

# 22. Keyword Recommendation Score

각 키워드에 다음 지표를 저장한다.

```text
Relevance
Search Demand
Competition
Commercial Intent
Content Fit
```

실제 검색량 데이터를 사용할 수 없는 경우 "검색량이 높다"라고 허위 표시하지 않는다.

그 경우:

```text
Estimated Demand
Observed Competition
Content Relevance
```

로 구분한다.

---

# 23. Naver Clip Title Generator

제목은 단순히 상품명을 넣지 않는다.

다음 전략을 테스트한다.

```text
Problem-first
Benefit-first
Curiosity
List
Comparison
Audience-specific
Experience
Loss-aversion
```

예:

```text
"출근길 땀 때문에 미치겠다면 이거 보세요"

"손선풍기 아무거나 사면 안 되는 이유"

"여름 출퇴근 필수템 3가지"
```

단, 제품과 무관한 낚시성 제목은 금지한다.

---

# 24. Hashtag Generator

다음 범주를 나눠서 생성한다.

```text
Core hashtag
Product hashtag
Problem hashtag
Audience hashtag
Context hashtag
Trend candidate
```

예:

```text
#휴대용선풍기
#손선풍기
#여름필수템
#출퇴근템
#직장인추천
```

해시태그가 실제 검색 노출을 보장한다고 표현하지 않는다.

---

# 25. Clip Optimization Score

최종적으로 다음을 표시한다.

```text
Hook Score
Title Score
Keyword Relevance
Hashtag Relevance
Audience Fit
Product Relevance
Visual Quality
CTA Score
```

예:

```text
Naver Clip Optimization Score
87 / 100
```

그리고 반드시 개선 이유를 제공한다.

예:

```text
- Hook: 91
- Title: 82
- Keyword: 94
- Hashtag: 76
- Audience: 91
- Visual: 88
- CTA: 83

Improvement:
해시태그가 제품 중심으로 편중되어 있습니다.
타겟/상황형 태그를 1~2개 추가하세요.
```

---

# 26. 전체 Pipeline

최종적으로 다음 파이프라인을 구현한다.

```text
[PRODUCT URL]
      ↓
Product Analyzer
      ↓
Audience Analyzer
      ↓
Naver Keyword Intelligence
      ↓
Hook Strategy Engine
      ↓
Script Generator
      ↓
Script Quality Evaluator
      ↓
Scene Planner
      ↓
Semantic Scene Matching
      ↓
Asset Quality Filter
      ↓
9:16 Asset Selection
      ↓
TTS
      ↓
Video Composition
      ↓
Caption
      ↓
Quality Check
      ↓
CapCut Draft
      ↓
Naver Clip Optimization
      ↓
Final Package
```

---

# 27. Final Output

최종 결과는 영상 파일 하나만 반환하지 않는다.

다음 패키지를 반환한다.

```text
AdForge Result
│
├── final_video.mp4
├── capcut_draft/
├── script.json
├── script.txt
├── title.txt
├── hashtags.txt
├── keywords.json
├── optimization_score.json
└── generation_report.json
```

---

# 28. Generation Report

`generation_report.json` 예:

```json
{
  "product": "...",
  "platform": "naver_clip",
  "duration": 27,
  "aspect_ratio": "9:16",
  "resolution": "1080x1920",
  "hook_strategy": "HOOK_01_LOSS_AVERSION",
  "script_score": 89,
  "visual_score": 91,
  "clip_optimization_score": 87,
  "scenes": [
    {
      "scene_id": "scene_01",
      "narration": "...",
      "search_queries": [
        "..."
      ],
      "selected_asset": "...",
      "semantic_score": 93,
      "quality_score": 96
    }
  ]
}
```

이렇게 하면 결과를 디버깅할 수 있다.

---

# 29. 디버깅 기능

현재 문제는 영상이 왜 잘못 선택됐는지 파악하기 어렵다는 것이다.

따라서 각 장면마다 다음을 저장한다.

```text
Narration
Scene Intent
Generated Search Queries
Fetched Candidates
Rejected Candidates
Rejection Reasons
Selected Asset
Semantic Score
Quality Score
```

예:

```text
scene_03

Narration:
"출근길 땀이 너무 많이 난다면"

Query:
"office worker sweating subway summer"

Candidate A:
semantic 92
quality 70
→ rejected: quality too low

Candidate B:
semantic 88
quality 95
→ selected
```

이 정보를 UI에서도 debug mode로 확인할 수 있도록 한다.

---

# 30. 중요한 개발 원칙

## 원칙 1

영상이 없으면 억지로 무관한 영상을 사용하지 않는다.

대신:

```text
Query refinement
→ second search
→ third search
```

를 수행한다.

---

## 원칙 2

영상의 의미보다 해상도를 먼저 희생하지 않는다.

품질 낮은 영상보다 조금 단순한 영상이 낫다.

---

## 원칙 3

대본에 존재하지 않는 사실을 광고에 추가하지 않는다.

---

## 원칙 4

실제 리뷰/판매량/전문 경력을 확인하지 않고 만들어내지 않는다.

---

## 원칙 5

Naver Clip 알고리즘을 역설계했다고 표현하지 않는다.

모델은:

> "Observed pattern"

> "Estimated optimization"

형태로만 표현한다.

---

# 31. 현재 레포 기준 구현 전략

현재 다음 파일을 우선 분석하고 기능을 추출한다.

```text
app.py
main.py
auto_script_to_draft.py
auto_stock_downloader.py
auto_tts_script_to_draft.py
stock_downloader.py
clip_reference_scraper.py
naver_clip_adforge.py
parse_sheet_keywords.py
```

각 파일에서 다음을 판단한다.

```text
KEEP
REFACTOR
REPLACE
DEPRECATE
```

단, 기존 기능이 정상작동한다면 먼저 service layer로 감싼다.

---

# 32. 현재 코드와의 호환성

다음 기존 기능은 가능하면 그대로 유지한다.

```text
TTS
Stock download
Keyword parsing
CapCut Draft generation
Video generation
Naver Clip reference scraping
```

새로운 v2 pipeline이 안정화될 때까지 legacy pipeline을 제거하지 않는다.

실행 옵션:

```text
--mode legacy
--mode v2
```

또는 UI에서:

```text
Legacy
AdForge v2
```

로 선택할 수 있게 한다.

---

# 33. 테스트 우선

다음 테스트를 만든다.

## Script tests

- Hook strategy 선택
- target specificity
- hallucination detection
- CTA
- script score

## Scene tests

- narration → scene intent
- intent → query
- candidate ranking
- irrelevant asset rejection

## Asset tests

- 9:16 detection
- resolution detection
- low-quality rejection
- crop eligibility

## Pipeline test

전체:

```text
URL
→ Script
→ Scene
→ Asset
→ TTS
→ Video
→ Output
```

을 자동 테스트할 수 있게 한다.

---

# 34. Performance

영상 처리는 시간이 오래 걸리므로 모든 작업을 동기식으로 만들지 않는다.

가능하면:

```text
Pipeline Job
Job ID
Step Status
Progress
Error
```

형태를 사용한다.

예:

```json
{
  "job_id": "abc123",
  "status": "processing",
  "step": "semantic_matching",
  "progress": 67
}
```

---

# 35. 비용 관리

LLM 호출을 불필요하게 반복하지 않는다.

Cache 대상:

```text
Product analysis
Keyword analysis
Scene analysis
Search result
Asset metadata
```

같은 입력의 반복 호출을 줄인다.

---

# 36. 환경변수

API Key와 로컬 경로를 코드에 하드코딩하지 않는다.

`.env` 사용.

예:

```env
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
PEXELS_API_KEY=
PIXABAY_API_KEY=
```

실제 프로젝트에서 사용하는 provider에 맞춰 조정한다.

---

# 37. 구현 순서

무작정 모든 기능을 동시에 구현하지 않는다.

반드시 다음 순서로 진행한다.

## Phase 1

현재 코드 분석 및 리팩터링

```text
schemas
config
services
pipeline
logging
```

---

## Phase 2

Script Intelligence

```text
Hook Strategy Library
Script Generator
Quality Evaluator
```

---

## Phase 3

Semantic Scene Matching

```text
Scene Planner
Query Generator
Candidate Ranking
Irrelevance Filter
```

---

## Phase 4

9:16 Quality Pipeline

```text
Portrait-first retrieval
Resolution filter
Aspect ratio filter
Smart crop
```

---

## Phase 5

Naver Clip Intelligence

```text
Keyword
Title
Hashtag
Optimization Score
```

---

## Phase 6

Full Pipeline Integration

```text
URL
→ script
→ scene
→ video
→ capcut
→ optimization
```

---

# 38. 완료 기준

이 작업의 완료 기준은 "코드가 추가되었다"가 아니다.

다음 테스트 케이스를 통과해야 한다.

## Test Case A

상품:

```text
휴대용 선풍기
```

대본:

```text
출근길마다 땀이 너무 많이 난다면 이 제품을 한번 보세요.
```

기대:

- 직장인/출퇴근/더위 맥락의 영상
- 가급적 9:16
- 1080p 이상
- 무관한 해변/휴양지 영상 사용 금지

---

## Test Case B

상품:

```text
목 마사지기
```

대본:

```text
하루 종일 컴퓨터 앞에 앉아있는 직장인이라면 목이 뻐근한 이유가 있습니다.
```

기대:

- office worker
- desk/computer
- neck pain/stiffness
- massage/neck-related visual

이 나와야 한다.

---

## Test Case C

원본 영상이 모두 가로이고 저해상도라면:

```text
억지로 확대하지 말고
→ 다른 검색어 재생성
→ 다른 영상 재탐색
```

해야 한다.

---

# 39. 가장 중요한 제품 철학

AdForge는:

```text
"AI가 영상을 만들어준다"
```

에서 끝나면 안 된다.

다음 단계로 가야 한다.

```text
"AI가 왜 이 영상을 선택했는지 설명할 수 있고,
왜 이 대본을 만들었는지 설명할 수 있으며,
Naver Clip에서 더 나은 결과를 얻기 위한 다음 행동까지 제안한다."
```

즉:

> **Generation → Evaluation → Optimization → Learning**

의 순환 구조를 만들어라.

---

# 40. 작업 방식

구현 전에 먼저 현재 프로젝트를 분석한다.

분석 결과를 다음 형식으로 먼저 정리한다.

```text
1. Current Architecture
2. Existing Working Features
3. Critical Problems
4. Files to Keep
5. Files to Refactor
6. Files to Replace
7. Proposed v2 Architecture
8. Implementation Order
```

그 다음 실제 코드를 수정한다.

각 Phase가 끝날 때마다 기존 기능이 계속 정상적으로 작동하는지 확인한다.

**가장 중요한 것은 기존에 잘 되는 영상 생성 기능을 깨뜨리지 않으면서, 그 위에 Intelligence Layer를 추가하는 것이다.**

최종적으로 사용자는:

```text
상품 URL
```

하나만 입력해도

```text
상품 분석
→ 타겟 분석
→ Naver Clip 키워드 분석
→ Hook 전략 선택
→ 고품질 대본 생성
→ 장면별 의미 분석
→ 맥락에 맞는 9:16 고화질 영상 선택
→ TTS
→ 영상 제작
→ CapCut Draft
→ 제목
→ 해시태그
→ Naver Clip Optimization Score
```

까지 한 번의 pipeline으로 수행할 수 있어야 한다.

이것을 **AdForge v2의 핵심 목표**로 삼아 구현하라.