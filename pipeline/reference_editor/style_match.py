"""Reference style -> CapCut resources (effects, transitions, caption animations, fonts).

The reference MP4 carries no resource IDs, so identification is by *family*: the vision model (and pixel
measurements) say what kind of effect is on screen (flash, zoom, typewriter, ...), and this module picks the
closest real CapCut resource of that family. Paid (VIP) resources are preferred when the family has them,
because the reference editors use them. Every pick is labelled honestly: ``family_match`` (same family, a
similar look) or ``fallback`` (nothing in the family; closest general-purpose substitute). Nothing here claims an
exact identification.

Resources come from pycapcut's bundled catalog (names in Chinese/English, ``is_vip`` flag, resource IDs),
plus resources already cached by the user's own drafts (known to be downloadable on this PC).
"""
from functools import lru_cache
from pathlib import Path
import os
import re

# --- family taxonomy -------------------------------------------------------------------------------------------
# Order matters: the first family whose keyword appears in a resource name wins.
TRANSITION_FAMILIES = {
    'glitch': ['故障', 'glitch', '信号', 'signal', 'rgb', 'crt', 'vhs', 'distort', '干扰', 'pixel', '像素', 'jerky'],
    'flash': ['闪', 'flash', 'dazzle', 'shimmer', 'glare', '炫光', 'bling', 'spark', 'shine', 'flare', 'lumin',
              'light leak', 'leaks', '漏光', '白场', 'burn', '눈부심', '섬광'],
    'dip_black': ['黑场', 'dip to black', '闪黑', '渐黑', 'fade to black', '暗场'],
    'zoom': ['缩放', '放大', '缩小', 'zoom', '拉近', '拉远', 'dolly', 'push in', 'pull', '推进', 'shrink', '줌'],
    'spin': ['旋', '转', 'rotate', 'spin', 'flip', '翻转', 'twist', 'cube', 'vortex', 'swirl', '回转'],
    'blur': ['模糊', 'blur', '虚化', 'defocus', '焦', '雾'],
    'shake': ['抖', '晃', 'shake', 'bounce', '震', '弹跳', 'elastic'],
    'fade': ['叠化', '渐', 'fade', 'dissolve', '溶解', '淡', 'crossfade', '페이드'],
    'slide': ['滑', '移', 'slide', 'wipe', '擦', 'push', 'pan', '翻页', 'page', 'reveal', '卷', 'left', 'right',
              '左', '右', '上', '下', 'up', 'down'],
}
EFFECT_FAMILIES = {
    'glitch': ['故障', 'glitch', '信号', 'signal', 'rgb', '干扰', 'x-signal', 'distort'],
    'vhs_film': ['vhs', 'film', '胶片', 'dv', 'ccd', 'camcorder', '录制', 'betamax', 'jvc', '老', 'retro', 'grain',
                 '噪', 'polaroid', '宝丽莱', 'crt', 'dvd', '复古'],
    'shake': ['抖', '晃', 'shake', 'shaky', '震', 'jitter'],
    'zoom_pulse': ['放大', '缩放', 'zoom', 'beat', 'pulse', '心跳', 'heartbeat', '긴장감', 'dolly', 'camera dance',
                   'close up', 'snap'],
    'blur': ['模糊', 'blur', 'focus', '焦', '虚化', 'defocus', 'ghost', '重影'],
    'particles': ['heart', '爱心', 'butterfly', '蝴蝶', 'snow', '雪', 'petal', '花', 'sakura', '樱', '星', 'star',
                  'sparkle', 'bling', 'kira', 'glitter', '粒子', 'bubble', '泡', 'confetti', 'firework', '烟花'],
    'flash_glow': ['闪', 'flash', 'glow', 'halo', '光', 'light', 'shine', 'lens', 'flare', 'neon', '霓虹', 'shimmer',
                   'dazzle', 'lumin', 'blinking'],
    'color_tint': ['色', 'color', 'tint', 'hdr', 'b&w', '黑白', 'cinema', '电影', 'dream', '梦', 'moody', 'warm', 'cold'],
}
TEXT_ANIM_FAMILIES = {
    'typewriter': ['打字机', 'typewriter', '逐字', '随机'],
    'glitch': ['故障', 'glitch'],
    'pop': ['弹', 'pop', 'bounce', 'spring', '放大', 'zoom', '冲屏', 'bumper', '空翻', '甩'],
    'blur': ['模糊', 'blur', '虚'],
    'glow': ['光', '辉', '荧光', '微光', 'glow', 'light', 'golden', '丁达尔', 'dust'],
    'flip_spin': ['翻', '旋', 'flip', 'spin', 'rotate', '螺旋'],
    'wipe': ['开幕', '擦', 'wipe', 'reveal', '露出', '扫'],
    'slide_up': ['向上', '上升', 'rise', '上移', 'up'],
    'slide_side': ['向左', '向右', '左', '右', 'slide', '滑', 'left', 'right'],
    'fade': ['渐显', 'fade', '淡', '溶解', 'dissolve', '渐'],
    'karaoke': ['卡拉', 'karaoke', 'ktv'],
}
FAMILY_TABLES = {'transition': TRANSITION_FAMILIES, 'effect': EFFECT_FAMILIES,
                 'animation': TEXT_ANIM_FAMILIES, 'text_in': TEXT_ANIM_FAMILIES}

