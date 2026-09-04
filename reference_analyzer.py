"""
레퍼런스 영상 학습 분석 엔진
- FFmpeg로 컷 타이밍 감지
- OpenCV로 키 프레임 추출
- Whisper로 대본 전사
- Claude/OpenRouter/Nvidia Vision으로 자막 스타일 분석
- 학습된 스타일 프로필을 JSON으로 저장
"""

import os
import re
import json
import base64
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional
import numpy as np

try:
    import cv2
except Exception:
    cv2 = None

try:
    import whisper
except Exception:
    whisper = None

import requests
from dotenv import load_dotenv

load_dotenv()

# -------------------------------------------------------------------
# 스타일 프로필 저장 경로
# -------------------------------------------------------------------
PROFILES_DIR = os.path.join(os.path.dirname(__file__), "style_profiles")
os.makedirs(PROFILES_DIR, exist_ok=True)

# -------------------------------------------------------------------
# Vision API 설정 (OpenRouter → Nvidia 폴백 체인)
# -------------------------------------------------------------------
VISION_PROVIDERS = [
    {
        "name": "OpenRouter (Claude Haiku Vision)",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "model": "anthropic/claude-3-haiku",
        "key_env": "OPENROUTER_API_KEY",
        "key_prefix": "sk-or-",
    },
    {
        "name": "OpenRouter (Llama Vision Free)",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "model": "meta-llama/llama-3.2-11b-vision-instruct:free",
        "key_env": "OPENROUTER_API_KEY",
        "key_prefix": "sk-or-",
    },
    {
        "name": "Nvidia (Llama 3.2 Vision)",
        "url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "model": "meta/llama-3.2-11b-vision-instruct",
        "key_env": "NVIDIA_API_KEY",
        "key_prefix": "nvapi-",
    },
]

FRAME_ANALYSIS_PROMPT = """이 영상 프레임을 분석하고 다음 JSON 형식으로만 응답하세요.

{
  "has_subtitle": true/false,
  "subtitle_text": "자막 텍스트 (없으면 null)",
  "subtitle_color": "yellow/white/red/orange/green/blue/gray/other",
  "subtitle_size": "small/medium/large/xlarge",
  "subtitle_position": "top/center/bottom_third/bottom",
  "estimated_role": "hook/empathy/agitate/evidence/solution/usp/cta/normal",
  "scene_type": "talking/product/testimonial/text_only/other"
}

추론 기준:
- 노란색 큰 자막 = hook (후킹)
- 흰색 보통 자막 = normal/evidence
- 빨간색 큰 자막 = cta
- 자막이 없는 프레임 = has_subtitle: false"""


