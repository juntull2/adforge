import json
from openai import OpenAI
from core.config import config
from core.schemas import ScriptScore
from core.logging import logger

HARD_GATES = [
    "MEDICAL_CLAIM_RISK",
    "UNSUPPORTED_EFFICACY",
    "FAKE_TESTIMONIAL",
    "FAKE_AUTHORITY",
    "UNSUPPORTED_NUMERICAL_CLAIM",
]

class QualityAgent:
    def __init__(self, api_key: str = None, base_url: str = "https://integrate.api.nvidia.com/v1", model: str = "meta/llama-3.1-70b-instruct"):
        key = api_key or config.NVIDIA_API_KEY
        self.client = OpenAI(api_key=key, base_url=base_url)
        self.model = model

    def evaluate_script(self, script_text: str, product_name: str) -> ScriptScore:
        prompt = f"""You are a Naver Clip Ad Quality Evaluator specializing in Korean health/wellness content.
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

## HARD GATES (Health Content Safety)
Check for the following violations. If ANY violation is found, list it in "hard_gate_violations":
- MEDICAL_CLAIM_RISK: Claims that a product cures, treats, or prevents a disease/condition
- UNSUPPORTED_EFFICACY: Claims like "통증이 싹 사라진다", "기적", "완치" without evidence
- FAKE_TESTIMONIAL: Invented customer stories or fake before/after results
- FAKE_AUTHORITY: Made-up credentials, fake expert endorsements
- UNSUPPORTED_NUMERICAL_CLAIM: Made-up statistics, review counts, or sales numbers

Calculate 'total_score' as the average of all 10 dimensions.
Set 'is_approved' to true ONLY if total_score >= 85 AND factual_safety >= 90 AND hard_gate_violations is empty.
If is_approved is false, provide a brief 'rejection_reason'.

Return ONLY valid JSON:
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
  "rejection_reason": null,
  "hard_gate_violations": []
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
            
            violations = result.get("hard_gate_violations", [])
            is_approved = result.get("is_approved", False)
            
            # Enforce hard gate regardless of LLM's own approval
            if violations:
                is_approved = False
                
            return ScriptScore(
                hook_strength=result.get("hook_strength", 0),
                target_specificity=result.get("target_specificity", 0),
                clarity=result.get("clarity", 0),
                curiosity=result.get("curiosity", 0),
                credibility=result.get("credibility", 0),
                emotional_relevance=result.get("emotional_relevance", 0),
                product_relevance=result.get("product_relevance", 0),
                pacing=result.get("pacing", 0),
                cta_strength=result.get("cta_strength", 0),
                factual_safety=result.get("factual_safety", 0),
                total_score=result.get("total_score", 0),
                is_approved=is_approved,
                rejection_reason=result.get("rejection_reason"),
                hard_gate_violations=violations,
            )
        except Exception as e:
            logger.error(f"Script evaluation failed: {e}")
            return ScriptScore(
                hook_strength=0, target_specificity=0, clarity=0, curiosity=0, credibility=0, 
                emotional_relevance=0, product_relevance=0, pacing=0, cta_strength=0, 
                factual_safety=0, total_score=0, is_approved=False, 
                rejection_reason="Evaluation API failed",
                hard_gate_violations=[],
            )
