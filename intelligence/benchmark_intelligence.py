"""
Benchmark Intelligence — Automated Pipeline
MP4 → Audio/Transcript → Scene Sampling → LLM Analysis → analyzed JSON → DNA Aggregation
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Dict, Any
from core.config import config
from core.schemas import BenchmarkVideo, BenchmarkScene, BenchmarkDNA, BenchmarkPattern
from core.logging import logger


# ═══════════════════════════════════════════════════════════════════════
# 1. Audio Extraction & Transcription
# ═══════════════════════════════════════════════════════════════════════
class TranscriptExtractor:
    """Extract transcript from MP4 using Whisper (OpenAI)."""

    def __init__(self, whisper_model: str = "base"):
        self._whisper_model_name = whisper_model
        self._model = None  # lazy-load

    def _load_model(self):
        if self._model is None:
            try:
                import whisper
                logger.info(f"Loading Whisper model '{self._whisper_model_name}'...")
                self._model = whisper.load_model(self._whisper_model_name)
            except ImportError:
                logger.error("openai-whisper is not installed. Run: pip install openai-whisper")
                raise
        return self._model

    def extract_audio(self, mp4_path: Path, out_wav: Path) -> bool:
        """Extract audio track from MP4 to WAV using ffmpeg."""
        try:
            cmd = [
                "ffmpeg", "-y", "-i", str(mp4_path),
                "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                str(out_wav),
            ]
            subprocess.run(cmd, capture_output=True, check=True, timeout=120)
            return True
        except FileNotFoundError:
            logger.error("ffmpeg not found. Please install ffmpeg and add it to PATH.")
            return False
        except subprocess.CalledProcessError as e:
            logger.error(f"ffmpeg failed: {e.stderr.decode('utf-8', errors='replace')}")
            return False

    def transcribe(self, mp4_path: Path) -> Dict[str, Any]:
        """Transcribe MP4 → { text, segments }."""
        model = self._load_model()
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "audio.wav"
            if not self.extract_audio(mp4_path, wav_path):
                return {"text": "", "segments": []}
            result = model.transcribe(
                str(wav_path), language="ko", verbose=False
            )
            return {
                "text": result.get("text", ""),
                "segments": [
                    {
                        "start": seg["start"],
                        "end": seg["end"],
                        "text": seg["text"],
                    }
                    for seg in result.get("segments", [])
                ],
            }


# ═══════════════════════════════════════════════════════════════════════
# 2. Frame / Scene Sampling
# ═══════════════════════════════════════════════════════════════════════
class FrameSampler:
    """Extract representative frames from MP4 for visual analysis."""

    def sample_frames(self, mp4_path: Path, interval_sec: float = 3.0, max_frames: int = 10) -> List[Path]:
        """Extract frames at fixed intervals using ffmpeg."""
        out_dir = Path(tempfile.mkdtemp())
        try:
            cmd = [
                "ffmpeg", "-y", "-i", str(mp4_path),
                "-vf", f"fps=1/{interval_sec}",
                "-frames:v", str(max_frames),
                str(out_dir / "frame_%03d.jpg"),
            ]
            subprocess.run(cmd, capture_output=True, check=True, timeout=120)
            frames = sorted(out_dir.glob("frame_*.jpg"))
            return frames
        except Exception as e:
            logger.error(f"Frame sampling failed: {e}")
            return []

    def get_video_info(self, mp4_path: Path) -> Dict[str, Any]:
        """Get duration, resolution, aspect ratio using ffprobe."""
        try:
            cmd = [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format", "-show_streams",
                str(mp4_path),
            ]
            result = subprocess.run(cmd, capture_output=True, check=True, timeout=30)
            info = json.loads(result.stdout.decode("utf-8"))
            
            duration = float(info.get("format", {}).get("duration", 0))
            video_stream = next(
                (s for s in info.get("streams", []) if s.get("codec_type") == "video"), {}
            )
            width = int(video_stream.get("width", 0))
            height = int(video_stream.get("height", 0))
            
            if width > 0 and height > 0:
                if width < height:
                    aspect = "9:16"
                elif width > height:
                    aspect = "16:9"
                else:
                    aspect = "1:1"
            else:
                aspect = "unknown"
            
            return {
                "duration_sec": round(duration, 1),
                "resolution": f"{width}x{height}",
                "aspect_ratio": aspect,
                "width": width,
                "height": height,
            }
        except Exception as e:
            logger.error(f"ffprobe failed: {e}")
            return {"duration_sec": 0, "resolution": "unknown", "aspect_ratio": "unknown"}


# ═══════════════════════════════════════════════════════════════════════
# 3. LLM-based Benchmark Video Analyzer
# ═══════════════════════════════════════════════════════════════════════
class BenchmarkAnalyzer:
    """Analyze a benchmark video using transcript + video info → structured JSON via LLM."""

    def __init__(self, api_key: str = None, base_url: str = "https://integrate.api.nvidia.com/v1",
                 model: str = "meta/llama-3.1-70b-instruct"):
        from openai import OpenAI
        key = api_key or config.NVIDIA_API_KEY
        self.client = OpenAI(api_key=key, base_url=base_url)
        self.model = model

    def analyze(self, video_id: str, transcript: Dict[str, Any], video_info: Dict[str, Any]) -> BenchmarkVideo:
        """Send transcript + metadata to LLM for structured analysis."""
        full_text = transcript.get("text", "")
        segments = transcript.get("segments", [])
        segments_text = "\n".join(
            [f"[{s['start']:.1f}s-{s['end']:.1f}s] {s['text']}" for s in segments]
        )

        prompt = f"""You are a short-form video content analyst specializing in Korean health/wellness Naver Clip videos.

