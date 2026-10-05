import json
from pathlib import Path

import pytest

from pipeline.reference_editor.plan import AudioBeat, ReferencePlan, build_plan
from pipeline.reference_editor.catalog import harvest_catalog, clone_material


def test_plan_keeps_script_and_uses_real_audio_duration():
    beats = [AudioBeat('첫 문장입니다.', 'one.wav', 2.5), AudioBeat('지금 확인하세요.', 'two.wav', 3.0)]
    assets = [{'id': 'a', 'path': 'a.mp4', 'start': 1, 'end': 11, 'visual': '제품을 보여주는 손'}]
    ref = {'duration': 10, 'scenes': [{'start': 0, 'end': 2, 'role': 'hook'}, {'start': 2, 'end': 10, 'role': 'cta'}]}
    plan = build_plan(beats, assets, ref)
    assert plan.duration == 5.5
    assert [b.text for b in plan.audio] == [b.text for b in beats]
    assert plan.shots[0].start == 0 and plan.shots[-1].end == 5.5
    assert all(s.source_end <= 11 for s in plan.shots)
    assert ReferencePlan.from_dict(plan.to_dict()).to_dict() == plan.to_dict()


def test_missing_sources_are_review_items_not_random_paths():
    p = build_plan([AudioBeat('내용입니다.', 'one.wav', 2)], [], {'duration': 2, 'scenes': []})
    assert p.shots[0].asset_path == ''
    assert p.issues
    with pytest.raises(ValueError, match='소스'):
        p.validate(require_sources=True)


def test_short_sources_split_instead_of_overrunning():
    p = build_plan([AudioBeat('긴 문장입니다.', 'one.wav', 6)],
                   [{'id': 'a', 'path': 'a.mp4', 'start': 2, 'end': 3.2, 'visual': '얼굴'}],
                   {'duration': 6, 'scenes': [{'start': 0, 'end': 6}]})
    assert len(p.shots) >= 5
    assert all(s.source_end <= 3.2 + 1e-6 for s in p.shots)
    p.validate()


def test_ai_can_only_select_known_ids_and_cannot_rewrite_script():
    p = build_plan([AudioBeat('원문 유지', 'a.wav', 2)],
                   [{'id': 'known', 'path': 'k.mp4', 'start': 0, 'end': 5, 'visual': '손'}],
                   {'duration': 2, 'scenes': []},
                   decisions=[{'beat': 0, 'asset_id': 'invented', 'text': '다른 대사', 'role': 'hook'}])
    assert p.audio[0].text == '원문 유지'
    assert p.shots[0].asset_path == 'k.mp4'
    assert any('없는 소스' in i for i in p.issues)


def test_catalog_does_not_confuse_same_resource_in_different_categories(tmp_path):
    folder = tmp_path / 'original'; folder.mkdir()
    data = {'materials': {'transitions': [{'id': 't', 'resource_id': '42', 'name': 'Fade'}],
                          'video_effects': [{'id': 'e', 'resource_id': '42', 'name': 'Light'}]}}
    content = folder / 'draft_content.json'
    content.write_text(json.dumps(data), encoding='utf-8')
    before = content.read_bytes()
    entries = harvest_catalog(tmp_path)['entries']
    assert len(entries) == 2
    assert {e['kind'] for e in entries} == {'transition', 'effect'}
    assert all(e['verification'] == 'unverified' for e in entries)
    assert content.read_bytes() == before


def test_clone_remaps_entire_resource_graph_without_altering_source():
    materials = {'material_animations': [{'id': 'anim', 'animations': [{'id': 'inner', 'resource_id': '500'}]}],
                 'video_effects': [{'id': 'fx', 'resource_id': '700', 'extra_material_refs': ['anim']}]}
    before = json.dumps(materials)
    dest = {}
    fx_id = clone_material(materials, 'fx', dest)
    effect = dest['video_effects'][0]
    assert fx_id != 'fx' and effect['resource_id'] == '700'
    assert effect['extra_material_refs'][0] == dest['material_animations'][0]['id']
    assert dest['material_animations'][0]['animations'][0]['resource_id'] == '500'
    assert dest['material_animations'][0]['animations'][0]['id'] == 'inner'
    assert json.dumps(materials) == before


