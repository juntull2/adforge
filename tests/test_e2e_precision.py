import os
import sys
import json
from pathlib import Path
from datetime import datetime

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.schemas import SceneIntent
from intelligence.semantic_matcher import SemanticMatcher
from core.config import config
from core.logging import logger

def main():
    logger.info("Starting End-to-End Precision Test for Generic Scenes...")
    
    # Override config for faster test execution
    config.MAX_SEARCH_RETRIES = 1
    config.VLM_THRESHOLD = 75 # Keep threshold at 75 for now as requested
    
    matcher = SemanticMatcher()
    
    test_scenes = [
        # 1. Pain (Generic easily polluted by fitness or beach)
        SceneIntent(
            scene_id="scene_01_pain",
            narration="여름철 에어컨 바람에 어깨가 결리고 쑤신다면?",
            subject="middle aged person", age_group="middle aged",
            action="rubbing stiff shoulder in pain",
            location="indoors", object="air conditioner", body_part="shoulder",
            symptom="stiffness", emotion="discomfort",
            context="feeling cold from AC",
            visual_goal="Person rubbing shoulder showing discomfort indoors",
            avoid=["exercise", "sports", "outdoors", "happy"]
        ),
        # 2. Summer (Generic easily polluted by beach vacations when it should be hot home)
        SceneIntent(
            scene_id="scene_02_summer",
            narration="올여름, 집에서도 숨막히는 더위 때문에 잠 못 이루시죠?",
            subject="person", age_group="any",
            action="tossing and turning in bed sweating",
            location="bedroom", object="bed, fan", body_part="",
            symptom="insomnia, heat", emotion="frustrated, exhausted",
            context="hot summer night",
            visual_goal="Person awake in bed looking hot and frustrated",
            avoid=["beach", "pool", "daytime outdoors", "vacation"]
        ),
        # 3. Office (Generic easily polluted by empty desks or happy workers)
        SceneIntent(
            scene_id="scene_03_office",
            narration="사무실에 오래 앉아 있다 보면 허리가 뻐근하게 굳어옵니다.",
            subject="office worker", age_group="adult",
            action="stretching back holding lower back",
            location="office", object="office chair, computer", body_part="lower back",
            symptom="back pain", emotion="tired",
            context="working long hours",
            visual_goal="Office worker standing up and holding lower back in pain",
            avoid=["empty office", "smiling", "exercising in gym"]
        ),
        # 4. Exercise (Generic easily polluted by extreme sports when it should be light senior exercise)
        SceneIntent(
            scene_id="scene_04_exercise",
            narration="무릎 관절이 안 좋을 때는 무리한 운동보다 가벼운 스트레칭이 좋습니다.",
            subject="senior", age_group="senior",
            action="doing light stretching carefully",
            location="living room or park", object="yoga mat", body_part="knee",
            symptom="joint stiffness", emotion="calm, careful",
            context="senior health care",
            visual_goal="Senior person doing gentle stretches carefully",
            avoid=["weightlifting", "running fast", "extreme sports", "young people"]
        ),
        # 5. Beauty (Generic easily polluted by heavy makeup when it should be skincare trouble)
        SceneIntent(
            scene_id="scene_05_beauty",
            narration="거울 볼 때마다 늘어난 눈가 주름 때문에 한숨이 나오시나요?",
            subject="middle aged woman", age_group="middle aged",
            action="touching wrinkles near eyes looking sad",
            location="bathroom or bedroom", object="mirror", body_part="eyes, face",
            symptom="wrinkles", emotion="sad, sighing",
            context="skincare routine",
            visual_goal="Middle-aged woman looking in mirror and touching eye wrinkles sadly",
            avoid=["heavy makeup", "laughing", "fashion model", "teenager"]
        ),
        # 6. Food (Generic easily polluted by restaurant cooking when it should be eating indigestion)
        SceneIntent(
            scene_id="scene_06_food",
            narration="기름진 음식을 먹고 나면 속이 더부룩하고 답답하죠.",
            subject="person", age_group="adult",
            action="holding stomach in discomfort after eating",
            location="dining table", object="greasy food, plate", body_part="stomach",
            symptom="indigestion, bloating", emotion="uncomfortable",
            context="after eating a heavy meal",
            visual_goal="Person sitting at dining table holding stomach with uncomfortable expression",
            avoid=["chef cooking", "empty plate", "happy eating", "diet food"]
        ),
        # 7. Sleep (Generic easily polluted by peaceful sleeping when it should be tossing)
        SceneIntent(
            scene_id="scene_07_sleep",
            narration="밤새 뒤척이느라 아침에 일어나도 피곤함이 가시지 않는다면?",
            subject="person", age_group="adult",
            action="waking up looking exhausted and rubbing eyes",
            location="bedroom", object="bed, alarm clock", body_part="eyes",
            symptom="chronic fatigue", emotion="exhausted",
            context="morning after bad sleep",
            visual_goal="Person sitting on bed rubbing eyes looking very tired in the morning",
            avoid=["sleeping peacefully", "smiling", "jumping out of bed", "empty bed"]
        ),
        # 8. Diet (Generic easily polluted by healthy eating when it should be weight gain frustration)
        SceneIntent(
            scene_id="scene_08_diet",
            narration="물만 먹어도 살이 찌는 것 같아 우울하신가요?",
            subject="middle aged person", age_group="middle aged",
            action="looking in mirror and grabbing belly fat",
            location="bedroom or bathroom", object="mirror", body_part="belly",
            symptom="weight gain", emotion="depressed, frustrated",
            context="weight loss struggle",
            visual_goal="Person looking at their belly fat in the mirror with a sad expression",
            avoid=["eating healthy food", "exercising happily", "skinny models", "fast food"]
        ),
        # 9. Wrist Joint (Generic easily polluted by typing when it should be wrist pain)
        SceneIntent(
            scene_id="scene_09_wrist",
            narration="무거운 냄비를 들 때마다 손목이 시큰거리지 않나요?",
            subject="woman", age_group="middle aged",
            action="dropping a pot or rubbing wrist in pain",
            location="kitchen", object="pot, pan", body_part="wrist",
            symptom="wrist pain", emotion="pain, wincing",
            context="doing kitchen chores",
            visual_goal="Woman in kitchen rubbing her wrist in pain while holding or near a pot",
            avoid=["typing on keyboard", "playing tennis", "empty kitchen"]
        ),
        # 10. Eye Health (Generic easily polluted by reading when it should be dry eyes)
        SceneIntent(
            scene_id="scene_10_eye",
            narration="스마트폰을 조금만 봐도 눈이 뻑뻑하고 침침해진다면?",
            subject="senior", age_group="senior",
            action="rubbing dry eyes and blinking hard",
            location="living room", object="smartphone", body_part="eyes",
            symptom="dry eyes, blurred vision", emotion="uncomfortable",
            context="using smartphone",
            visual_goal="Senior person holding a smartphone and rubbing their uncomfortable dry eyes",
            avoid=["reading a book", "wearing glasses normally", "smiling", "laptop"]
        )
    ]
    
    out_dir = Path("outputs/e2e_precision_test")
    os.makedirs(out_dir, exist_ok=True)
    out_file = out_dir / f"scene_debug_e2e.json"

    results = []
    
    for scene in test_scenes:
        logger.info(f"\n{'='*50}\nTesting Scene: {scene.scene_id}\n{'='*50}")
        best_asset, debug_info = matcher.find_best_asset_for_scene(scene)
        results.append(debug_info.model_dump())
        
        # Save incrementally
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
        logger.info(f"Progress saved to {out_file}")
        
    logger.info(f"E2E Precision Test Complete. Final results saved to {out_file}")
    
    # Print a quick summary
    print("\n\n" + "="*50)
    print("E2E PRECISION TEST SUMMARY")
    print("="*50)
    for res in results:
        scene_id = res['scene_id']
        decision = res['final_decision']
        asset = res.get('selected_asset', {})
        score = asset.get('score', {}).get('total_score', 0) if asset else 0
        print(f"[{scene_id}] -> {decision} (Score: {score})")

if __name__ == "__main__":
    main()
