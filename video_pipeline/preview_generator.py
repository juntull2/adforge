"""
AdForge V2 — Preview Generator (Phase 8)
Scene 순서대로 Stock/플레이스홀더 클립을 조합해 미리보기 MP4 생성.
ffmpeg 기반.
"""
from __future__ import annotations
import os
import json
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Dict

TARGET_W = 1080
TARGET_H = 1920


# ─────────────────────────────────────────────────────────────
# 1. 플레이스홀더 클립 생성 (AI 영상 필요 장면 / 소스 없는 장면)
# ─────────────────────────────────────────────────────────────

def create_placeholder_clip(
    narration: str,
    duration: float,
    output_path: str,
    bg_color: str = "0x1a1f2e",   # 다크 네이비
    text_color: str = "white",
    border_color: str = "0xF6AD55",  # 황금색 = AI 장면 표시
    label: str = "🤖 AI Video",
) -> str:
    """
    나레이션 텍스트 + AI 라벨이 포함된 플레이스홀더 클립 생성.
    반환: 생성된 파일 경로
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # 나레이션 텍스트 — 너무 길면 줄임
    narration_short = narration[:50] + "..." if len(narration) > 50 else narration
    # 특수문자 escape (ffmpeg drawtext)
    escaped = _escape_ffmpeg_text(narration_short)
    label_escaped = _escape_ffmpeg_text(label)

    vf = (
        f"color=c={bg_color}:size={TARGET_W}x{TARGET_H}:duration={duration}:rate=30,"
        f"drawbox=x=0:y=0:w={TARGET_W}:h={TARGET_H}:color={border_color}@0.5:t=12,"
        f"drawtext=text='{label_escaped}'"
        f":fontcolor={text_color}:fontsize=52:x=(w-text_w)/2:y=h/2-120"
        f":borderw=3:bordercolor=black,"
        f"drawtext=text='{escaped}'"
        f":fontcolor=#A0AEC0:fontsize=38:x=60:y=h/2:w={TARGET_W-120}"
        f":line_spacing=10:borderw=2:bordercolor=black"
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c={bg_color}:size={TARGET_W}x{TARGET_H}:rate=30",
        "-t", str(max(duration, 2.0)),
        "-vf", vf,
        "-c:v", "libx264", "-crf", "28", "-preset", "ultrafast",
        "-an",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        # 간소화 버전으로 재시도 (drawtext 없이)
        cmd_simple = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c={bg_color}:size={TARGET_W}x{TARGET_H}:rate=30",
            "-t", str(max(duration, 2.0)),
            "-c:v", "libx264", "-crf", "28", "-preset", "ultrafast",
            "-an",
            output_path,
        ]
        result2 = subprocess.run(cmd_simple, capture_output=True, text=True, timeout=60)
        if result2.returncode != 0:
            raise RuntimeError(f"플레이스홀더 클립 생성 실패: {result2.stderr}")

    return output_path


def create_stock_placeholder(
    narration: str,
    duration: float,
    output_path: str,
) -> str:
    """Stock 영상이 없는 장면용 플레이스홀더 (회색)"""
    return create_placeholder_clip(
        narration=narration,
        duration=duration,
        output_path=output_path,
        bg_color="0x2d3748",
        border_color="0x718096",
        label="📦 Stock 준비 필요",
    )


# ─────────────────────────────────────────────────────────────
# 2. 자막 오버레이 추가
# ─────────────────────────────────────────────────────────────

def add_subtitle_overlay(
    input_path: str,
    text: str,
    output_path: str,
    font_size: int = 48,
    text_color: str = "white",
    bg_color: str = "black@0.55",
    y_position: str = "h*0.82",
) -> str:
    """영상에 자막 텍스트 오버레이 추가"""
    escaped = _escape_ffmpeg_text(text[:40])

    vf = (
        f"drawbox=x=0:y={y_position}-10:w=iw:h={font_size + 30}"
        f":color={bg_color}:t=fill,"
        f"drawtext=text='{escaped}'"
        f":fontcolor={text_color}:fontsize={font_size}"
        f":x=(w-text_w)/2:y={y_position}"
        f":borderw=3:bordercolor=black"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264", "-crf", "22", "-preset", "fast",
        "-c:a", "copy",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        # 자막 없이 그냥 복사
        import shutil
        shutil.copy2(input_path, output_path)
    return output_path


# ─────────────────────────────────────────────────────────────
# 3. 영상 크기 맞추기 (concat 전 필수)
# ─────────────────────────────────────────────────────────────

def normalize_clip(input_path: str, output_path: str, duration: Optional[float] = None) -> str:
    """
    1080x1920, 30fps, yuv420p로 통일.
    duration이 지정되면 해당 길이만큼만 사용.
    """
    vf = f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p"

    cmd = ["ffmpeg", "-y", "-i", input_path]
    if duration:
        cmd += ["-t", str(duration)]
    cmd += ["-vf", vf, "-c:v", "libx264", "-crf", "22", "-preset", "fast", "-an", output_path]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"normalize_clip 실패: {result.stderr[-500:]}")
    return output_path


# ─────────────────────────────────────────────────────────────
# 4. Scene용 클립 결정 및 준비
# ─────────────────────────────────────────────────────────────

def _find_converted_asset(asset_id: str, converted_dir: str) -> Optional[str]:
    """변환된 9:16 파일 탐색"""
    converted_path = Path(converted_dir)
    if not converted_path.exists():
        return None

    from db.adforge_db import get_asset
    asset_data = get_asset(asset_id)
    if not asset_data:
        return None

    raw_path = asset_data.get("local_path", "")
    if not raw_path:
        return None

    stem = Path(raw_path).stem
    # 변환 파일 탐색: <stem>_916.mp4
    candidate = converted_path / f"{stem}_916.mp4"
    if candidate.exists():
        return str(candidate)

    # 폴더 내 stem 포함 파일 탐색
    for f in converted_path.glob("*.mp4"):
        if stem in f.stem:
            return str(f)
    return None


def prepare_scene_clip(
    scene_order: int,
    narration: str,
    visual_description: str,
    stock_asset_id: Optional[str],
    ai_video_required: bool,
    duration: float,
    temp_dir: str,
    converted_dir: str = "stock_videos/converted_916",
    raw_dir: str = "stock_videos/v2",
    add_subtitles: bool = True,
) -> tuple:
    """
    Scene 하나에 대한 클립을 준비한다.
    반환: (clip_path, source_type)
      source_type: "stock" | "ai_placeholder" | "missing_placeholder"
    """
    clip_base = os.path.join(temp_dir, f"scene_{scene_order:02d}")
    clip_norm = clip_base + "_norm.mp4"
    clip_final = clip_base + "_final.mp4"

    source_type = "missing_placeholder"
    raw_clip = None

    # 1) Stock 변환 파일 탐색
    if stock_asset_id:
        converted = _find_converted_asset(stock_asset_id, converted_dir)
        if converted and os.path.exists(converted):
            raw_clip = converted
            source_type = "stock"
        else:
            # 변환 안 됐으면 raw 파일 직접 사용
            from db.adforge_db import get_asset
            asset_data = get_asset(stock_asset_id)
            if asset_data:
                raw_path = asset_data.get("local_path", "")
                if raw_path and os.path.exists(raw_path):
                    raw_clip = raw_path
                    source_type = "stock_raw"

    # 2) AI 영상 필요 장면 → 플레이스홀더
    if raw_clip is None and ai_video_required:
        ph = clip_base + "_placeholder.mp4"
        create_placeholder_clip(
            narration=narration,
            duration=duration,
            output_path=ph,
            label="🤖 AI Video (Hailuo 생성 필요)",
        )
        raw_clip = ph
        source_type = "ai_placeholder"

    # 3) 소스 없음 → 회색 플레이스홀더
    if raw_clip is None:
        ph = clip_base + "_placeholder.mp4"
        create_stock_placeholder(narration=narration, duration=duration, output_path=ph)
        raw_clip = ph
        source_type = "missing_placeholder"

    # 4) 크기/FPS 통일
    try:
        normalize_clip(raw_clip, clip_norm, duration=duration if source_type == "stock" else None)
    except Exception:
        # normalize 실패시 플레이스홀더 사용
        ph = clip_base + "_fallback.mp4"
        create_placeholder_clip(narration=narration, duration=duration, output_path=ph)
        normalize_clip(ph, clip_norm)
        source_type = "missing_placeholder"

    # 5) 자막 오버레이
    if add_subtitles and narration.strip():
        try:
            add_subtitle_overlay(clip_norm, narration, clip_final)
        except Exception:
            import shutil
            shutil.copy2(clip_norm, clip_final)
    else:
        import shutil
        shutil.copy2(clip_norm, clip_final)

    return clip_final, source_type


# ─────────────────────────────────────────────────────────────
# 5. 전체 Preview 생성
# ─────────────────────────────────────────────────────────────

def generate_preview(
    scenes: list,       # List[Scene]
    output_path: str,
    converted_dir: str = "stock_videos/converted_916",
    raw_dir: str = "stock_videos/v2",
    add_subtitles: bool = True,
    progress_callback=None,   # callback(i, total, msg)
) -> Dict:
    """
    모든 Scene을 조합해 미리보기 MP4를 생성한다.
    반환: {
        "output_path": str,
        "scene_results": [(order, source_type), ...],
        "total_duration": float,
    }
    """
    sorted_scenes = sorted(scenes, key=lambda s: s.order)
    total = len(sorted_scenes)
    scene_results = []

    with tempfile.TemporaryDirectory(prefix="adforge_preview_") as temp_dir:
        clip_paths = []

        for i, scene in enumerate(sorted_scenes):
            if progress_callback:
                progress_callback(i, total, f"Scene {scene.order:02d} 준비 중...")

            dur = max(scene.end_time - scene.start_time, 2.5)

            try:
                clip_path, source_type = prepare_scene_clip(
                    scene_order=scene.order,
                    narration=scene.narration,
                    visual_description=scene.visual_description,
                    stock_asset_id=scene.stock_asset_id,
                    ai_video_required=scene.ai_video_required,
                    duration=dur,
                    temp_dir=temp_dir,
                    converted_dir=converted_dir,
                    raw_dir=raw_dir,
                    add_subtitles=add_subtitles,
                )
                clip_paths.append(clip_path)
                scene_results.append((scene.order, source_type))
            except Exception as e:
                # 실패한 장면은 에러 플레이스홀더로 대체
                ph = os.path.join(temp_dir, f"scene_{scene.order:02d}_error.mp4")
                create_placeholder_clip(
                    narration=f"[오류] {str(e)[:40]}",
                    duration=dur,
                    output_path=ph,
                    bg_color="0x6B1212",
                    border_color="0xFF4444",
                    label="❌ 오류",
                )
                norm = ph.replace("_error.mp4", "_error_norm.mp4")
                try:
                    normalize_clip(ph, norm)
                    clip_paths.append(norm)
                except Exception:
                    pass
                scene_results.append((scene.order, "error"))

        if not clip_paths:
            raise RuntimeError("조합할 클립이 없습니다.")

        # concat list 파일 생성
        concat_file = os.path.join(temp_dir, "concat.txt")
        with open(concat_file, "w", encoding="utf-8") as f:
            for cp in clip_paths:
                f.write(f"file '{cp}'\n")

        if progress_callback:
            progress_callback(total - 1, total, "영상 합치는 중...")

        # 최종 concat
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c:v", "libx264", "-crf", "22", "-preset", "fast",
            "-movflags", "+faststart",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"concat 실패: {result.stderr[-1000:]}")

    total_duration = sum(max(s.end_time - s.start_time, 2.5) for s in sorted_scenes)

    return {
        "output_path": output_path,
        "scene_results": scene_results,
        "total_duration": total_duration,
    }


# ─────────────────────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────────────────────

def _escape_ffmpeg_text(text: str) -> str:
    """ffmpeg drawtext용 특수문자 이스케이프"""
    return (
        text
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace(":", "\\:")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace(",", "\\,")
    )


def get_video_info_simple(path: str) -> dict:
    """파일 크기 + 길이 빠른 조회"""
    try:
        stat = os.stat(path)
        size_mb = stat.st_size / (1024 * 1024)
    except Exception:
        size_mb = 0.0

    try:
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        data = json.loads(r.stdout)
        duration = float(data.get("format", {}).get("duration", 0))
    except Exception:
        duration = 0.0

    return {"size_mb": size_mb, "duration": duration}
