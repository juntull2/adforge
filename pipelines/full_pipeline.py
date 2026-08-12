import json
from pathlib import Path
from typing import Dict, Any, Optional
import uuid
import datetime
from core.schemas import ProductInfo, AudienceProfile, GenerationReport, VideoPlan
from agents.script_agent import ScriptAgent
from agents.clip_seo_agent import ClipSEOAgent
from intelligence.semantic_matcher import SemanticMatcher
from core.logging import logger

class FullPipeline:
    def __init__(self, api_key: str = None):
        self.script_agent = ScriptAgent(api_key=api_key)
        self.semantic_matcher = SemanticMatcher(api_key=api_key)
        self.seo_agent = ClipSEOAgent(api_key=api_key)

    def run_generation(self, product: ProductInfo, audience: AudienceProfile) -> Optional[GenerationReport]:
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        logger.info(f"Starting Generation Job [{job_id}] for {product.name}")
        
        # 1. Script Generation
        logger.info(f"[{job_id}] Phase 2: Script Intelligence")
        script = self.script_agent.generate_script(product, audience)
        if not script:
            logger.error(f"[{job_id}] Script generation failed.")
            return None
            
        logger.info(f"[{job_id}] Script generated successfully: {script.title}")
        
        # 2. Scene Matching (Phase 3 & 4)
        logger.info(f"[{job_id}] Phase 3 & 4: Semantic Scene Matching & Quality Gate")
        scene_results = []
        visual_score_total = 0
        valid_scenes = 0
        
        for scene in script.body:
            best_asset, all_candidates = self.semantic_matcher.find_best_asset_for_scene(scene)
            
            if best_asset:
                scene_results.append({
                    "scene_id": scene.scene_id,
                    "narration": scene.narration,
                    "queries": [], # In a real scenario, we'd track the exact query that found it
                    "selected_asset": best_asset.dict(),
                    "semantic_score": best_asset.score.total_score if best_asset.score else 0,
                    "quality_score": best_asset.score.video_quality if best_asset.score else 0,
                    "selection_reason": "Highest semantic score after quality gate"
                })
                visual_score_total += (best_asset.score.total_score if best_asset.score else 0)
                valid_scenes += 1
            else:
                scene_results.append({
                    "scene_id": scene.scene_id,
                    "narration": scene.narration,
                    "error": "No suitable asset found"
                })
                
        visual_score = (visual_score_total // valid_scenes) if valid_scenes > 0 else 0
        
        # 3. SEO Optimization (Phase 5)
        logger.info(f"[{job_id}] Phase 5: Naver Clip Intelligence")
        seo_meta = self.seo_agent.generate_seo_metadata(product, audience, script.title)
        
        # 4. Synthesize Report (Phase 6)
        report = GenerationReport(
            job_id=job_id,
            product=product.name,
            platform="naver_clip",
            duration=script.duration_target,
            resolution="1080x1920",
            aspect_ratio="9:16",
            hook_strategy=script.hook_strategy,
            script_score=90, # From quality agent, ideally threaded through
            visual_score=visual_score,
            clip_optimization_score=seo_meta.optimization_score,
            scenes=scene_results
        )
        
        # Save output
        self._save_outputs(job_id, script, seo_meta, report)
        logger.info(f"[{job_id}] Pipeline complete!")
        return report

    def _save_outputs(self, job_id, script, seo_meta, report):
        import os
        out_dir = Path("outputs") / job_id
        os.makedirs(out_dir, exist_ok=True)
        
        # Pydantic v2 compliant dump
        with open(out_dir / "script.json", "w", encoding="utf-8") as f:
            f.write(json.dumps(script.model_dump(), ensure_ascii=False, indent=2))
            
        with open(out_dir / "seo_metadata.json", "w", encoding="utf-8") as f:
            f.write(json.dumps(seo_meta.model_dump(), ensure_ascii=False, indent=2))
            
        with open(out_dir / "generation_report.json", "w", encoding="utf-8") as f:
            f.write(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
