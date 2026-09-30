"""Reuse editable CapCut sound effects from a user-provided reference draft."""

import copy
import json
import os
import uuid


SOUND_BY_ROLE = {
    "hook": "사진 찍는 소리",
    "problem": "경고음",
    "result": "Wow",
    "cta": "Money Chakin(1184192)",
}


def apply_reference_sfx(destination_folder: str, reference_folder: str, scenes: list[dict]) -> list[str]:
    """Add up to four native SFX with the source project's metadata and cache paths."""
    source_path = os.path.join(reference_folder, "draft_content.json")
    destination_path = os.path.join(destination_folder, "draft_content.json")
    if not os.path.isfile(source_path):
        return []
    with open(source_path, encoding="utf-8") as handle:
        reference = json.load(handle)
    with open(destination_path, encoding="utf-8") as handle:
        destination = json.load(handle)

    source_materials = reference.get("materials", {})
    sounds = {
        sound.get("name"): sound for sound in source_materials.get("audios", [])
        if sound.get("type") == "sound" and os.path.isfile(sound.get("path") or "")
    }
    source_segments = {
        segment.get("material_id"): segment
        for track in reference.get("tracks", []) if track.get("type") == "audio"
        for segment in track.get("segments", [])
    }
    source_refs = {
        material.get("id"): (group_name, material)
        for group_name, group in source_materials.items() if isinstance(group, list)
        for material in group if isinstance(material, dict) and material.get("id")
    }
    sound_track = next(
        (track for track in destination.get("tracks", [])
         if track.get("type") == "audio" and track.get("name") == "효과음_트랙"), None
    )
    if sound_track is None:
        return []

    added = []
    for scene in scenes:
        name = SOUND_BY_ROLE.get(scene["role"])
        sound = sounds.get(name)
        template = source_segments.get(sound.get("id")) if sound else None
        if not template or len(added) >= 4:
            continue
        duration = min(sound.get("duration", 0), scene["duration_us"], 1_600_000)
        if duration < 100_000:
            continue

        material = copy.deepcopy(sound)
        material["id"] = uuid.uuid4().hex
        destination["materials"].setdefault("audios", []).append(material)

        segment = copy.deepcopy(template)
        segment["id"] = uuid.uuid4().hex
        segment["material_id"] = material["id"]
        segment["source_timerange"] = {"start": 0, "duration": duration}
        segment["target_timerange"] = {"start": scene["start_us"], "duration": duration}
        segment["volume"] = min(float(segment.get("volume", 1)), 0.35)
        new_refs = []
        for old_id in segment.get("extra_material_refs", []):
            source_ref = source_refs.get(old_id)
            if not source_ref:
                continue
            group_name, reference_material = source_ref
            cloned = copy.deepcopy(reference_material)
            cloned["id"] = uuid.uuid4().hex
            destination["materials"].setdefault(group_name, []).append(cloned)
            new_refs.append(cloned["id"])
        segment["extra_material_refs"] = new_refs
        sound_track.setdefault("segments", []).append(segment)
        added.append(name)

    if added:
        sound_track["segments"].sort(key=lambda segment: segment["target_timerange"]["start"])
        with open(destination_path, "w", encoding="utf-8") as handle:
            json.dump(destination, handle, ensure_ascii=False, separators=(",", ":"))
    return added
