# AdForge v2 Revision & Implementation Instructions

## Purpose

This document is a **revision instruction document for Antigravity**.

It is based on the existing `implementation_plan.md` and is intended to be applied to the current `juntull2/adforge` repository without destroying the currently working legacy video-generation pipeline.

The implementation plan already identifies four core problems:

1. Script quality is inconsistent → Hook Strategy Library + Script Quality Evaluator
2. Stock footage is often semantically wrong → Semantic Scene Planner + semantic matching
3. Landscape-to-portrait conversion degrades quality → Portrait-first 9:16 Asset Pipeline
4. Naver Clip strategy is missing → Keyword/Title/Hashtag Intelligence + Optimization Score

The existing plan also intentionally preserves the current legacy pipeline and adds an `AdForge v2` mode rather than replacing the existing application in one pass.

This revision keeps that strategy, but tightens the implementation rules in the areas most likely to fail in production.

---

# 1. Non-Negotiable Product Goal

AdForge v2 is not just a video generator.

The product goal is:

> **Given a product and a content objective, generate a high-quality short-form advertisement whose script, visual scenes, aspect ratio, asset quality, and Naver Clip metadata are all intentionally optimized together.**

The system should move from:

```text
Generation
```

to:

```text
Generation → Evaluation → Optimization → Learning
```

Do not add AI agents merely for architectural appearance. Each agent must have a clear input, output schema, evaluation rule, and failure/retry behavior.

---

# 2. Preserve the Existing Working Pipeline

The current implementation has important working components, including:

- `app.py` — Streamlit UI / overall orchestration
- `naver_clip_adforge.py` — existing script, TTS, stock search, CapCut-related logic
- `auto_stock_downloader.py` — Mixkit/Pexels/Pixabay stock download
- `auto_script_to_draft.py` — script-to-CapCut draft conversion
- `auto_tts_script_to_draft.py` — TTS + subtitle synchronization + CapCut draft
- `main.py` — existing entry/test point
- `stock_downloader.py`
- `clip_reference_scraper.py`
- `performance_logger.py`

These are identified in the existing plan as KEEP/REFACTOR candidates.

## Rules

- Do not delete the legacy pipeline during v2 development.
- Do not rewrite working video composition code unless required.
- Introduce v2 through new modules and adapters.
- Keep `Legacy` and `AdForge v2` execution paths independently runnable.
- Every phase must leave the legacy path runnable.
- New modules must be testable without the Streamlit UI.

Preferred compatibility approach:

```text
Legacy
└── existing functions

v2
└── services / agents / intelligence / pipelines
      └── adapters around proven legacy functionality where appropriate
```

---

# 3. Revised Architecture