def test_clone_deduplicates_shared_dependency_and_rejects_missing():
    source = {'effects': [{'id': 'a', 'extra_material_refs': ['b', 'b']}, {'id': 'b'}]}
    target = {}
    clone_material(source, 'a', target)
    assert len(target['effects']) == 2
    with pytest.raises(ValueError):
        clone_material(source, 'nope', {})


def test_plan_detects_timeline_gaps():
    p = build_plan([AudioBeat('대사', 'a.wav', 3)],
                   [{'id': 'a', 'path': 'a.mp4', 'start': 0, 'end': 10}], {'duration': 3, 'scenes': []})
    p.shots[0].start = 1
    with pytest.raises(ValueError, match='타임라인'):
        p.validate()


def test_plan_rejects_nan_caption_and_source_length_mismatch():
    p = build_plan([AudioBeat('대사', 'a.wav', 3)],
                   [{'id': 'a', 'path': 'a.mp4', 'start': 0, 'end': 10}], {'duration': 3, 'scenes': []})
    p.captions[0].end = float('nan')
    with pytest.raises(ValueError, match='자막'):
        p.validate()
    p.captions[0].end = 3
    p.shots[0].source_end = 4
    with pytest.raises(ValueError, match='구간 길이'):
        p.validate()


def test_auto_resources_do_not_invent_reference_animations():
    from pipeline.reference_editor.catalog import select_resources
    p = build_plan([AudioBeat('대사', 'a.wav', 3)],
                   [{'id': 'a', 'path': 'a.mp4', 'start': 0, 'end': 10}], {'duration': 3, 'scenes': []})
    entry = dict(key='animation:123:in', name='윤곽선 팝', kind='animation', subtype='in',
                 verification='unverified', cached=True, seen_in=['original'])
    select_resources(p, {'entries': [entry]})
    assert not p.captions[0].animation_key
    select_resources(p, {'entries': [entry]}, {'animation': entry['key']})
    assert p.captions[0].animation_key == entry['key']


@pytest.fixture
def media(tmp_path):
    import cv2
    import numpy as np
    import wave
    video = tmp_path / 'sample.mp4'
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'mp4v'), 30, (180, 320))
    for i in range(90):
        frame = np.full((320, 180, 3), (30, 90, 180) if i < 45 else (180, 80, 30), np.uint8)
        writer.write(frame)
    writer.release()
    audio = tmp_path / 'narration.wav'
    with wave.open(str(audio), 'wb') as handle:
        handle.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        handle.writeframes(np.zeros(48000, dtype=np.int16).tobytes())
    return video, audio


def test_scene_detection_keeps_actual_cut_boundaries(media):
    from pipeline.reference_editor.analysis import scenes
    metadata, cuts = scenes(media[0])
    assert metadata['duration'] == pytest.approx(3, abs=.05)
    assert len(cuts) == 2
    assert cuts[0]['end'] == pytest.approx(1.5, abs=1/30)


def test_render_plan_creates_portable_editable_tracks_and_does_not_overwrite(media, tmp_path):
    from pipeline.reference_editor.render import render_plan
    video, audio = media
    p = build_plan([AudioBeat('첫 장면. 두 번째 장면.', str(audio), 3)],
                   [{'id': 'a', 'path': str(video), 'start': 0, 'end': 3}],
                   {'duration': 3, 'scenes': [{'start': 0, 'end': 1.5, 'motion': 'zoom_in'}, {'start': 1.5, 'end': 3}]})
    result = render_plan(p, tmp_path / 'drafts', {'entries': []}, 'fresh')
    content = json.loads((Path(result['project']) / 'draft_content.json').read_text(encoding='utf-8'))
    assert {t['type'] for t in content['tracks']} == {'video', 'text', 'audio'}
    assert content['duration'] == 3000000
    assert all(Path(m['path']).is_file() for bucket in ('videos', 'audios') for m in content['materials'][bucket])
    assert content['tracks'][0]['segments'][0]['common_keyframes']
    assert not result['native_verified']
    with pytest.raises(FileExistsError):
        render_plan(p, tmp_path / 'drafts', {'entries': []}, 'fresh')