# Closest general-purpose family when the observed one has no resource at all.
FALLBACK_FAMILY = {
    'transition': {'flash': 'fade', 'dip_black': 'fade', 'glitch': 'flash', 'zoom': 'blur', 'spin': 'slide',
                   'blur': 'fade', 'shake': 'zoom', 'slide': 'fade', 'fade': 'flash'},
    'effect': {'glitch': 'vhs_film', 'vhs_film': 'color_tint', 'shake': 'zoom_pulse', 'zoom_pulse': 'shake',
               'blur': 'flash_glow', 'particles': 'flash_glow', 'flash_glow': 'particles', 'color_tint': 'vhs_film'},
    'animation': {'typewriter': 'fade', 'glitch': 'pop', 'pop': 'fade', 'blur': 'fade', 'glow': 'fade',
                  'flip_spin': 'pop', 'wipe': 'fade', 'slide_up': 'slide_side', 'slide_side': 'fade',
                  'fade': 'pop', 'karaoke': 'typewriter'},
}
FAMILY_IDS = {'transition': ['hard_cut'] + list(TRANSITION_FAMILIES) + ['other'],
              'effect': ['none'] + list(EFFECT_FAMILIES) + ['other'],
              'animation': ['none'] + list(TEXT_ANIM_FAMILIES) + ['other']}


def classify_family(name, kind):
    """Family of a resource, judged from its (Chinese/English/Korean) name."""
    text = str(name).lower()
    for family, words in FAMILY_TABLES[kind].items():
        if any(w.lower() in text for w in words):
            return family
    return 'other'


# --- resource catalog ------------------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def pycapcut_resources():
    """Every pycapcut-bundled resource with its VIP flag. Empty list when pycapcut is unavailable."""
    try:
        from pycapcut.metadata.text_intro import TextIntro
        from pycapcut.metadata.transition_meta import TransitionType
        from pycapcut.metadata.video_scene_effect import VideoSceneEffectType
    except Exception:  # pragma: no cover - environment without pycapcut
        return []
    entries = []
    for kind, enum in (('animation', TextIntro), ('transition', TransitionType), ('effect', VideoSceneEffectType)):
        for member in enum:
            meta = member.value
            name = str(getattr(meta, 'title', None) or getattr(meta, 'name', '')).strip()
            entries.append({'key': f'pyc:{enum.__name__}:{member.name}', 'kind': kind, 'name': name,
                            'is_pro': bool(meta.is_vip), 'resource_id': str(meta.resource_id),
                            'family': classify_family(name, kind), 'source': 'pycapcut', 'cached': False})
    return entries


def resolve_pyc_key(key):
    """('pyc:TransitionType:White_Flash') -> enum member, validated against the bundled catalog."""
    match = re.fullmatch(r'pyc:(TextIntro|TransitionType|VideoSceneEffectType):(.+)', key or '')
    if not match:
        raise ValueError(f'pycapcut 리소스 키가 아닙니다: {key}')
    from pycapcut.metadata.text_intro import TextIntro
    from pycapcut.metadata.transition_meta import TransitionType
    from pycapcut.metadata.video_scene_effect import VideoSceneEffectType
    enum = {'TextIntro': TextIntro, 'TransitionType': TransitionType,
            'VideoSceneEffectType': VideoSceneEffectType}[match.group(1)]
    try:
        return enum[match.group(2)]
    except KeyError:
        raise ValueError(f'CapCut 카탈로그에 없는 리소스입니다: {key}') from None


def style_catalog(local_catalog=None):
    """pycapcut catalog + resources already cached by the user's drafts (flagged ``cached``)."""
    entries = [dict(e) for e in pycapcut_resources()]
    cached_ids = {}
    for e in (local_catalog or {}).get('entries', []):
        if e.get('kind') in ('animation', 'transition', 'effect') and e.get('cached') and e.get('resource_id'):
            cached_ids[(e['kind'], e['resource_id'])] = e
    for e in entries:
        if (e['kind'], e['resource_id']) in cached_ids:
            e['cached'] = True
    return entries


def _rank(entry):
    # Paid first (the reference editors use Pro resources), then ones already downloaded on this PC.
    return (not entry['is_pro'], not entry['cached'], entry['name'])


