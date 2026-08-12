# True Vision Evaluation Pipeline

## 1. Goal Description
The goal is to implement a strict, real-world Vision LLM (VLM) evaluation of stock video assets to pass the user's Asset Precision Test. We will completely remove any fake scoring, random score bypasses, and deterministic metadata-only logic. Instead, we will fetch real thumbnails/frames from candidate videos and pass them to a reliable Vision API (OpenAI GPT-4o-mini).

## 2. User Review Required
> [!WARNING]
> Since the NVIDIA Vision API was previously timing out (504), this plan proposes using the **OpenAI Vision API** (GPT-4o or GPT-4o-mini) to evaluate the image frames. This ensures stability and accurate parsing of the strict JSON format you requested. Please confirm if using OpenAI for the Vision component is acceptable.

## 3. Open Questions
- Do you want to extract a specific frame from the video using `ffmpeg`/`opencv`, or is it acceptable to use the default thumbnail URLs provided by Pixabay/Pexels? (Using provided thumbnails is much faster and doesn't require downloading the full video first, but extracting middle frames might be more accurate). I will default to using the provided thumbnails if available.

## 4. Proposed Changes

### 4.1 Intelligence / Semantic Matcher
- **[MODIFY] [semantic_matcher.py](file:///c:/adforge/intelligence/semantic_matcher.py)**
  - Remove the deterministic VLM bypass (base score 50, etc.).
  - Implement `_evaluate_frames_vlm` to make a real call to the OpenAI API using `gpt-4o-mini` (or `gpt-4o`).
  - Pass the thumbnail URL directly to the Vision API along with the exact `SceneIntent` context (subject, action, object, location, context, emotion, avoid).
  - Enforce the exact JSON response schema requested by the user:
    ```json
    {
      "subject_match": true,
      "action_match": true,
      "object_match": true,
      "context_match": true,
      "emotion_match": false,
      "avoid_match": false,
      "confidence": 0.94,
      "decision": "PASS",
      "reason": "..."
    }
    ```
  - Only candidates with `"decision": "PASS"` will be selected.

### 4.2 Pipeline & Tests
- **[MODIFY] [full_pipeline.py](file:///c:/adforge/pipelines/full_pipeline.py)**
  - Ensure the pipeline correctly checks for `c_debug.decision == "SELECTED"` or `"PASS"` and proceeds to actually download the asset to `outputs/{job_id}/assets/scene_{id}.mp4`.
- **[MODIFY] [test_e2e_precision.py](file:///c:/adforge/tests/test_e2e_precision.py)** (or create `test_true_vision.py`)
  - Create a new explicit test script that runs the exact two test cases provided by the user (computer neck pain & cold air conditioner) with specific mock URLs (or real search queries) to prove the Vision API correctly Rejects/Passes based on the visual content.
  - The script will output the exact log format required: Scene, Query, Candidate URL, Frame URLs, Vision Decision, Reason, Score, Selected, Download Path.

## 5. Verification Plan
I will run the new test script against the actual OpenAI Vision API with the specific edge cases (e.g., person smiling vs person in pain, beach vs office) to prove that the VLM correctly rejects incorrect visual content and only passes the perfect match, followed by a successful mp4 download.
