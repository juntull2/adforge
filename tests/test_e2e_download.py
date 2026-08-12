import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.schemas import SceneIntent, ProductInfo, AudienceProfile, BrandProfile
from pipelines.full_pipeline import FullPipeline
from core.logging import logger

def main():
    logger.info("Starting E2E Download Acceptance Test...")
    pipeline = FullPipeline()
    
    # We mock the Script output to exactly match the user's acceptance test prompt
    class MockScript:
        title = "Neck Pain Product Script"
        duration_target = 15
        hook_strategy = "Problem Solution"
        body = [
            SceneIntent(
                scene_id="scene_01",
                narration="하루 종일 컴퓨터 앞에 앉아 목이 뻐근하죠?",
                subject="office worker", age_group="adult",
                action="massaging stiff neck", location="office",
                object="computer", body_part="neck", symptom="stiffness",
                emotion="pain", context="working at desk",
                avoid=["gym", "laughing"], visual_goal="Office worker massaging stiff neck at computer desk"
            ),
            SceneIntent(
                scene_id="scene_02",
                narration="차가운 에어컨 바람까지 계속 맞으면 더 불편해집니다.",
                subject="person", age_group="adult",
                action="shivering holding shoulders", location="indoors",
                object="air conditioner", body_part="shoulder", symptom="cold",
                emotion="discomfort", context="feeling cold",
                avoid=["summer beach", "sweating"], visual_goal="Person shivering under air conditioner"
            ),
            SceneIntent(
                scene_id="scene_03",
                narration="그래서 저는 일할 때 이것을 챙겨요.",
                subject="person", age_group="adult",
                action="showing a product smiling", location="office",
                object="product box", body_part="hands", symptom="",
                emotion="happy", context="solution",
                avoid=["sadness"], visual_goal="Person holding and showing a product happily"
            )
        ]
        
        def model_dump(self):
            return {
                "title": self.title,
                "duration_target": self.duration_target,
                "hook_strategy": self.hook_strategy,
                "body": [s.model_dump() for s in self.body]
            }
        
    # We will override the script agent to just return our mock
    pipeline.script_agent.generate_script = lambda *args, **kwargs: MockScript()
    
    from core.schemas import ClipOptimizationResult
    pipeline.seo_agent.generate_seo_metadata = lambda *args, **kwargs: ClipOptimizationResult(
        title="Mock Title", description="Mock Desc", hashtags=["mock"],
        optimization_score=100, score_breakdown={}, improvement_suggestions=[]
    )
    
    product = ProductInfo(name="Neck Massager", description="Massager", category="Health", key_features=["Heating", "Massage"])
    audience = AudienceProfile(core_problem="Stiff neck from office work", age_group="30s", gender="Any")
    brand = BrandProfile(brand_id="test", brand_name="TestBrand", brand_tone="Friendly")
    
    report = pipeline.run_generation(product, audience, brand)
    
    if not report:
        logger.error("Pipeline failed to generate report.")
        sys.exit(1)
        
    job_id = report.job_id
    assets_dir = Path("outputs") / job_id / "assets"
    
    # Verify outputs
    expected_files = ["scene_01.mp4", "scene_02.mp4", "scene_03.mp4"]
    all_passed = True
    
    logger.info("=" * 50)
    logger.info("Verifying Downloads...")
    logger.info("=" * 50)
    
    for fname in expected_files:
        fpath = assets_dir / fname
        if not fpath.exists() or fpath.stat().st_size == 0:
            all_passed = False
            
    if all_passed:
        logger.info("Acceptance Test PASSED.")
    else:
        logger.error("Acceptance Test FAILED. Some files are missing or 0 bytes.")
        
    logger.info("\n" + "=" * 50)
    logger.info("PRECISION TEST RESULTS")
    logger.info("=" * 50)
    
    for scene in report.scenes:
        logger.info(f"NARRATION: {scene.get('narration')}")
        logger.info(f"QUERY: {scene.get('query')}")
        if scene.get("download_status") == "SUCCESS":
            logger.info(f"SELECTED ASSET: {scene.get('source_url')}")
            logger.info(f"SCORE: {scene.get('score')}")
            logger.info(f"DOWNLOAD PATH: {scene.get('local_path')}")
        else:
            logger.info(f"STATUS: {scene.get('download_status')}")
            logger.info(f"ERROR: {scene.get('error', 'No suitable asset')}")
        logger.info("-" * 30)

if __name__ == "__main__":
    main()
