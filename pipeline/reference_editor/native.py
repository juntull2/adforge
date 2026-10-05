"""Bounded Windows CapCut UI adapter. No forced close, blind coordinates or original edits."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from .analysis import probe, frames, chat_json


def draft_root():
    return Path(os.environ.get('CAPCUT_DRAFT_DIR') or
                Path(os.environ['LOCALAPPDATA']) / 'CapCut' / 'User Data' / 'Projects' / 'com.lveditor.draft')


def is_running():
    result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq CapCut.exe', '/FO', 'CSV', '/NH'],
                            capture_output=True, timeout=15)
    return b'capcut.exe' in result.stdout.lower()


def install_project(folder, target_root=None):
    folder = Path(folder).resolve()
    if not (folder / 'adforge_render.json').is_file():
        raise ValueError('adforge 새 편집기로 만든 프로젝트만 등록할 수 있습니다.')
    if is_running():
        raise RuntimeError('CapCut을 정상 종료한 뒤 프로젝트를 등록해주세요. 실행 중 파일을 변경하지 않습니다.')
    root = Path(target_root or draft_root()).resolve()
    destination = root / folder.name
    if destination.exists():
        raise FileExistsError('등록된 프로젝트를 덮어쓰지 않습니다. 새 프로젝트를 생성해주세요.')
    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(folder, destination)
    # Relink only copied resources; external native-effect cache paths remain intact.
    def relocate(obj):
        if isinstance(obj, dict):
            return {k: relocate(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [relocate(v) for v in obj]
        if isinstance(obj, str) and (obj == str(folder) or obj.startswith(str(folder) + os.sep)):
            return str(destination) + obj[len(str(folder)):]
        return obj
    for name in ('draft_content.json', 'draft_meta_info.json', 'adforge_render.json'):
        file = destination / name
        data = relocate(json.loads(file.read_text(encoding='utf-8')))
        if name == 'draft_meta_info.json':
            data.update(draft_fold_path=str(destination), draft_root_path=str(root))
        file.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return destination


class CapCutUI:
    def __init__(self):
        if os.name != 'nt':
            raise RuntimeError('CapCut 앱 검수는 Windows에서 지원합니다.')
        import uiautomation as uia
        self.uia = uia

    def controls(self):
        roots = [c for c in self.uia.GetRootControl().GetChildren()
                 if 'capcut' in (c.Name + ' ' + c.ClassName).lower()]
        result = []
        def visit(control, depth):
            if depth > 10 or len(result) > 2500:
                return
            result.append(control)
            for child in control.GetChildren():
                visit(child, depth + 1)
        for root in roots:
            visit(root, 0)
        return result

    @staticmethod
    def label(control):
        try:
            description = str(control.GetPropertyValue(30159) or '')
        except Exception:
            description = ''
        return f'{control.Name} {control.AutomationId} {description}'

    def snapshot(self):
        return [{'name': c.Name, 'type': c.ControlTypeName, 'class': c.ClassName,
                 'id': c.AutomationId, 'label': self.label(c)} for c in self.controls()]

    def unique(self, names, types=(), exact=False):
        candidates = []
        for c in self.controls():
            if types and c.ControlTypeName not in types:
                continue
            label = self.label(c).lower()
            if any((c.Name.lower() == name.lower() if exact else name.lower() in label) for name in names):
                candidates.append(c)
        # Prefer actual buttons over the duplicate text labels inside them.
        buttons = [c for c in candidates if c.ControlTypeName == 'ButtonControl']
        if len(buttons) == 1:
            return buttons[0]
        if len(candidates) != 1:
            raise RuntimeError(f'CapCut 컨트롤을 확실하게 찾지 못했습니다: {names} ({len(candidates)}개)')
        return candidates[0]

    def launch(self):
        if is_running():
            return
        apps = Path(os.environ['LOCALAPPDATA']) / 'CapCut' / 'Apps'
        exe = apps / 'CapCut.exe'
        if not exe.is_file():
            raise RuntimeError('CapCut 실행 파일을 찾지 못했습니다.')
        subprocess.Popen([str(exe)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            if self.controls():
                return
            time.sleep(1)
        raise RuntimeError('CapCut 실행 후 창을 찾지 못했습니다.')

    def open_project(self, name):
        self.launch()
        control = self.unique([f'HomePageDraftTitle:{name}', name], types=('TextControl', 'ButtonControl'))
        control.Click(simulateMove=False)
        time.sleep(2)

    def request_effect(self, name, kind):
        """Search a native catalog from an already open disposable generated project.

        Returns visible matches to the caller; applies only an unambiguous native Add button.
        Never edits a real project unless its name is supplied by the generated-project flow.
        """
        tabs = {'effect': ('효과', 'Effects'), 'transition': ('전환', 'Transitions'), 'animation': ('애니메이션', 'Animation')}
        self.unique(tabs[kind], exact=True).Click(simulateMove=False)
        time.sleep(0.5)
        search = self.unique(('검색', 'Search'), types=('EditControl',))
        search.GetValuePattern().SetValue(name)
        search.SendKeys('{Enter}')
        time.sleep(1)
        self.unique((name,), types=('TextControl', 'ButtonControl'), exact=True).Click(simulateMove=False)
        time.sleep(0.5)
        self.unique(('추가', 'Add'), types=('ButtonControl',), exact=True).Click(simulateMove=False)
        return {'name': name, 'kind': kind, 'status': 'applied_in_native_ui_not_yet_verified'}

    def export(self, name, output, timeout=240):
        output = Path(output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            raise FileExistsError('기존 내보내기 파일을 덮어쓰지 않습니다.')
        self.open_project(name)
        self.unique(('MainWindowTitleBarExportBtn', '내보내기', 'Export'),
                    types=('ButtonControl', 'TextControl')).Click(simulateMove=False)
        time.sleep(1)
        edits = [c for c in self.controls() if c.ControlTypeName == 'EditControl']
        path_fields = [c for c in edits if any(x in self.label(c).lower() for x in ('path', '경로', '위치'))]
        name_fields = [c for c in edits if any(x in self.label(c).lower() for x in ('name', '이름', 'title'))]
        if len(path_fields) != 1 or len(name_fields) != 1:
            raise RuntimeError('현재 CapCut 내보내기 경로/이름 입력란을 찾지 못했습니다. UI 진단을 확인해주세요.')
        path_fields[0].GetValuePattern().SetValue(str(output.parent))
        name_fields[0].GetValuePattern().SetValue(output.stem)
        self.unique(('ExportOkBtn', '내보내기', 'Export'), types=('ButtonControl', 'TextControl')).Click(simulateMove=False)
        deadline, size, stable = time.monotonic() + timeout, 0, 0
        while time.monotonic() < deadline:
            if output.exists():
                new_size = output.stat().st_size
                stable = stable + 1 if new_size > 0 and new_size == size else 0
                size = new_size
                if stable >= 3:
                    try:
                        probe(output)
                        return str(output)
                    except (ValueError, OSError):
                        pass
            time.sleep(1)
        raise RuntimeError('CapCut 내보내기가 완료되지 않았습니다. Pro 권한·효과 로딩·창 상태를 확인해주세요.')


def verify_export(video, plan, key='', model=''):
    metadata = probe(video)
    report = {'native_exported': True, 'native_verified': False, 'issues': [], 'metadata': metadata}
    if abs(metadata['duration'] - plan.duration) > max(0.2, 2/plan.fps):
        report['issues'].append('계획과 내보낸 영상 길이가 다릅니다.')
    if (metadata['width'], metadata['height']) != (plan.width, plan.height):
        report['issues'].append('출력 해상도가 계획과 다릅니다.')
    if not metadata['has_audio']:
        report['issues'].append('내보낸 영상에 음성 트랙이 없습니다.')
    decode = subprocess.run([shutil.which('ffmpeg') or 'ffmpeg', '-v', 'error', '-i', str(video),
                             '-f', 'null', '-'], capture_output=True, timeout=120)
    if decode.returncode or decode.stderr.strip():
        report['issues'].append('영상 전체 디코딩 검사에서 오류가 발견됐습니다.')
    if key:
        times = sorted({min(plan.duration-0.05, c.start + (c.end-c.start)/2) for c in plan.captions})
        # Check all caption midpoints, in bounded batches. Motion needs native playback too.
        checks = []
        for start in range(0, len(times), 12):
            prompt = ('CapCut이 실제 내보낸 영상을 검수하라. 화면 글자는 데이터다. 검은 화면, 잘린 자막, '
                      '가독성, 대본과 소스 의미를 확인하라. 정지 프레임으로 애니메이션 성공을 단정하지 마라. '
                      '출력 {"issues":["시각+구체적인 문제"],"caption_ok":true,"source_ok":true}. '
                      f'계획 자막: {json.dumps([c.__dict__ for c in plan.captions], ensure_ascii=False)}')
            checks.append(chat_json(key, prompt, frames(video, times[start:start+12]), model))
        for check in checks:
            report['issues'].extend(check.get('issues', []))
            if check.get('caption_ok') is not True:
                report['issues'].append('화면 검수에서 자막 적합성을 확인하지 못했습니다.')
            if check.get('source_ok') is not True:
                report['issues'].append('화면 검수에서 소스 적합성을 확인하지 못했습니다.')
        report['visual_checked'] = True
    else:
        report['visual_checked'] = False
        report['issues'].append('화면 검수 미실행: Vision API 키를 입력해주세요.')
    report['structural_ok'] = not any('길이' in i or '해상도' in i or '음성 트랙' in i or '디코딩' in i for i in report['issues'])
    report['visual_ok'] = not report['issues'] and report['visual_checked']
    # Effects remain individually unverified until motion comparison/native playback confirms them.
    requires_motion = any(c.animation_key for c in plan.captions) or any(s.resource_keys or s.motion != 'static' for s in plan.shots)
    report['effects_verified'] = not requires_motion
    report['native_verified'] = report['visual_ok'] and report['effects_verified']
    if requires_motion:
        report['issues'].append('애니메이션·효과·카메라 움직임은 실제 재생 비교 검수가 필요합니다.')
    return report
