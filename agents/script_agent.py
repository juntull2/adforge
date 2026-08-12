import json
from openai import OpenAI
from core.config import config
from core.schemas import ProductInfo, AudienceProfile, ScriptResult, SceneIntent, HookCandidate
from agents.quality_agent import QualityAgent
from intelligence.hook_engine import HookEngine
from core.logging import logger
from typing import List

class ScriptAgent:
    def __init__(self, api_key: str = None, base_url: str = "https://integrate.api.nvidia.com/v1", model: str = "meta/llama-3.1-70b-instruct"):
        key = api_key or config.NVIDIA_API_KEY
        self.client = OpenAI(api_key=key, base_url=base_url)
        self.model = model
        self.quality_agent = QualityAgent(api_key=key, base_url=base_url, model=model)
        self.hook_engine = HookEngine(api_key=key, base_url=base_url, model=model)

    def generate_script(self, product: ProductInfo, audience: AudienceProfile, benchmark_patterns: List[str] = None) -> ScriptResult:
        logger.info(f"Generating script for {product.name} targeting {audience.age_group}...")

        # 1. Select Hook Strategies
        logger.info("Selecting hook strategies...")
        strategies = self.hook_engine.select_strategies(product, audience, benchmark_patterns)
        
        # 2. Generate Hook Candidates
        logger.info("Generating hook candidates...")
        hook_candidates = self.hook_engine.generate_hook_candidates(product, audience, strategies, benchmark_patterns)
        
        if not hook_candidates:
            logger.error("Failed to generate any hook candidates.")
            return None

        # 3. For MVP, just pick the first valid candidate (later we can add scoring)
        best_hook = hook_candidates[0]
        logger.info(f"Selected hook strategy: {best_hook.strategy_id}")

        # 4. Generate Body Script (incorporating the selected hook)
        max_attempts = 3
        for attempt in range(max_attempts):
            logger.info(f"Generating full script... (Attempt {attempt + 1}/{max_attempts})")
            
            benchmark_hint = ""
            if benchmark_patterns:
                benchmark_hint = f"""
Benchmark Intelligence (observed structural patterns from successful videos in this domain):
{', '.join(benchmark_patterns)}
Use these as structural inspiration for the script's pacing and narrative flow. Do NOT copy any specific content."""

            prompt = f"""You are a top-tier short-form copywriter for Naver Clip.
Write a highly engaging health/lifestyle product ad script.

Product: {product.name} ({product.category})
Description: {product.description}
Audience: {audience.age_group} ({audience.gender}), Core Problem: {audience.core_problem}
{benchmark_hint}

Selected Hook Strategy: {best_hook.strategy_id}
Selected Hook Sentence: "{best_hook.content}"

Requirements:
1. Video Title: Engaging, click-worthy (under 25 chars).
2. Narration: Natural Korean spoken language (~해요, ~습니다). No filler words.
3. Scenes: Break the video into 4-6 scenes.
4. Scene details: Provide highly specific details for stock footage search.
   - subject: who is on screen
   - age_group: e.g. "middle_aged", "senior", "young"
   - action: what they are doing
   - location: where are they
   - object: what object is visible
   - body_part: what body part is focused on (e.g. "lower back", "knee")
   - symptom: what symptom is shown (e.g. "pain", "stiffness")
   - emotion: their expression
   - context: the situation
   - visual_goal: a 1-sentence summary for the search engine
   - avoid: things NOT to show (e.g. "cartoons", "doctors")
5. CTA: The final sentence must ask viewers to check the comment section or link.
6. MUST pass safety gates: Do NOT use medical claims ("완치", "치료"), fake data, or fake authority.

Return ONLY valid JSON matching this schema:
{{
  "title": "Video Title",
  "hook_strategy": "{best_hook.strategy_id}",
  "hook": "{best_hook.content}",
  "body": [
    {{
      "scene_id": "scene_01",
      "narration": "First 1-2 sentences of narration (must start with the Selected Hook Sentence)",
      "subject": "middle aged man",
      "age_group": "middle_aged",
      "action": "rubbing lower back",
      "location": "office",
      "object": "office chair",
      "body_part": "lower back",
      "symptom": "pain",
      "emotion": "in pain",
      "context": "working long hours",
      "visual_goal": "A middle aged man in an office rubbing his lower back in pain",
      "avoid": ["animation", "clinic"]
    }}
  ],
  "cta": "Check the comments for the link!",
  "duration_target": 25
}}
"""
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.7
                )
                result = json.loads(response.choices[0].message.content)
                
                # Check formatting
                body_scenes = []
                for s in result.get("body", []):
                    body_scenes.append(SceneIntent(
                        scene_id=s.get("scene_id", f"scene_{len(body_scenes)}"),
                        narration=s.get("narration", ""),
                        subject=s.get("subject", ""),
                        age_group=s.get("age_group", ""),
                        action=s.get("action", ""),
                        location=s.get("location", ""),
                        object=s.get("object", ""),
                        body_part=s.get("body_part", ""),
                        symptom=s.get("symptom", ""),
                        emotion=s.get("emotion", ""),
                        context=s.get("context", ""),
                        visual_goal=s.get("visual_goal", ""),
                        avoid=s.get("avoid", []),
                    ))

                script_result = ScriptResult(
                    title=result.get("title", f"{product.name} Ad"),
                    hook_strategy=result.get("hook_strategy", best_hook.strategy_id),
                    hook=result.get("hook", best_hook.content),
                    body=body_scenes,
                    cta=result.get("cta", ""),
                    duration_target=result.get("duration_target", 25)
                )

                # 5. Quality Gate Evaluation
                full_script_text = " ".join([s.narration for s in script_result.body])
                score = self.quality_agent.evaluate_script(full_script_text, product.name)
                
                if score.is_approved:
                    logger.info(f"Script approved with score {score.total_score}/100")
                    return script_result
                else:
                    logger.warning(f"Script rejected by Quality Gate: {score.rejection_reason} | Violations: {score.hard_gate_violations}")
                    
            except Exception as e:
                logger.error(f"Error generating script: {e}")

        logger.error("Failed to generate an approved script after max attempts.")
        return None
