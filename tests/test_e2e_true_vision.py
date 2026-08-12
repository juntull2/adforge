import os
import sys
import logging
from pathlib import Path
import traceback

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.schemas import SceneIntent
from intelligence.semantic_matcher import SemanticMatcher
from core.logging import logger
from pipelines.full_pipeline import FullPipeline

def setup_test_logging():
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] [%(name)s] - %(message)s')
    handler.setFormatter(formatter)
    
    # Remove existing handlers to avoid duplicates
    if logger.hasHandlers():
        logger.handlers.clear()
        
    logger.addHandler(handler)


def test_scene(scene: SceneIntent, matcher: SemanticMatcher):
    print("\n" + "="*80)
    print(f"🎬 TESTING SCENE: {scene.scene_id}")
    print(f"NARRATION: {scene.narration}")
    print(f"HARD REQUIREMENTS: {scene.hard_requirements}")
    print("="*80)
    
    best_assets, debug_info = matcher.find_best_asset_for_scene(scene)
    
    print("\n" + "-"*80)
    print(f"🔍 CANDIDATE EVALUATION LOG ({debug_info.candidate_count} found)")
    print("-"*80)
    
    for idx, c in enumerate(debug_info.candidates, 1):
        print(f"\n[{idx}] URL: {c.url}")
        print(f"    Title: {c.title}")
        if c.pre_filter_score > 0:
            print(f"    Pre-Filter Score: {c.pre_filter_score}")
        print(f"    Total Score: {c.total_score}")
        print(f"    Decision: {c.decision}")
        if c.reject_reason:
            print(f"    Reject Reason: {c.reject_reason}")
            
    if best_assets:
        selected = best_assets[0]
        print("\n" + "="*80)
        print("✅ FINAL DECISION: PASS")
        print(f"SELECTED URL: {selected.url}")
        print(f"DOWNLOAD URL: {selected.download_url}")
        print(f"SCORE: {selected.score.total_score}")
        print("="*80)
        return selected
    else:
        print("\n" + "="*80)
        print("❌ FINAL DECISION: FAILED (No asset met hard requirements)")
        print("="*80)
        return None

def main():
    setup_test_logging()
    
    matcher = SemanticMatcher()
    
    # Scene 1: Neck pain at computer
    scene_01 = SceneIntent(
        scene_id="scene_01",
        narration="하루 종일 컴퓨터 앞에 앉아 목이 뻐근하죠?",
        subject="person",
        action="neck discomfort massage",
        object="computer",
        avoid=["smiling", "happy", "empty room"],
        hard_requirements={
            "subject": "person",
            "action": "neck or shoulder discomfort",
            "object": "computer or desk"
        }
    )
    
    # Scene 2: Cold air conditioner
    scene_02 = SceneIntent(
        scene_id="scene_02",
        narration="차가운 에어컨 바람까지 계속 맞으면 더 불편해집니다.",
        subject="person",
        action="shivering cold discomfort",
        object="air conditioner",
        avoid=["winter outdoor", "snow", "happy"],
        hard_requirements={
            "subject": "person",
            "action": "shivering or feeling cold",
            "context": "indoor air conditioner"
        }
    )
    
    print("\n🚀 STARTING TRUE VISION E2E TEST\n")
    
    selected_1 = test_scene(scene_01, matcher)
    selected_2 = test_scene(scene_02, matcher)
    
    pipeline = FullPipeline("job_true_vision_test")
    import os
    os.makedirs(f"outputs/job_true_vision_test/assets", exist_ok=True)
    
    if selected_1:
        print("\n📥 Downloading Scene 1...")
        pipeline._download_asset(selected_1, "job_true_vision_test", "scene_01")
        
    if selected_2:
        print("\n📥 Downloading Scene 2...")
        pipeline._download_asset(selected_2, "job_true_vision_test", "scene_02")
        
    print("\n🎉 TEST COMPLETE")

if __name__ == "__main__":
    main()
