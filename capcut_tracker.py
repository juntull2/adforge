"""CapCut Project Tracker & Style Preset Engine for AdForge.

Allows scanning local CapCut draft directories, inspecting used effects,
transitions, and subtitle styles, saving them as reusable presets, and
injecting them into newly generated CapCut projects.
"""

import os
import json
import uuid
import glob
import copy
from datetime import datetime
from typing import List, Dict, Any, Optional

PRESETS_FILE = os.path.join(os.path.dirname(__file__), "outputs", "capcut_presets.json")


def get_capcut_draft_dir() -> str:
    """사용자 PC의 캡컷 로컬 드래프트 폴더 경로를 반환합니다."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        local_app_data = os.path.expanduser("~\\AppData\\Local")
    
    # CapCut 글로벌 PC 버전 기본 경로
    capcut_path = os.path.join(local_app_data, "CapCut", "User Data", "Projects", "com.lveditor.draft")
    if os.path.exists(capcut_path):
        return capcut_path
    
    # Jianying(중국어판) 호환 경로
    jianying_path = os.path.join(local_app_data, "JianyingPro", "User Data", "Projects", "com.lveditor.draft")
    if os.path.exists(jianying_path):
        return jianying_path
        
    return capcut_path


def list_local_projects(limit: int = 50) -> List[Dict[str, Any]]:
    """로컬 캡컷 프로젝트 목록을 최신 수정일순으로 반환합니다."""
    draft_dir = get_capcut_draft_dir()
    if not os.path.exists(draft_dir):
        return []

    folders = [
        f for f in glob.glob(os.path.join(draft_dir, "*"))
        if os.path.isdir(f)
    ]
    folders.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    folders = folders[:limit]

    projects = []
    for f in folders:
        meta_path = os.path.join(f, "draft_meta_info.json")
        content_path = os.path.join(f, "draft_content.json")
        cover_path = os.path.join(f, "draft_cover.jpg")

        draft_name = os.path.basename(f)
        draft_id = ""
        duration_sec = 0.0
        create_time_str = ""
        modify_time_str = datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M")

        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as mf:
                    meta = json.load(mf)
                    draft_name = meta.get("draft_name") or draft_name
                    draft_id = meta.get("draft_id", "")
                    dur_us = meta.get("tm_duration", 0)
                    duration_sec = round(dur_us / 1000000.0, 1) if dur_us else 0.0
                    create_us = meta.get("tm_draft_create", 0)
                    if create_us:
                        # 캡컷 타임스탬프는 마이크로초
                        create_time_str = datetime.fromtimestamp(create_us / 1000000.0).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass

        counts = {
            "texts": 0,
            "effects": 0,
            "transitions": 0,
            "animations": 0,
            "videos": 0,
            "audios": 0,
            "stickers": 0
        }

        if os.path.exists(content_path):
            try:
                with open(content_path, "r", encoding="utf-8") as cf:
                    content = json.load(cf)
                    m = content.get("materials", {})
                    counts["texts"] = len(m.get("texts", []))
                    counts["effects"] = len(m.get("effects", []))
                    counts["transitions"] = len(m.get("transitions", []))
                    counts["animations"] = len(m.get("material_animations", []))
                    counts["videos"] = len(m.get("videos", []))
                    counts["audios"] = len(m.get("audios", []))
                    counts["stickers"] = len(m.get("stickers", []))
            except Exception:
                pass

        projects.append({
            "folder_name": os.path.basename(f),
            "folder_path": f,
            "draft_name": draft_name,
            "draft_id": draft_id,
            "duration_sec": duration_sec,
            "create_time": create_time_str or modify_time_str,
            "modify_time": modify_time_str,
            "has_cover": os.path.exists(cover_path),
            "cover_path": cover_path if os.path.exists(cover_path) else None,
            "counts": counts
        })

    return projects


def inspect_project_details(folder_path: str) -> Dict[str, Any]:
    """프로젝트 폴더의 상세 자막 스타일, 효과, 전환 정보를 정밀 파싱합니다."""
    content_path = os.path.join(folder_path, "draft_content.json")
    if not os.path.exists(content_path):
        return {"error": "draft_content.json 파일이 존재하지 않습니다."}

    with open(content_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    materials = data.get("materials", {})
    tracks = data.get("tracks", [])

    # 1. 텍스트 트랙 세그먼트와 extra_material_refs 맵 구축
    text_seg_refs = {}
    for tr in tracks:
        if tr.get("type") == "text":
            for s in tr.get("segments", []):
                mat_id = s.get("material_id")
                if mat_id:
                    text_seg_refs[mat_id] = s.get("extra_material_refs", [])

    # 2. 자막 스타일 분석
    parsed_texts = []
    raw_texts = materials.get("texts", [])
    for t in raw_texts:
        t_id = t.get("id")
        content_str = t.get("content", "")
        text_preview = ""
        font_name = t.get("font_name") or t.get("font_title") or "기본 폰트"
        font_path = t.get("font_path", "")
        color_rgb = [1.0, 1.0, 1.0]
        border_info = {"has_border": False, "color": [0.0, 0.0, 0.0], "width": 0.0}
        shadow_info = {"has_shadow": t.get("has_shadow", False)}
        font_size = t.get("font_size") or 8.0

        if content_str:
            try:
                c_json = json.loads(content_str)
                text_preview = c_json.get("text", "")
                styles = c_json.get("styles", [])
                if styles:
                    st0 = styles[0]
                    # fill color
                    fill_solid = st0.get("fill", {}).get("content", {}).get("solid", {})
                    if "color" in fill_solid:
                        color_rgb = fill_solid["color"]
                    # font
                    if "font" in st0:
                        font_name = st0["font"].get("name") or font_name
                        font_path = st0["font"].get("path") or font_path
                    # border
                    if "border" in st0:
                        b_solid = st0["border"].get("content", {}).get("solid", {})
                        if "color" in b_solid:
                            border_info = {
                                "has_border": True,
                                "color": b_solid["color"],
                                "width": st0["border"].get("width", 25.0)
                            }
                    # size
                    if "size" in st0:
                        font_size = st0["size"]
            except Exception:
                text_preview = content_str[:50]

        # fallback from direct properties if border exists in t
        if t.get("border_width", 0) > 0 and not border_info["has_border"]:
            border_info = {
                "has_border": True,
                "color": t.get("border_color", [0.0, 0.0, 0.0]),
                "width": t.get("border_width", 25.0)
            }

        parsed_texts.append({
            "id": t_id,
            "text": text_preview.strip(),
            "font_name": font_name,
            "font_path": font_path,
            "color_rgb": color_rgb,
            "font_size": font_size,
            "border": border_info,
            "shadow": shadow_info,
            "extra_refs": text_seg_refs.get(t_id, [])
        })

    # 3. 효과 (Effects) 목록
    parsed_effects = []
    for eff in materials.get("effects", []):
        parsed_effects.append({
            "id": eff.get("id"),
            "name": eff.get("name") or "효과",
            "effect_id": eff.get("effect_id"),
            "resource_id": eff.get("resource_id"),
            "type": eff.get("type", "effect"),
            "sub_type": eff.get("sub_type", "none"),
            "path": eff.get("path", "")
        })

    # 4. 전환 (Transitions) 목록
    parsed_transitions = []
    for tr in materials.get("transitions", []):
        parsed_transitions.append({
            "id": tr.get("id"),
            "name": tr.get("name") or "전환",
            "effect_id": tr.get("effect_id"),
            "resource_id": tr.get("resource_id"),
            "duration": tr.get("duration", 500000),
            "path": tr.get("path", "")
        })

    # 5. 애니메이션 (Material Animations) 목록
    parsed_animations = []
    for ma in materials.get("material_animations", []):
        for anim in ma.get("animations", []):
            parsed_animations.append({
                "id": anim.get("id"),
                "name": anim.get("name") or "애니메이션",
                "type": anim.get("type"),
                "duration": anim.get("duration", 0),
                "resource_id": anim.get("resource_id"),
                "path": anim.get("path", "")
            })

    return {
        "texts": parsed_texts,
        "effects": parsed_effects,
        "transitions": parsed_transitions,
        "animations": parsed_animations,
        "raw_materials": materials
    }


def _ensure_presets_file():
    os.makedirs(os.path.dirname(PRESETS_FILE), exist_ok=True)
    if not os.path.exists(PRESETS_FILE):
        with open(PRESETS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)


def load_presets() -> List[Dict[str, Any]]:
    """저장된 스타일 프리셋 목록을 반환합니다."""
    _ensure_presets_file()
    try:
        with open(PRESETS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ 프리셋 로드 실패: {e}")
        return []


def save_preset_from_project(
    project_folder: str,
    preset_name: str,
    description: str = ""
) -> Dict[str, Any]:
    """선택된 캡컷 프로젝트에서 스타일/효과/전환을 추출하여 프리셋으로 저장합니다."""
    details = inspect_project_details(project_folder)
    if "error" in details:
        raise ValueError(details["error"])

    # 자막 스타일 대표값 추출 (자막이 여러 개면 첫 번째 훅 자막과 일반 자막 분리)
    texts = details["texts"]
    hook_style = {}
    body_style = {}

    if texts:
        # 첫 번째 자막 (훅)
        t0 = texts[0]
        hook_style = {
            "font_name": t0["font_name"],
            "font_path": t0["font_path"],
            "color_rgb": t0["color_rgb"],
            "font_size": t0["font_size"],
            "border": t0["border"]
        }
        # 두 번째 자막 또는 첫 번째 자막 (본문)
        t1 = texts[1] if len(texts) > 1 else t0
        body_style = {
            "font_name": t1["font_name"],
            "font_path": t1["font_path"],
            "color_rgb": t1["color_rgb"],
            "font_size": t1["font_size"],
            "border": t1["border"]
        }

    # 효과 목록
    effects = details["effects"]
    # 전환 효과 목록
    transitions = details["transitions"]
    # 애니메이션 목록
    animations = details["animations"]

    preset = {
        "id": str(uuid.uuid4())[:8],
        "name": preset_name,
        "description": description,
        "source_project": os.path.basename(project_folder),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "hook_text_style": hook_style,
        "body_text_style": body_style,
        "effects": effects,
        "transitions": transitions,
        "animations": animations,
        # 원본 복제를 위한 raw materials 일부 보존
        "raw_template": {
            "effects": details["raw_materials"].get("effects", []),
            "transitions": details["raw_materials"].get("transitions", []),
            "material_animations": details["raw_materials"].get("material_animations", [])
        }
    }

    presets = load_presets()
    presets.insert(0, preset)

    with open(PRESETS_FILE, "w", encoding="utf-8") as f:
        json.dump(presets, f, ensure_ascii=False, indent=2)

    return preset


def delete_preset(preset_id: str) -> bool:
    """특정 프리셋을 삭제합니다."""
    presets = load_presets()
    new_presets = [p for p in presets if p.get("id") != preset_id]
    if len(new_presets) != len(presets):
        with open(PRESETS_FILE, "w", encoding="utf-8") as f:
            json.dump(new_presets, f, ensure_ascii=False, indent=2)
        return True
    return False


def apply_preset_to_draft(draft_folder_path: str, preset: Dict[str, Any]) -> bool:
    """새로 생성된 CapCut 프로젝트(초안)에 프리셋의 캡컷 효과, 전환 효과, 자막 스타일을 직접 주입합니다."""
    content_path = os.path.join(draft_folder_path, "draft_content.json")
    if not os.path.exists(content_path):
        return False

    try:
        with open(content_path, "r", encoding="utf-8") as f:
            content = json.load(f)

        materials = content.setdefault("materials", {})
        tracks = content.setdefault("tracks", [])

        # -------------------------------------------------------------
        # 1. 전환 효과 (Transitions) 주입
        # -------------------------------------------------------------
        preset_transitions = preset.get("raw_template", {}).get("transitions", []) or preset.get("transitions", [])
        if preset_transitions:
            target_trans = copy.deepcopy(preset_transitions[0])
            # 새 UUID 부여 및 등록
            trans_id = str(uuid.uuid4()).upper()
            target_trans["id"] = trans_id
            materials.setdefault("transitions", []).append(target_trans)

            # 비디오 트랙을 찾아서 컷과 컷 사이에 전환 효과 적용
            for tr in tracks:
                if tr.get("type") == "video":
                    segs = tr.get("segments", [])
                    # 마지막 세그먼트를 제외한 앞 세그먼트들에 전환 효과 바인딩
                    for s in segs[:-1]:
                        s["transition_id"] = trans_id

        # -------------------------------------------------------------
        # 2. 텍스트 효과 (Text Effects) 주입
        # -------------------------------------------------------------
        preset_effects = preset.get("raw_template", {}).get("effects", []) or preset.get("effects", [])
        text_effects = [e for e in preset_effects if e.get("type") == "text_effect"]
        applied_effect_id = None

        if text_effects:
            target_eff = copy.deepcopy(text_effects[0])
            applied_effect_id = str(uuid.uuid4()).upper()
            target_eff["id"] = applied_effect_id
            materials.setdefault("effects", []).append(target_eff)

        # -------------------------------------------------------------
        # 3. 자막 스타일 & 폰트 적용
        # -------------------------------------------------------------
        hook_style = preset.get("hook_text_style", {})
        body_style = preset.get("body_text_style", {})

        raw_texts = materials.get("texts", [])
        for idx, t in enumerate(raw_texts):
            active_style = hook_style if idx == 0 and hook_style else body_style
            if not active_style:
                continue

            # 폰트명 및 폰트 경로 변경
            if active_style.get("font_name"):
                t["font_name"] = active_style["font_name"]
                t["font_title"] = active_style["font_name"]
            if active_style.get("font_path"):
                t["font_path"] = active_style["font_path"]

            # 내부 JSON content 문자열 업데이트
            content_str = t.get("content", "")
            if content_str:
                try:
                    c_json = json.loads(content_str)
                    if "styles" in c_json and len(c_json["styles"]) > 0:
                        st0 = c_json["styles"][0]
                        # 색상
                        if "color_rgb" in active_style:
                            st0.setdefault("fill", {}).setdefault("content", {}).setdefault("solid", {})["color"] = active_style["color_rgb"]
                        # 폰트
                        if active_style.get("font_name"):
                            st0.setdefault("font", {})["name"] = active_style["font_name"]
                            st0["font"]["title"] = active_style["font_name"]
                            if active_style.get("font_path"):
                                st0["font"]["path"] = active_style["font_path"]
                        # 테두리
                        border_data = active_style.get("border", {})
                        if border_data.get("has_border"):
                            st0.setdefault("border", {}).setdefault("content", {}).setdefault("solid", {})["color"] = border_data.get("color", [0.0, 0.0, 0.0])
                            st0["border"]["width"] = border_data.get("width", 25.0)

                        t["content"] = json.dumps(c_json, ensure_ascii=False)
                except Exception:
                    pass

        # 4. 텍스트 트랙의 훅 세그먼트에 텍스트 효과(네온 등) 연결
        if applied_effect_id:
            for tr in tracks:
                if tr.get("type") == "text":
                    segs = tr.get("segments", [])
                    if segs:
                        hook_seg = segs[0]
                        extra_refs = hook_seg.setdefault("extra_material_refs", [])
                        if applied_effect_id not in extra_refs:
                            extra_refs.append(applied_effect_id)

        # 저장
        with open(content_path, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)

        return True
    except Exception as e:
        print(f"⚠️ 프리셋 적용 중 오류: {e}")
        return False
