import os
import re
import streamlit as st
from naver_clip_adforge import (
    build_capcut_project_for_naver_clip,
    generate_hailuo_prompts_stream,
    generate_strategic_script_stream
)

# -------------------------------------------------------------------
# Streamlit 대시보드 페이지 설정
# -------------------------------------------------------------------
st.set_page_config(page_title="AdForge - 4050 타겟 영상 자동화", page_icon="🎬", layout="wide")

st.markdown('''
<style>
    .main-header { font-size: 2.2rem; font-weight: 800; color: #00E676; margin-bottom: 0.2rem; }
    .sub-header { font-size: 1.05rem; color: #A0AEC0; margin-bottom: 1.5rem; }
    .prompt-box { background-color: #F0F4F8; color: #1A202C; padding: 1rem; border-radius: 8px; margin-bottom: 1rem; font-family: monospace; white-space: pre-wrap; border: 1px solid #CBD5E0; }
    .comment-box { background-color: #2b1f31; padding: 1rem; border-radius: 8px; margin-bottom: 1rem; border-left: 4px solid #d53f8c; }
</style>
''', unsafe_allow_html=True)

st.markdown('<div class="main-header">🚀 AdForge :: 4050 숏폼 기획 & 영상 자동화</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">대본 기획부터 캡컷 프로젝트 생성, Hailuo AI 프롬프트까지 원스톱!</div>', unsafe_allow_html=True)

# -------------------------------------------------------------------
# 전역 설정 및 API 키 캐싱
# -------------------------------------------------------------------
API_KEY_FILE = "nv_api_key.txt"
cached_api_key = os.environ.get("NVIDIA_API_KEY", "")
if os.path.exists(API_KEY_FILE):
    with open(API_KEY_FILE, "r", encoding="utf-8-sig") as f:
        cached_api_key = f.read().strip()

