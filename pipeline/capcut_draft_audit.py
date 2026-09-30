"""Check that an editable CapCut draft actually references its media and effects."""

import json
import os


def audit_draft(draft_path: str) -> dict:
    with open(os.path.join(draft_path, "draft_content.json"), encoding="utf-8") as handle:
        content = json.load(handle)

    materials = content.get("materials", {})
    tracks = content.get("tracks", [])
    all_materials = {
        material.get("id"): material
        for group in materials.values()
        if isinstance(group, list)
        for material in group
        if isinstance(material, dict) and material.get("id")
    }
    counts = {kind: 0 for kind in ("video", "audio", "sfx", "text")}
    referenced = {kind: set() for kind in ("transitions", "video_effects", "material_animations")}
    known_effect_ids = {
        kind: {item.get("id") for item in materials.get(kind, [])}
        for kind in referenced
    }
    missing_materials = []
    missing_files = []
    unlinked_effects = []
    longest_video_us = 0
    for track in tracks:
        kind = track.get("type")
        for segment in track.get("segments", []):
            count_kind = "sfx" if kind == "audio" and track.get("name") == "효과음_트랙" else kind
            if count_kind in counts:
                counts[count_kind] += 1
            if kind == "video":
                duration = (segment.get("target_timerange") or {}).get("duration") or 0
                longest_video_us = max(longest_video_us, int(duration))
            material_id = segment.get("material_id")
            material = all_materials.get(material_id)
            if material_id and material is None:
                missing_materials.append(material_id)
            if material and kind in ("video", "audio"):
                path = material.get("path")
                if path and not os.path.isfile(path):
                    missing_files.append(path)
            for ref in segment.get("extra_material_refs", []):
                matched = False
                for effect_kind, ids in known_effect_ids.items():
                    if ref in ids:
                        referenced[effect_kind].add(ref)
                        matched = True
                if not matched and ref not in all_materials:
                    unlinked_effects.append(ref)

    return {
        "clips": counts,
        "effects": {kind: len(ids) for kind, ids in referenced.items()},
        "missing_materials": sorted(set(missing_materials)),
        "missing_files": sorted(set(missing_files)),
        "unlinked_effects": sorted(set(unlinked_effects)),
        # 소스 하나가 타임라인에 머무는 가장 긴 시간 (컷당 3초 규칙 확인용)
        "longest_video_clip_sec": round(longest_video_us / 1_000_000, 2),
        # pyCapCut can emit text style refs without separate material records.
        "ok": bool(counts["audio"] and counts["text"] and not missing_materials
                   and not missing_files),
    }
