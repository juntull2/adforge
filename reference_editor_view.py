"""Reference + new script -> native draft, in the existing video page."""
import hashlib
import json
import os
from pathlib import Path

import streamlit as st

from pipeline.reference_editor.catalog import harvest_catalog
from pipeline.reference_editor.native import draft_root
from pipeline.reference_editor.workflow import create_edit, native_check
from pipeline.capcut_font_catalog import available_user_fonts


def render_reference_editor():
    st.subheader('레퍼런스로 새 영상 편집')
    st.caption('잘 만든 영상의 편집 리듬을 새 대본과 보유 소스에 적용합니다. 대본 내용은 바꾸지 않습니다.')
    reference = st.file_uploader('레퍼런스 영상', type=['mp4', 'mov', 'webm'], key='re_reference')
    script = st.text_area('새 대본', height=180, key='re_script')
    folders = st.text_area('보유 소스 폴더 (한 줄에 하나)', key='re_folders')
    key = st.text_input('Vision API 키', type='password',
                        value=os.environ.get('OPENROUTER_API_KEY') or os.environ.get('OPENAI_API_KEY', ''), key='re_api')
    with st.expander('음성·폰트·효과 설정'):
        model = st.text_input('Vision 모델 (비우면 기본 모델)', key='re_model')
        voice = st.selectbox('나레이션', ['ko-KR-SunHiNeural', 'ko-KR-InJoonNeural'], key='re_voice')
        fonts = available_user_fonts()
        font = st.selectbox('자막 폰트', ['기본'] + list(fonts), key='re_font')
        limit = st.number_input('최대 분석할 소스 파일 수', min_value=1, max_value=500, value=30, key='re_limit')
        align_python = st.text_input('WhisperX 별도 환경 Python 경로 (선택)', key='re_align')
        refresh = st.button('CapCut 효과 목록 읽기', key='re_catalog_refresh')
        if refresh or 're_catalog' not in st.session_state:
            st.session_state['re_catalog'] = harvest_catalog(draft_root())
        catalog = st.session_state['re_catalog']
        st.caption('내 프로젝트에서 읽은 효과입니다. 캐시가 있어도 실제 적용 검수 전에는 미검증으로 표시합니다.')
        selections = {}
        for kind, title in [('animation', '자막 입장 애니메이션'), ('transition', '장면 전환'), ('effect', '영상 효과')]:
            entries = [e for e in catalog['entries'] if e['kind'] == kind and
                       (kind != 'animation' or e['subtype'] == 'in')]
            options = {e['key']: e for e in entries}
            selected = st.selectbox(title, ['자동 선택', '사용 안 함'] + list(options), key=f're_{kind}',
                                    format_func=lambda k: k if k not in options else
                                    f"{options[k]['name']} · {'Pro · ' if options[k]['is_pro'] else ''}미검증")
            if selected != '자동 선택':
                selections[kind] = selected if selected != '사용 안 함' else '__disabled__'
    st.caption('소스가 부족하면 보유 장면으로 대체하고 검토 항목에 표시합니다. 장면 분석 시 영상 프레임과 대본을 선택한 API에 보냅니다.')
    if st.button('레퍼런스 기반 프로젝트 만들기', type='primary', key='re_create',
                 disabled=not(reference and script.strip() and folders.strip() and key)):
        root = Path('outputs/reference_editor/uploads'); root.mkdir(parents=True, exist_ok=True)
        payload = reference.getvalue()
        path = root / (hashlib.sha256(payload).hexdigest() + Path(reference.name).suffix.lower())
        path.write_bytes(payload)
        status = st.empty()
        with st.spinner('장면 분석과 편집 설계를 진행합니다…'):
            try:
                result = create_edit(str(path), script, [f.strip().strip('"') for f in folders.splitlines() if f.strip()],
                                     key, model=model, voice=voice, font_path=fonts.get(font, ''), source_limit=int(limit),
                                     selections=selections, align_python=align_python, progress=status.info)
                st.session_state['re_result'] = result
            except Exception as exc:
                st.error(str(exc))
    result = st.session_state.get('re_result')
    if result:
        st.success('편집 가능한 프로젝트를 생성했습니다. 실제 CapCut 검수는 아래에서 진행합니다.')
        st.code(result['project'])
        if result['issues']:
            with st.expander(f"검토할 항목 {len(result['issues'])}개", expanded=True):
                for issue in result['issues']:
                    st.write(issue)
        st.download_button('편집 계획 내려받기', Path(result['plan']).read_bytes(), 'reference_edit_plan.json',
                           mime='application/json', key='re_plan_download')
        st.caption('CapCut을 정상 종료한 상태에서 실행하세요. 새 프로젝트를 등록하고 CapCut에서 열어 시험 내보내기를 진행합니다.')
        if st.button('CapCut에서 열고 실제 결과 검수', key='re_native'):
            with st.spinner('CapCut 프로젝트 등록·내보내기·화면 검수…'):
                result['native_review'] = native_check(result, key, model)
                st.session_state['re_result'] = result
        review = result.get('native_review')
        with st.expander('직접 내보낸 CapCut 영상 검수'):
            exported = st.file_uploader('CapCut에서 내보낸 MP4', type=['mp4'], key='re_export_upload')
            if exported and st.button('내보낸 영상 검사', key='re_export_verify'):
                from pipeline.reference_editor.native import verify_export
                from pipeline.reference_editor.plan import ReferencePlan
                from pipeline.reference_editor.workflow import write_json
                import json
                target = Path(result['run']) / ('manual_' + hashlib.sha256(exported.getvalue()).hexdigest()[:12] + '.mp4')
                target.write_bytes(exported.getvalue())
                try:
                    plan = ReferencePlan.from_dict(json.loads(Path(result['plan']).read_text(encoding='utf-8'))).validate()
                    review = verify_export(target, plan, key, model)
                    review.update(video=str(target), export_method='manual_capcut_export')
                    result.update(native_review=review, native_verified=review['native_verified'])
                    write_json(Path(result['run']) / 'native_review.json', review)
                    write_json(Path(result['run']) / 'result.json', result)
                except Exception as exc:
                    st.error(str(exc))
        if review:
            if review.get('native_verified'):
                st.success('실제 내보내기와 화면 검수를 통과했습니다.')
            else:
                st.warning('실제 검수가 완료되지 않았거나 확인할 항목이 있습니다.')
            if review.get('video'):
                st.video(review['video'])
            st.json({k: v for k, v in review.items() if k not in ('controls', 'metadata')})
