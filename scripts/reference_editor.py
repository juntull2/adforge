"""Reference editor CLI. Subcommands: inspect, create, native, acquire."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
from pipeline.reference_editor.workflow import create_edit, native_check, write_json
from pipeline.reference_editor.catalog import harvest_catalog
from pipeline.reference_editor.native import CapCutUI, draft_root


def main():
    load_dotenv()
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    inspect = sub.add_parser('inspect'); inspect.add_argument('--ui', action='store_true'); inspect.add_argument('--launch', action='store_true')
    create = sub.add_parser('create')
    create.add_argument('--reference', required=True); create.add_argument('--script', required=True, help='UTF-8 text file')
    create.add_argument('--sources', nargs='+', required=True); create.add_argument('--model', default='')
    create.add_argument('--limit', type=int, default=30); create.add_argument('--voice', default='ko-KR-SunHiNeural')
    native = sub.add_parser('native'); native.add_argument('result'); native.add_argument('--model', default='')
    acquire = sub.add_parser('acquire'); acquire.add_argument('result'); acquire.add_argument('--name', required=True)
    acquire.add_argument('--kind', choices=['effect', 'transition', 'animation'], required=True)
    args = p.parse_args()
    key = os.environ.get('OPENROUTER_API_KEY') or os.environ.get('OPENAI_API_KEY', '')
    if args.action == 'inspect':
        catalog = harvest_catalog(draft_root())
        print(json.dumps({'resources': len(catalog['entries']), 'errors': catalog['errors'],
                          'kinds': {kind: sum(e['kind'] == kind for e in catalog['entries']) for kind in
                                    ('animation', 'effect', 'transition', 'text_style')}}, ensure_ascii=True))
        if args.ui:
            ui = CapCutUI()
            if args.launch:
                ui.launch()
            print(json.dumps(ui.snapshot(), ensure_ascii=True))
    elif args.action == 'create':
        result = create_edit(args.reference, Path(args.script).read_text(encoding='utf-8'), args.sources,
                             key, model=args.model, source_limit=args.limit, voice=args.voice, progress=print)
        print(json.dumps(result, ensure_ascii=True))
    elif args.action == 'native':
        result = json.loads(Path(args.result).read_text(encoding='utf-8'))
        print(json.dumps(native_check(result, key, args.model), ensure_ascii=True))
    else:
        result = json.loads(Path(args.result).read_text(encoding='utf-8'))
        manifest = Path(result['run']) / 'installed.json'
        if not manifest.is_file():
            raise ValueError('먼저 새 프로젝트를 등록해주세요.')
        folder = Path(json.loads(manifest.read_text(encoding='utf-8'))['project'])
        if not (folder / 'adforge_render.json').is_file():
            raise ValueError('시험용 생성 프로젝트만 사용할 수 있습니다.')
        ui = CapCutUI(); ui.open_project(folder.name)
        print(json.dumps(ui.request_effect(args.name, args.kind), ensure_ascii=True))


if __name__ == '__main__':
    main()