Use the current plan as the foundation, but implement the following concrete architecture.

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
│   ├── script_agent.py
│   ├── scene_agent.py
│   ├── quality_agent.py
│   └── clip_seo_agent.py
│
├── intelligence/
│   ├── hook_engine.py
│   ├── semantic_matcher.py
│   ├── asset_quality.py
│   ├── keyword_intelligence.py
│   └── clip_intelligence.py
│
├── services/
│   ├── product_service.py
│   ├── script_service.py
│   ├── stock_service.py
│   ├── tts_service.py
│   ├── video_service.py
│   ├── capcut_service.py
│   ├── keyword_service.py
│   └── naver_clip_service.py
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
└── tests/
```

Do not force a large framework migration if the existing project does not need it. The goal is separation of concerns, not architecture theater.

---

# 4. Phase Order: Revised Priority

The original plan proposes six phases. Use the same six phases, but prioritize actual user pain in this order:

```text
Phase 1 → Foundation
Phase 2 → Script Intelligence
Phase 3 → Semantic Scene Matching
Phase 4 → 9:16 / Asset Quality
Phase 5 → Naver Clip Intelligence
Phase 6 → Full Integration / UX
```

## Critical milestone

Do not move to Phase 5 simply because Phase 4 code exists.

Phase 1–4 must first pass the real-world video test cases and produce visibly better results than the legacy pipeline.

A phase is complete only when its verification criteria pass.

---

# 5. Phase 1 — Foundation / Refactor

Create the new foundation without breaking legacy behavior.

## 5.1 `core/config.py`

Centralize:

- API keys
- model/provider selection
- paths
- stock provider settings
- quality thresholds
- render settings
- retry limits
- cache settings

Move hard-coded local paths and secrets out of source files.

Use `.env` and `.env.example`.

---

## 5.2 `core/schemas.py`

Use Pydantic models for all important v2 objects.

At minimum:

```text
ProductInfo
AudienceProfile
HookCandidate
ScriptResult
ScriptScore
SceneIntent
SearchQuery
AssetCandidate
AssetScore
VideoPlan
ClipOptimizationResult
GenerationReport
```

Do not pass unstructured dictionaries everywhere once the object crosses a module boundary.

---

## 5.3 Structured Logging

Every v2 job should expose:

- job_id
- pipeline_step
- timestamp
- status
- retry count
- error message
- relevant score

This is required for debugging why a bad asset was selected.

---

# 6. Phase 2 — Script Intelligence Engine

This phase is not merely “better prompting.”

The system must generate multiple strategic options, evaluate them, and select the best one.

---

# 7. Hook Strategy Library

Implement these eight strategies explicitly:

1. `LOSS_AVERSION`
2. `CURIOSITY_GAP`
3. `PATTERN_INTERRUPT`
4. `SPECIFIC_EMPATHY`
5. `AUTHORITY`
6. `SOCIAL_PROOF_FOMO`
7. `SIMPLE_LIST`
8. `EXPERIENCE_STORY`

Store each strategy as structured configuration/prompt data rather than embedding the entire strategy in one giant prompt.

Each strategy must define:

```text
strategy_id
name
psychological_mechanism
best_for
avoid_when
required_evidence
example_patterns
risk_flags
```

---

# 8. Hook Selection Must Precede Full Script Generation

Do NOT generate one complete script and then evaluate its hook.

Use a candidate approach:

```text
Product analysis
      ↓
Audience analysis
      ↓
Content objective
      ↓
Select 2–3 hook strategies
      ↓
Generate 3–5 hook candidates
      ↓
Score hook candidates
      ↓
Select winner
      ↓
Generate body
      ↓
