"""Compile an explicit reference edit plan to a fresh, editable native draft."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import uuid

import pycapcut as cc

from .analysis import probe
from .catalog import clone_material


def _us(seconds):
    return round(seconds * 1_000_000)


def _local_copy(path, root):
    source = Path(path).resolve()
    if not source.is_file():
        raise ValueError(f'미디어 파일 없음: {source.name}')
    name = hashlib.sha256(str(source).encode()).hexdigest()[:12] + source.suffix.lower()
    target = root / 'media' / name
    target.parent.mkdir(exist_ok=True)
    if not target.exists():
        shutil.copy2(source, target)
    return str(target)


def render_plan(plan, output_root, catalog, project_name=None):
    plan.validate(require_sources=True)
    name = project_name or f'AdForge_Reference_{uuid.uuid4().hex[:10]}'
    if Path(name).name != name or name in ('', '.', '..'):
        raise ValueError('프로젝트 이름이 유효하지 않습니다.')
    root = Path(output_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    folder = root / name
    if folder.exists():
        raise FileExistsError('기존 프로젝트를 덮어쓰지 않습니다.')
    script = cc.DraftFolder(str(root)).create_draft(name, plan.width, plan.height, plan.fps)
    for kind, label in ((cc.TrackType.video, '영상'), (cc.TrackType.text, '자막'), (cc.TrackType.audio, '나레이션')):
        script.add_track(kind, label)
    video_ids, text_ids = [], []
    for shot in plan.shots:
        material = cc.VideoMaterial(_local_copy(shot.asset_path, folder))
        if shot.source_end > material.duration / 1_000_000 + 0.05:
            raise ValueError('선택된 소스 범위가 실제 영상 길이를 초과합니다.')
        # Fill the canvas rather than leaving accidental letterboxing.
        scale = max(plan.width / material.width, plan.height / material.height) / min(plan.width / material.width, plan.height / material.height)
        segment = cc.VideoSegment(material, cc.trange(_us(shot.start), _us(shot.end)-_us(shot.start)),
                                  source_timerange=cc.trange(_us(shot.source_start), _us(shot.source_end)-_us(shot.source_start)),
                                  volume=0, clip_settings=cc.ClipSettings(scale_x=scale, scale_y=scale))
        if shot.motion != 'static':
            left, right = (scale, scale * 1.08) if shot.motion == 'zoom_in' else (scale * 1.08, scale)
            segment.add_keyframe(cc.KeyframeProperty.uniform_scale, 0, left)
            segment.add_keyframe(cc.KeyframeProperty.uniform_scale, segment.duration, right)
        script.add_segment(segment, '영상')
        video_ids.append(segment.segment_id)
    cursor = 0
    for beat in plan.audio:
        segment = cc.AudioSegment(_local_copy(beat.path, folder), cc.trange(_us(cursor), _us(beat.duration)))
        script.add_segment(segment, '나레이션'); cursor += beat.duration
    for caption in plan.captions:
        segment = cc.TextSegment(caption.text, cc.trange(_us(caption.start), _us(caption.end)-_us(caption.start)),
                                 style=cc.TextStyle(size=caption.size, align=1, color=tuple(caption.color),
                                                    auto_wrapping=True, max_line_width=0.82),
                                 clip_settings=cc.ClipSettings(transform_y=caption.y))
        script.add_segment(segment, '자막')
        text_ids.append(segment.segment_id)
    script.save()
    file = folder / 'draft_content.json'
    data = json.loads(file.read_text(encoding='utf-8'))
    data['canvas_config'] = {'width': plan.width, 'height': plan.height, 'ratio': '9:16'}
    segments = {s['id']: s for t in data['tracks'] for s in t['segments']}
    texts = {m['id']: m for m in data['materials'].get('texts', [])}
    for caption, sid in zip(plan.captions, text_ids):
        text = texts[segments[sid]['material_id']]
        content = json.loads(text['content'])
        if caption.font_path:
            font = _local_copy(caption.font_path, folder)
            text.update(font_path=font, font_name=Path(caption.font_path).stem)
            for style in content.get('styles', []):
                style['font'] = {'path': font, 'id': '', 'name': Path(caption.font_path).stem}
        # Apply emphasis only to verbatim words; separate style spans remain editable.
        base_style = deepcopy(content['styles'][0]) if content.get('styles') else {}
        for word in caption.emphasis:
            offset = caption.text.find(word)
            if offset >= 0:
                emphasis = deepcopy(base_style)
                emphasis.update(range=[offset, offset + len(word)], bold=True)
                emphasis['fill'] = {'content': {'solid': {'color': [1.0, 0.85, 0.2], 'alpha': 1.0}}}
                content.setdefault('styles', []).append(emphasis)
        text['content'] = json.dumps(content, ensure_ascii=False)
    entries = {e['key']: e for e in catalog['entries']}
    applied, missing = [], []
    def apply(key, sid, duration):
        entry = entries.get(key)
        if not entry:
            raise ValueError(f'선택한 네이티브 리소스를 찾을 수 없습니다: {key}')
        source_path = Path(entry['source_project']) / 'draft_content.json'
        source = json.loads(source_path.read_text(encoding='utf-8'))
        fresh = clone_material(source['materials'], entry['material_id'], data['materials'])
        segment = segments[sid]
        material = next(m for bucket in data['materials'].values() if isinstance(bucket, list)
                        for m in bucket if isinstance(m, dict) and m.get('id') == fresh)
        if entry['kind'] == 'effect' and material.get('apply_target_type') == 2:
            template = next((s for t in source.get('tracks', []) for s in t.get('segments', [])
                             if s.get('material_id') == entry['material_id']), None)
            if template is None:
                raise ValueError('효과 트랙의 원본 세그먼트를 찾을 수 없습니다.')
            effect_segment = deepcopy(template)
            effect_segment.update(id=uuid.uuid4().hex.upper(), material_id=fresh,
                                  target_timerange=deepcopy(segment['target_timerange']),
                                  extra_material_refs=[])
            effect_segment['common_keyframes'] = []
            data['tracks'].append({'id': uuid.uuid4().hex.upper(), 'type': 'effect',
                                   'attribute': 0, 'flag': 0, 'segments': [effect_segment]})
        else:
            segment.setdefault('extra_material_refs', []).append(fresh)
        if entry['kind'] == 'animation':
            material = next(m for m in data['materials']['material_animations'] if m['id'] == fresh)
            selected = [a for a in material.get('animations', []) if str(a.get('resource_id')) == entry['resource_id']
                        and a.get('type', '') == entry['subtype']]
            if not selected:
                raise ValueError('선택한 애니메이션 데이터를 찾지 못했습니다.')
            material['animations'] = selected
            for anim in selected:
                anim['start'] = 0
                anim['duration'] = min(int(anim.get('duration') or 300000), _us(duration) // 3)
        if entry['kind'] == 'transition':
            material = next(m for m in data['materials']['transitions'] if m['id'] == fresh)
            material['duration'] = min(int(material.get('duration') or 250000), _us(duration) // 4)
        applied.append(dict(key=key, segment=sid, status='requires_native_verification'))
    for shot, sid in zip(plan.shots, video_ids):
        for key in dict.fromkeys(shot.resource_keys):
            apply(key, sid, shot.end - shot.start)
    for caption, sid in zip(plan.captions, text_ids):
        if caption.animation_key:
            apply(caption.animation_key, sid, caption.end - caption.start)
    file.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    meta_path = folder / 'draft_meta_info.json'
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    meta.update(draft_name=name, draft_id=data['id'], draft_fold_path=str(folder), draft_root_path=str(root),
                tm_duration=_us(plan.duration))
    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding='utf-8')
    (folder / 'adforge_plan.json').write_text(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2), encoding='utf-8')
    result = {'project': str(folder), 'name': name, 'duration': plan.duration, 'resources': applied,
              'missing_resources': missing, 'native_verified': False}
    (folder / 'adforge_render.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result
