"""Reference style replication: family matching, paid-resource preference, measurements, 3s shot limit."""
import json
from pathlib import Path
import wave

import cv2
import numpy as np
import pytest

from pipeline.reference_editor.analysis import measure_transitions, pick_source_files
from pipeline.reference_editor.catalog import select_resources
from pipeline.reference_editor.plan import AudioBeat, build_plan
from pipeline.reference_editor.render import render_plan
from pipeline.reference_editor.style_match import (classify_family, pick_font, pick_resource, style_catalog)


def _texture(seed, hue):
    rng = np.random.default_rng(seed)
    img = cv2.resize((rng.random((32, 18)) * 255).astype(np.uint8), (180, 320), interpolation=cv2.INTER_NEAREST)
    return (img[:, :, None] * np.array(hue)[None, None, :]).astype(np.uint8)


def _video(path, kind, fps=30, seconds=3):
    a, b = _texture(1, (0.9, 0.6, 0.4)), _texture(2, (0.4, 0.7, 0.9))
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), fps, (180, 320))
    cut = fps * seconds // 2
    for i in range(fps * seconds):
        frame, d = (a if i < cut else b).copy(), abs(i - cut)
        if d < 4:
            k = 1 - d / 4
            if kind == 'flash':
                frame = cv2.addWeighted(frame, 1 - k, np.full_like(frame, 255), k, 0)
            elif kind == 'dip':
                frame = cv2.addWeighted(frame, 1 - k, np.zeros_like(frame), k, 0)
            elif kind == 'blur':
                size = int((4 - d) * 4) * 2 + 1
                frame = cv2.GaussianBlur(frame, (size, size), 0)
        writer.write(frame)
    writer.release()
    return path


@pytest.mark.parametrize('kind,expected', [('hard', 'hard_cut'), ('flash', 'flash'), ('dip', 'dip_black'), ('blur', 'blur')])
def test_transition_family_is_measured_from_pixels(tmp_path, kind, expected):
    video = _video(tmp_path / f'{kind}.mp4', kind)
    result = measure_transitions(video, [{'start': 0, 'end': 1.5}, {'start': 1.5, 'end': 3}])
    assert result[0] is None and result[1]['family'] == expected


def test_families_are_classified_from_chinese_and_english_names():
    assert classify_family('打字机', 'animation') == 'typewriter'
    assert classify_family('White Flash', 'transition') == 'flash'
    assert classify_family('Signal Glitch 2', 'transition') == 'glitch'
    assert classify_family('CCD', 'effect') == 'vhs_film'


def test_paid_resources_are_preferred_and_fallback_is_labelled():
    catalog = [
        dict(key='free', kind='transition', name='a', is_pro=False, cached=True, family='flash', resource_id='1'),
        dict(key='paid', kind='transition', name='b', is_pro=True, cached=False, family='flash', resource_id='2'),
        dict(key='fade', kind='transition', name='c', is_pro=False, cached=False, family='fade', resource_id='3')]
    assert pick_resource('transition', 'flash', catalog)['key'] == 'paid'
    assert pick_resource('transition', 'flash', catalog, prefer_pro=False)['key'] == 'free'
    nearest = pick_resource('transition', 'dip_black', catalog)       # no dip_black resource -> nearest family
    assert nearest['key'] == 'fade' and nearest['match'] == 'fallback'
    assert pick_resource('transition', 'hard_cut', catalog) is None and pick_resource('transition', 'none', catalog) is None


def test_font_follows_observed_feel_and_never_returns_a_missing_font():
    fonts = [dict(name='얇은', path='a.ttf', tags=['gothic']), dict(name='굵은', path='b.ttf', tags=['bold', 'display'])]
    assert pick_font('bold_gothic', fonts)['name'] == '굵은'
    assert pick_font('serif', fonts)['match'] == 'fallback'
    assert pick_font('serif', []) is None


def test_source_selection_keeps_script_relevant_korean_clips():
    files = [Path(n) for n in sorted([f'Hailuo_{i}.mp4' for i in range(20)] + ['모델_거울_흉터.mp4', '제품_알약.mp4'])]
    chosen = [p.name for p in pick_source_files(files, 6, '거울 볼 때마다 흉터, 알약 복용')]
    assert len(chosen) == 6 and '모델_거울_흉터.mp4' in chosen and '제품_알약.mp4' in chosen


