import os
import streamlit as st
from naver_clip_adforge import (
    build_capcut_project_for_naver_clip,
    PRODUCTS_DB,
    generate_naver_clip_script,
    generate_seo_recommendation,
)
from clip_reference_scraper import analyze_custom_clip_link
from performance_logger import log_performance

# -------------------------------------------------------------------
# Streamlit 대시보드 페이지 설정
# -------------------------------------------------------------------
st.set_page_config(page_title="AdForge - 건강 콘텐츠 제작 파이프라인", page_icon="🎬", layout="wide")

st.markdown('''
<style>
    .main-header { font-size: 2.2rem; font-weight: 800; color: #00E676; margin-bottom: 0.2rem; }
    .sub-header { font-size: 1.05rem; color: #A0AEC0; margin-bottom: 1.5rem; }
</style>
''', unsafe_allow_html=True)

st.markdown('<div class="main-header">🚀 AdForge :: 4050 건강 콘텐츠 제작·운영 시스템</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">리서치부터 성과 기록까지! 네이버 클립 건강 정보 숏폼 6단계 MVP 파이프라인</div>', unsafe_allow_html=True)

# -------------------------------------------------------------------
# 전역 설정 (API Key 등)
# -------------------------------------------------------------------
with st.expander("⚙️ 기본 설정 (Gemini API Key 및 제품/주제)", expanded=True):
    gemini_api_key = st.text_input("🔑 Gemini API Key (AI 대본/SEO 생성용)", type="password")
    
    product_options = list(PRODUCTS_DB.keys())
    product_choice = st.selectbox("📦 타겟 제품 선택", options=product_options)
    default_kw = PRODUCTS_DB.get(product_choice, {}).get("hub_keyword", "건강 꿀팁")
    topic_input = st.text_input("🔍 메인 주제 (키워드)", value=default_kw)
    
st.markdown("---")

# -------------------------------------------------------------------
# 1. Content Research
# -------------------------------------------------------------------
st.subheader("1. Content Research (레퍼런스 구조 조사)")
with st.expander("🔍 벤치마킹할 네이버 클립 영상 링크 분석", expanded=False):
    clip_url = st.text_input("네이버 클립 URL 입력 (예: https://m.clip.naver.com/...)")
    if st.button("레퍼런스 구조 단순 분석"):
        if clip_url:
            with st.spinner("분석 중..."):
                res = analyze_custom_clip_link(clip_url, topic_input)
                st.write(f"**원본 제목:** {res['title']}")
                st.table(res['script_table'])
        else:
            st.warning("URL을 입력해주세요.")

st.markdown("---")

# -------------------------------------------------------------------
# 2. Creative Script
# -------------------------------------------------------------------
st.subheader("2. Creative Script (AI 대본 기획)")
if "script_text" not in st.session_state:
    st.session_state["script_text"] = ""
if "seo_title" not in st.session_state:
    st.session_state["seo_title"] = ""

if st.button("✨ 4050 여성 타깃 건강 정보 대본 AI 자동 생성 (가드레일 적용)"):
    if not gemini_api_key:
        st.error("상단 설정에서 API Key를 입력해주세요.")
    else:
        with st.spinner("의료적 단정 및 과도한 공포를 배제한 안전한 대본 작성 중..."):
            seo_title, script_text = generate_naver_clip_script(product_choice, topic_input, gemini_api_key)
            st.session_state["seo_title"] = seo_title
            st.session_state["script_text"] = script_text

seo_title = st.text_input("영상 제목 (SEO Title)", value=st.session_state["seo_title"])
st.session_state["seo_title"] = seo_title

script_text = st.text_area("내레이션 대본", value=st.session_state["script_text"], height=150)
st.session_state["script_text"] = script_text

st.markdown("---")

# -------------------------------------------------------------------
# 3. SEO / 검색 최적화
# -------------------------------------------------------------------
st.subheader("3. SEO / 검색 최적화 추천")
if st.button("📈 추천 해시태그, Hook, CTA AI 생성"):
    if not st.session_state["script_text"]:
        st.warning("먼저 대본을 생성해주세요.")
    elif not gemini_api_key:
        st.error("상단 설정에서 API Key를 입력해주세요.")
    else:
        with st.spinner("SEO 요소 분석 중..."):
            seo_rec = generate_seo_recommendation(st.session_state["script_text"], gemini_api_key)
            st.info(seo_rec)

