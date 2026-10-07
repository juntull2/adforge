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


def _reference_scene(plan, shot):
    scenes = plan.reference.get('scenes', [])
    return scenes[shot.reference_scene] if shot.reference_scene < len(scenes) else {}


def _dominant(values, minimum=1):
    values = [v for v in values if v and v not in ('none', 'other', 'hard_cut')]
    if not values:
        return ''
    top = max(set(values), key=values.count)
    return top if values.count(top) >= minimum else ''


def select_resources(plan, catalog, selections=None, fonts=None, prefer_pro=True):
    """Reference-driven choice of effects, transitions, caption animation and font.

    The reference's observed families (vision + pixel measurements) select the closest real CapCut resource,
    paid ones first. An explicit ``selections`` entry always wins; ``'__disabled__'`` switches a kind off.
    Every automatic pick is recorded in ``plan.reference['style_matches']`` with its honest match quality.
    """
    from .style_match import classify_family, pick_font, pick_resource, scan_fonts, style_catalog
    selections = selections or {}
    local = {e['key']: e for e in catalog.get('entries', [])}
    pool = style_catalog(catalog)
    by_key = {e['key']: e for e in pool}
    matches, scenes = [], plan.reference.get('scenes', [])
    cache = {}

    def explicit(kind):
        requested = selections.get(kind)
        if requested == '__disabled__':
            return 'disabled'
        return (local.get(requested) or by_key.get(requested)) if requested else None

    def automatic(kind, family, observed_text=''):
        if not family or family in ('none', 'hard_cut'):
            return None
        if (kind, family) in cache:
            return cache[(kind, family)]
        # An exact, identified name from the reference beats a family guess.
        exact = next((e for e in local.values() if e['kind'] == kind and e.get('name') and len(e['name']) > 1
                      and e['name'].lower() in observed_text.lower()), None)
        entry = dict(exact, match='exact_name', observed_family=family) if exact else \
            pick_resource(kind, family, pool, avoid={m['key'] for m in matches if m['kind'] == kind and
                                                    m['observed_family'] != family}, prefer_pro=prefer_pro)
        cache[(kind, family)] = entry
        if entry:
            matches.append({'kind': kind, 'observed_family': family, 'key': entry['key'], 'name': entry['name'],
                            'is_pro': bool(entry.get('is_pro')), 'match': entry['match']})
        else:
            matches.append({'kind': kind, 'observed_family': family, 'key': '', 'name': '', 'is_pro': False,
                            'match': 'none'})
        return entry

    # Caption in-animation: the reference's dominant family (single editing language per video).
    wanted = explicit('animation')
    family = _dominant([x.get('caption_anim') for x in scenes], max(1, len(scenes) // 3))
    for caption in plan.captions:
        if wanted == 'disabled':
            caption.animation_key = ''
        elif wanted:
            caption.animation_key = wanted['key']
        else:
            entry = automatic('animation', family)
            caption.animation_key = entry['key'] if entry else ''

    wanted_fx, wanted_tr = explicit('effect'), explicit('transition')
    for i, shot in enumerate(plan.shots):
        scene = _reference_scene(plan, shot)
        text = str(scene.get('editing', ''))
        if wanted_fx != 'disabled':
            entry = wanted_fx or automatic('effect', scene.get('effect_family'), text)
            if entry:
                shot.resource_keys.append(entry['key'])
        nxt = plan.shots[i + 1] if i + 1 < len(plan.shots) else None
        # Transitions follow the reference's cut points; extra cuts from the 3-second limit stay hard cuts.
        if nxt and nxt.reference_scene != shot.reference_scene and wanted_tr != 'disabled':
            incoming = _reference_scene(plan, nxt)
            entry = wanted_tr or automatic('transition', incoming.get('transition_in'), str(incoming.get('editing', '')))
            if entry:
                shot.transition_key = entry['key']

    # Font: user's explicit font wins; otherwise the installed font closest to the reference's feel.
    if not any(c.font_path for c in plan.captions):
        feel = _dominant([x.get('font_feel') for x in scenes])
        if feel:
            if fonts is None:
                try:
                    from pipeline.capcut_font_catalog import available_user_fonts
                    fonts = scan_fonts(available_user_fonts())
                except Exception:
                    fonts = []
            chosen = pick_font(feel, fonts)
            if chosen:
                for caption in plan.captions:
                    caption.font_path = chosen['path']
                matches.append({'kind': 'font', 'observed_family': feel, 'key': chosen['path'],
                                'name': chosen['name'], 'is_pro': False, 'match': chosen['match']})

    plan.reference['style_matches'] = matches
    label = {'effect': '영상 효과', 'transition': '전환', 'animation': '자막 애니메이션', 'font': '폰트'}
    quality = {'exact_name': '이름 일치', 'family_match': '유사 계열', 'fallback': '대체(계열 내 없음)', 'none': '매칭 실패'}
    for m in matches:
        if m['match'] == 'none':
            plan.issues.append(f"{label[m['kind']]}: 레퍼런스의 '{m['observed_family']}' 계열에 맞는 리소스를 찾지 못했습니다.")
        else:
            plan.issues.append(f"{label[m['kind']]}: 레퍼런스 '{m['observed_family']}' → {m['name']} "
                               f"({'Pro · ' if m['is_pro'] else ''}{quality[m['match']]})")
    if any(m['is_pro'] for m in matches):
        plan.issues.append('Pro 리소스가 포함됐습니다. CapCut Pro 계정으로 열어야 내보내기에 반영됩니다.')
    if any(s.get('editing') for s in scenes):
        plan.issues.append('효과·폰트는 레퍼런스와 같은 계열의 가장 가까운 CapCut 리소스입니다. 동일 리소스라는 보장은 없어 실제 재생 비교가 필요합니다.')
    return plan