Generate CTA
```

This makes the eight hook principles actionable rather than decorative.

---

# 9. Required Script Quality Dimensions

Score every final script on a 0–100 scale for:

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

Recommended gating:

```text
< 75      → regenerate
75–84     → revise
85+       → approve
```

However, do not allow a high arithmetic average to hide a catastrophic weakness.

Add hard gates for:

- factual hallucination
- fake credentials
- fake social proof
- unsupported numerical claims
- misleading product claims
- hook unrelated to product

A script that violates a hard gate must be rejected regardless of total score.

---

# 10. Script Structure

The final script should be structured, not stored as a single text blob.

Required shape:

```json
{
  "title": "...",
  "hook_strategy": "LOSS_AVERSION",
  "hook": "...",
  "body": [
    {
      "scene_id": "scene_01",
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

This structured representation is mandatory because the visual system must understand the intended meaning of each line.

---

# 11. Curiosity / “여운” Rule

For `CURIOSITY_GAP`, do not simply withhold random information.

The script must establish a clear expectation:

```text
tease → useful partial information → reason to continue → resolution/CTA
```

Never create an empty cliffhanger that wastes viewer attention.

---

# 12. Authority / Social Proof Safety

The script generator must never invent:

- years of experience
- employer history
- certifications
- customer counts
- review counts
- sales numbers
- “everyone is using this” claims

Unless the source data explicitly supports them.

---

# 13. Phase 3 — Semantic Scene Matching

This is the highest-priority functional fix because the current system can retrieve visually unrelated stock footage.

The legacy keyword-based retrieval should not be treated as sufficient for v2.

---

# 14. Scene Understanding Schema

Each narration segment must be transformed into:

```json
{
  "subject": "...",
  "action": "...",
  "location": "...",
  "object": "...",
  "emotion": "...",
  "context": "...",
  "visual_goal": "...",
  "avoid": ["..."]
}
```

The purpose is to represent the intended visual meaning rather than merely extract nouns from text.

---

# 15. Visual Intent vs Search Query

Keep these concepts separate.

### Visual Intent
What the viewer should literally see.

### Search Query
The provider-specific words used to retrieve candidates.

Example:

```text
Narration:
“출근길 지하철에서 더위 때문에 땀을 많이 흘리는 직장인이라면…”
```

Visual Intent:

```text
A young office worker commuting in a subway during hot weather, visibly uncomfortable because of heat.
```

Search queries:

```text
portrait office worker sweating subway summer
vertical office worker hot subway commute
portrait commuter using handheld fan subway
```

Do not search for generic terms such as only `summer` or `heat` when the narration clearly describes a person, action, and place.

---

# 16. Search Candidate Expansion

For every scene, generate 3–5 search queries with deliberate variation.

Vary:

- subject wording
- action wording
- location wording
- product wording
- emotional wording
- portrait/vertical hints

Do not blindly add `vertical` to every query if the provider returns poor results. Search strategy should be adaptive.

---

# 17. Candidate Scoring

Use the original plan’s weighting as the starting point:

```text
Semantic Relevance  40%
Action Match        20%
Object Match        15%
Emotion Match       10%
Context Match       10%
Video Quality        5%
```

But introduce hard constraints before weighted scoring.

Example:

```text
if corrupted → reject
if below minimum resolution → reject
if clearly contradicts avoid list → reject
if semantic relevance < minimum threshold → reject
```

Only surviving candidates should enter weighted ranking.

---

# 18. Required Feature: Reject → Query Refinement → Re-search Loop

This is a mandatory revision to the existing implementation plan.

Do NOT implement only:

```text
Scene → 5 queries → select best
```

Implement:

```text
Scene Intent
   ↓
Query generation
   ↓
Candidate retrieval
   ↓
Hard filters
   ↓
Semantic ranking
   ↓
Pass?
 ├── YES → accept
 └── NO
       ↓
Query refinement
       ↓
Second retrieval
       ↓
Re-score
       ↓
Pass?
 ├── YES → accept
 └── NO
       ↓
Third retrieval OR scene visual reinterpretation
       ↓
If still failing → do not use a bad clip
```

Use a maximum retry count to avoid runaway API costs.

Recommended default:

```text
3 retrieval rounds per scene
```

Make this configurable.

---

# 19. Mandatory `avoid` Logic

For each scene, derive negative concepts.

Example:

```text
Narration:
“컴퓨터 앞에 오래 앉아 목이 뻐근한 직장인이라면…”
```

Avoid:

```text
beach
vacation
running
fitness
landscape
food
```

If a candidate strongly matches forbidden contexts, reject or heavily penalize it.

This exists specifically to prevent the common failure mode where generic words such as `summer` cause beach footage to appear.

---

# 20. Scene-Level Debug Information

For every scene, save:

```text
Narration
Scene Intent
Search Queries
Candidates
Hard-filter rejections
Semantic score
Quality score
Final asset
Reason for selection
```

Example:

```text
scene_03

Narration:
“출근길 더위가 힘들다면…”

Query:
“portrait office worker hot subway”

Candidate A
semantic=91
quality=65
→ rejected: insufficient resolution

Candidate B
semantic=88
quality=94
→ selected
```

This must be accessible in Debug mode in the UI.

---

# 21. Phase 4 — 9:16 High-Quality Asset Pipeline

The quality policy must be:

> **Do not force a low-quality landscape asset into a 9:16 video merely to satisfy the aspect-ratio requirement.**

---

# 22. Asset Priority Order

Implement the following preference order:

```text
1. Native 9:16 / portrait high-resolution
2. Native portrait with slightly different portrait ratio
3. High-resolution 4K landscape that can be safely reframed/cropped
4. High-resolution landscape suitable for crop
5. Reject and search again
```

Do not treat a 1080p landscape clip as automatically equivalent to a 1080×1920 portrait source.

---

# 23. Quality Gate Must Consider Post-Crop Resolution

This is mandatory.

Do not validate only the source resolution.

If an asset is cropped, calculate the effective usable pixel area after crop and the required scaling factor for the 9:16 output.

Example conceptual rule:

```text
source resolution
→ intended crop region
→ effective crop resolution
→ target 1080×1920
→ required upscale factor
```

If required enlargement becomes excessive, reject the asset.

Make thresholds configurable rather than hard-coded.

---

# 24. Smart Crop Is a Fallback, Not the Default

Smart Crop is allowed only when:

- the source is sufficiently high resolution
- the important subject can remain inside the crop
- the crop does not destroy the scene meaning
- the resulting effective resolution passes the quality gate

Prefer:

```text
native portrait > safe reframe > smart crop > rejection
```

Do not use Smart Crop simply because the source is landscape.

---

# 25. AI Reframe

If the implementation is practical within the current stack, support subject-following reframe for moving subjects.

However, do not delay the critical pipeline for a sophisticated video-tracking subsystem.

Treat AI Reframe as:

```text
Phase 4 core if stable
or
Phase 4.1 / follow-up feature if implementation complexity is excessive
```

The core quality requirement remains: use good portrait assets first.

---

# 26. 9:16 Rendering Requirement

Every final video must explicitly validate:

```text
aspect_ratio = 9:16
resolution >= configured minimum
codec valid
video playable
no accidental pillarboxing/letterboxing unless intentionally designed
```

Default target:

```text
1080 × 1920
```

where the source and rendering stack allow it.

---

# 27. Phase 5 — Naver Clip Intelligence

Implement this only after Phase 1–4 produce consistently good videos.

The system must not claim to know Naver’s private ranking algorithm.

All ranking advice should be represented as:

- observed pattern
- estimated relevance
- optimization recommendation

not as a guaranteed ranking formula.

---

# 28. Naver Clip Data Model

Support the following where public or user-provided data is actually available:

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
traffic source
impressions
clicks
CTR
audience age
audience gender
```

Do not fabricate unavailable metrics.

Distinguish:

```text
Observed
Estimated
User-provided
Unavailable
```

---

# 29. Keyword Intelligence

Generate:

```text
Primary keyword
Secondary keyword
Long-tail keyword
Problem keyword
Solution keyword
Commercial/intention keyword
Audience keyword
Context keyword
```

Store a recommendation score with transparent dimensions:

```text
Relevance
Observed competition
Estimated demand (only when clearly labeled)
Commercial intent
Content fit
```

Never label an estimate as official Naver search volume.

---

# 30. Naver Clip Title Generator

Support at least:

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

Generate multiple candidates, score them, and select a default while retaining alternatives.

The title must remain semantically faithful to the product and video.

---

# 31. Hashtag Generator

Separate tags into:

```text
Core product
Product category
Problem
Audience
Context
Trend candidate
```

Do not create a meaningless list of high-level generic tags.

Do not claim a tag guarantees top placement.

---

# 32. Optimization Score

Create a transparent score such as:

```text
Hook
Title
Keyword relevance
Hashtag relevance
Audience fit
Product relevance
Visual quality
CTA
```

The UI must show the component scores and concrete recommendations.

Do not present the score as an official Naver score.

Recommended label:

> `AdForge Clip Optimization Score`

not:

> `Naver Ranking Score`

---

# 33. Phase 6 — Full Pipeline

The final pipeline should become:

```text
Product URL / Product Data
        ↓
Product Analysis
        ↓
Audience Analysis
        ↓
Naver Keyword Intelligence
        ↓
Hook Strategy Selection
        ↓
Hook Candidate Generation
        ↓
Script Generation
        ↓
Script Quality Gate
        ↓
Scene Planning
        ↓
Semantic Scene Matching
        ↓
Asset Quality Gate
        ↓
9:16 Asset Selection
        ↓
TTS
        ↓
Caption/Subtitles
        ↓
Video Composition
        ↓
Render Validation
        ↓
CapCut Draft
        ↓
Naver Title / Hashtag / Description
        ↓
Optimization Report
```

---

# 34. Final Output Package

Produce:

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
```

---

# 35. Generation Report Must Explain Every Important Decision

At minimum:

```json
{
  "job_id": "...",
  "product": "...",
  "platform": "naver_clip",
  "duration": 27,
  "resolution": "1080x1920",
  "aspect_ratio": "9:16",
  "hook_strategy": "...",
  "script_score": 89,
  "visual_score": 91,
  "clip_optimization_score": 87,
  "scenes": [
    {
      "scene_id": "scene_01",
      "narration": "...",
      "queries": ["..."],
      "selected_asset": "...",
      "semantic_score": 93,
      "quality_score": 96,
      "selection_reason": "..."
    }
  ]
}
```

---

# 36. UI Requirements

Keep the existing Streamlit application and add an `AdForge v2` mode.

The new interface should expose:

```text
Product URL / Product Info
Target audience (optional)
Content goal
Tone
Target duration
```

Then show pipeline progress:

```text
✓ Product analysis
✓ Audience analysis
✓ Hook strategy
✓ Script generation
✓ Script quality
✓ Scene planning
✓ Asset search
✓ Asset quality
✓ TTS
✓ Video rendering
✓ Clip optimization
```

---

# 37. Debug Mode

Add a toggle:

```text
Debug Mode: ON/OFF
```

When enabled, expose:

- selected hook strategy
- rejected hook candidates
- script score
- scene intent
- search queries
- rejected assets and reasons
- selected asset score
- crop/reframe decision
- output resolution
- Clip optimization components

This is mandatory because the major current issue is not merely “bad output” but inability to explain why the bad output was produced.

---

# 38. Caching / Cost Control

Cache deterministic or reusable intermediate results:

```text
product analysis
keyword analysis
scene analysis
search metadata
asset metadata
```

Do not repeatedly call an LLM for identical inputs unless regeneration is explicitly requested.

Retry loops must have a hard cap.

---

# 39. Async Job Model

Use job-based execution for long-running generation.

At minimum:

```text
job_id
status
current_step
progress
error
created_at
completed_at
```

Example:

```json
{
  "job_id": "abc123",
  "status": "processing",
  "current_step": "semantic_matching",
  "progress": 67
}
```

Do not turn this into a heavy queue infrastructure unless required. A lightweight implementation is acceptable for the current stage.

---

# 40. Verification Strategy

Every phase must have automated or repeatable verification.

## Phase 1

- `streamlit run app.py` works
- Legacy workflow still works
- v2 modules import successfully
- configuration loads correctly

## Phase 2

- 8 hook strategies can be selected
- multiple hooks can be generated
- script scoring works
- hard safety gates reject bad claims

## Phase 3

- narration becomes structured scene intent
- queries are context-aware
- unrelated candidates are rejected
- failed searches trigger query refinement
- debug information is stored

## Phase 4

- native portrait preferred
- output target is 9:16
- minimum quality enforced
- low-resolution landscape footage is not blindly enlarged
- post-crop effective resolution is checked

## Phase 5

- keyword candidates generated
- title candidates generated
- hashtag categories generated
- optimization score is transparent

## Phase 6

- full URL-to-package pipeline works
- Legacy mode still works
- v2 output contains all required files

---

# 41. Required End-to-End Test Cases

## Test A — Portable Fan / Commuter

Product:

```text
portable handheld fan
```

Narration concept:

```text
If the heat on your commute is exhausting you...
```

Expected visual semantics:

```text
office worker
commuting
subway / transit
hot weather
portable fan / heat relief
```

Reject examples:

```text
beach vacation
palm trees
summer resort
generic landscape
```

Final:

```text
9:16
>= configured HD threshold
```

---

## Test B — Neck Massager / Office Worker

Narration concept:

```text
If your neck feels stiff after sitting at a computer all day...
```

Expected:

```text
office worker
desk
computer
neck discomfort
massage / neck relief
```

Reject generic:

```text
gym
running
beach
spa vacation
food
```

---

## Test C — Low-Resolution Landscape Only

If the search returns only poor landscape footage:

```text
Do NOT blindly upscale.

Retry search.

Refine query.

If still unavailable, reject the asset.
```

A lower-quality but semantically closer asset may still be rejected if it fails the quality gate. The system should prefer a re-search over silently degrading the final video.

---

# 42. Additional Regression Test Cases

Add tests for:

### Abstract / Non-visual narration

Example:

```text
“This is the reason most people waste money.”
```

The scene planner should create a visually useful metaphor or product-related visual instead of searching literally for “waste money”.

### Product demonstration narration

If narration says:

```text
“Press this button and the temperature changes immediately.”
```

the visual intent must prioritize an actual hand/product interaction over generic lifestyle footage.

### Emotional narration

If narration expresses anxiety, relief, surprise, or frustration, the scene intent should encode emotion rather than only nouns.

---

# 43. Important UX Principle

The user should not need to manually troubleshoot search queries.

The system should do this internally:

```text
bad result
→ detect
→ explain internally
→ refine
→ retry
```

Only surface the process in Debug Mode.

The normal user experience should remain simple:

```text
Enter product
→ Generate
→ Review
→ Export
```

---

# 44. Do Not Over-Engineer the First Release

Do not introduce unnecessary infrastructure merely to satisfy the architecture diagram.

Examples of features that may be deferred if they substantially increase complexity:

- full autonomous multi-agent orchestration framework
- vector database before there is meaningful data
- GPU-heavy local multimodal models
- complex distributed workers
- automatic publishing to Naver before platform/API support is verified

Prioritize measurable improvements in:

```text
script quality
visual relevance
9:16 quality
workflow reliability
```

---

# 45. Definition of Done for the Revised Plan

The revised implementation is considered successful only when a human reviewer can compare Legacy vs v2 on the same product and observe:

1. The v2 script has a stronger hook and clearer target.
2. The v2 scenes are materially more relevant to each narration segment.
3. v2 preferentially uses native portrait/high-quality footage.
4. v2 rejects poor landscape footage instead of blindly enlarging it.
5. v2 can explain why each scene asset was selected.
6. v2 can generate Naver Clip title/keyword/hashtag recommendations.
7. Existing Legacy generation still works.

---

# 46. Implementation Instructions to Antigravity

Before changing code:

1. Inspect the repository and current implementations.
2. Map each current feature to `KEEP / REFACTOR / REPLACE / DEPRECATE`.
3. Identify any existing functions that already solve part of the new requirements.
4. Avoid duplicating functionality unnecessarily.
5. Create the new schemas and module boundaries first.

Then implement in this order:

```text
Phase 1
↓
Phase 2
↓
Phase 3
↓
Phase 4
↓
Run real end-to-end comparison
↓
Only after passing Phase 1–4 tests
↓
Phase 5
↓
Phase 6
```

At the end of each phase, provide a concise implementation report:

```text
Implemented
Changed files
Tests run
Test results
Known limitations
Next phase
```

Do not ask for confirmation about Phase scope if the repository and this document already provide enough information to proceed. Use the priority defined here.

---

# 47. Final Product Principle

The final AdForge v2 should behave like a marketing production system, not a random content generator.

For every output, the system should be able to answer:

```text
Why this hook?
Why this script structure?
Why this scene?
Why this stock asset?
Why was this asset rejected?
Why this title?
Why these hashtags?
Why this final score?
```

The central product loop is:

```text
Understand
→ Strategize
→ Generate
→ Verify
→ Optimize
→ Export
```

Build for this loop while preserving the working legacy pipeline.