Analyze the following benchmark video and extract structured patterns.

## Video Info
- Duration: {video_info.get('duration_sec', 0)} seconds
- Resolution: {video_info.get('resolution', 'unknown')}
- Aspect Ratio: {video_info.get('aspect_ratio', 'unknown')}

## Full Transcript (Korean)
{full_text}

## Timed Segments
{segments_text}

## Task
Extract the following in valid JSON format:

{{
  "hook": {{
    "text": "The hook sentence (first 3 seconds)",
    "duration_sec": 3.0,
    "pattern_ids": ["list of observed patterns like micro_commitment, specific_body_problem, loss_aversion, etc."]
  }},
  "target": ["target audience descriptions, e.g. 40-50대 여성, 허리 통증 직장인"],
  "topic": ["main topics, e.g. 허리 통증, 스트레칭, 찜질"],
  "body_parts": ["mentioned body parts, e.g. 허리, 무릎, 목"],
  "script_structure": ["structure labels in order, e.g. hook, problem, authority, solution_step1, solution_step2, solution_step3, cta"],
  "visual_patterns": ["observed visual patterns, e.g. body_part_closeup, exercise_demo, middle_aged_person, before_after"],
  "caption_patterns": ["caption/subtitle style patterns, e.g. large_text_overlay, key_number_highlight, step_numbering"],
  "cta_patterns": ["CTA patterns, e.g. comment_specific_keyword, like_before_tip, follow_for_more"],
  "scenes": [
    {{
      "scene_id": "scene_01",
      "start_sec": 0.0,
      "end_sec": 3.0,
      "purpose": "hook",
      "visual_description": "brief description of what is shown",
      "caption_text": "caption text shown on screen if any",
      "subject": "who is shown",
      "action": "what they are doing",
      "body_part": "body part focus if any",
      "environment": "where the scene takes place"
    }}
  ]
}}

IMPORTANT:
- Extract STRUCTURE and PATTERNS, not a simple summary.
- Identify recurring strategies (micro_commitment, loss_aversion, curiosity_gap, etc.)
- The scenes should cover the entire video timeline.
- Return ONLY valid JSON, no markdown wrapping.
"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            result = json.loads(response.choices[0].message.content)

            scenes = []
            for s in result.get("scenes", []):
                scenes.append(BenchmarkScene(
                    scene_id=s.get("scene_id", ""),
                    start_sec=s.get("start_sec", 0),
                    end_sec=s.get("end_sec", 0),
                    purpose=s.get("purpose", ""),
                    visual_description=s.get("visual_description", ""),
                    caption_text=s.get("caption_text", ""),
                    subject=s.get("subject", ""),
                    action=s.get("action", ""),
                    body_part=s.get("body_part", ""),
                    environment=s.get("environment", ""),
                ))

            return BenchmarkVideo(
                video_id=video_id,
                duration_sec=video_info.get("duration_sec", 0),
                aspect_ratio=video_info.get("aspect_ratio", "9:16"),
                resolution=video_info.get("resolution", ""),
                transcript=full_text,
                hook=result.get("hook", {}),
                target=result.get("target", []),
                topic=result.get("topic", []),
                body_parts=result.get("body_parts", []),
                script_structure=result.get("script_structure", []),
                visual_patterns=result.get("visual_patterns", []),
                caption_patterns=result.get("caption_patterns", []),
                cta_patterns=result.get("cta_patterns", []),
                scenes=scenes,
            )
        except Exception as e:
            logger.error(f"LLM analysis failed for {video_id}: {e}")
            return BenchmarkVideo(
                video_id=video_id,
                duration_sec=video_info.get("duration_sec", 0),
                transcript=transcript.get("text", ""),
            )


