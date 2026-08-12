import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.schemas import ProductInfo, AudienceProfile
from agents.script_agent import ScriptAgent

def main():
    product = ProductInfo(
        name="휴대용 선풍기",
        category="가전/여름용품",
        description="출퇴근길 더위를 식혀주는 컴팩트한 휴대용 무선 선풍기"
    )
    audience = AudienceProfile(
        age_group="3050",
        gender="all",
        core_problem="출근길 지하철에서 땀이 너무 많이 나서 불쾌함"
    )
    
    agent = ScriptAgent(model="meta/llama-3.1-70b-instruct")
    
    # Try testing script generation
    result = agent.generate_script(product, audience)
    if result:
        print(f"Title: {result.title}")
        print(f"Hook Strategy: {result.hook_strategy}")
        print(f"Hook: {result.hook}")
        for scene in result.body:
            print(f"[{scene.scene_id}] {scene.narration} (Search: {scene.search_intent})")
        print(f"CTA: {result.cta}")
    else:
        print("Failed to generate script.")

if __name__ == "__main__":
    main()