def test_native_install_relinks_copy_and_keeps_original(media, tmp_path, monkeypatch):
    from pipeline.reference_editor.render import render_plan
    from pipeline.reference_editor import native
    video, audio = media
    p = build_plan([AudioBeat('대본', str(audio), 3)],
                   [{'id': 'a', 'path': str(video), 'start': 0, 'end': 3}], {'duration': 3, 'scenes': []})
    r = render_plan(p, tmp_path / 'stage', {'entries': []}, 'fresh')
    original = (Path(r['project']) / 'draft_content.json').read_bytes()
    monkeypatch.setattr(native, 'is_running', lambda: False)
    dest = native.install_project(r['project'], tmp_path / 'native')
    data = json.loads((dest / 'draft_content.json').read_text(encoding='utf-8'))
    assert str(tmp_path / 'stage') not in json.dumps(data)
    assert (Path(r['project']) / 'draft_content.json').read_bytes() == original
    with pytest.raises(FileExistsError):
        native.install_project(r['project'], tmp_path / 'native')
    monkeypatch.setattr(native, 'is_running', lambda: True)
    with pytest.raises(RuntimeError):
        native.install_project(r['project'], tmp_path / 'another')


def test_global_native_effect_is_written_on_effect_track(media, tmp_path):
    from pipeline.reference_editor.render import render_plan
    video, audio = media
    original = tmp_path / 'original'; original.mkdir()
    data = {'materials': {'video_effects': [{'id': 'fx', 'resource_id': '123', 'apply_target_type': 2}]},
            'tracks': [{'type': 'effect', 'segments': [{'id': 'old', 'material_id': 'fx',
                       'extra_material_refs': [], 'target_timerange': {'start': 0, 'duration': 1}, 'clip': None}]}]}
    (original / 'draft_content.json').write_text(json.dumps(data), encoding='utf-8')
    p = build_plan([AudioBeat('대본', str(audio), 3)],
                   [{'id': 'a', 'path': str(video), 'start': 0, 'end': 3}], {'duration': 3, 'scenes': []})
    p.shots[0].resource_keys = ['effect:123:']
    result = render_plan(p, tmp_path / 'stage', {'entries': [dict(key='effect:123:', kind='effect',
                         material_id='fx', source_project=str(original), resource_id='123')]})
    generated = json.loads((Path(result['project']) / 'draft_content.json').read_text(encoding='utf-8'))
    track = next(t for t in generated['tracks'] if t['type'] == 'effect')
    assert track['segments'][0]['target_timerange'] == {'start': 0, 'duration': 3000000}
    assert track['segments'][0]['material_id'] == generated['materials']['video_effects'][0]['id']
    assert track['segments'][0]['id'] != 'old'


def test_narrative_words_drive_caption_boundary():
    beat = AudioBeat('첫 번째 둘째 문장 마지막문장입니다', 'a.wav', 4,
                     words=[{'text': '첫', 'start': .1, 'end': .2}, {'text': '번째', 'start': .2, 'end': .5},
                            {'text': '둘째', 'start': .5, 'end': 1}, {'text': '문장', 'start': 1, 'end': 1.2},
                            {'text': '마지막문장입니다', 'start': 2, 'end': 3.7}])
    p = build_plan([beat], [{'id': 'a', 'path': 'a.mp4', 'start': 0, 'end': 8}], {'duration': 4, 'scenes': []})
    assert p.captions[0].end == 1.2


def test_vision_response_cannot_inject_time_boundaries(media, tmp_path, monkeypatch):
    from pipeline.reference_editor import analysis
    monkeypatch.setattr(analysis, 'chat_json', lambda *a, **k:
                        {'scenes': [{'index': 0, 'start': -100, 'end': 999, 'visual': '손'},
                                    {'index': 1, 'start': -10, 'end': 999, 'visual': '얼굴'}]})
    result = analysis.analyze_video(media[0], 'fake', tmp_path / 'cache')
    assert result['scenes'][0]['start'] == 0
    assert result['scenes'][-1]['end'] == pytest.approx(3, abs=.05)
