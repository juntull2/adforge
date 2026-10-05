"""Mine exact native materials; cache presence and native verification are distinct.

Inspired by LHenri88/capcut-mcp's MIT catalog design; independently implemented.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import uuid

KINDS = {'transitions': 'transition', 'video_effects': 'effect', 'effects': 'filter',
         'material_animations': 'animation', 'texts': 'text_style', 'audio_effects': 'audio_effect'}


def harvest_catalog(root):
    entries, errors = {}, []
    for path in sorted(Path(root).glob('*/draft_content.json')):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append({'project': str(path.parent), 'error': type(exc).__name__}); continue
        materials = data.get('materials') or {}
        for bucket, kind in KINDS.items():
            for material in materials.get(bucket) or []:
                items = material.get('animations', []) if bucket == 'material_animations' else [material]
                for item in items:
                    rid = item.get('resource_id') or item.get('effect_id')
                    if kind == 'text_style':
                        rid = hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()[:16]
                    if not rid or not material.get('id'):
                        continue
                    subtype = item.get('type', '') if bucket == 'material_animations' else ''
                    key = f'{kind}:{rid}:{subtype}'
                    paths = [str(item.get('path') or ''), str(item.get('file_path') or '')]
                    entry = entries.setdefault(key, {
                        'key': key, 'kind': kind, 'resource_id': str(rid), 'subtype': subtype,
                        'name': item.get('name') or item.get('title') or str(rid),
                        'source_project': str(path.parent), 'material_id': material['id'],
                        'is_pro': bool(item.get('is_vip') or item.get('is_pro') or material.get('is_vip')),
                        'cached': any(p and Path(p).exists() for p in paths),
                        'verification': 'unverified', 'seen_in': [],
                    })
                    entry['seen_in'].append(str(path.parent))
    return {'schema_version': 1, 'entries': list(entries.values()), 'errors': errors}


def clone_material(source, material_id, destination, mapping=None):
    """Clone referenced material graph, preserving resource IDs but renewing object IDs."""
    mapping = {} if mapping is None else mapping
    index = {m['id']: (bucket, m) for bucket, items in source.items() if isinstance(items, list)
             for m in items if isinstance(m, dict) and m.get('id')}
    def clone(mid):
        if mid in mapping:
            return mapping[mid]
        if mid not in index:
            raise ValueError(f'효과 종속 소재를 찾지 못했습니다: {mid}')
        bucket, material = index[mid]
        mapping[mid] = uuid.uuid4().hex.upper()
        copied = deepcopy(material)
        def renew(value):
            if isinstance(value, dict):
                for key, child in list(value.items()):
                    if key == 'id' and value is not copied and value.get('resource_id'):
                        # Native animation IDs identify cloud resources, not draft objects.
                        continue
                    elif key == 'id':
                        value[key] = mapping[mid] if value is copied else uuid.uuid4().hex.upper()
                    elif key == 'extra_material_refs':
                        value[key] = [clone(ref) for ref in child]
                    elif key.endswith('material_id') and child in index:
                        value[key] = clone(child)
                    else:
                        renew(child)
            elif isinstance(value, list):
                for child in value:
                    renew(child)
        renew(copied)
        destination.setdefault(bucket, []).append(copied)
        return mapping[mid]
    return clone(material_id)


def select_resources(plan, catalog, selections=None):
    """Explicit choices or role-compatible known materials; never invent native IDs."""
    entries = catalog['entries']
    selections = selections or {}
    def choose(kind, role, subtype='', observed=''):
        requested = selections.get(f'{kind}:{role}') or selections.get(kind)
        matches = [e for e in entries if e['kind'] == kind and (not subtype or e['subtype'] == subtype)]
        if requested:
            return next((e for e in matches if e['key'] == requested), None)
        # Auto only reuses an identified observed resource; generic cache popularity
        # cannot establish what effect the reference uses.
        matches = [e for e in matches if e['name'] and e['name'].lower() in observed.lower()]
        matches.sort(key=lambda e: (e['verification'] != 'verified', not e['cached'], -len(e['seen_in'])))
        return matches[0] if matches else None
    for caption in plan.captions:
        role = plan.audio[caption.beat].role
        shot = next((s for s in plan.shots if s.start <= (caption.start+caption.end)/2 < s.end), plan.shots[-1])
        scenes = plan.reference.get('scenes', [])
        observed = str(scenes[shot.reference_scene].get('editing', '')) if shot.reference_scene < len(scenes) else ''
        entry = choose('animation', role, 'in', observed)
        caption.animation_key = entry['key'] if entry else ''
    for i, shot in enumerate(plan.shots):
        # Preserve hard cuts within a scene; effects follow editorial purpose.
        kinds = ['effect'] if shot.role in ('hook', 'result') and i == 0 else []
        if i + 1 < len(plan.shots) and plan.shots[i + 1].reference_scene != shot.reference_scene:
            kinds.append('transition')
        for kind in kinds:
            scenes = plan.reference.get('scenes', [])
            observed = str(scenes[shot.reference_scene].get('editing', '')) if shot.reference_scene < len(scenes) else ''
            entry = choose(kind, shot.role, observed=observed)
            if entry:
                shot.resource_keys.append(entry['key'])
    if any(s.get('editing') for s in plan.reference.get('scenes', [])):
        plan.issues.append('관찰된 효과는 카탈로그 이름이 확인되는 항목만 자동 적용합니다. 미식별 효과·폰트는 수동 선택 후 실제 재생 확인이 필요합니다.')
    return plan