def _reference():
    base = dict(caption_y=0.05, caption_height=0.04, caption_color='#FFE000', caption_bold=True, font_feel='bold_gothic')
    return {'duration': 9, 'scenes': [
        dict(start=0, end=3, transition_in='hard_cut', effect_family='none', caption_anim='typewriter', **base),
        dict(start=3, end=6, transition_in='flash', effect_family='vhs_film', caption_anim='typewriter', **base),
        dict(start=6, end=9, transition_in='glitch', effect_family='none', caption_anim='pop', **base)]}


def _wav(path, seconds):
    with wave.open(str(path), 'wb') as handle:
        handle.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        handle.writeframes(np.zeros(int(16000 * seconds), dtype=np.int16).tobytes())
    return str(path)


def test_reference_style_reaches_the_capcut_draft(tmp_path):
    video = _video(tmp_path / 'src.mp4', 'hard')
    beats = [AudioBeat('첫 번째 문장입니다 길게 이어집니다.', _wav(tmp_path / 'a.wav', 4.5), 4.5),
             AudioBeat('두 번째 문장입니다.', _wav(tmp_path / 'b.wav', 4.5), 4.5)]
    assets = [{'id': i, 'path': str(video), 'start': 0, 'end': 3, 'visual': 'x', 'category': '얼굴'} for i in 'ab']
    plan = build_plan(beats, assets, _reference())
    assert max(s.end - s.start for s in plan.shots) <= 3.0 + 1e-6          # no scene over 3 seconds
    font = tmp_path / 'bold.ttf'; font.write_bytes(b'x')
    fonts = [dict(name='굵은체', path=str(font), tags=['bold', 'display'], hangul=None)]
    select_resources(plan, {'entries': []}, fonts=fonts)
    kinds = {m['kind'] for m in plan.reference['style_matches']}
    assert {'animation', 'transition', 'effect', 'font'} <= kinds
    assert len({c.size for c in plan.captions}) == 1 and plan.captions[0].bold      # one caption size for the video
    assert plan.captions[0].color[0] == 1.0 and plan.captions[0].font_path == str(font)
    result = render_plan(plan, tmp_path / 'out', {'entries': []}, 'styled')
    materials = json.loads((Path(result['project']) / 'draft_content.json').read_text(encoding='utf-8'))['materials']
    assert materials['video_effects'] and materials['transitions'] and materials['material_animations']
    assert any(r.get('pro') for r in result['resources'])
    assert any('Pro' in issue for issue in plan.issues)


def test_explicit_selection_overrides_and_disabled_turns_a_kind_off(tmp_path):
    video = _video(tmp_path / 'src.mp4', 'hard')
    beats = [AudioBeat('문장입니다.', _wav(tmp_path / 'a.wav', 3), 3)]
    plan = build_plan(beats, [{'id': 'a', 'path': str(video), 'start': 0, 'end': 3}], _reference())
    select_resources(plan, {'entries': []}, {'animation': '__disabled__', 'effect': '__disabled__', 'transition': '__disabled__'}, fonts=[])
    assert not any(c.animation_key for c in plan.captions)
    assert not any(s.resource_keys or s.transition_key for s in plan.shots)


def test_caption_measurement_ignores_pinned_headline_and_white_banner(tmp_path):
    from pipeline.reference_editor.analysis import measure_captions
    path = tmp_path / 'overlay.mp4'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), 30, (360, 640))
    def outlined(frame, text, y):
        mask = np.zeros(frame.shape[:2], np.uint8)
        cv2.putText(mask, text, (20, y), cv2.FONT_HERSHEY_DUPLEX, 1.0, 255, 2)
        ring = cv2.dilate(mask, np.ones((7, 7), np.uint8))
        frame[ring > 0] = 0
        frame[mask > 0] = 255
    for i in range(180):
        frame = np.full((640, 360, 3), 110, np.uint8)
        frame[:] = (110 + (i // 60) * 20, 120, 100)
        outlined(frame, 'HEADLINE', 60)                               # pinned in every frame
        cv2.rectangle(frame, (0, 580), (360, 630), (255, 255, 255), -1)  # white price ticker
        cv2.putText(frame, 'PRICE 9,900', (20, 615), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
        outlined(frame, ('WIDE CAPTION', 'SHORT', 'MEDIUM ONE')[i // 60], 430)                      # the real caption, changes per scene
        writer.write(frame)
    writer.release()
    result = measure_captions(path, [{'start': 0, 'end': 2}, {'start': 2, 'end': 4}, {'start': 4, 'end': 6}])
    assert all(r and -0.5 < r['y'] < -0.2 for r in result), result       # y of the caption (~ -0.34), not +0.8 / -0.9