class ReferenceAnalyzer:
    """레퍼런스 영상을 분석해서 스타일 프로필을 학습하는 엔진"""

    def __init__(self, openrouter_api_key: str = "", nvidia_api_key: str = ""):
        self.openrouter_api_key = openrouter_api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.nvidia_api_key = nvidia_api_key or os.environ.get("NVIDIA_API_KEY", "")
        self._whisper_model = None  # 지연 로딩

    def _get_whisper_model(self):
        if whisper is None:
            raise RuntimeError("whisper 모듈이 설치되어 있지 않습니다.")
        if self._whisper_model is None:
            print("[ReferenceAnalyzer] Whisper 모델 로딩 중... (base)")
            self._whisper_model = whisper.load_model("base")
        return self._whisper_model

    # -------------------------------------------------------------------
    # 1. 대본 전사 (Whisper)
    # -------------------------------------------------------------------
    def transcribe_audio(self, video_path: str) -> dict:
        """Whisper로 오디오를 전사하여 타임스탬프 포함 대본 반환"""
        model = self._get_whisper_model()
        print(f"  [전사] Whisper 분석 중: {Path(video_path).name}")
        result = model.transcribe(video_path, language="ko", verbose=False)
        segments = []
        for seg in result.get("segments", []):
            segments.append({
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"].strip()
            })
        return {
            "full_text": result.get("text", "").strip(),
            "segments": segments,
            "duration": segments[-1]["end"] if segments else 0
        }

    # -------------------------------------------------------------------
    # 2. 컷 타이밍 감지 (FFmpeg)
    # -------------------------------------------------------------------
    def detect_scene_changes(self, video_path: str, threshold: float = 0.4) -> list:
        """FFmpeg로 장면 전환 시점(초)을 감지"""
        print(f"  [컷분석] FFmpeg 장면 감지 중...")
        cmd = [
            "ffmpeg", "-i", video_path,
            "-vf", f"select='gt(scene,{threshold})',showinfo",
            "-vsync", "vfr",
            "-f", "null", "-"
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120
            )
            # showinfo 출력에서 pts_time 파싱
            cut_times = []
            for line in result.stderr.split("\n"):
                if "pts_time:" in line:
                    m = re.search(r"pts_time:([\d.]+)", line)
                    if m:
                        cut_times.append(float(m.group(1)))
            # 0초 추가 (시작)
            if not cut_times or cut_times[0] > 0.5:
                cut_times.insert(0, 0.0)
            print(f"  [컷분석] 감지된 컷: {len(cut_times)}개")
            return sorted(set(cut_times))
        except Exception as e:
            print(f"  [컷분석] 오류: {e}")
            return [0.0]

    # -------------------------------------------------------------------
    # 3. 키 프레임 추출 (OpenCV)
    # -------------------------------------------------------------------
    def extract_key_frames(self, video_path: str, cut_times: list, max_frames: int = 20) -> list:
        """컷 전환 직후 프레임을 추출하여 Base64로 반환"""
        if cv2 is None:
            raise RuntimeError("OpenCV (cv2) 모듈이 설치되어 있지 않습니다.")
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        frames = []

        # 너무 많으면 균등 샘플링
        sample_times = cut_times[:max_frames]
        if len(cut_times) > max_frames:
            step = len(cut_times) // max_frames
            sample_times = cut_times[::step][:max_frames]

        for t in sample_times:
            cap.set(cv2.CAP_PROP_POS_MSEC, (t + 0.5) * 1000)  # 컷 직후 0.5초
            ret, frame = cap.read()
            if not ret:
                continue
            # JPEG 인코딩 → Base64
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            b64 = base64.b64encode(buf.tobytes()).decode()
            frames.append({"time": t, "b64": b64})

        cap.release()
        print(f"  [프레임] {len(frames)}개 키프레임 추출 완료")
        return frames

    # -------------------------------------------------------------------
    # 4. Vision API 호출 (OpenRouter → Nvidia 폴백 체인)
    # -------------------------------------------------------------------
    def _call_vision_api(self, image_b64: str, prompt: str) -> Optional[str]:
        """OpenRouter → Nvidia 순서로 Vision API 시도, 모두 실패 시 None"""
        for provider in VISION_PROVIDERS:
            key_env = provider["key_env"]
            api_key = self.openrouter_api_key if key_env == "OPENROUTER_API_KEY" else self.nvidia_api_key
            
            if not api_key:
                continue

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": provider["model"],
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                        {"type": "text", "text": prompt},
                    ]
                }],
                "max_tokens": 256,
                "temperature": 0.1,
            }

            try:
                resp = requests.post(
                    provider["url"], headers=headers, json=payload, timeout=30
                )
                if resp.status_code == 200:
                    content = resp.json()["choices"][0]["message"]["content"]
                    print(f"  [Vision] {provider['name']} 성공")
                    return content
                else:
                    print(f"  [Vision] {provider['name']} 실패 ({resp.status_code}) → 다음 provider 시도")
                    time.sleep(1)
            except Exception as e:
                print(f"  [Vision] {provider['name']} 오류: {e} → 다음 provider 시도")
                time.sleep(1)

        return None

    def analyze_frames_vision(self, frames: list) -> list:
        """모든 키프레임을 Vision API로 분석"""
        results = []
        for i, frame_data in enumerate(frames):
            print(f"  [Vision] 프레임 {i+1}/{len(frames)} 분석 중...")
            response = self._call_vision_api(frame_data["b64"], FRAME_ANALYSIS_PROMPT)
            if response:
                try:
                    # JSON 추출
                    json_match = re.search(r'\{[\s\S]*\}', response)
                    if json_match:
                        analysis = json.loads(json_match.group())
                        analysis["time"] = frame_data["time"]
                        results.append(analysis)
                except (json.JSONDecodeError, KeyError):
                    pass
            time.sleep(0.5)  # API rate limit 방지
        return results

    # -------------------------------------------------------------------
    # 5. 스타일 프로필 집계
    # -------------------------------------------------------------------
    def _build_profile_from_analysis(self, transcript: dict, cut_times: list, frame_analyses: list) -> dict:
        """분석 결과를 스타일 프로필 JSON으로 집계"""
        duration = transcript.get("duration", 0) or 1

        # 컷 리듬 계산
        if len(cut_times) > 1:
            intervals = [cut_times[i+1] - cut_times[i] for i in range(len(cut_times)-1)]
            avg_cut_interval = round(sum(intervals) / len(intervals), 2)
            
            # 구간별 (초반 20% = hook, 후반 20% = cta)
            hook_end = duration * 0.2
            cta_start = duration * 0.8
            hook_intervals = [iv for t, iv in zip(cut_times[:-1], intervals) if t < hook_end]
            cta_intervals = [iv for t, iv in zip(cut_times[:-1], intervals) if t >= cta_start]
            body_intervals = [iv for t, iv in zip(cut_times[:-1], intervals) if hook_end <= t < cta_start]
        else:
            avg_cut_interval = 3.0
            hook_intervals = body_intervals = cta_intervals = [3.0]

        # 역할별 자막 스타일 집계
        role_styles = {}
        for analysis in frame_analyses:
            if not analysis.get("has_subtitle"):
                continue
            role = analysis.get("estimated_role", "normal")
            if role not in role_styles:
                role_styles[role] = {
                    "colors": [], "sizes": [], "positions": [], "count": 0
                }
            role_styles[role]["colors"].append(analysis.get("subtitle_color", "white"))
            role_styles[role]["sizes"].append(analysis.get("subtitle_size", "medium"))
            role_styles[role]["positions"].append(analysis.get("subtitle_position", "bottom_third"))
            role_styles[role]["count"] += 1

        # 최빈값으로 집계
        def most_common(lst):
            return max(set(lst), key=lst.count) if lst else None

        aggregated_roles = {}
        for role, data in role_styles.items():
            aggregated_roles[role] = {
                "dominant_color": most_common(data["colors"]),
                "dominant_size": most_common(data["sizes"]),
                "dominant_position": most_common(data["positions"]),
                "sample_count": data["count"],
            }

        return {
            "version": "1.0",
            "source_count": 1,
            "duration_sec": round(duration, 1),
            "total_cuts": len(cut_times),
            "cut_rhythm": {
                "avg_cut_interval_sec": avg_cut_interval,
                "hook_avg_sec": round(sum(hook_intervals)/len(hook_intervals), 2) if hook_intervals else avg_cut_interval,
                "body_avg_sec": round(sum(body_intervals)/len(body_intervals), 2) if body_intervals else avg_cut_interval,
                "cta_avg_sec": round(sum(cta_intervals)/len(cta_intervals), 2) if cta_intervals else avg_cut_interval,
            },
            "role_styles": aggregated_roles,
            "transcript_preview": transcript.get("full_text", "")[:200],
        }

    def _merge_profiles(self, profiles: list) -> dict:
        """여러 영상의 프로필을 통합 평균으로 병합"""
        if not profiles:
            return {}
        if len(profiles) == 1:
            return profiles[0]

        # 컷 리듬 평균
        merged_cut = {}
        for key in ["avg_cut_interval_sec", "hook_avg_sec", "body_avg_sec", "cta_avg_sec"]:
            vals = [p["cut_rhythm"].get(key, 3.0) for p in profiles]
            merged_cut[key] = round(sum(vals) / len(vals), 2)

        # 역할별 스타일 병합 (최빈값)
        all_roles = set()
        for p in profiles:
            all_roles.update(p.get("role_styles", {}).keys())

        merged_roles = {}
        for role in all_roles:
            colors = []
            sizes = []
            positions = []
            for p in profiles:
                style = p.get("role_styles", {}).get(role, {})
                if style.get("dominant_color"):
                    colors.append(style["dominant_color"])
                if style.get("dominant_size"):
                    sizes.append(style["dominant_size"])
                if style.get("dominant_position"):
                    positions.append(style["dominant_position"])

            def most_common(lst):
                return max(set(lst), key=lst.count) if lst else None

            merged_roles[role] = {
                "dominant_color": most_common(colors),
                "dominant_size": most_common(sizes),
                "dominant_position": most_common(positions),
                "sample_count": sum(p.get("role_styles", {}).get(role, {}).get("sample_count", 0) for p in profiles),
            }

        return {
            "version": "1.0",
            "source_count": len(profiles),
            "cut_rhythm": merged_cut,
            "role_styles": merged_roles,
            "total_cuts": sum(p.get("total_cuts", 0) for p in profiles),
        }

    # -------------------------------------------------------------------
    # 6. 메인 분석 API
    # -------------------------------------------------------------------
    def analyze_video(self, video_path: str, progress_callback=None) -> dict:
        """단일 영상 전체 분석 → 스타일 프로필 dict 반환"""
        name = Path(video_path).name
        print(f"\n[ReferenceAnalyzer] 분석 시작: {name}")

        def _cb(step, total, msg):
            if progress_callback:
                progress_callback(step / total, msg)

        _cb(1, 5, f"🎙️ 오디오 전사 중... ({name})")
        transcript = self.transcribe_audio(video_path)

        _cb(2, 5, "✂️ 컷 타이밍 감지 중...")
        cut_times = self.detect_scene_changes(video_path)

        _cb(3, 5, "🖼️ 키프레임 추출 중...")
        frames = self.extract_key_frames(video_path, cut_times)

        _cb(4, 5, "🔍 Vision AI 자막 스타일 분석 중...")
        frame_analyses = self.analyze_frames_vision(frames)

        _cb(5, 5, "📊 프로필 집계 중...")
        profile = self._build_profile_from_analysis(transcript, cut_times, frame_analyses)

        print(f"[ReferenceAnalyzer] 완료: {name} — 컷 {len(cut_times)}개, 프레임 분석 {len(frame_analyses)}개")
        return profile

    def analyze_batch(self, video_paths: list, profile_name: str = "default",
                      progress_callback=None) -> dict:
        """여러 영상 배치 분석 → 통합 프로필 저장"""
        profiles = []
        for i, vpath in enumerate(video_paths):
            def per_video_cb(frac, msg):
                if progress_callback:
                    overall = (i + frac) / len(video_paths)
                    progress_callback(overall, f"[{i+1}/{len(video_paths)}] {msg}")

            profile = self.analyze_video(vpath, progress_callback=per_video_cb)
            profiles.append(profile)

        merged = self._merge_profiles(profiles)
        merged["profile_name"] = profile_name
        merged["source_videos"] = [Path(p).name for p in video_paths]

        # 저장
        save_path = os.path.join(PROFILES_DIR, f"{profile_name}.json")
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        print(f"\n[ReferenceAnalyzer] 프로필 저장: {save_path}")

        return merged

    @staticmethod
    def list_profiles() -> list:
        """저장된 스타일 프로필 목록 반환"""
        if not os.path.exists(PROFILES_DIR):
            return []
        files = [f for f in os.listdir(PROFILES_DIR) if f.endswith(".json")]
        profiles = []
        for fname in files:
            fpath = os.path.join(PROFILES_DIR, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            profiles.append({
                "name": data.get("profile_name", fname.replace(".json", "")),
                "file": fpath,
                "source_count": data.get("source_count", 1),
                "total_cuts": data.get("total_cuts", 0),
                "avg_cut_interval": data.get("cut_rhythm", {}).get("avg_cut_interval_sec", 0),
            })
        return profiles

    @staticmethod
    def load_profile(profile_name: str) -> Optional[dict]:
        """저장된 스타일 프로필 로딩"""
        fpath = os.path.join(PROFILES_DIR, f"{profile_name}.json")
        if os.path.exists(fpath):
            with open(fpath, "r", encoding="utf-8") as f:
                return json.load(f)
        return None
