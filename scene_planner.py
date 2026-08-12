"""
AdForge V2 — Scene Planner
대본 텍스트 → 장면(Scene) 분할 + 검색어 생성 + Stock/AI 판단
NVIDIA API (mistral-nemotron) 사용
"""
from __future__ import annotations
import json
import re
import uuid
from typing import List, Optional
from openai import OpenAI

from models.scene import Scene


SCENE_SPLIT_SYSTEM_PROMPT = """You are a professional short-form video production planner specializing in Korean health content for senior audiences (50-70s).

Your task: Given a Korean script, split it into video scenes and for each scene provide:
1. The narration text for that scene
2. A visual description in Korean
3. 3-5 English search keywords for finding stock footage
4. Whether stock footage ("stock") or AI-generated video ("ai_video") is better suited

Stock footage rules:
- Use "stock" for: walking seniors, sitting, eating, everyday activities, nature, parks, general exercise
- Use "ai_video" for: specific medical demonstrations, precise exercise form corrections, hard-to-find realistic scenes, unique product interactions

Output ONLY valid JSON in this exact format (no markdown, no explanation):
{
  "scenes": [
    {
      "order": 1,
      "narration": "나레이션 텍스트",
      "visual_description": "화면 묘사 (한국어)",
      "search_keywords": ["keyword1", "keyword2", "keyword3"],
      "preferred_source": "stock",
      "estimated_duration": 3.5
    }
  ],
  "hook": "훅 문장 (첫 문장 또는 핵심 강조 문장)",
  "total_estimated_duration": 45.0
}

Rules:
- Each scene should be 2-6 seconds
- 1 clear action per scene (NEVER combine multiple actions)
- search_keywords MUST be in English
- preferred_source must be exactly "stock" or "ai_video"
- Typical video: 5-10 scenes for a 30-60 second script"""


def plan_scenes(
    script: str,
    nvidia_api_key: str,
    model: str = "mistralai/mistral-nemotron",
    content_id: Optional[str] = None,
) -> List[Scene]:
    """
    대본을 입력받아 Scene 리스트를 반환한다.
    """
    if not content_id:
        content_id = str(uuid.uuid4())

    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=nvidia_api_key,
    )

    user_message = f"""다음 대본을 장면별로 분리해주세요:

---대본 시작---
{script.strip()}
---대본 끝---

JSON 형식으로만 응답하세요."""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SCENE_SPLIT_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.3,
        max_tokens=2000,
    )

    raw = response.choices[0].message.content.strip()

    # JSON 추출 (마크다운 코드블록이 섞인 경우 대비)
    json_match = re.search(r'\{[\s\S]+\}', raw)
    if not json_match:
        raise ValueError(f"Scene Planner: JSON 파싱 실패\n원문:\n{raw}")

    data = json.loads(json_match.group())
    scenes_raw = data.get("scenes", [])

    scenes: List[Scene] = []
    running_time = 0.0

    for s in scenes_raw:
        dur = float(s.get("estimated_duration", 3.0))
        start = running_time
        end = running_time + dur
        running_time = end

        scene = Scene(
            content_id=content_id,
            order=int(s.get("order", len(scenes) + 1)),
            narration=s.get("narration", ""),
            visual_description=s.get("visual_description", ""),
            search_keywords=[k.strip() for k in s.get("search_keywords", []) if k.strip()],
            preferred_source=s.get("preferred_source", "stock"),
            start_time=start,
            end_time=end,
            ai_video_required=(s.get("preferred_source", "stock") == "ai_video"),
        )
        scenes.append(scene)

    return scenes, data.get("hook", ""), data.get("total_estimated_duration", running_time)


def plan_scenes_stream(
    script: str,
    nvidia_api_key: str,
    model: str = "mistralai/mistral-nemotron",
    content_id: Optional[str] = None,
):
    """
    스트리밍으로 Scene 분석 텍스트를 yield 하고,
    마지막에 (scenes, hook, duration) 튜플을 yield한다.
    """
    if not content_id:
        content_id = str(uuid.uuid4())

    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=nvidia_api_key,
    )

    user_message = f"""다음 대본을 장면별로 분리해주세요:

---대본 시작---
{script.strip()}
---대본 끝---

JSON 형식으로만 응답하세요."""

    stream = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SCENE_SPLIT_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.3,
        max_tokens=2000,
        stream=True,
    )

    full_text = ""
    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        full_text += delta
        yield delta

    # 스트림 완료 후 파싱
    json_match = re.search(r'\{[\s\S]+\}', full_text)
    if not json_match:
        yield "\n\n❌ Scene 분석 JSON 파싱 실패"
        return

    data = json.loads(json_match.group())
    scenes_raw = data.get("scenes", [])
    scenes: List[Scene] = []
    running_time = 0.0

    for s in scenes_raw:
        dur = float(s.get("estimated_duration", 3.0))
        start = running_time
        end = running_time + dur
        running_time = end

        scene = Scene(
            content_id=content_id,
            order=int(s.get("order", len(scenes) + 1)),
            narration=s.get("narration", ""),
            visual_description=s.get("visual_description", ""),
            search_keywords=[k.strip() for k in s.get("search_keywords", []) if k.strip()],
            preferred_source=s.get("preferred_source", "stock"),
            start_time=start,
            end_time=end,
            ai_video_required=(s.get("preferred_source", "stock") == "ai_video"),
        )
        scenes.append(scene)

    yield ("__SCENES_RESULT__", scenes, data.get("hook", ""), data.get("total_estimated_duration", running_time))
