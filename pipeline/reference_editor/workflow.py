"""End-to-end reference editing orchestration, with durable stages and honest status."""
import json
from pathlib import Path
import uuid

from .analysis import analyze_video, index_sources, direct_beats
from .audio import narration
from .catalog import harvest_catalog, select_resources
from .plan import build_plan, ReferencePlan
from .render import render_plan
from .native import draft_root, CapCutUI, install_project, verify_export
from pipeline.capcut_draft_audit import audit_draft


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def create_edit(reference_path, script, folders, key, output='outputs/reference_editor', voice='ko-KR-SunHiNeural',
                model='', font_path='', source_limit=30, selections=None, align_python='', progress=lambda _: None):
    if not Path(reference_path).is_file():
        raise ValueError('레퍼런스 영상 파일을 확인해주세요.')
    if not folders or any(not Path(folder).is_dir() for folder in folders):
        raise ValueError('보유 소스 폴더를 확인해주세요.')
    if not script.strip():
        raise ValueError('새 대본을 입력해주세요.')
    root = Path(output).resolve(); root.mkdir(parents=True, exist_ok=True)
    run = root / f'run_{uuid.uuid4().hex[:12]}'; run.mkdir()
    status = {'stage': 'reference', 'native_verified': False, 'run': str(run)}
    def stage(name):
        status['stage'] = name; write_json(run / 'status.json', status); progress(name)
    try:
        stage('레퍼런스 장면 분석')
        reference = analyze_video(reference_path, key, root / 'analysis_cache', model, True, progress)
        write_json(run / 'reference.json', reference)
        stage('보유 소스 장면 분석')
        assets, source_issues = index_sources(folders, key, root / 'analysis_cache', model, source_limit, progress)
        write_json(run / 'sources.json', assets)
        if not assets:
            raise ValueError('실제 화면을 분석한 소스가 없습니다. API와 소스 파일을 확인해주세요.')
        stage('나레이션 생성·시간 측정')
        beats, audio_issues = narration(script, root / 'audio_cache', voice, align_python=align_python, progress=progress)
        stage('대본 구조·소스 선택')
        decisions = direct_beats(beats, assets, reference, key, model)
        write_json(run / 'decisions.json', decisions)
        catalog = harvest_catalog(draft_root())
        write_json(run / 'catalog.json', catalog)
        plan = select_resources(build_plan(beats, assets, reference, decisions, font_path), catalog, selections)
        plan.issues.extend(source_issues + audio_issues)
        write_json(run / 'plan.json', plan.to_dict())
        stage('CapCut 프로젝트 생성')
        result = render_plan(plan, run / 'projects', catalog)
        result['audit'] = audit_draft(result['project'])
        result.update(run=str(run), issues=plan.issues, plan=str(run / 'plan.json'))
        status.update(stage='생성 완료 · CapCut 검수 전', project=result['project'])
        write_json(run / 'result.json', result); write_json(run / 'status.json', status)
        return result
    except Exception as exc:
        status.update(failed=True, error_type=type(exc).__name__)
        write_json(run / 'status.json', status)
        raise


def native_check(result, key='', model=''):
    run = Path(result['run'])
    plan = ReferencePlan.from_dict(json.loads(Path(result['plan']).read_text(encoding='utf-8')))
    # Installed-project mapping makes retrying export possible without copying again.
    manifest = run / 'installed.json'
    ui = None
    try:
        if manifest.exists():
            destination = Path(json.loads(manifest.read_text(encoding='utf-8'))['project'])
        else:
            destination = install_project(result['project'])
            write_json(manifest, {'project': str(destination)})
        ui = CapCutUI()
        video = ui.export(destination.name, run / f'native_{uuid.uuid4().hex[:8]}.mp4')
        report = verify_export(video, plan, key, model)
        report['video'] = video
        write_json(run / 'native_review.json', report)
        result['native_review'] = report
        result['native_verified'] = report['native_verified']
        write_json(run / 'result.json', result)
        return report
    except Exception as exc:
        diagnostic = {'native_verified': False, 'error_type': type(exc).__name__,
                      'message': str(exc)[:500]}
        if ui:
            try:
                diagnostic['controls'] = ui.snapshot()
            except Exception:
                diagnostic['controls'] = []
        write_json(run / 'native_review.json', diagnostic)
        result.update(native_review=diagnostic, native_verified=False)
        write_json(run / 'result.json', result)
        return diagnostic
