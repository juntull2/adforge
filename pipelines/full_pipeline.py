import json
from pathlib import Path
from typing import Dict, Any, Optional
import uuid
import datetime
from core.schemas import ProductInfo, AudienceProfile, GenerationReport, BrandProfile
from agents.script_agent import ScriptAgent
from agents.clip_seo_agent import ClipSEOAgent
from intelligence.semantic_matcher import SemanticMatcher
from intelligence.benchmark_intelligence import BenchmarkRetriever
from core.logging import logger

class FullPipeline:
    def __init__(self, api_key: str = None):
        self.script_agent = ScriptAgent(api_key=api_key)
        self.semantic_matcher = SemanticMatcher(api_key=api_key)
        self.seo_agent = ClipSEOAgent(api_key=api_key)
        self.benchmark_retriever = BenchmarkRetriever()

    def run_generation(self, product: ProductInfo, audience: AudienceProfile, brand: BrandProfile) -> Optional[GenerationReport]:
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        logger.info(f"Starting Generation Job [{job_id}] for {product.name} (Brand: {brand.brand_name})")
        
        # 1. Benchmark Intelligence
        logger.info(f"[{job_id}] Phase 1: Benchmark Intelligence")
        topic_keywords = [product.category, audience.core_problem, product.name]
        benchmark_results = self.benchmark_retriever.get_relevant_patterns_for_topic(topic_keywords)
        
        hook_patterns = [p.name for p in benchmark_results.get("hook_patterns", [])]
        visual_patterns = [p.name for p in benchmark_results.get("visual_patterns", [])]
        
        used_patterns = hook_patterns + visual_patterns
        logger.info(f"[{job_id}] Retrieved {len(used_patterns)} benchmark patterns to inform generation.")

        # 2. Script Generation
        logger.info(f"[{job_id}] Phase 2: Script Intelligence")
        script = self.script_agent.generate_script(product, audience, benchmark_patterns=hook_patterns)
        if not script:
            logger.error(f"[{job_id}] Script generation failed.")
            return None
            
        logger.info(f"[{job_id}] Script generated successfully: {script.title}")
        
        # 3. Scene Matching (Phase 3 & 4)
        logger.info(f"[{job_id}] Phase 3 & 4: Semantic Scene Matching & Quality Gate")
        scene_results = []
        scene_debugs = []
        visual_score_total = 0
        valid_scenes = 0
        
        assets_dir = Path("outputs") / job_id / "assets"
        import os
        os.makedirs(assets_dir, exist_ok=True)
        
        for idx, scene in enumerate(script.body, 1):
            best_assets, debug_info = self.semantic_matcher.find_best_asset_for_scene(scene, benchmark_visuals=visual_patterns)
            scene_debugs.append(debug_info)
            
            selected_asset = None
            local_path = None
            download_status = "ASSET_SELECTION_FAILED"
            
            if best_assets:
                download_status = "DOWNLOAD_FAILED"
                # Try downloading from top to bottom
                for asset in best_assets:
                    if not asset.download_url:
                        continue
                        
                    file_name = f"{scene.scene_id}.mp4"
                    output_path = assets_dir / file_name
                    logger.info(f"[{job_id}] Downloading {asset.url} to {output_path}...")
                    
                    if self._download_asset(asset.download_url, str(output_path)):
                        selected_asset = asset
                        local_path = str(output_path).replace("\\", "/")
                        download_status = "SUCCESS"
                        logger.info(f"[{job_id}] Successfully downloaded {scene.scene_id}.mp4")
                        break
                        
            if selected_asset:
                scene_results.append({
                    "scene_id": scene.scene_id,
                    "narration": scene.narration,
                    "query": " | ".join(debug_info.search_queries), 
                    "provider": selected_asset.provider,
                    "asset_id": selected_asset.asset_id,
                    "source_url": selected_asset.url,
                    "download_url": selected_asset.download_url,
                    "local_path": local_path,
                    "download_status": download_status,
                    "score": selected_asset.score.total_score if selected_asset.score else 0,
                    "selected_asset": selected_asset.model_dump(),
                    "selection_reason": "Highest semantic score after quality and metadata gates"
                })
                visual_score_total += (selected_asset.score.total_score if selected_asset.score else 0)
                valid_scenes += 1
            else:
                scene_results.append({
                    "scene_id": scene.scene_id,
                    "narration": scene.narration,
                    "download_status": download_status,
                    "error": "No suitable asset found or all downloads failed."
                })
                
        visual_score = (visual_score_total // valid_scenes) if valid_scenes > 0 else 0
        
        # 4. SEO Optimization (Phase 5)
        logger.info(f"[{job_id}] Phase 5: Naver Clip Intelligence")
        seo_meta = self.seo_agent.generate_seo_metadata(product, audience, script.title)
        
        # 5. Synthesize Report
        report = GenerationReport(
            job_id=job_id,
            brand_id=brand.brand_id,
            product=product.name,
            platform="naver_clip",
            duration=script.duration_target,
            resolution="1080x1920",
            aspect_ratio="9:16",
            hook_strategy=script.hook_strategy,
            script_score=90, 
            visual_score=visual_score,
            clip_optimization_score=seo_meta.optimization_score,
            scenes=scene_results,
            benchmark_patterns_used=used_patterns
        )
        
        # Save output
        self._save_outputs(job_id, script, seo_meta, report, scene_debugs)
        logger.info(f"[{job_id}] Pipeline complete!")
        return report
        
    def _download_asset(self, url: str, output_path: str) -> bool:
        import requests
        import shutil
        try:
            with requests.get(url, stream=True, timeout=30, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}) as r:
                r.raise_for_status()
                with open(output_path, 'wb') as f:
                    shutil.copyfileobj(r.raw, f)
            return True
        except Exception as e:
            logger.error(f"Download failed for {url}: {e}")
            return False

    def _save_outputs(self, job_id, script, seo_meta, report, scene_debugs):
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
            
        with open(out_dir / "benchmark_usage.json", "w", encoding="utf-8") as f:
            f.write(json.dumps({"used_patterns": report.benchmark_patterns_used}, ensure_ascii=False, indent=2))
            
        with open(out_dir / "scene_debug.json", "w", encoding="utf-8") as f:
            debug_list = [d.model_dump() for d in scene_debugs]
            f.write(json.dumps(debug_list, ensure_ascii=False, indent=2))
