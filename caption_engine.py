import os
import json
import subprocess
import time
import uuid

VENDOR_DIR = os.path.join(os.path.dirname(__file__), "vendor", "caption-os")
BUILD_HTML_SCRIPT = os.path.join(VENDOR_DIR, "lib", "build_caption_html.mjs")
RENDER_CAPS_SCRIPT = os.path.join(VENDOR_DIR, "lib", "render_caps.cjs")
MANIFEST_PATH = os.path.join(VENDOR_DIR, "fonts", "manifest.json")

def generate_plan_json(phrases_data, total_duration_us, style="karaoke", mood="professional", plan_out_path="plan.json"):
    """
    phrases_data: list of dicts { 'text': str, 'start_us': int, 'end_us': int }
    """
    duration_sec = total_duration_us / 1000000.0
    
    accent_color = None
    try:
        if os.path.exists(MANIFEST_PATH):
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                manifest = json.load(f)
                for cat in manifest.get("categories", []):
                    if cat["key"] == mood:
                        # try to get an interesting accent color
                        palette = cat.get("palette", {})
                        accent_color = palette.get("ink") or palette.get("accent1")
                        break
    except Exception as e:
        print(f"Error reading manifest: {e}")

    lines_formatted = []
    for line in phrases_data:
        words = []
        for p in line["phrases"]:
            words.append({
                "w": p["text"],
                "start": p["start_us"] / 1000000.0,
                "end": p["end_us"] / 1000000.0
            })
        lines_formatted.append({
            "start": line["start_us"] / 1000000.0,
            "end": line["end_us"] / 1000000.0,
            "words": words,
            "text": " ".join([w["w"] for w in words])
        })

    plan = {
        "lang": "ko",
        "style": style,
        "duration": duration_sec,
        "lines": lines_formatted
    }
    if accent_color:
        plan["accent"] = accent_color

    with open(plan_out_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    return plan_out_path

def render_caption_frames(plan_path, duration_sec, fps=30):
    html_out_path = plan_path.replace(".json", ".html")
    frames_out_dir = plan_path.replace(".json", "_frames")
    
    # 1. Build HTML
    cmd_build = ["node", BUILD_HTML_SCRIPT, plan_path, html_out_path]
    subprocess.run(cmd_build, check=True)
    
    # 2. Render Frames
    cmd_render = ["node", RENDER_CAPS_SCRIPT, html_out_path, frames_out_dir, str(duration_sec), str(fps), "1080", "1920"]
    subprocess.run(cmd_render, check=True)
    
    return frames_out_dir

def composite_final_video(base_video_path, frames_dir, output_path, fps=30):
    """
    Overlay the PNG sequence over the base video.
    """
    cmd = [
        "ffmpeg",
        "-i", base_video_path,
        "-framerate", str(fps),
        "-i", os.path.join(frames_dir, "f-%05d.png"),
        "-filter_complex", "[1:v]scale=1080:1920[cap];[0:v][cap]overlay=0:0:format=auto",
        "-c:v", "libx264",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-y", output_path
    ]
    subprocess.run(cmd, check=True)
    return output_path

def render_transparent_video(frames_dir, output_path, fps=30):
    """
    PNG 시퀀스를 알파 채널(투명도)이 유지되는 ProRes 4444 코덱의 .mov 영상으로 변환합니다.
    이 영상은 캡컷에서 최상단 비디오 트랙에 올리면 배경이 투명하게 빠집니다.
    """
    cmd = [
        "ffmpeg",
        "-framerate", str(fps),
        "-i", os.path.join(frames_dir, "f-%05d.png"),
        "-c:v", "prores_ks",
        "-profile:v", "4444",
        "-pix_fmt", "yuva444p10le",
        "-y", output_path
    ]
    subprocess.run(cmd, check=True)
    return output_path
