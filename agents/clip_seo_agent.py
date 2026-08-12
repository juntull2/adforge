import json
from openai import OpenAI
from core.config import config
from core.schemas import ProductInfo, AudienceProfile, ClipOptimizationResult
from core.logging import logger

class ClipSEOAgent:
    def __init__(self, api_key: str = None, base_url: str = "https://integrate.api.nvidia.com/v1", model: str = "meta/llama-3.1-70b-instruct"):
        key = api_key or config.NVIDIA_API_KEY
        self.client = OpenAI(api_key=key, base_url=base_url)
        self.model = model

    def generate_seo_metadata(self, product: ProductInfo, audience: AudienceProfile, script_title: str) -> ClipOptimizationResult:
        logger.info(f"Generating Clip SEO metadata for {product.name}...")
        
        prompt = f"""You are a Naver Clip SEO Expert.
Given the product, audience, and the video's script title, generate optimized metadata for Naver Clip.

Product: {product.name} ({product.category})
Description: {product.description}
Audience: {audience.age_group} ({audience.gender}), Core Problem: {audience.core_problem}
Video Title (from Script): "{script_title}"

Task:
1. Generate an optimized, click-worthy Title for the Naver Clip (can be based on the script title).
2. Generate a 2-3 sentence description with a clear CTA.
3. Generate exactly 10 relevant hashtags (mix of core product, problem, audience, and context). Do not include the '#' symbol.
4. Provide a theoretical Optimization Score (0-100) based on keyword relevance, audience fit, and title hook strength. Break down the score into 'title_hook', 'keyword_relevance', 'audience_fit'.
5. Provide 2-3 brief improvement suggestions for the user.

Return ONLY valid JSON matching this schema:
{{
  "title": "Optimized Title",
  "description": "Video description...",
  "hashtags": ["tag1", "tag2"],
  "optimization_score": 92,
  "score_breakdown": {{
    "title_hook": 95,
    "keyword_relevance": 90,
    "audience_fit": 91
  }},
  "improvement_suggestions": [
    "Suggestion 1"
  ]
}}
"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.7,
                timeout=15
            )
            result = json.loads(response.choices[0].message.content)
            
            return ClipOptimizationResult(
                title=result.get("title", script_title),
                description=result.get("description", ""),
                hashtags=result.get("hashtags", []),
                optimization_score=result.get("optimization_score", 0),
                score_breakdown=result.get("score_breakdown", {}),
                improvement_suggestions=result.get("improvement_suggestions", [])
            )
        except Exception as e:
            logger.error(f"Failed to generate SEO metadata: {e}")
            return ClipOptimizationResult(
                title=script_title,
                description="",
                hashtags=[product.name],
                optimization_score=0,
                score_breakdown={},
                improvement_suggestions=["Failed to generate AI SEO metadata."]
            )
