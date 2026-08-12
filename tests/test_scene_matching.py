import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.schemas import SceneIntent
from intelligence.semantic_matcher import SemanticMatcher

def main():
    scene = SceneIntent(
        scene_id="scene_01",
        narration="출근길 지하철에서 더위 때문에 땀을 많이 흘리는 직장인이라면",
        subject="office worker",
        action="sweating",
        location="subway",
        object="smartphone",
        emotion="uncomfortable",
        context="hot summer commute",
        visual_goal="A young office worker commuting in a subway during hot weather, visibly uncomfortable because of heat.",
        avoid=["beach", "vacation"]
    )
    
    matcher = SemanticMatcher()
    
    print("Testing query generation...")
    queries = matcher._generate_search_queries(scene, [])
    print(f"Generated queries: {queries}")
    
    print("\nTesting full search loop (Requires Pexels/Pixabay keys in .env)...")
    best_asset, all_evaluated = matcher.find_best_asset_for_scene(scene)
    
    if best_asset:
        print(f"\nBest Asset Found: {best_asset.provider} - {best_asset.asset_id}")
        print(f"URL: {best_asset.url}")
        print(f"Resolution: {best_asset.width}x{best_asset.height} ({best_asset.orientation})")
        print(f"Score: {best_asset.score.total_score}")
    else:
        print("\nNo asset found (Check API keys or query logic).")

if __name__ == "__main__":
    main()
