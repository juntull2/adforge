import json
import uuid
from typing import Optional
from openai import OpenAI
from core.config import config
from core.schemas import ProductInfo, AudienceProfile, ScriptResult, SceneIntent
from intelligence.hook_engine import HookEngine
from agents.quality_agent import QualityAgent
from core.logging import logger

class ScriptAgent:
    def __init__(self, api_key: str = None, base_url: str = "https://integrate.api.nvidia.com/v1", model: str = "meta/llama-3.1-70b-instruct"):
        key = api_key or config.NVIDIA_API_KEY
        self.client = OpenAI(api_key=key, base_url=base_url)
        self.model = model
        self.hook_engine = HookEngine(api_key=key, base_url=base_url, model=model)
        self.quality_agent = QualityAgent(api_key=key, base_url=base_url, model=model)

    def generate_script(self, product: ProductInfo, audience: AudienceProfile, max_retries: int = 3) -> Optional[ScriptResult]:
        logger.info(f"Generating script for {product.name}...")
        
        # 1. Hook Strategy Selection
        strategies = self.hook_engine.select_strategies(product, audience)
        logger.info(f"Selected strategies: {strategies}")
        
        # 2. Hook Candidate Generation
        hook_candidates = self.hook_engine.generate_hook_candidates(product, audience, strategies)
        if not hook_candidates:
            logger.error("Failed to generate any hooks.")
            return None
            
        # Select best hook (for now, just pick the first one, or we could score them individually)
        # Simplified: pick the first generated hook
        selected_hook = hook_candidates[0]
        logger.info(f"Selected hook: {selected_hook.content}")

        # 3. Generate Body and CTA
        attempt = 0
        while attempt < max_retries:
            attempt += 1
            logger.info(f"Generating script body and CTA (Attempt {attempt})...")
            
            prompt = f"""You are an expert copywriter for Naver Clip.
Write a short-form ad script based on the provided Hook.

Product: {product.name} ({product.category})
Description: {product.description}
Audience: {audience.age_group} ({audience.gender}), Core Problem: {audience.core_problem}

Hook Strategy: {selected_hook.strategy_id}
Hook Sentence: "{selected_hook.content}"

Task:
1. Provide a catchy Title.
2. Generate the Body of the script (break it down into 3-5 scenes).
   For each scene, provide:
   - narration: The spoken text
   - subject: Main subject (e.g., "office worker")
   - action: Action happening (e.g., "sweating")
   - location: Location (e.g., "subway")
   - object: Main object (e.g., "smartphone")
   - emotion: Emotion conveyed (e.g., "frustrated")
   - context: General context (e.g., "hot summer commute")
   - visual_goal: A 1-sentence visual description
   - avoid: Array of words/contexts to avoid (e.g., ["beach", "vacation"])
3. Provide a Call to Action (CTA) sentence at the end.

Return ONLY valid JSON:
{{
  "title": "Catchy Title",
  "body": [
    {{
      "narration": "text",
      "subject": "office worker",
      "action": "sweating",
      "location": "subway",
      "object": "fan",
      "emotion": "frustrated",
      "context": "hot commute",
      "visual_goal": "close up of person sweating",
      "avoid": ["beach", "vacation"]
    }}
  ],
  "cta": "Click here to buy"
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
                
                scenes = []
                for i, s in enumerate(result.get("body", [])):
                    scenes.append(SceneIntent(
                        scene_id=f"scene_{i+1:02d}",
                        narration=s.get("narration", ""),
                        subject=s.get("subject", ""),
                        action=s.get("action", ""),
                        location=s.get("location", ""),
                        object=s.get("object", ""),
                        emotion=s.get("emotion", ""),
                        context=s.get("context", ""),
                        visual_goal=s.get("visual_goal", ""),
                        avoid=s.get("avoid", [])
                    ))
                
                # Create a temporary ScriptResult to evaluate
                script_text = selected_hook.content + "\n" + "\n".join([s.narration for s in scenes]) + "\n" + result.get("cta", "")
                
                # 4. Quality Evaluation
                score = self.quality_agent.evaluate_script(script_text, product.name)
                logger.info(f"Script evaluated: Score {score.total_score}. Approved? {score.is_approved}")
                
                if score.is_approved or attempt == max_retries:
                    return ScriptResult(
                        title=result.get("title", ""),
                        hook_strategy=selected_hook.strategy_id,
                        hook=selected_hook.content,
                        body=scenes,
                        cta=result.get("cta", "")
                    )
                else:
                    logger.warning(f"Script rejected: {score.rejection_reason}. Retrying...")
            except Exception as e:
                logger.error(f"Script generation error: {e}")
                
        return None
