import json
from openai import OpenAI
from core.config import config
from core.schemas import ScriptScore
from core.logging import logger

class QualityAgent:
    def __init__(self, api_key: str = None, base_url: str = "https://integrate.api.nvidia.com/v1", model: str = "meta/llama-3.1-70b-instruct"):
        key = api_key or config.NVIDIA_API_KEY
        self.client = OpenAI(api_key=key, base_url=base_url)
        self.model = model

    def evaluate_script(self, script_text: str, product_name: str) -> ScriptScore:
        prompt = f"""You are a Naver Clip Ad Quality Evaluator.
Evaluate the following script for a product ad on Naver Clip.
Product: {product_name}

Script:
{script_text}

Rate the following dimensions from 0 to 100:
1. hook_strength
2. target_specificity
3. clarity
4. curiosity
5. credibility
6. emotional_relevance
7. product_relevance
8. pacing
9. cta_strength
10. factual_safety

HARD GATES: If the script hallucinates fake numbers, fake credentials, fake social proof, or makes illegal claims, set 'factual_safety' to 0.

Calculate the 'total_score' as the average.
Set 'is_approved' to true ONLY if total_score >= 85 AND factual_safety >= 90.
If is_approved is false, provide a brief 'rejection_reason'.

Return ONLY valid JSON matching this structure:
{{
  "hook_strength": 90,
  "target_specificity": 85,
  "clarity": 95,
  "curiosity": 80,
  "credibility": 85,
  "emotional_relevance": 90,
  "product_relevance": 95,
  "pacing": 88,
  "cta_strength": 82,
  "factual_safety": 100,
  "total_score": 89,
  "is_approved": true,
  "rejection_reason": null
}}
"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            result = json.loads(response.choices[0].message.content)
            return ScriptScore(**result)
        except Exception as e:
            logger.error(f"Script evaluation failed: {e}")
            # Fallback score if evaluation fails
            return ScriptScore(
                hook_strength=0, target_specificity=0, clarity=0, curiosity=0, credibility=0, 
                emotional_relevance=0, product_relevance=0, pacing=0, cta_strength=0, 
                factual_safety=0, total_score=0, is_approved=False, rejection_reason="Evaluation API failed"
            )
