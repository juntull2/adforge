import os
import sys
import json
from pathlib import Path
from unittest.mock import patch

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.schemas import SceneIntent, AssetCandidate, CandidateDebugInfo
from intelligence.semantic_matcher import SemanticMatcher
from core.config import config
from core.logging import logger

def run_timeout_test(scene: SceneIntent, mock_candidates: list, mock_vlm_func, test_name: str):
    logger.info(f"\n{'='*70}\nStarting Timeout Test: {test_name}\n{'='*70}")
    
    matcher = SemanticMatcher()
    
    call_count = {"count": 0}
    def mock_search_videos(*args, **kwargs):
        if call_count["count"] == 0:
            call_count["count"] += 1
            return mock_candidates
        return []
        
    def mock_generate_queries(*args, **kwargs):
        return ["office worker rubbing stiff shoulder"]

    with patch.object(matcher.stock_api, 'search_videos', side_effect=mock_search_videos), \
         patch.object(matcher, '_evaluate_frames_vlm', side_effect=mock_vlm_func), \
         patch.object(matcher, '_generate_search_queries', side_effect=mock_generate_queries):
         
        best_asset, debug_info = matcher.find_best_asset_for_scene(scene)
        
        print(f"\nTEST: {test_name}")
        print(f"FINAL DECISION: {debug_info.final_decision}")
        if best_asset:
            print(f"SELECTED ASSET ID: {best_asset.asset_id}")
        else:
            print("NO ASSET SELECTED (None returned) - NO FALLBACK")
            
        print("\n--- CANDIDATE EVALUATION LIFECYCLE ---")
        for i, c in enumerate(debug_info.candidates, 1):
            if c.decision != "REJECTED": # Skip pre-filter rejects for clean logs
                print(f"Candidate {c.url}")
                print(f"  > Decision       : {c.decision}")
                print(f"  > Failure Type   : {c.failure_type}")
                print(f"  > Retry Count    : {c.retry_count}")
                print(f"  > Latency (ms)   : {c.latency_ms}")
                print(f"  > Reject Reason  : {c.reject_reason}")
                print("-" * 50)
        print("="*70)
        return best_asset, debug_info


def main():
    config.MAX_SEARCH_RETRIES = 1
    
    scene = SceneIntent(
        scene_id="test_timeout",
        narration="어깨가 결리는 직장인",
        subject="office worker", age_group="adult",
        action="rubbing stiff shoulder",
        location="office", object="computer", body_part="shoulder",
        symptom="pain", emotion="discomfort", context="working",
        visual_goal="office worker rubbing stiff shoulder",
        avoid=["exercise"]
    )
    
    base_candidate = AssetCandidate(
        provider="mock", asset_id="id_1", url="url_1", download_url="", width=1080, height=1920, duration=5.0, orientation="portrait",
        title="office worker rubbing shoulder", thumbnail_urls=["url_1.jpg"]
    )
    
    # 1. 정상 VLM 응답 -> 정상 asset 선택
    def mock_vlm_normal(thumbnail_urls, scene):
        return {"total_score": 95, "avoid_match": False, "reasoning": "Perfect"}
        
    run_timeout_test(scene, [base_candidate], mock_vlm_normal, "1. Normal VLM Response -> SELECTED")
    
    # 2. VLM timeout 1회 -> retry 성공 -> asset 선택
    call_state = {"attempts": 0}
    def mock_vlm_timeout_once(thumbnail_urls, scene):
        call_state["attempts"] += 1
        if call_state["attempts"] == 1:
            import time
            time.sleep(0.1)
            raise TimeoutError("Request timed out")
        return {"total_score": 95, "avoid_match": False, "reasoning": "Recovered"}
        
    run_timeout_test(scene, [base_candidate], mock_vlm_timeout_once, "2. Timeout 1x -> Retry Success -> SELECTED")
    
    # 3. VLM timeout 2회 -> candidate evaluation failed -> 다음 candidate 평가
    cand_1 = base_candidate.model_copy(update={"asset_id": "fail_cand", "url": "url_fail", "thumbnail_urls": ["url_fail.jpg"]})
    cand_2 = base_candidate.model_copy(update={"asset_id": "success_cand", "url": "url_success", "thumbnail_urls": ["url_success.jpg"]})
    
    call_state_3 = {"fail_attempts": 0}
    def mock_vlm_timeout_twice(thumbnail_urls, scene):
        if "fail" in thumbnail_urls[0]:
            call_state_3["fail_attempts"] += 1
            import time
            time.sleep(0.1)
            raise TimeoutError("Request timed out forever")
        return {"total_score": 90, "avoid_match": False, "reasoning": "Next candidate success"}
        
    run_timeout_test(scene, [cand_1, cand_2], mock_vlm_timeout_twice, "3. Timeout 2x -> EVALUATION_FAILED -> Next Cand SELECTED")
    
    # 4. 모든 candidate timeout -> ASSET_SELECTION_FAILED
    def mock_vlm_always_timeout(thumbnail_urls, scene):
        import time
        time.sleep(0.1)
        raise TimeoutError("Always times out")
        
    run_timeout_test(scene, [cand_1, cand_2], mock_vlm_always_timeout, "4. All Candidates Timeout -> ASSET_SELECTION_FAILED (No Fallback)")


if __name__ == "__main__":
    main()
