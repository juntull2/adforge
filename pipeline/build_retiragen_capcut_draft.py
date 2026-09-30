"""
AdForge: 레티라겐 모공요철 1:1 클론 CapCut 프로젝트 초안 생성기
"""

import os
import sys
import json
import time

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import pycapcut as cc
from pycapcut import (
    TrackType, AudioMaterial, AudioSegment, VideoMaterial, VideoSegment,
    TextSegment, TextStyle, TextBorder, ClipSettings, Timerange, SEC
)

def build_retiragen_draft():
    local_app_data = os.environ.get("LOCALAPPDATA", "C:/Users/5700G/AppData/Local")
    draft_base = os.path.join(local_app_data, "CapCut", "User Data", "Projects", "com.lveditor.draft")
    
    if not os.path.exists(draft_base):
        print(f"CapCut draft base directory not found: {draft_base}")
        return None

    project_name = f"AutoProject_레티라겐_모공프락셀_{int(time.time())}"
    project_dir = os.path.join(draft_base, project_name)
    os.makedirs(project_dir, exist_ok=True)

    print(f"🎬 CapCut 프로젝트 초안 폴더 생성: {project_dir}")
    return project_dir

if __name__ == "__main__":
    build_retiragen_draft()
