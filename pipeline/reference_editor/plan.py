"""Validated timeline contract. AI supplies choices, never CapCut JSON or new copy."""
from dataclasses import asdict, dataclass, field
import math
import re
import statistics

MAX_SHOT_SECONDS = 3.0   # no single scene may run longer than this


@dataclass
class AudioBeat:
    text: str
    path: str
    duration: float
    role: str = 'body'
    words: list = field(default_factory=list)


@dataclass
class Shot:
    start: float
    end: float
    asset_path: str
    source_start: float
    source_end: float
    beat: int
    role: str = 'body'
    reference_scene: int = 0
    reason: str = ''
    resource_keys: list = field(default_factory=list)
    motion: str = 'static'
    transition_key: str = ''


@dataclass
class Caption:
    text: str
    start: float
    end: float
    beat: int
    size: float = 8.0
    y: float = -0.45
    outline: bool = False
    font_path: str = ''
    animation_key: str = ''
    color: list = field(default_factory=lambda: [1.0, 1.0, 1.0])
    emphasis: list = field(default_factory=list)
    bold: bool = False


@dataclass
class ReferencePlan:
    audio: list
    shots: list
    captions: list
    duration: float
    width: int = 1080
    height: int = 1920
    fps: int = 30
    issues: list = field(default_factory=list)
    reference: dict = field(default_factory=dict)
    schema_version: int = 1

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        d = dict(data)
        d['audio'] = [AudioBeat(**b) for b in d['audio']]
        d['shots'] = [Shot(**s) for s in d['shots']]
        d['captions'] = [Caption(**c) for c in d['captions']]
        return cls(**d)

    def validate(self, require_sources=False):
        if not self.audio or not math.isfinite(self.duration) or self.duration <= 0:
            raise ValueError('유효한 실제 음성 시간이 필요합니다.')
        if abs(sum(b.duration for b in self.audio) - self.duration) > 0.001:
            raise ValueError('음성과 타임라인 길이가 다릅니다.')
        cursor = 0.0
        for s in self.shots:
            values = (s.start, s.end, s.source_start, s.source_end)
            if not all(math.isfinite(v) for v in values) or abs(s.start - cursor) > 0.001 or s.end <= s.start:
                raise ValueError('영상 타임라인에 빈 구간 또는 겹침이 있습니다.')
            if s.source_start < 0 or s.source_end <= s.source_start:
                raise ValueError('소스 구간이 유효하지 않습니다.')
            if abs((s.source_end-s.source_start)-(s.end-s.start)) > 0.001:
                raise ValueError('소스와 타임라인 구간 길이가 다릅니다.')
            if require_sources and not s.asset_path:
                raise ValueError('맞는 소스가 없는 컷을 먼저 확인해주세요.')
            cursor = s.end
        if abs(cursor - self.duration) > 0.001:
            raise ValueError('영상 타임라인 길이가 음성과 다릅니다.')
        for i, b in enumerate(self.audio):
            if not math.isfinite(b.duration) or b.duration <= 0:
                raise ValueError('음성 길이가 유효하지 않습니다.')
            cs = [c for c in self.captions if c.beat == i]
            normalize = lambda text: re.sub(r'\s+', '', text)
            if normalize(''.join(c.text for c in cs)) != normalize(b.text):
                raise ValueError('자막이 입력 대본과 다릅니다.')
        cursor = 0
        for c in self.captions:
            if not all(math.isfinite(v) for v in (c.start, c.end, c.size, c.y)) or not 0 <= c.beat < len(self.audio):
                raise ValueError('자막 시간이 유효하지 않습니다.')
            if c.start < cursor - 0.001 or c.end <= c.start or c.end > self.duration + 0.001:
                raise ValueError('자막 시간이 유효하지 않습니다.')
            cursor = c.end
        return self


def _caption_units(text, limit=18):
    """Wrap without losing punctuation, spaces or words."""
    units, current = [], ''
    for token in re.findall(r'\S+\s*', text):
        if current and len(current + token) > limit:
            units.append(current.strip()); current = ''
        current += token
    if current.strip():
        units.append(current.strip())
    return units or [text]


def _merge_fragments(shots, max_length=MAX_SHOT_SECONDS):
    """Join consecutive pieces of one continuous source range; split points inside a sentence are not cuts."""
    merged = []
    for shot in shots:
        last = merged[-1] if merged else None
        if (last and last.asset_path == shot.asset_path and last.beat == shot.beat
                and abs(last.source_end - shot.source_start) < 0.001 and shot.end - last.start <= max_length):
            last.end, last.source_end = shot.end, shot.source_end
        else:
            merged.append(shot)
    return merged


def _alternative(catalog, current, usage):
    """Another source for the same beat once a clip has run for the maximum shot length."""
    pool = [a for a in catalog.values() if current and a['id'] != current['id']]
    if not pool:
        return current
    same = [a for a in pool if a.get('category') == current.get('category')]
    return min(same or pool, key=lambda a: (usage.get(a['id'], 0.0), a['id']))


