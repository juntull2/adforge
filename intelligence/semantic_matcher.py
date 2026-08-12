import json
import base64
import requests
from openai import OpenAI
from core.config import config
from core.schemas import SceneIntent, AssetCandidate, AssetScore, SceneDebugInfo, CandidateDebugInfo
from services.stock_api import StockAPI
from intelligence.asset_quality import AssetQualityGate
from core.logging import logger
from typing import List, Tuple, Dict, Any

class SemanticMatcher:
    def __init__(self, api_key: str = None, base_url: str = "https://integrate.api.nvidia.com/v1", model: str = "meta/llama-3.1-70b-instruct", vision_model: str = "meta/llama-3.2-90b-vision-instruct"):
        key = api_key or config.NVIDIA_API_KEY
        self.client = OpenAI(api_key=key, base_url=base_url)
        self.model = model
        self.vision_model = vision_model
        self.stock_api = StockAPI()
        self.quality_gate = AssetQualityGate()

    def _generate_search_queries(self, scene: SceneIntent, previous_failures: List[Dict[str, Any]], benchmark_visuals: List[str] = None) -> List[str]:
        """Generate deterministic search queries without VLM due to API instability."""
        queries = []
        
        # Very specific but shorter queries work best
        
        # 1. Action + Body Part (often most visually distinct)
        if scene.action and scene.body_part:
            queries.append(f"{scene.body_part} {scene.action}".replace("massaging stiff", "massage"))
            
        # 2. Symptom + Body Part (e.g., "neck pain")
        if scene.symptom and scene.body_part:
            queries.append(f"{scene.body_part} {scene.symptom}")
            
        # 3. Subject + Object (e.g., "person air conditioner")
        if scene.object:
            queries.append(f"{scene.object}")
            
        # 4. Subject + Emotion/Action
        simple = f"{scene.subject} {scene.action}".strip()
        if simple and simple not in queries:
            queries.append(simple)
            
        # Filter empty and limit
        queries = [q for q in queries if q][:4]
        if not queries:
            queries.append(scene.subject or "person")
            
        return queries

    def _pre_filter_candidate(self, candidate: AssetCandidate, scene: SceneIntent) -> Tuple[bool, int, str]:
        """Cheap metadata-based filter. Returns (is_passed, score, reject_reason)."""
        title = candidate.title.lower()
        score = 0
        
        # 1. Hard reject on Avoid Words in title
        for avoid_word in scene.avoid:
            if avoid_word.lower() in title and len(avoid_word) > 2:
                return False, 0, f"Pre-filter Reject: Title contains avoid word '{avoid_word}'"
                
        # 2. Score based on keyword matching
        subject_words = scene.subject.lower().split()
        for w in subject_words:
            if w in title and len(w) > 2:
                score += 10
                
        action_words = scene.action.lower().split()
        for w in action_words:
            if w in title and len(w) > 2:
                score += 10
                
        if scene.body_part and scene.body_part.lower() in title:
            score += 15
            
        return True, score, ""

    def _extract_frames_from_video(self, url: str) -> List[str]:
        """Download video to temp file, extract 3 frames (10%, 50%, 90%), return base64 encoded strings."""
        if not url:
            return []
        
        frames_b64 = []
        import tempfile, requests, cv2, os, base64
        
        fd, path = tempfile.mkstemp(suffix='.mp4')
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            r = requests.get(url, stream=True, headers=headers, timeout=10)
            with os.fdopen(fd, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            cap = cv2.VideoCapture(path)
            if cap.isOpened():
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                if total_frames > 0:
                    for pct in [0.1, 0.5, 0.9]:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, int(total_frames * pct))
                        ret, frame = cap.read()
                        if ret:
                            _, buffer = cv2.imencode('.jpg', frame)
                            frames_b64.append(base64.b64encode(buffer).decode('utf-8'))
                cap.release()
        except Exception as e:
            logger.error(f"Error extracting frames from {url}: {e}")
        finally:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass
        return frames_b64

    def _evaluate_frames_vlm(self, frames_b64: List[str], scene: SceneIntent) -> Dict[str, Any]:
        """Use OpenAI GPT-4o-mini to evaluate multiple frames against the SceneIntent."""
        import json
        from openai import OpenAI
        
        client = OpenAI(
            api_key=config.OPENROUTER_API_KEY, 
            base_url="https://openrouter.ai/api/v1"
        )
        
        content = [
            {"type": "text", "text": f"Evaluate if this video content matches the following scene requirements.\n"
                                     f"Narration: {scene.narration}\n"
                                     f"Subject: {scene.subject}\n"
                                     f"Action: {scene.action}\n"
                                     f"Object: {scene.object}\n"
                                     f"Location: {scene.location}\n"
                                     f"Avoid: {', '.join(scene.avoid)}\n"
                                     f"\nReturn ONLY a valid JSON object with exactly these fields:\n"
                                     f"{{\n"
                                     f"  \"subject_match\": true/false,\n"
                                     f"  \"action_match\": true/false,\n"
                                     f"  \"object_match\": true/false,\n"
                                     f"  \"context_match\": true/false,\n"
                                     f"  \"emotion_match\": true/false,\n"
                                     f"  \"avoid_match\": true/false,\n"
                                     f"  \"confidence\": 0.0 to 1.0,\n"
                                     f"  \"decision\": \"PASS\" or \"REJECT\",\n"
                                     f"  \"reason\": \"brief explanation\"\n"
                                     f"}}\n"
                                     f"A PASS decision requires the video to clearly depict the requested action, subject, and object visually. Do not assume context."}
        ]
        
        for b64 in frames_b64:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
            })
            
        try:
            response = client.chat.completions.create(
                model="openai/gpt-4o-mini",
                messages=[{"role": "user", "content": content}],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            raw_json = response.choices[0].message.content
            return json.loads(raw_json)
        except Exception as e:
            raise Exception(f"OpenAI VLM Evaluation failed: {e}")

    def find_best_asset_for_scene(self, scene: SceneIntent, benchmark_visuals: List[str] = None) -> Tuple[List[AssetCandidate], SceneDebugInfo]:
        """Strict Reject -> Refine -> Re-search loop using actual semantic validation."""
        
        debug_info = SceneDebugInfo(
            scene_id=scene.scene_id,
            narration=scene.narration,
            visual_goal=scene.visual_goal
        )
        
        failed_queries_log = []
        THRESHOLD = config.VLM_THRESHOLD
        
        for attempt in range(config.MAX_SEARCH_RETRIES):
            logger.info(f"[{scene.scene_id}] Asset search attempt {attempt + 1}/{config.MAX_SEARCH_RETRIES}")
            
            queries = self._generate_search_queries(scene, failed_queries_log, benchmark_visuals)
            debug_info.search_queries.extend(queries)
            logger.info(f"[{scene.scene_id}] Generated queries: {queries}")
            
            for query in queries:
                # 1. Search (Returns up to 30 sorted candidates)
                candidates = self.stock_api.search_videos(query, limit=30)
                debug_info.candidate_count += len(candidates)
                
                if not candidates:
                    failed_queries_log.append({"query": query, "reason": "No results returned"})
                    continue
                
                # Pre-filter phase
                pre_filtered_candidates = []
                for asset in candidates:
                    c_debug = CandidateDebugInfo(
                        url=asset.url,
                        title=asset.title,
                        duration=asset.duration,
                        resolution=f"{asset.width}x{asset.height}",
                        aspect_ratio=asset.orientation
                    )
                    
                    # 2-1. Asset Quality Gate (Hard Reject for crop/upscale limits)
                    quality_result = self.quality_gate.evaluate_asset(asset)
                    if not quality_result.passes_quality:
                        c_debug.decision = "REJECTED"
                        c_debug.reject_reason = quality_result.rejection_reason
                        debug_info.candidates.append(c_debug)
                        continue
                        
                    # 2-2. Pre-filter (Cheap metadata text check)
                    passed_pre, pre_score, pre_reason = self._pre_filter_candidate(asset, scene)
                    c_debug.pre_filter_score = pre_score
                    if not passed_pre:
                        c_debug.decision = "REJECTED"
                        c_debug.reject_reason = pre_reason
                        debug_info.candidates.append(c_debug)
                        continue
                    
                    pre_filtered_candidates.append((asset, c_debug))
                
                # Sort by pre_filter_score (descending) and take Top 5 for expensive VLM evaluation
                pre_filtered_candidates.sort(key=lambda x: x[1].pre_filter_score, reverse=True)
                top_candidates = pre_filtered_candidates[:5]
                
                # Mark the others as skipped to save VLM cost
                for asset, c_debug in pre_filtered_candidates[5:]:
                    c_debug.decision = "SKIPPED"
                    c_debug.reject_reason = "Passed pre-filter but not in Top 5. Skipped VLM to save latency."
                    debug_info.candidates.append(c_debug)
                
                # 3. Evaluate Top Candidates with VLM
                passed_vlm_candidates = []
                
                for asset, c_debug in top_candidates:
                    import time
                    start_time = time.time()
                    retry_count = 0
                    vlm_res = None
                    
                    frames_b64 = self._extract_frames_from_video(asset.download_url)
                    # Fallback to thumbnail if frame extraction failed
                    if not frames_b64 and asset.thumbnail_url:
                        try:
                            import requests, base64
                            resp = requests.get(asset.thumbnail_url, timeout=5)
                            if resp.status_code == 200:
                                frames_b64 = [base64.b64encode(resp.content).decode('utf-8')]
                        except Exception:
                            pass

                    while retry_count <= 1:
                        try:
                            if not frames_b64:
                                raise ValueError("No frames or thumbnail available for evaluation.")
                                
                            vlm_res = self._evaluate_frames_vlm(frames_b64, scene)
                            c_debug.latency_ms = int((time.time() - start_time) * 1000)
                            c_debug.retry_count = retry_count
                            break
                        except Exception as e:
                            logger.error(f"VLM Timeout/Error on {c_debug.url} (Attempt {retry_count+1}): {e}")
                            retry_count += 1
                            if retry_count > 1:
                                c_debug.latency_ms = int((time.time() - start_time) * 1000)
                                c_debug.retry_count = retry_count
                                c_debug.decision = "EVALUATION_FAILED"
                                c_debug.failure_type = "TIMEOUT" if "time" in str(e).lower() else "API_ERROR"
                                c_debug.reject_reason = f"Evaluation failed after retry: {e}"
                                vlm_res = None
                                break
                    
                    if not vlm_res:
                        continue # Skip this candidate completely without fallback
                    
                    # Hard Requirement Validation
                    hard_reject_reason = None
                    if scene.hard_requirements:
                        for req_key, req_val in scene.hard_requirements.items():
                            match_key = f"{req_key}_match"
                            if match_key in vlm_res and not vlm_res[match_key]:
                                hard_reject_reason = f"Hard Requirement Failed: '{req_key}' was '{req_val}', but match is false."
                                break
                    
                    c_debug.overall_semantic_match = int(vlm_res.get("confidence", 0) * 100)
                    c_debug.narrative_match = 100 if vlm_res.get("decision") == "PASS" else 0
                    c_debug.subject_match = 100 if vlm_res.get("subject_match") else 0
                    c_debug.action_match = 100 if vlm_res.get("action_match") else 0
                    c_debug.object_match = 100 if vlm_res.get("object_match") else 0
                    c_debug.location_context_match = 100 if vlm_res.get("context_match") else 0
                    c_debug.emotion_match = 100 if vlm_res.get("emotion_match") else 0
                    c_debug.visual_quality = 80 # default
                    c_debug.avoid_match = vlm_res.get("avoid_match", False)
                    c_debug.total_score = int(vlm_res.get("confidence", 0) * 100)
                    
                    reasoning = vlm_res.get("reason", "")
                    
                    if vlm_res.get("error"):
                        c_debug.decision = "REJECTED"
                        c_debug.reject_reason = f"VLM Error: {vlm_res.get('error')}"
                        debug_info.candidates.append(c_debug)
                        continue
                        
                    if c_debug.avoid_match:
                        c_debug.decision = "REJECTED"
                        c_debug.reject_reason = f"Hard Reject: Avoid match found. {reasoning}"
                        debug_info.candidates.append(c_debug)
                        continue
                        
                    if hard_reject_reason:
                        c_debug.decision = "REJECTED"
                        c_debug.reject_reason = hard_reject_reason + f" ({reasoning})"
                        debug_info.candidates.append(c_debug)
                        continue
                        
                    if vlm_res.get("decision") == "PASS" and c_debug.total_score >= THRESHOLD:
                        c_debug.decision = "SELECTED (PENDING BEST)"
                        debug_info.candidates.append(c_debug)
                        passed_vlm_candidates.append((asset, c_debug))
                        
                        if c_debug.total_score >= 90:
                            logger.info(f"[{scene.scene_id}] Found exceptional asset >= 90: {asset.url} (Score: {c_debug.total_score})")
                            break
                    else:
                        c_debug.decision = "REJECTED"
                        if vlm_res.get("decision") != "PASS":
                            c_debug.reject_reason = f"VLM Decision was not PASS. {reasoning}"
                        else:
                            c_debug.reject_reason = f"Score too low ({c_debug.total_score} < {THRESHOLD}). {reasoning}"
                        debug_info.candidates.append(c_debug)
                        
                if passed_vlm_candidates:
                    # Sort passed candidates by VLM total score
                    passed_vlm_candidates.sort(key=lambda x: x[1].total_score, reverse=True)
                    best_asset, best_c_debug = passed_vlm_candidates[0]
                    
                    # Update decision strings for the chosen one vs others
                    for a, c in passed_vlm_candidates:
                        if c.url == best_c_debug.url:
                            c.decision = "SELECTED"
        # Select best assets across all queries
        if passed_vlm_candidates:
            passed_vlm_candidates.sort(key=lambda x: x[1].total_score, reverse=True)
            
            best_assets = []
            for asset, c_debug in passed_vlm_candidates:
                asset.score = AssetScore(
                    visual_quality=c_debug.visual_quality,
                    overall_semantic_match=c_debug.overall_semantic_match,
                    narrative_match=c_debug.narrative_match,
                    subject_match=c_debug.subject_match,
                    action_match=c_debug.action_match,
                    object_match=c_debug.object_match,
                    location_context_match=c_debug.location_context_match,
                    emotion_match=c_debug.emotion_match,
                    avoid_match=c_debug.avoid_match,
                    total_score=c_debug.total_score,
                    reasoning=c_debug.reject_reason or "Selected via deterministic logic"
                )
                best_assets.append(asset)
            
            # Mark the very best one
            passed_vlm_candidates[0][1].decision = "SELECTED"
            debug_info.final_decision = "SUCCESS"
            
            logger.info(f"[{scene.scene_id}] Final selected asset: {best_assets[0].url} (Score: {best_assets[0].score.total_score})")
            return best_assets, debug_info
            
        else:
            if not debug_info.candidates:
                failed_queries_log.append({"query": "all", "reason": "All candidates failed gates or score thresholds."})
                
        logger.error(f"[{scene.scene_id}] Exhausted {config.MAX_SEARCH_RETRIES} attempts. NO FALLBACK ALLOWED.")
        debug_info.final_decision = "FAILED - No asset met the strict threshold or all evaluations failed."
        return [], debug_info
