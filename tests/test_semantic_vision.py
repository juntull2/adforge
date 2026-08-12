import os
import sys
from pathlib import Path
from unittest.mock import patch
import json

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.schemas import SceneIntent, AssetCandidate
from intelligence.semantic_matcher import SemanticMatcher
from core.logging import logger
from core.config import config

def run_test(scene: SceneIntent, mock_candidates: list, mock_vlm_func, test_name: str):
    logger.info(f"--- Starting Test: {test_name} ---")
    
    matcher = SemanticMatcher(vision_model="meta/llama-3.2-90b-vision-instruct")

    call_count = {"count": 0}
    def mock_search_videos(*args, **kwargs):
        if call_count["count"] == 0:
            call_count["count"] += 1
            return mock_candidates
        return []
        
    def mock_generate_queries(*args, **kwargs):
        return ["office worker sitting at computer touching neck"]

    with patch.object(matcher.stock_api, 'search_videos', side_effect=mock_search_videos), \
         patch.object(matcher, '_evaluate_frames_vlm', side_effect=mock_vlm_func), \
         patch.object(matcher, '_generate_search_queries', side_effect=mock_generate_queries):
         
        best_asset, debug_info = matcher.find_best_asset_for_scene(scene)
        
        print("\n" + "="*70)
        print(f"TEST: {test_name}")
        print(f"FINAL DECISION: {debug_info.final_decision}")
        if best_asset:
            print(f"SELECTED ASSET ID: {best_asset.asset_id} (Expected to match exactly)")
            # Validate ID matching requested by user
            assert best_asset.asset_id == debug_info.selected_asset.asset_id
            print(f"SELECTED ASSET SCORE: {best_asset.score.total_score}")
        else:
            print("NO ASSET SELECTED (None returned)")
        
        print("\n--- CANDIDATE EVALUATION LIFECYCLE ---")
        for i, c in enumerate(debug_info.candidates, 1):
            print(f"Candidate {c.url} (Title: {c.title})")
            print(f"  > Pre-Filter Score : {c.pre_filter_score}")
            print(f"  > VLM Score        : {c.total_score}")
            print(f"  > Decision         : {c.decision}")
            if c.decision != "SELECTED":
                print(f"  > Reject Reason    : {c.reject_reason}")
            print("-" * 50)

        print("="*70 + "\n")
        return best_asset, debug_info

def main():
    scene = SceneIntent(
        scene_id="test_scene_01",
        narration="하루 종일 컴퓨터 앞에 앉아 목이 뻐근하죠?",
        subject="office worker",
        age_group="middle aged",
        action="sitting at computer touching neck in pain",
        location="office",
        object="computer",
        body_part="neck",
        symptom="stiffness, pain",
        emotion="discomfort, tired",
        context="working long hours",
        visual_goal="An office worker sitting at a desk looking tired and rubbing their stiff neck",
        avoid=["beach", "vacation", "running outdoors", "food", "empty room"]
    )
    
    # --- TEST 1: False Positives & Early Exit Logic ---
    mock_candidates_1 = [
        AssetCandidate(
            provider="mock", asset_id="id_perfect", url="url_perfect", download_url="", width=1080, height=1920, duration=5.0, orientation="portrait",
            title="office worker neck pain computer", thumbnail_urls=["perfect.jpg"]
        ),
        AssetCandidate(
            provider="mock", asset_id="id_good_but_not_90", url="url_85", download_url="", width=1080, height=1920, duration=5.0, orientation="portrait",
            title="office worker neck pain computer", thumbnail_urls=["85.jpg"]
        ),
        AssetCandidate(
            provider="mock", asset_id="id_wrong_action", url="url_wrong_action", download_url="", width=1080, height=1920, duration=5.0, orientation="portrait",
            title="office worker happy computer", thumbnail_urls=["wrong_action.jpg"] # 사무실이지만 행동이 다름
        ),
        AssetCandidate(
            provider="mock", asset_id="id_wrong_place", url="url_wrong_place", download_url="", width=1080, height=1920, duration=5.0, orientation="portrait",
            title="man neck pain beach", thumbnail_urls=["wrong_place.jpg"] # 행동은 맞지만 장소가 다름
        ),
        AssetCandidate(
            provider="mock", asset_id="id_no_object", url="url_no_object", download_url="", width=1080, height=1920, duration=5.0, orientation="portrait",
            title="office worker neck pain desk", thumbnail_urls=["no_object.jpg"] # 사람은 있지만 object(computer)가 없음
        ),
        AssetCandidate(
            provider="mock", asset_id="id_no_person", url="url_no_person", download_url="", width=1080, height=1920, duration=5.0, orientation="portrait",
            title="office desk computer", thumbnail_urls=["no_person.jpg"] # object는 있지만 사람이 없음
        )
    ]
    
    def mock_vlm_1(thumbnail_urls, scene):
        url = thumbnail_urls[0] if thumbnail_urls else ""
        if url == "perfect.jpg":
            return {"total_score": 95, "avoid_match": False, "reasoning": "Perfect match."}
        elif url == "85.jpg":
            return {"total_score": 85, "avoid_match": False, "reasoning": "Good match, but not exceptional."}
        elif url == "wrong_action.jpg":
            return {"total_score": 40, "avoid_match": True, "reasoning": "Smiling, not in pain."}
        elif url == "wrong_place.jpg":
            return {"total_score": 50, "avoid_match": True, "reasoning": "At the beach, not office."}
        elif url == "no_object.jpg":
            return {"total_score": 60, "avoid_match": True, "reasoning": "Missing required object (computer)."}
        elif url == "no_person.jpg":
            return {"total_score": 10, "avoid_match": True, "reasoning": "Missing REQUIRED human."}
        return {"total_score": 0, "avoid_match": True, "reasoning": "Unknown"}

    # Test 1: Should exit early with 'id_perfect' because it scores >= 90.
    # Note: candidates are evaluated in order of Pre-Filter score.
    # We set pre_filter scores based on title matching. 'perfect.jpg' and '85.jpg' have the exact same title.
    # The list order is preserved for equal pre-filter scores. 
    # Let's run it.
    run_test(scene, mock_candidates_1, mock_vlm_1, "False Positives & 90+ Early Exit")


    # --- TEST 2: All Fail Integration Test ---
    # We want to ensure that if ALL candidates fail, it returns FAILED/None and NEVER falls back.
    mock_candidates_2 = [
        AssetCandidate(
            provider="mock", asset_id="id_fail_1", url="url_fail_1", download_url="", width=1080, height=1920, duration=5.0, orientation="portrait",
            title="office worker neck pain computer", thumbnail_urls=["85.jpg"] # Will score 74 this time
        ),
        AssetCandidate(
            provider="mock", asset_id="id_fail_2", url="url_fail_2", download_url="", width=1080, height=1920, duration=5.0, orientation="portrait",
            title="office worker happy computer", thumbnail_urls=["wrong_action.jpg"]
        )
    ]
    
    def mock_vlm_2(thumbnail_urls, scene):
        url = thumbnail_urls[0] if thumbnail_urls else ""
        if url == "85.jpg":
            return {"total_score": 74, "avoid_match": False, "reasoning": "Close, but below threshold (74 < 75)."}
        elif url == "wrong_action.jpg":
            return {"total_score": 40, "avoid_match": True, "reasoning": "Wrong action."}
        return {"total_score": 0, "avoid_match": True, "reasoning": "Unknown"}

    run_test(scene, mock_candidates_2, mock_vlm_2, "ALL FAIL - No Hidden Fallbacks")


if __name__ == "__main__":
    main()