# ═══════════════════════════════════════════════════════════════════════
# 4. DNA Aggregator
# ═══════════════════════════════════════════════════════════════════════
class DNAAggregator:
    """Aggregate patterns from multiple analyzed benchmark JSONs into benchmark_dna.json."""

    def aggregate(self, analyzed_videos: List[BenchmarkVideo]) -> BenchmarkDNA:
        hook_counter: Dict[str, Dict] = {}
        visual_counter: Dict[str, Dict] = {}
        caption_counter: Dict[str, Dict] = {}
        cta_counter: Dict[str, Dict] = {}
        topic_counter: Dict[str, Dict] = {}
        structure_counter: Dict[str, Dict] = {}
        target_counter: Dict[str, Dict] = {}

        for v in analyzed_videos:
            vid = v.video_id
            # Hook patterns
            for pid in v.hook.get("pattern_ids", []):
                if pid not in hook_counter:
                    hook_counter[pid] = {"name": pid, "count": 0, "sources": []}
                hook_counter[pid]["count"] += 1
                hook_counter[pid]["sources"].append(vid)
            # Visual patterns
            for p in v.visual_patterns:
                if p not in visual_counter:
                    visual_counter[p] = {"name": p, "count": 0, "sources": []}
                visual_counter[p]["count"] += 1
                visual_counter[p]["sources"].append(vid)
            # Caption patterns
            for p in v.caption_patterns:
                if p not in caption_counter:
                    caption_counter[p] = {"name": p, "count": 0, "sources": []}
                caption_counter[p]["count"] += 1
                caption_counter[p]["sources"].append(vid)
            # CTA patterns
            for p in v.cta_patterns:
                if p not in cta_counter:
                    cta_counter[p] = {"name": p, "count": 0, "sources": []}
                cta_counter[p]["count"] += 1
                cta_counter[p]["sources"].append(vid)
            # Topics
            for t in v.topic:
                if t not in topic_counter:
                    topic_counter[t] = {"name": t, "count": 0, "sources": []}
                topic_counter[t]["count"] += 1
                topic_counter[t]["sources"].append(vid)
            # Structures
            struct_key = " → ".join(v.script_structure) if v.script_structure else ""
            if struct_key:
                if struct_key not in structure_counter:
                    structure_counter[struct_key] = {"name": struct_key, "count": 0, "sources": []}
                structure_counter[struct_key]["count"] += 1
                structure_counter[struct_key]["sources"].append(vid)
            # Targets
            for t in v.target:
                if t not in target_counter:
                    target_counter[t] = {"name": t, "count": 0, "sources": []}
                target_counter[t]["count"] += 1
                target_counter[t]["sources"].append(vid)

        def to_patterns(counter: Dict) -> List[BenchmarkPattern]:
            total = len(analyzed_videos) if analyzed_videos else 1
            return [
                BenchmarkPattern(
                    pattern_id=pid,
                    name=info["name"],
                    observed_count=info["count"],
                    confidence=round(info["count"] / total, 2),
                    generation_policy="strategy_only",
                    source_video_ids=info["sources"],
                )
                for pid, info in sorted(counter.items(), key=lambda x: x[1]["count"], reverse=True)
            ]

        return BenchmarkDNA(
            source_count=len(analyzed_videos),
            hook_patterns=to_patterns(hook_counter),
            target_patterns=to_patterns(target_counter),
            topic_clusters=to_patterns(topic_counter),
            script_structures=to_patterns(structure_counter),
            visual_patterns=to_patterns(visual_counter),
            caption_patterns=to_patterns(caption_counter),
            cta_patterns=to_patterns(cta_counter),
        )