col_key, col_model = st.columns(2)
with col_key:
    nvidia_api_key = st.text_input("🔑 NVIDIA API Key (대본 & 프롬프트 생성용)", type="password", value=cached_api_key, placeholder="nvapi-...")
    if nvidia_api_key and nvidia_api_key != cached_api_key:
        with open(API_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(nvidia_api_key)
with col_model:
    model_choice = st.selectbox(
        "🧠 NVIDIA 모델 선택",
        options=[
            "meta/llama-3.1-70b-instruct",
            "nvidia/llama-3.1-nemotron-70b-instruct",
            "nvidia/nemotron-3-ultra-550b-a55b"
        ]
    )

st.markdown("---")

# -------------------------------------------------------------------
# STEP 1: 4050 타겟 맞춤 대본 기획
# -------------------------------------------------------------------
st.subheader("STEP 1: 4050 타겟 맞춤 대본 기획")

col_cat, col_sub = st.columns(2)
with col_cat:
    topic_category = st.selectbox(
        "📌 타겟 카테고리 (순위별)",
        ["1순위: 건강 (관여도 높은 질병, 허리 보호 등)", "2순위: 골프 (시니어 스포츠)", "3순위: 미용 (주름, 머리 등)"]
    )
with col_sub:
    sub_topic = st.text_input("✏️ 세부 주제", placeholder="예) 일상 속 허리를 보호하는 법")

col_fmt, col_prod = st.columns(2)
with col_fmt:
    video_format = st.selectbox(
        "🎬 영상 포맷(전략) 선택",
        [
            "포맷 A (순수 정보성): 제품 노출 0%, 꿀팁만 제공",
            "포맷 B (간접 홍보): 꿀팁 + '제가 쓰는 기구는 댓글에~' (영상 내 브랜드 금지)",
            "포맷 C (직접 홍보): 대놓고 리뷰 및 제품 장점 어필"
        ]
    )
with col_prod:
    product_name = st.text_input("📦 연결할 제품명", value="다피다 허리찜질기")

if st.button("✨ AI 맞춤형 숏폼 대본 생성 (실시간)", use_container_width=True):
    if not nvidia_api_key:
        st.error("NVIDIA API Key를 입력해주세요.")
    elif not sub_topic:
        st.error("세부 주제를 입력해주세요.")
    else:
        st.session_state["raw_script_output"] = ""
        st.session_state["parsed_script"] = ""
        st.session_state["parsed_comment"] = ""
        st.session_state["parsed_description"] = ""
        
        with st.spinner(f"대본 기획 중... ({model_choice})"):
            st.markdown("##### 💡 대본 작성 중 (실시간)")
            def script_stream_generator():
                for chunk in generate_strategic_script_stream(
                    topic_category, sub_topic, video_format, product_name, nvidia_api_key, model_choice
                ):
                    yield chunk
                    
            raw_output = st.write_stream(script_stream_generator())
            st.session_state["raw_script_output"] = raw_output
            
            # Parsing the output robustly with regex
            script_part = raw_output
            comment_part = ""
            desc_part = ""
            
            comment_matches = list(re.finditer(r'={2,}\s*COMMENT\s*={2,}', raw_output, re.IGNORECASE))
            desc_matches = list(re.finditer(r'={2,}\s*DESCRIPTION\s*={2,}', raw_output, re.IGNORECASE))
            
            if comment_matches and desc_matches:
                # Use the last occurrence in case the reasoning block also included it
                c_match = comment_matches[-1]
                d_match = desc_matches[-1]
                
                if c_match.start() < d_match.start():
                    script_part = raw_output[:c_match.start()].strip()
                    comment_part = raw_output[c_match.end():d_match.start()].strip()
                    desc_part = raw_output[d_match.end():].strip()
                else:
                    script_part = raw_output[:d_match.start()].strip()
                    desc_part = raw_output[d_match.end():c_match.start()].strip()
                    comment_part = raw_output[c_match.end():].strip()
            elif comment_matches:
                c_match = comment_matches[-1]
                script_part = raw_output[:c_match.start()].strip()
                comment_part = raw_output[c_match.end():].strip()
            elif desc_matches:
                d_match = desc_matches[-1]
                script_part = raw_output[:d_match.start()].strip()
                desc_part = raw_output[d_match.end():].strip()
                
            # If reasoning text is at the beginning of script_part, we can optionally clean it,
            # but usually it's fine.
            st.session_state["parsed_script"] = script_part
            st.session_state["parsed_comment"] = comment_part
            st.session_state["parsed_description"] = desc_part

# Show parsed comment & description always
col_out1, col_out2 = st.columns(2)
with col_out1:
    st.markdown("##### 💬 유튜브/클립용 고정 댓글 (CTA)")
    c_val = st.session_state.get("parsed_comment", "")
    st.text_area("댓글 복사", value=c_val, height=150, label_visibility="collapsed")
with col_out2:
    st.markdown("##### 📝 영상 본문 설명 & 해시태그")
    d_val = st.session_state.get("parsed_description", "")
    st.text_area("설명 복사", value=d_val, height=150, label_visibility="collapsed")

st.markdown("---")

# -------------------------------------------------------------------
# STEP 2: 대본 입력 및 캡컷/Hailuo 자동화
# -------------------------------------------------------------------
st.subheader("STEP 2: 캡컷 연동 & Hailuo 프롬프트 추출")

default_script = st.session_state.get("parsed_script", "")
script_text = st.text_area("📝 영상 자막(대본) 전문 (STEP 1에서 생성 시 자동 입력됨)", value=default_script, height=200)

voice_choice = st.selectbox(
    "🎙️ AI 성우 보이스 선택",
    options=[
        ("👩‍💼 마케팅 여성 - 선희 (차분/신뢰)", "ko-KR-SunHiNeural"),
        ("👩‍🏫 아나운서 여성 - 지민 (깔끔/명확)", "ko-KR-JiMinNeural"),
        ("👵 다정한 아주머니 - 순복 (포근/시니어)", "ko-KR-SoonBokNeural"),
        ("👨‍💼 마케팅 남성 - 인준 (지적/차분)", "ko-KR-InJoonNeural"),
        ("👨‍🏫 신뢰감 남성 - 봉진 (묵직/안정)", "ko-KR-BongJinNeural"),
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
                st.markdown("##### 💡 추출 중인 Hailuo AI 프롬프트 (실시간)")
                def stream_generator():
                    for chunk in generate_hailuo_prompts_stream(script_text, nvidia_api_key, model_choice):
                        yield chunk
                        
                hailuo_result = st.write_stream(stream_generator())
                st.session_state["hailuo_prompts"] = hailuo_result

if "hailuo_prompts" in st.session_state and st.session_state["hailuo_prompts"]:
    st.markdown("---")
    st.subheader("💡 추출된 Hailuo AI 프롬프트 전문")
    st.markdown(f'<div class="prompt-box">{st.session_state["hailuo_prompts"]}</div>', unsafe_allow_html=True)
