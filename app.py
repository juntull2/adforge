import os
import streamlit as st
from naver_clip_adforge import (
    build_capcut_project_for_naver_clip,
    generate_hailuo_prompts_stream
)

# -------------------------------------------------------------------
# Streamlit 대시보드 페이지 설정
# -------------------------------------------------------------------
st.set_page_config(page_title="AdForge - 초간단 영상 자동화", page_icon="🎬", layout="wide")

st.markdown('''
<style>
    .main-header { font-size: 2.2rem; font-weight: 800; color: #00E676; margin-bottom: 0.2rem; }
    .sub-header { font-size: 1.05rem; color: #A0AEC0; margin-bottom: 1.5rem; }
    .prompt-box { background-color: #2D3748; padding: 1rem; border-radius: 8px; margin-bottom: 1rem; font-family: monospace; white-space: pre-wrap; }
</style>
''', unsafe_allow_html=True)

st.markdown('<div class="main-header">🚀 AdForge :: 초간단 영상 자동화 & 프롬프트 추출</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">대본만 넣으면 캡컷 프로젝트 생성과 Hailuo AI 영상 프롬프트가 한 번에!</div>', unsafe_allow_html=True)

# -------------------------------------------------------------------
# 전역 설정
# -------------------------------------------------------------------
col_key, col_model = st.columns(2)
with col_key:
    nvidia_api_key = st.text_input("🔑 NVIDIA API Key (Hailuo 프롬프트 자동 생성용)", type="password", placeholder="nvapi-...")
with col_model:
    model_choice = st.selectbox(
        "🧠 NVIDIA 모델 선택",
        options=[
            "nvidia/nemotron-3-ultra-550b-a55b",
            "meta/llama-3.1-70b-instruct",
            "meta/llama-3.1-405b-instruct",
            "nvidia/llama-3.1-nemotron-70b-instruct"
        ]
    )

# -------------------------------------------------------------------
# 대본 입력 및 캡컷 자동화
# -------------------------------------------------------------------
st.subheader("1. 대본 입력 및 자동화")

script_text = st.text_area("📝 영상 자막(대본) 전문 입력", height=200, placeholder="여기에 대본을 붙여넣으세요...")

voice_choice = st.selectbox(
    "🎙️ AI 성우 보이스 선택",
    options=[
        ("👩‍💼 마케팅 여성 - 선희 (차분/신뢰)", "ko-KR-SunHiNeural"),
        ("👨‍💼 마케팅 남성 - 인준 (지적/차분)", "ko-KR-InJoonNeural"),
        ("🎧 유튜버 청년 - 현수 (친근/밝음)", "ko-KR-HyunsuNeural")
    ],
    format_func=lambda x: x[0]
)[1]

col1, col2 = st.columns(2)

with col1:
    if st.button("🎬 캡컷 프로젝트 1초 자동 생성", use_container_width=True):
        if not script_text.strip():
            st.error("대본이 비어있습니다!")
        else:
            with st.spinner("CapCut 초안 프로젝트 렌더링 중..."):
                try:
                    proj_name = build_capcut_project_for_naver_clip(script_text, voice_choice)
                    st.success(f"성공적으로 캡컷 프로젝트 '{proj_name}' 초안을 생성했습니다! 캡컷 앱에서 확인해주세요.")
                except Exception as e:
                    st.error(f"오류 발생: {e}")

with col2:
    if st.button("🤖 Hailuo AI 장면 프롬프트 추출", use_container_width=True):
        if not script_text.strip():
            st.error("대본이 비어있습니다!")
        elif not nvidia_api_key:
            st.error("NVIDIA API Key를 입력해주세요.")
        else:
            with st.spinner(f"장면별 프롬프트 분석 중... ({model_choice})"):
                st.markdown("---")
                st.subheader("💡 추출 중인 Hailuo AI 프롬프트 (실시간)")
                
                def stream_generator():
                    for chunk in generate_hailuo_prompts_stream(script_text, nvidia_api_key, model_choice):
                        yield chunk
                        
                hailuo_result = st.write_stream(stream_generator())
                st.session_state["hailuo_prompts"] = hailuo_result

# -------------------------------------------------------------------
# 결과 출력
# -------------------------------------------------------------------
if "hailuo_prompts" in st.session_state and st.session_state["hailuo_prompts"]:
    st.markdown("---")
    st.subheader("💡 추출된 Hailuo AI 프롬프트")
    st.markdown("아래 프롬프트를 복사하여 Hailuo AI에 입력한 뒤, 생성된 영상을 캡컷에 덮어쓰기 하세요.")
    st.markdown(f'<div class="prompt-box">{st.session_state["hailuo_prompts"]}</div>', unsafe_allow_html=True)