st.markdown("---")

# -------------------------------------------------------------------
# 4. CapCut Automation
# -------------------------------------------------------------------
st.subheader("4. CapCut Automation (영상 자동 제작)")
voice_choice = st.selectbox(
    "🎙️ AI 성우 보이스 선택",
    options=[
        ("👩‍💼 마케팅 여성 - 선희 (차분/신뢰)", "ko-KR-SunHiNeural"),
        ("👨‍💼 마케팅 남성 - 인준 (지적/차분)", "ko-KR-InJoonNeural"),
        ("🎧 유튜버 청년 - 현수 (친근/밝음)", "ko-KR-HyunsuNeural")
    ],
    format_func=lambda x: x[0]
)[1]

if st.button("🎬 캡컷 프로젝트 1초 자동 생성 (TTS + 자막 + 영상 배치)"):
    if not st.session_state["script_text"]:
        st.error("대본이 비어있습니다!")
    else:
        with st.spinner("CapCut 초안 프로젝트 렌더링 중..."):
            try:
                # 반환값이 (project_name, seo_title) 일 수도 있고 하나일 수도 있음. naver_clip_adforge.py에서 project_name, seo_title 를 반환했다가 수정되었나? 
                # 아까 refactor_adforge.py에서 return seo_title, script_text 였고, 
                # build_capcut_project_for_naver_clip 은 return project_name, seo_title 였음!
                # Wait, earlier I didn't change what build_capcut_project_for_naver_clip returns. It returns `project_name, seo_title`.
                result = build_capcut_project_for_naver_clip(
                    product_choice, topic_input, st.session_state["script_text"], st.session_state["seo_title"], voice_choice
                )
                proj_name = result[0] if isinstance(result, tuple) else result
                st.success(f"성공적으로 캡컷 프로젝트 '{proj_name}' 초안을 생성했습니다! 캡컷 앱에서 확인해주세요.")
            except Exception as e:
                st.error(f"오류 발생: {e}")

st.markdown("---")

# -------------------------------------------------------------------
# 5. Publish
# -------------------------------------------------------------------
st.subheader("5. Publish (네이버 클립 발행 가이드)")
st.markdown(f'''
* **네이버 크리에이터 스튜디오 링크**: [업로드하러 가기](https://creator.tv.naver.com/channel/healthylife1/content/video)
* **필수 행동 유도(CTA) 고정 댓글 복사용**: 
  `💡 건강을 위한 필수템! 네이버에 '{product_choice}' 검색해보세요!`
''')

st.markdown("---")

# -------------------------------------------------------------------
# 6. Performance Logging
# -------------------------------------------------------------------
st.subheader("6. Performance Logging (초기 성과 기록)")
with st.expander("📊 발행 완료된 영상 정보 기록하기 (Intelligence 기반 데이터)", expanded=False):
    col1, col2 = st.columns(2)
    with col1:
        log_content_id = st.text_input("클립 URL 또는 영상 ID (필수)")
        log_hook = st.text_input("사용된 Hook 텍스트")
        log_cta = st.text_input("사용된 CTA")
        log_views = st.number_input("현재 조회수", min_value=0, value=0)
    with col2:
        log_hashtags = st.text_input("해시태그 (쉼표 구분)")
        log_duration = st.number_input("영상 길이 (초)", min_value=0, value=30)
        log_shopping_tag = st.checkbox("쇼핑 태그 연동 여부")
    
    if st.button("💾 성과 데이터베이스에 저장"):
        if log_content_id:
            data = {
                "content_id": log_content_id,
                "topic": topic_input,
                "hook": log_hook,
                "title": st.session_state["seo_title"],
                "hashtags": log_hashtags,
                "duration": log_duration,
                "cta": log_cta,
                "shopping_tag": log_shopping_tag,
                "views": log_views
            }
            log_performance(data)
            st.success("성과 데이터가 안전하게 기록되었습니다! 추후 Intelligence 기능에 활용됩니다.")
        else:
            st.warning("클립 URL 또는 영상 ID를 입력해주세요.")
