import os
import sys
import json
import csv
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.schemas import SceneIntent
from intelligence.semantic_matcher import SemanticMatcher
from core.config import config
from core.logging import logger

def main():
    logger.info("Starting Precision Benchmark (20 Scenes)...")
    
    # Do not change thresholds. Keep it at 75 for testing precision.
    config.MAX_SEARCH_RETRIES = 2
    
    matcher = SemanticMatcher()
    
    # 20 Scenes designed to test generic pollution and near-misses
    benchmark_scenes = [
        # Generic Pollution Tests (1-10)
        SceneIntent(scene_id="BM_01_Pain", narration="여름철 에어컨 바람에 어깨가 결리고 쑤신다면?", subject="middle aged person", age_group="middle aged", action="rubbing stiff shoulder in pain", location="indoors", object="air conditioner", body_part="shoulder", symptom="stiffness", emotion="discomfort", context="feeling cold from AC", visual_goal="Person rubbing shoulder showing discomfort indoors", avoid=["exercise", "sports", "outdoors"]),
        SceneIntent(scene_id="BM_02_Summer", narration="올여름, 집에서도 숨막히는 더위 때문에 잠 못 이루시죠?", subject="person", age_group="any", action="tossing and turning in bed sweating", location="bedroom", object="bed", body_part="", symptom="insomnia", emotion="frustrated", context="hot summer night", visual_goal="Person awake in bed looking hot and frustrated", avoid=["beach", "pool", "daytime"]),
        SceneIntent(scene_id="BM_03_Office", narration="사무실에 오래 앉아 있다 보면 허리가 뻐근하게 굳어옵니다.", subject="office worker", age_group="adult", action="stretching back holding lower back", location="office", object="computer", body_part="lower back", symptom="back pain", emotion="tired", context="working", visual_goal="Office worker holding lower back in pain", avoid=["empty office", "smiling", "gym"]),
        SceneIntent(scene_id="BM_04_Exercise", narration="관절이 안 좋을 때는 무리한 운동보다 가벼운 스트레칭이 좋습니다.", subject="senior", age_group="senior", action="doing light stretching carefully", location="living room", object="yoga mat", body_part="knee", symptom="stiffness", emotion="calm", context="senior health", visual_goal="Senior doing gentle stretches", avoid=["weightlifting", "running fast"]),
        SceneIntent(scene_id="BM_05_Beauty", narration="거울 볼 때마다 늘어난 눈가 주름 때문에 한숨이 나오시나요?", subject="middle aged woman", age_group="middle aged", action="touching wrinkles near eyes looking sad", location="bathroom", object="mirror", body_part="eyes", symptom="wrinkles", emotion="sad", context="skincare", visual_goal="Middle-aged woman touching eye wrinkles sadly", avoid=["heavy makeup", "laughing"]),
        SceneIntent(scene_id="BM_06_Food", narration="기름진 음식을 먹고 나면 속이 더부룩하고 답답하죠.", subject="person", age_group="adult", action="holding stomach in discomfort after eating", location="dining table", object="greasy food", body_part="stomach", symptom="indigestion", emotion="uncomfortable", context="after eating", visual_goal="Person holding stomach with uncomfortable expression at table", avoid=["chef cooking", "happy eating"]),
        SceneIntent(scene_id="BM_07_Sleep", narration="밤새 뒤척이느라 아침에 일어나도 피곤함이 가시지 않는다면?", subject="person", age_group="adult", action="waking up looking exhausted and rubbing eyes", location="bedroom", object="bed", body_part="eyes", symptom="chronic fatigue", emotion="exhausted", context="morning", visual_goal="Person sitting on bed rubbing eyes looking tired", avoid=["sleeping peacefully", "smiling"]),
        SceneIntent(scene_id="BM_08_Diet", narration="물만 먹어도 살이 찌는 것 같아 우울하신가요?", subject="middle aged person", age_group="middle aged", action="looking in mirror and grabbing belly fat", location="bedroom", object="mirror", body_part="belly", symptom="weight gain", emotion="depressed", context="weight loss", visual_goal="Person looking at belly fat sadly", avoid=["eating healthy", "exercising happily"]),
        SceneIntent(scene_id="BM_09_Wrist", narration="무거운 냄비를 들 때마다 손목이 시큰거리지 않나요?", subject="woman", age_group="middle aged", action="rubbing wrist in pain", location="kitchen", object="pot", body_part="wrist", symptom="wrist pain", emotion="pain", context="kitchen chores", visual_goal="Woman in kitchen rubbing wrist in pain near a pot", avoid=["typing", "playing tennis"]),
        SceneIntent(scene_id="BM_10_Eye", narration="스마트폰을 조금만 봐도 눈이 뻑뻑하고 침침해진다면?", subject="senior", age_group="senior", action="rubbing dry eyes", location="living room", object="smartphone", body_part="eyes", symptom="dry eyes", emotion="uncomfortable", context="using smartphone", visual_goal="Senior holding smartphone rubbing dry eyes", avoid=["reading a book", "smiling"]),
        
        # Near-Miss / Edge Case Tests (11-19)
        SceneIntent(scene_id="BM_11_WrongAction", narration="컴퓨터 앞에서 열심히 일하는 당신", subject="office worker", age_group="adult", action="typing fast on keyboard", location="office", object="computer", body_part="", symptom="", emotion="focused", context="working", visual_goal="Office worker typing fast", avoid=["sleeping", "eating"]),
        SceneIntent(scene_id="BM_12_WrongContext", narration="헬스장에서 무거운 역기를 들다가 허리를 삐끗했다면?", subject="man", age_group="adult", action="holding lower back in extreme pain", location="gym", object="barbell", body_part="lower back", symptom="injury", emotion="agony", context="weightlifting", visual_goal="Man holding lower back in extreme pain at gym near barbell", avoid=["office", "bed"]),
        SceneIntent(scene_id="BM_13_WrongObject", narration="종일 운전하느라 뻣뻣해진 목", subject="driver", age_group="adult", action="rubbing stiff neck", location="inside a car", object="steering wheel", body_part="neck", symptom="stiffness", emotion="tired", context="driving", visual_goal="Driver rubbing stiff neck holding steering wheel", avoid=["office", "desk"]),
        SceneIntent(scene_id="BM_14_WrongEmotion", narration="매운 음식을 먹고 속이 쓰려 고통스러운 표정", subject="person", age_group="adult", action="holding stomach in pain", location="restaurant", object="spicy food", body_part="stomach", symptom="stomachache", emotion="agony", context="eating spicy food", visual_goal="Person holding stomach in extreme pain", avoid=["smiling", "relaxed"]),
        SceneIntent(scene_id="BM_15_WrongNarrative", narration="출근길 지옥철에서 사람들에게 밀려 스트레스 받는 아침", subject="person", age_group="adult", action="looking stressed in crowd", location="subway", object="train", body_part="", symptom="stress", emotion="frustrated", context="morning commute", visual_goal="Person looking stressed squeezed in crowded subway", avoid=["empty train", "scenic road"]),
        SceneIntent(scene_id="BM_16_HairLoss", narration="샤워 후 수챗구멍에 한가득 빠진 머리카락을 보며 절망합니다.", subject="man", age_group="adult", action="holding fallen hair looking devastated", location="bathroom", object="hair", body_part="head", symptom="hair loss", emotion="devastated", context="after shower", visual_goal="Man looking at fallen hair in his hand with shocked expression", avoid=["combing hair normally", "smiling"]),
        SceneIntent(scene_id="BM_17_KneeStairs", narration="계단을 오르내릴 때마다 무릎이 시큰거려서 난간을 잡아야 한다면?", subject="senior", age_group="senior", action="holding knee in pain holding handrail", location="stairs", object="handrail", body_part="knee", symptom="joint pain", emotion="pain", context="walking stairs", visual_goal="Senior holding knee in pain on stairs", avoid=["running up stairs", "flat ground"]),
        SceneIntent(scene_id="BM_18_FootPain", narration="아침에 일어나 첫 발을 디딜 때 발바닥이 찌릿하게 아프신가요?", subject="person", age_group="adult", action="holding sole of foot in pain", location="bedroom", object="floor", body_part="foot", symptom="plantar fasciitis", emotion="pain", context="morning", visual_goal="Person sitting on bed holding sole of foot in pain", avoid=["running", "shoes"]),
        SceneIntent(scene_id="BM_19_TeethPain", narration="차가운 물을 마실 때마다 이가 시려서 깜짝 놀라시죠?", subject="person", age_group="adult", action="holding cheek wincing after drinking cold water", location="kitchen", object="glass of ice water", body_part="teeth", symptom="sensitive teeth", emotion="wincing", context="drinking", visual_goal="Person holding cheek in pain drinking ice water", avoid=["warm tea", "eating food"]),
        
        # 20. Forced ALL FAIL (Highly specific, impossible to find exactly on free stock)
        # Should result in ASSET_SELECTION_FAILED without fallback.
        SceneIntent(
            scene_id="BM_20_ForcedFail", 
            narration="우주복을 입고 화성 표면에서 텐트를 치며 기타를 치는 우주비행사", 
            subject="astronaut", age_group="adult", 
            action="playing guitar while setting up a tent", 
            location="mars surface", object="spacesuit, guitar, tent", body_part="", 
            symptom="", emotion="happy", context="camping on mars", 
            visual_goal="Astronaut in full spacesuit playing guitar and setting up tent on red planet Mars", 
            avoid=["earth", "indoors"]
        )
    ]
    
    out_dir = Path("outputs/benchmark")
    os.makedirs(out_dir, exist_ok=True)
    csv_file = out_dir / "precision_benchmark.csv"
    
    # Initialize CSV
    with open(csv_file, mode='w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow([
            "Scene ID", "Narration", "Visual Goal", 
            "Generated Queries", "Candidates Evaluated", 
            "Final Decision", "Selected Asset URL", 
            "Overall Match", "Narrative Match", "Subject Match", "Action Match", "Object Match", "Total Score",
            "Human Eval (PASS/FAIL)", "Notes"
        ])
    
    for i, scene in enumerate(benchmark_scenes, 1):
        logger.info(f"\n{'='*50}\nBenchmarking Scene {i}/20: {scene.scene_id}\n{'='*50}")
        best_asset, debug_info = matcher.find_best_asset_for_scene(scene)
        
        queries = " | ".join(debug_info.search_queries)
        eval_count = len(debug_info.candidates)
        decision = debug_info.final_decision
        
        if best_asset:
            url = best_asset.url
            om = best_asset.score.overall_semantic_match
            nm = best_asset.score.narrative_match
            sm = best_asset.score.subject_match
            am = best_asset.score.action_match
            obm = best_asset.score.object_match
            ts = best_asset.score.total_score
        else:
            url = "NONE"
            om = nm = sm = am = obm = ts = 0
            
        # Append to CSV
        with open(csv_file, mode='a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                scene.scene_id, scene.narration, scene.visual_goal,
                queries, eval_count,
                decision, url,
                om, nm, sm, am, obm, ts,
                "", "" # Leave empty for human evaluation
            ])
            
        logger.info(f"Progress saved to {csv_file}")
        
    logger.info(f"Benchmark Complete! Please open {csv_file} to perform Human Evaluation.")

if __name__ == "__main__":
    main()
