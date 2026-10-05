"""Measured narration; Edge supplies word boundaries, WhisperX can align other voices."""
import asyncio
import hashlib
import json
from pathlib import Path
import re
import subprocess

from .analysis import probe
from .plan import AudioBeat


async def _edge(text, path, voice, speed):
    import edge_tts
    words = []
    communicate = edge_tts.Communicate(text, voice, rate=f'{round((speed-1)*100):+d}%', boundary='WordBoundary')
    with Path(path).open('wb') as handle:
        async for chunk in communicate.stream():
            if chunk['type'] == 'audio':
                handle.write(chunk['data'])
            elif chunk['type'] == 'WordBoundary':
                words.append({'text': chunk['text'], 'start': chunk['offset'] / 10_000_000,
                              'end': (chunk['offset'] + chunk['duration']) / 10_000_000})
    return words


def align_whisperx(path, python_executable, output):
    """Optional isolated worker, never install torch into the application environment."""
    worker = Path(__file__).resolve().parents[2] / 'scripts' / 'reference_align.py'
    result = subprocess.run([str(python_executable), str(worker), str(path), str(output)],
                            capture_output=True, timeout=600)
    if result.returncode:
        raise RuntimeError('WhisperX 정렬 실패. 분석 환경과 한국어 정렬 모델을 확인해주세요.')
    return json.loads(Path(output).read_text(encoding='utf-8'))['words']


def narration(script, output, voice='ko-KR-SunHiNeural', speed=1.0, align_python='', progress=lambda _: None):
    units = [s.strip() for s in re.split(r'(?<=[.!?。！？])\s+|\n+', script) if s.strip()]
    if not units:
        raise ValueError('대본이 비어 있습니다.')
    root = Path(output); root.mkdir(parents=True, exist_ok=True)
    beats, issues = [], []
    for i, text in enumerate(units):
        digest = hashlib.sha256(json.dumps([text, voice, speed], ensure_ascii=False).encode()).hexdigest()[:20]
        path = root / f'{digest}.mp3'
        metadata = root / f'{digest}.json'
        progress(f'나레이션 {i+1}/{len(units)}')
        words = []
        if path.exists() and metadata.exists():
            words = json.loads(metadata.read_text(encoding='utf-8')).get('words', [])
        elif not voice.startswith(('fish_', 'el_')):
            words = asyncio.run(_edge(text, path, voice, speed))
            metadata.write_text(json.dumps({'words': words}, ensure_ascii=False), encoding='utf-8')
        else:
            from naver_clip_adforge import generate_voice_for_text
            generate_voice_for_text(text, str(path), voice, speed)
        duration = probe(path)['duration']
        if not words and align_python:
            words = align_whisperx(path, align_python, root / f'{digest}_aligned.json')
            metadata.write_text(json.dumps({'words': words}, ensure_ascii=False), encoding='utf-8')
        words = [w for w in words if 0 <= w['start'] < w['end'] <= duration + 0.2]
        if not words:
            issues.append(f'문장 {i+1}: 단어 정렬 없음. 자막 시간은 실제 문장 길이에 비례 배치했습니다.')
        beats.append(AudioBeat(text, str(path.resolve()), duration, 'hook' if i == 0 else 'body', words))
    return beats, issues
