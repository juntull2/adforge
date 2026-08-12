"""
AdForge V2 — Hailuo Prompt Generator
Scene 단위로 Hailuo AI 영상 프롬프트 자동 생성.
기존 generate_hailuo_prompts_stream 과 별개 — Scene별 정밀 생성.
"""
from __future__ import annotations
from typing import Optional
from models.scene import Scene

# Hailuo 실패 방지 기본 접미사
HAILUO_SAFETY_SUFFIX = (
    "9:16 vertical video, "
    "realistic, "
    "natural human movement, "
    "single clear action, "
    "stable camera, "
    "no text, "
    "no subtitles, "
    "no watermark, "
    "no extra limbs, "
    "no duplicated person, "
    "no unnatural movement"
)

HAILUO_SYSTEM_PROMPT = """You are a Hailuo AI video prompt engineer for Korean health content targeting seniors (50-70 years old).

Rules:
1. Write prompts in English only
2. ONE simple, clear action per prompt (never combine multiple actions)
3. Always include: 9:16 vertical, Korean elderly person, realistic setting
4. Always end with: stable camera, no text, no subtitles, no watermark
5. Keep it under 80 words
6. Use specific, visual language (not abstract concepts)
7. Specify camera angle: medium shot, close-up, wide shot, etc.

Output ONLY the prompt text, no explanation."""

HAILUO_USER_TEMPLATE = """Scene: {visual_description}
Narration: {narration}
Keywords: {keywords}

Generate a Hailuo video prompt for this scene."""


def generate_hailuo_prompt_for_scene(
    scene: Scene,
    project_target_audience: str = "Korean senior woman aged 60s",
    nvidia_api_key: Optional[str] = None,
    model: str = "mistralai/mistral-nemotron",
) -> str:
    """
    Scene → Hailuo 프롬프트 생성.
    nvidia_api_key가 없으면 룰 기반 기본 프롬프트 생성.
    """
    if nvidia_api_key:
        return _generate_with_ai(scene, project_target_audience, nvidia_api_key, model)
    else:
        return _generate_rule_based(scene, project_target_audience)


def _generate_with_ai(
    scene: Scene,
    target_audience: str,
    nvidia_api_key: str,
    model: str,
) -> str:
    from openai import OpenAI
    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=nvidia_api_key,
    )
    user_msg = HAILUO_USER_TEMPLATE.format(
        visual_description=scene.visual_description,
        narration=scene.narration,
        keywords=", ".join(scene.search_keywords),
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": HAILUO_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.4,
        max_tokens=200,
    )
    prompt = resp.choices[0].message.content.strip()
    # 안전 접미사가 없으면 추가
    if "9:16" not in prompt:
        prompt = prompt.rstrip(".,") + ", " + HAILUO_SAFETY_SUFFIX
    return prompt


def _generate_rule_based(scene: Scene, target_audience: str) -> str:
    """AI 없이 룰 기반으로 기본 프롬프트 생성"""
    visual = scene.visual_description
    keywords = " ".join(scene.search_keywords[:2])

    prompt = (
        f"9:16 vertical video, "
        f"{target_audience}, "
        f"{visual[:80]}, "
        f"realistic Korean indoor setting, "
        f"soft natural daylight, "
        f"static medium shot, "
        f"realistic documentary style, "
        f"no text, no subtitles, no watermark, "
        f"no extra limbs, no unnatural movement"
    )
    return prompt


def generate_prompts_for_content(
    scenes: list,
    nvidia_api_key: Optional[str] = None,
    model: str = "mistralai/mistral-nemotron",
    project_target_audience: str = "Korean senior woman aged 60s",
) -> dict:
    """
    ai_video_required=True인 Scene들에 대해서만 프롬프트 생성.
    반환: {scene_id: prompt}
    """
    results = {}
    for scene in scenes:
        if scene.ai_video_required:
            prompt = generate_hailuo_prompt_for_scene(
                scene,
                project_target_audience=project_target_audience,
                nvidia_api_key=nvidia_api_key,
                model=model,
            )
            results[scene.scene_id] = prompt
    return results
