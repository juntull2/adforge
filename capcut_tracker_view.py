"""Streamlit View Component for CapCut Project Tracking & Style Preset Extraction.
"""

import os
import streamlit as st
from typing import Dict, Any

import capcut_tracker


def render_capcut_tracker_view():
    """탭 4: 캡컷 로컬 프로젝트 실시간 탐색 & 스타일 추출 뷰 렌더링"""
    draft_dir = capcut_tracker.get_capcut_draft_dir()

    col_title, col_btn = st.columns([8, 2])
    with col_title:
        st.subheader("🎨 캡컷 로컬 프로젝트 실시간 추적 & 스타일 추출")
        st.caption(f"📁 캡컷 프로젝트 폴더: `{draft_dir}`")
    with col_btn:
        if st.button("🔄 프로젝트 목록 새로고침", use_container_width=True, key="btn_refresh_capcut"):
            st.rerun()

    if not os.path.exists(draft_dir):
        st.warning(f"⚠️ 캡컷 초안 폴더를 찾을 수 없습니다: `{draft_dir}`\nPC에 캡컷이 설치되어 있고 최소 하나의 프로젝트가 저장되어 있는지 확인해주세요.")
        return

    projects = capcut_tracker.list_local_projects(limit=40)
    if not projects:
        st.info("💡 캡컷 초안 폴더에 생성된 프로젝트가 없습니다. 캡컷 PC 프로그램을 열고 새 프로젝트를 저장해 보세요.")
        return

    col_list, col_detail = st.columns([4.5, 5.5])

    # -----------------------------------------------------------------
    # 좌측: 프로젝트 목록 (카드 형태 또는 선택기)
    # -----------------------------------------------------------------
    with col_list:
        st.markdown(f"##### 📂 PC 내 캡컷 프로젝트 목록 ({len(projects)}개 발견)")
        
        project_options = {p["folder_name"]: p for p in projects}
        
        # 기본 선택값: 세션 스테이트 유지
        current_sel = st.session_state.get("selected_capcut_folder", projects[0]["folder_name"])
        if current_sel not in project_options:
            current_sel = projects[0]["folder_name"]

        selected_folder = st.selectbox(
            "분석할 캡컷 프로젝트 선택",
            options=list(project_options.keys()),
            format_func=lambda x: f"{project_options[x]['draft_name']} ({project_options[x]['modify_time']})",
            index=list(project_options.keys()).index(current_sel),
            key="sb_selected_capcut_folder"
        )
        st.session_state["selected_capcut_folder"] = selected_folder
        selected_proj = project_options[selected_folder]

        # 선택된 프로젝트 간략 요약 카드
        with st.container(border=True):
            col_cover, col_meta = st.columns([1, 2])
            with col_cover:
                if selected_proj["has_cover"] and selected_proj["cover_path"]:
                    st.image(selected_proj["cover_path"], use_container_width=True)
                else:
                    st.markdown("🎬 **미리보기 없음**")
            with col_meta:
                st.markdown(f"**{selected_proj['draft_name']}**")
                st.caption(f"🕒 수정일: {selected_proj['modify_time']}")
                st.caption(f"⏱️ 재생 시간: 약 {selected_proj['duration_sec']}초")
                
                c = selected_proj["counts"]
                st.markdown(
                    f"📝 자막: **{c['texts']}** | ✨ 효과: **{c['effects']}** | "
                    f"🔄 전환: **{c['transitions']}** | 🎬 애니: **{c['animations']}**"
                )

        st.markdown("---")
        st.markdown("##### 💡 활용 팁")
        st.info(
            "1. 캡컷에서 마음에 드는 **자막 디자인, 네온/글로우 효과, 전환 효과**를 넣은 10초짜리 템플릿 영상을 만듭니다.\n"
            "2. 여기서 해당 프로젝트를 선택하고 **'스타일 프리셋으로 저장'**을 누릅니다.\n"
            "3. '🎬 캡컷 영상 자동 생성' 탭에서 새 광고를 만들 때 해당 프리셋을 선택하면 **캡컷 고유 효과가 100% 자동 적용**됩니다!"
        )

    # -----------------------------------------------------------------
    # 우측: 상세 분석 및 프리셋 저장
    # -----------------------------------------------------------------
    with col_detail:
        st.markdown(f"##### 🔍 '{selected_proj['draft_name']}' 상세 분석 결과")
        
        details = capcut_tracker.inspect_project_details(selected_proj["folder_path"])
        if "error" in details:
            st.error(details["error"])
        else:
            texts = details["texts"]
            effects = details["effects"]
            transitions = details["transitions"]
            animations = details["animations"]

            # 1. 자막 디자인 분석
            with st.expander(f"📝 자막 디자인 분석 ({len(texts)}개 텍스트)", expanded=True):
                if texts:
                    t0 = texts[0]
                    # 자막 스타일 미리보기 박스 (CSS 시뮬레이션)
                    col_r, col_g, col_b = t0["color_rgb"][:3]
                    hex_color = f"#{int(col_r*255):02x}{int(col_g*255):02x}{int(col_b*255):02x}"
                    border_css = "none"
                    if t0["border"]["has_border"]:
                        bw = max(1, int(t0["border"]["width"] / 10))
                        border_css = f"{bw}px solid #000"

                    st.markdown(
                        f"""
                        <div style="background-color: #1a1a1a; padding: 12px; border-radius: 8px; text-align: center; margin-bottom: 10px;">
                            <span style="font-size: 1.3rem; font-weight: 700; color: {hex_color}; text-shadow: 2px 2px 4px #000;">
                                {t0['text'] or '미리보기 텍스트 예시'}
                            </span>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                    c_f1, c_f2 = st.columns(2)
                    with c_f1:
                        st.markdown(f"**폰트명:** `{t0['font_name']}`")
                        st.markdown(f"**글자 색상:** `{hex_color}`")
                    with c_f2:
                        st.markdown(f"**외곽선(Border):** {'적용됨' if t0['border']['has_border'] else '없음'}")
                        st.markdown(f"**그림자(Shadow):** {'적용됨' if t0['shadow']['has_shadow'] else '없음'}")
                else:
                    st.caption("프로젝트에 포함된 자막이 없습니다.")

            # 2. 캡컷 고유 효과 (Effects)
            with st.expander(f"✨ 캡컷 고유 효과 (Effects) ({len(effects)}개)", expanded=True):
                if effects:
                    for eff in effects:
                        st.markdown(f"- **{eff['name']}** `[유형: {eff['type']}]` *(ID: `{eff['effect_id']}`)*")
                else:
                    st.caption("적용된 특수 효과가 없습니다.")

            # 3. 전환 효과 (Transitions)
            with st.expander(f"🔄 장면 전환 효과 (Transitions) ({len(transitions)}개)", expanded=True):
                if transitions:
                    for tr in transitions:
                        st.markdown(f"- **{tr['name']}** *(ID: `{tr['effect_id']}`)*")
                else:
                    st.caption("적용된 전환 효과가 없습니다.")

            # 4. 애니메이션
            if animations:
                with st.expander(f"🎬 애니메이션 ({len(animations)}개)", expanded=False):
                    for anim in animations[:5]:
                        st.markdown(f"- **{anim['name']}** `[{anim['type']}]`")

            # -------------------------------------------------------------
            # 프리셋 저장 인터페이스
            # -------------------------------------------------------------
            st.markdown("---")
            st.markdown("##### ⭐ 이 스타일을 AdForge 프리셋으로 저장")
            
            p_col1, p_col2 = st.columns([1.5, 1])
            with p_col1:
                preset_name_input = st.text_input(
                    "프리셋 이름",
                    value=f"{selected_proj['draft_name']} 스타일",
                    key="input_preset_name"
                )
            with p_col2:
                preset_desc_input = st.text_input(
                    "간단 설명 (선택)",
                    placeholder="예: 핑크 네온 자막 + 행복한 섬광",
                    key="input_preset_desc"
                )

            if st.button("💾 프리셋으로 등록하기", use_container_width=True, type="primary", key="btn_save_preset"):
                if not preset_name_input.strip():
                    st.error("프리셋 이름을 입력해주세요.")
                else:
                    try:
                        new_p = capcut_tracker.save_preset_from_project(
                            project_folder=selected_proj["folder_path"],
                            preset_name=preset_name_input.strip(),
                            description=preset_desc_input.strip()
                        )
                        st.success(f"🎉 '{new_p['name']}' 프리셋이 성공적으로 저장되었습니다!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"저장 중 오류 발생: {e}")

    # -----------------------------------------------------------------
    # 하단: 저장된 스타일 프리셋 보관함 관리
    # -----------------------------------------------------------------
    st.markdown("---")
    st.subheader("📦 저장된 스타일 프리셋 보관함")
    saved_presets = capcut_tracker.load_presets()

    if not saved_presets:
        st.info("아직 저장된 프리셋이 없습니다. 위에서 캡컷 프로젝트를 선택한 뒤 프리셋으로 저장해 보세요.")
    else:
        for p in saved_presets:
            with st.container(border=True):
                p_c1, p_c2, p_c3, p_c4 = st.columns([3, 3, 3, 1])
                with p_c1:
                    st.markdown(f"**🎨 {p.get('name')}**")
                    if p.get("description"):
                        st.caption(p.get("description"))
                with p_c2:
                    st.caption(f"📁 원본: `{p.get('source_project')}`")
                    st.caption(f"🕒 등록일: {p.get('created_at')}")
                with p_c3:
                    eff_count = len(p.get("effects", []))
                    trans_count = len(p.get("transitions", []))
                    font_n = p.get("hook_text_style", {}).get("font_name", "기본")
                    st.caption(f"폰트: **{font_n}** | 효과: **{eff_count}개** | 전환: **{trans_count}개**")
                with p_c4:
                    if st.button("🗑️ 삭제", key=f"del_preset_{p.get('id')}"):
                        capcut_tracker.delete_preset(p.get("id"))
                        st.success("프리셋이 삭제되었습니다.")
                        st.rerun()
