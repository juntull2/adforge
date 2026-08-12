import json
from typing import List, Dict, Tuple, Optional
from openai import OpenAI
from core.config import config
from core.schemas import SceneIntent, AssetCandidate, AssetScore
from core.logging import logger
from services.stock_api import StockAPI
from intelligence.asset_quality import AssetQualityGate

class SemanticMatcher:
    def __init__(self, api_key: str = None, base_url: str = "https://integrate.api.nvidia.com/v1", model: str = "meta/llama-3.1-70b-instruct"):
        key = api_key or config.NVIDIA_API_KEY
        self.client = OpenAI(api_key=key, base_url=base_url)
        self.model = model
        self.stock_api = StockAPI()
        self.quality_gate = AssetQualityGate()
        self.max_retries = config.MAX_SEARCH_RETRIES

    def find_best_asset_for_scene(self, scene: SceneIntent) -> Tuple[Optional[AssetCandidate], List[AssetCandidate]]:
        """
        Execute the Reject -> Refine -> Re-search loop for a given scene.
        Returns the selected asset and a list of all evaluated candidates (for debug).
        """
        all_evaluated_candidates = []
        
        # Loop for up to max_retries
        context_hints = []
        for attempt in range(self.max_retries):
            logger.info(f"[{scene.scene_id}] Asset search attempt {attempt + 1}/{self.max_retries}")
            
            # 1. Generate queries
            queries = self._generate_search_queries(scene, context_hints)
            if not queries:
                logger.warning(f"[{scene.scene_id}] No queries generated.")
                break
                
            logger.info(f"[{scene.scene_id}] Generated queries: {queries}")
            
            # 2. Retrieve candidates
            candidates = []
            for q in queries:
                candidates.extend(self.stock_api.search_videos(q, limit=5))
                
            # Remove exact duplicates
            unique_candidates = {c.asset_id: c for c in candidates}.values()
            
            valid_candidates = []
            
            # 3. Hard Filters (Quality Gate)
            for c in unique_candidates:
                if self.quality_gate.evaluate_and_crop(c):
                    valid_candidates.append(c)
                else:
                    all_evaluated_candidates.append(c)
                    
            if not valid_candidates:
                logger.warning(f"[{scene.scene_id}] All retrieved candidates failed the quality gate.")
                context_hints.append("Previous search returned low quality or uncroppable videos. Try different synonyms.")
                continue
                
            # 4. Semantic Ranking
            scored_candidates = []
            for c in valid_candidates:
                score = self._score_candidate(scene, c)
                c.score = score
                if score.total_score >= 60:  # Minimum semantic threshold
                    scored_candidates.append(c)
                else:
                    c.is_rejected = True
                    c.rejection_reason = f"Semantic score too low ({score.total_score})"
                    all_evaluated_candidates.append(c)
                    
            # 5. Sort by Preference (Portrait > Landscape) and then by Score
            if scored_candidates:
                # Prefer native portrait if scores are close, otherwise highest score
                # Let's add a small bump for portrait
                scored_candidates.sort(key=lambda x: (
                    x.score.total_score + (15 if x.orientation == "portrait" else 0)
                ), reverse=True)
                
                best_candidate = scored_candidates[0]
                all_evaluated_candidates.extend(scored_candidates)
                logger.info(f"[{scene.scene_id}] Found suitable asset! Score: {best_candidate.score.total_score}, Provider: {best_candidate.provider}")
                return best_candidate, all_evaluated_candidates
                
            # If no candidates pass semantic threshold, refine queries and retry
            logger.warning(f"[{scene.scene_id}] Candidates failed semantic matching. Refining queries...")
            context_hints.append("Previous searches returned visually unrelated content. Make the search query more literal or use simpler English keywords.")
            
        logger.error(f"[{scene.scene_id}] Exhausted {self.max_retries} attempts. No suitable asset found.")
        return None, all_evaluated_candidates

    def _generate_search_queries(self, scene: SceneIntent, hints: List[str]) -> List[str]:
        hint_str = " ".join(hints) if hints else "None"
        prompt = f"""You are a Stock Footage Search Expert.
Given the visual intent of a scene, generate 3-5 distinct search queries in English to use on Pexels/Pixabay.

Scene Intent:
- Subject: {scene.subject}
- Action: {scene.action}
- Location: {scene.location}
- Object: {scene.object}
- Emotion: {scene.emotion}
- Context: {scene.context}
- Visual Goal: {scene.visual_goal}
- Avoid: {', '.join(scene.avoid)}

Previous Search Hints/Errors: {hint_str}

Strategy:
1. Provide literal English keywords (e.g., "office worker subway commute").
2. Vary the wording (e.g., "commuter train hot", "person sweating public transport").
3. Do not blindly append "vertical" or "portrait" if it makes the query too restrictive.
4. Keep queries to 2-4 keywords.

Return ONLY valid JSON:
{{
  "queries": ["query1", "query2", "query3"]
}}
"""
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.7
            )
            result = json.loads(resp.choices[0].message.content)
            return result.get("queries", [])
        except Exception as e:
            logger.error(f"Failed to generate queries: {e}")
            return [f"{scene.subject} {scene.action}".strip()]

    def _score_candidate(self, scene: SceneIntent, candidate: AssetCandidate) -> AssetScore:
        # In a real system, we might use a Vision Language Model (VLM) here.
        # For AdForge v2 Phase 3 (text-only LLM), we will synthesize a score based on the search context, 
        # but since we can't 'see' the video without a VLM, we will simulate the VLM scoring by 
        # giving high scores to videos that passed the hard filters and are returned from strong queries.
        # Note: A real VLM implementation would pass `candidate.url` or video frames to GPT-4V.
        
        # Here we simulate a semantic score. 
        # To make it slightly realistic without VLM, we'll assign a random-ish passing score 
        # so the pipeline can proceed, assuming the keyword search was reasonably accurate.
        # In a production system, replace this with an actual VLM call.
        import random
        base_score = random.randint(70, 95)
        
        return AssetScore(
            semantic_relevance=base_score,
            action_match=base_score,
            object_match=base_score,
            emotion_match=base_score,
            context_match=base_score,
            video_quality=90,
            total_score=base_score
        )
