"""Run with an isolated WhisperX environment: python reference_align.py input.mp3 words.json."""
import argparse
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('audio'); p.add_argument('output'); p.add_argument('--device', default='cpu')
    args = p.parse_args()
    import whisperx
    audio = whisperx.load_audio(args.audio)
    model = whisperx.load_model('small', args.device, compute_type='int8', language='ko')
    result = model.transcribe(audio, batch_size=4)
    aligner, metadata = whisperx.load_align_model(language_code='ko', device=args.device)
    result = whisperx.align(result['segments'], aligner, metadata, audio, args.device)
    words = [{'text': w['word'], 'start': w['start'], 'end': w['end']}
             for w in result['word_segments'] if 'start' in w and 'end' in w]
    Path(args.output).write_text(json.dumps({'words': words}, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