def build_plan(beats, assets, reference, decisions=None, font_path=''):
    duration = sum(b.duration for b in beats)
    ref_duration = max(float(reference.get('duration', 0)), 0.001)
    scenes = reference.get('scenes') or [{'start': 0, 'end': ref_duration}]
    catalog = {a['id']: a for a in assets if a.get('end', 0) > a.get('start', 0)}
    choices = {int(d['beat']): d for d in (decisions or []) if isinstance(d, dict)
               and isinstance(d.get('beat'), int) and 0 <= d['beat'] < len(beats)}
    shots, captions, issues, usage = [], [], [], {}
    timeline = 0.0
    roles = {'hook', 'body', 'problem', 'result', 'cta'}
    for i, beat in enumerate(beats):
        decision = choices.get(i, {})
        role = decision.get('role', beat.role)
        role = role if role in roles else beat.role
        beat.role = role
        source_id = decision.get('asset_id')
        if source_id and source_id not in catalog:
            issues.append(f'문장 {i + 1}: AI가 선택한 없는 소스 ID를 제외했습니다.')
        preferred = catalog.get(source_id)
        if not preferred and catalog:
            text = beat.text.lower()
            preferred = max(catalog.values(), key=lambda a: (
                sum(t in str(a.get('visual', '')).lower() for t in re.findall(r'[가-힣a-z]{2,}', text)),
                -usage.get(a['id'], 0)))
            if not decision.get('asset_id'):
                issues.append(f'문장 {i + 1}: 보유 소스로 대체했습니다. 장면 적합성을 확인해주세요.')
        if not preferred:
            issues.append(f'문장 {i + 1}: 필요한 영상 소스가 없습니다.')
        beat_end = timeline + beat.duration
        caption_cursor = timeline
        units = _caption_units(beat.text)
        weights = [max(1, len(re.sub(r'\s', '', u))) for u in units]
        for n, unit in enumerate(units):
            end = beat_end if n == len(units) - 1 else caption_cursor + beat.duration * weights[n] / sum(weights)
            if beat.words and n < len(units) - 1:
                # Match only a contiguous transcript prefix, never invent word offsets.
                compact = lambda t: re.sub(r'[\s.,!?。！？]', '', t)
                prefix = compact(''.join(units[:n+1]))
                spoken = ''
                for word in beat.words:
                    spoken += compact(word['text'])
                    if spoken == prefix:
                        end = min(beat_end, timeline + word['end'])
                        break
                    if not prefix.startswith(spoken):
                        break
            end = max(caption_cursor + 0.001, end)
            captions.append(Caption(unit, caption_cursor, end, i, font_path=font_path,
                                    emphasis=[w for w in decision.get('emphasis', []) if isinstance(w, str) and w in unit]))
            caption_cursor = end
        # Split a long sentence into equal runs (never a 3s run plus a flickering leftover).
        runs = max(1, math.ceil(beat.duration / MAX_SHOT_SECONDS - 1e-9))
        run_cap = beat.duration / runs
        current, run_start = preferred, timeline
        while timeline < beat_end - 1e-8:
            normalized = timeline / max(duration, 0.001) * ref_duration
            idx = next((n for n, s in enumerate(scenes) if s['start'] <= normalized < s['end']), len(scenes) - 1)
            scene = scenes[idx]
            next_boundary = scene['end'] / ref_duration * duration
            room = run_cap - (timeline - run_start)
            if room <= 1e-6:
                current, run_start, room = _alternative(catalog, current, usage), timeline, run_cap
            available = current['end'] - current['start'] if current else beat.duration
            length = min(beat_end - timeline, max(0.1, next_boundary - timeline), available, room)
            used = usage.get(current['id'], 0.0) if current else 0.0
            offset = used % available if current else 0
            if available - offset < min(length, 0.15):
                offset = 0
            length = min(length, available - offset)
            start = current['start'] + offset if current else 0
            shots.append(Shot(timeline, timeline + length, current['path'] if current else '',
                              start, start + length, i, role, idx,
                              str(decision.get('reason') or '레퍼런스 컷 리듬에 맞춘 보유 소스'),
                              motion=scene.get('motion', 'static') if scene.get('motion') in ('static', 'zoom_in', 'zoom_out') else 'static'))
            if current:
                usage[current['id']] = used + length
            timeline += length
    shots = _merge_fragments(shots)
    heights = [x['caption_height'] for x in scenes if isinstance(x.get('caption_height'), (int, float))
               and math.isfinite(x['caption_height']) and x['caption_height'] > 0]
    # One caption size for the whole video: per-scene blob heights vary with line count, the reference's font size doesn't.
    uniform_size = round(max(5.0, min(16.0, statistics.median(heights) * 130)), 1) if heights else None
    ys = [x['caption_y'] for x in scenes if isinstance(x.get('caption_y'), (int, float)) and math.isfinite(x['caption_y'])]
    # Captions sit at one fixed spot in a reference; a stray scene reading (other on-screen text) must not move them.
    uniform_y = max(-0.7, min(0.7, statistics.median(ys))) if ys else None
    colors = [x['caption_color'] for x in scenes if isinstance(x.get('caption_color'), str)]
    color = None
    if colors:
        top = max(set(colors), key=colors.count)
        color = [int(top[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    bold = sum(1 for x in scenes if x.get('caption_bold') is True) * 2 > max(1, len(scenes))
    for caption in captions:
        normalized = (caption.start + caption.end) / 2 / duration * ref_duration
        scene = next((s for s in scenes if s['start'] <= normalized < s['end']), scenes[-1])
        if uniform_y is not None:
            caption.y = uniform_y
        if uniform_size:
            caption.size = uniform_size
        caption.outline = bool(scene.get('caption_outline'))
        caption.bold = bold
        if color:
            caption.color = color
    return ReferencePlan(beats, shots, captions, duration, issues=list(dict.fromkeys(issues)), reference=reference).validate()
