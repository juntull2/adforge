"""
AdForge V2 — 9:16 Smart Crop Pipeline (ffmpeg 기반)
"""
from __future__ import annotations
import subprocess
import os
from pathlib import Path
from typing import Optional, Tuple

TARGET_W = 1080
TARGET_H = 1920
TARGET_RATIO = TARGET_W / TARGET_H  # 0.5625


def get_video_dimensions(path: str) -> Tuple[int, int, float]:
    """(width, height, duration) 반환"""
    import json
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe 실패: {result.stderr}")
    data = json.loads(result.stdout)
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            return (
                int(stream.get("width", 0)),
                int(stream.get("height", 0)),
                float(stream.get("duration", 0.0)),
            )
    raise RuntimeError(f"영상 스트림을 찾을 수 없음: {path}")


def convert_to_916(
    src_path: str,
    dest_dir: str,
    output_name: Optional[str] = None,
    overwrite: bool = False,
) -> str:
    """
    영상을 1080x1920 (9:16)으로 변환.
    이미 9:16이면 스케일만 맞춤.
    16:9는 중앙 crop.
    반환: 변환된 파일 경로
    """
    Path(dest_dir).mkdir(parents=True, exist_ok=True)
    src = Path(src_path)
    if not output_name:
        output_name = f"{src.stem}_916.mp4"
    dest_path = str(Path(dest_dir) / output_name)

    if os.path.exists(dest_path) and not overwrite:
        return dest_path

    w, h, dur = get_video_dimensions(src_path)
    if w == 0 or h == 0:
        raise RuntimeError(f"해상도 감지 실패: {src_path}")

    src_ratio = w / h

    # 이미 9:16 (±5%) → 스케일만
    if abs(src_ratio - TARGET_RATIO) < 0.05:
        vf = f"scale={TARGET_W}:{TARGET_H}:flags=lanczos"
    # 16:9 (가로) → 중앙 crop
    elif src_ratio > 1.0:
        # crop_w = h * 9/16
        crop_w = int(h * TARGET_RATIO)
        crop_x = (w - crop_w) // 2
        # 크롭 후 스케일
        vf = f"crop={crop_w}:{h}:{crop_x}:0,scale={TARGET_W}:{TARGET_H}:flags=lanczos"
    # 기타 세로 비율 → crop + scale
    else:
        crop_h = int(w / TARGET_RATIO)
        if crop_h > h:
            crop_h = h
        crop_y = (h - crop_h) // 2
        vf = f"crop={w}:{crop_h}:0:{crop_y},scale={TARGET_W}:{TARGET_H}:flags=lanczos"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(src_path),
        "-vf", vf,
        "-c:v", "libx264",
        "-crf", "18",          # 고화질
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        dest_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 변환 실패:\n{result.stderr}")

    return dest_path


def is_subject_likely_centered(w: int, h: int) -> bool:
    """
    피사체가 중앙에 있을 가능성 추정.
    세로 영상이면 True, 가로이면 False (크롭 시 주의).
    실제 CV 분석 없이 휴리스틱 사용.
    """
    return w < h  # 세로 영상이면 중앙 피사체 가능성 높음


def batch_convert(
    file_paths: list,
    dest_dir: str,
    overwrite: bool = False,
) -> list:
    """여러 파일 일괄 변환, (src, dest, ok, error) 튜플 리스트 반환"""
    results = []
    for src in file_paths:
        try:
            dest = convert_to_916(src, dest_dir, overwrite=overwrite)
            results.append((src, dest, True, None))
        except Exception as e:
            results.append((src, None, False, str(e)))
    return results