def pick_resource(kind, family, catalog, avoid=(), prefer_pro=True, seed=0):
    """Closest resource for an observed family. ``avoid`` lowers repetition; ``seed`` rotates among equals."""
    if not family or family in ('none', 'hard_cut'):
        return None
    pool = [e for e in catalog if e['kind'] == kind]
    for target, quality in ((family, 'family_match'), (FALLBACK_FAMILY.get(kind, {}).get(family), 'fallback')):
        if not target:
            continue
        matches = [e for e in pool if e['family'] == target]
        if not matches:
            continue
        ranked = sorted(matches, key=_rank if prefer_pro else (lambda e: (not e['cached'], e['name'])))
        best_tier = [e for e in ranked if _rank(e)[:2] == _rank(ranked[0])[:2]] if prefer_pro else ranked
        fresh = [e for e in best_tier if e['key'] not in avoid] or best_tier
        return dict(fresh[seed % len(fresh)], match=quality, observed_family=family)
    return None


# --- fonts ----------------------------------------------------------------------------------------------------
# Tags for fonts the user is known to own; other files are tagged from their file names.
KNOWN_FONT_TAGS = {
    '양굵은구조폰트': {'bold', 'display'}, '상상토끼 꽃집막내딸': {'hand', 'round'}, '김씨와일드각체': {'bold', 'display'},
    '메모먼트꾹꾹체': {'hand', 'bold'}, '케리스케듀체': {'display'}, 'HS잔다리체': {'hand'}, '속초바다 돋움체': {'gothic'},
}
NAME_TAGS = [('bold', ['black', 'bold', 'heavy', 'extra', '굵', '블랙', 'kkukkuk', 'gag', 'han sans', 'hansans']),
             ('hand', ['hand', 'pen', '손', 'brush', '붓', 'gaegu', 'kkukkuk', '필기', 'script']),
             ('round', ['round', '둥', 'jua', 'yeol', 'cute', '토끼']),
             ('serif', ['myeongjo', '명조', 'batang', '바탕', 'serif', 'gungsuh', '궁서', 'nanummyeongjo']),
             ('gothic', ['gothic', '고딕', 'dotum', '돋움', 'sans', 'gulim', '굴림', 'pretendard', 'noto'])]
FONT_FEELS = ['bold_gothic', 'regular_gothic', 'round', 'handwriting', 'serif', 'brush_display']
FEEL_TAGS = {'bold_gothic': ({'bold', 'gothic', 'display'}, 'bold'), 'regular_gothic': ({'gothic'}, ''),
             'round': ({'round'}, ''), 'handwriting': ({'hand'}, ''), 'serif': ({'serif'}, ''),
             'brush_display': ({'display', 'hand', 'bold'}, 'bold')}
FONT_SUFFIXES = ('.ttf', '.otf', '.ttc')


def _tags_for(name, filename):
    tags = set(KNOWN_FONT_TAGS.get(name, ()))
    text = f'{name} {filename}'.lower()
    for tag, words in NAME_TAGS:
        if any(w in text for w in words):
            tags.add(tag)
    return tags


def _covers_hangul(path):
    try:
        from fontTools.ttLib import TTFont
        font = TTFont(str(path), fontNumber=0, lazy=True)
        return any(0xAC00 in table.cmap for table in font['cmap'].tables if table.isUnicode())
    except Exception:
        return None   # unknown: keep the font (user-installed fonts are Korean by selection)


def scan_fonts(named_fonts=None, directories=None):
    """User-installed fonts the draft can really use (local file paths, Hangul-capable when it can be checked)."""
    fonts = {}
    for name, path in (named_fonts or {}).items():
        fonts[str(Path(path))] = {'name': name, 'path': str(path)}
    for directory in directories if directories is not None else [
            os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Windows', 'Fonts')]:
        if directory and Path(directory).is_dir():
            for file in sorted(Path(directory).iterdir()):
                if file.suffix.lower() in FONT_SUFFIXES:
                    fonts.setdefault(str(file), {'name': file.stem, 'path': str(file)})
    result = []
    for info in fonts.values():
        hangul = _covers_hangul(info['path']) if Path(info['path']).is_file() else None
        if hangul is False:
            continue
        result.append(dict(info, tags=sorted(_tags_for(info['name'], Path(info['path']).name)), hangul=hangul))
    return result


def pick_font(feel, fonts, avoid=()):
    """Installed font closest to the observed feel. Returns None only when no usable font exists."""
    if not fonts:
        return None
    wanted, weight = FEEL_TAGS.get(feel, (set(), ''))
    def score(font):
        tags = set(font['tags'])
        return (len(tags & wanted) * 2 + (1 if weight == 'bold' and 'bold' in tags else 0)
                - (0.5 if font['name'] in avoid else 0), font['name'])
    best = max(fonts, key=score)
    overlap = set(best['tags']) & wanted
    return dict(best, match='family_match' if overlap else 'fallback', observed_family=feel)