# ═══════════════════════════════════════════════════════════════════════
# 5. Benchmark Retriever
# ═══════════════════════════════════════════════════════════════════════
class BenchmarkRetriever:
    """Retrieve relevant benchmark patterns given a product/audience/topic."""

    def __init__(self):
        self.dna = self._load_dna()

    def _load_dna(self) -> Optional[BenchmarkDNA]:
        if config.BENCHMARK_DNA_PATH.exists():
            try:
                data = json.loads(config.BENCHMARK_DNA_PATH.read_text(encoding="utf-8"))
                return BenchmarkDNA(**data)
            except Exception as e:
                logger.error(f"Failed to load benchmark DNA: {e}")
        return None

    def get_top_hook_patterns(self, n: int = 5) -> List[BenchmarkPattern]:
        if not self.dna:
            return []
        return self.dna.hook_patterns[:n]

    def get_top_visual_patterns(self, n: int = 5) -> List[BenchmarkPattern]:
        if not self.dna:
            return []
        return self.dna.visual_patterns[:n]

    def get_top_script_structures(self, n: int = 3) -> List[BenchmarkPattern]:
        if not self.dna:
            return []
        return self.dna.script_structures[:n]

    def get_relevant_patterns_for_topic(self, topics: List[str]) -> Dict[str, List[BenchmarkPattern]]:
        """Return patterns that overlap with given topics."""
        if not self.dna:
            return {}
        # Simple keyword overlap matching
        relevant_topics = [
            p for p in self.dna.topic_clusters
            if any(t.lower() in p.name.lower() for t in topics)
        ]
        return {
            "hook_patterns": self.get_top_hook_patterns(),
            "visual_patterns": self.get_top_visual_patterns(),
            "topic_matches": relevant_topics,
            "script_structures": self.get_top_script_structures(),
        }

    def get_dna_summary(self) -> Dict[str, Any]:
        """Return a concise summary for UI display."""
        if not self.dna:
            return {"status": "empty", "source_count": 0}
        return {
            "status": self.dna.status,
            "source_count": self.dna.source_count,
            "top_hooks": [p.name for p in self.dna.hook_patterns[:3]],
            "top_visuals": [p.name for p in self.dna.visual_patterns[:3]],
            "top_ctas": [p.name for p in self.dna.cta_patterns[:3]],
        }


# ═══════════════════════════════════════════════════════════════════════
# 6. Full Automated Pipeline: MP4 → analyzed JSON → DNA
# ═══════════════════════════════════════════════════════════════════════
class BenchmarkPipeline:
    """
    End-to-end: scan benchmark/raw/*.mp4, analyze each, save to
    benchmark/analyzed/*.json, then aggregate into benchmark_dna.json.
    """

    def __init__(self, api_key: str = None):
        self.transcript_extractor = TranscriptExtractor(whisper_model="base")
        self.frame_sampler = FrameSampler()
        self.analyzer = BenchmarkAnalyzer(api_key=api_key)
        self.aggregator = DNAAggregator()

    def run(self, force_reanalyze: bool = False) -> BenchmarkDNA:
        """Analyze all MP4s in benchmark/raw/ and aggregate DNA."""
        raw_dir = config.BENCHMARK_RAW_DIR
        analyzed_dir = config.BENCHMARK_ANALYZED_DIR

        mp4_files = sorted(raw_dir.glob("*.mp4"))
        if not mp4_files:
            logger.warning("No MP4 files found in benchmark/raw/")
            return BenchmarkDNA()

        logger.info(f"Found {len(mp4_files)} benchmark videos in {raw_dir}")

        all_videos: List[BenchmarkVideo] = []

        for mp4 in mp4_files:
            video_id = mp4.stem  # filename without extension
            analyzed_path = analyzed_dir / f"{video_id}.json"

            # Skip if already analyzed (unless forced)
            if analyzed_path.exists() and not force_reanalyze:
                logger.info(f"[{video_id}] Already analyzed, loading from cache.")
                try:
                    data = json.loads(analyzed_path.read_text(encoding="utf-8"))
                    all_videos.append(BenchmarkVideo(**data))
                    continue
                except Exception:
                    logger.warning(f"[{video_id}] Cache corrupt, re-analyzing.")

            logger.info(f"[{video_id}] Analyzing {mp4.name}...")

            # 1. Get video metadata
            video_info = self.frame_sampler.get_video_info(mp4)
            logger.info(f"[{video_id}] Duration: {video_info['duration_sec']}s, Resolution: {video_info['resolution']}")

            # 2. Extract transcript
            logger.info(f"[{video_id}] Extracting transcript...")
            transcript = self.transcript_extractor.transcribe(mp4)
            logger.info(f"[{video_id}] Transcript length: {len(transcript.get('text', ''))} chars")

            # 3. LLM analysis
            logger.info(f"[{video_id}] Running LLM analysis...")
            benchmark_video = self.analyzer.analyze(video_id, transcript, video_info)

            # 4. Save analyzed JSON
            analyzed_path.write_text(
                json.dumps(benchmark_video.model_dump(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info(f"[{video_id}] Saved to {analyzed_path}")

            all_videos.append(benchmark_video)

        # 5. Aggregate DNA
        logger.info("Aggregating Benchmark DNA...")
        dna = self.aggregator.aggregate(all_videos)

        # 6. Save DNA
        config.BENCHMARK_DNA_PATH.write_text(
            json.dumps(dna.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"Benchmark DNA saved ({dna.source_count} videos, {len(dna.hook_patterns)} hook patterns)")

        # 7. Update index
        index = {
            "videos": [
                {"video_id": v.video_id, "duration_sec": v.duration_sec, "topics": v.topic}
                for v in all_videos
            ]
        }
        config.BENCHMARK_INDEX_PATH.write_text(
            json.dumps(index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return dna
