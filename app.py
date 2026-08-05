import os
import glob
import streamlit as st
from naver_clip_adforge import build_capcut_project_for_naver_clip, PRODUCTS_DB, generate_naver_clip_script
from auto_stock_downloader import fetch_and_download_mixkit_stock_videos

# -------------------------------------------------------------------
# Streamlit 대시보드 페이지 설정 (다크 테마 & 넓은 레이아웃)
# -------------------------------------------------------------------
st.set_page_config(
    page_title="AdForge - 네이버 클립 숏폼 자동 제작 시스템",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 커스텀 CSS 스타일링 (스마트 마케터용 프리미엄 UI)
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 800;
        color: #00E676;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #A0AEC0;
        margin-bottom: 2rem;
    }
    .stButton>button {
        background: linear-gradient(135deg, #00C853 0%, #00E676 100%);
        color: #000000;
        font-size: 1.2rem;
        font-weight: 800;
        border: none;
        padding: 0.75rem 2rem;
        border-radius: 8px;
        width: 100%;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(0,230,118,0.4);
    }
    .card-box {
        background-color: #1A202C;
        padding: 1.5rem;
        border-radius: 12px;
        border: 1px solid #2D3748;
        margin-bottom: 1.5rem;
    }
</style>
""", unsafe_allow_html=True)

# 헤더 영역
st.markdown('<div class="main-header">🚀 AdForge :: 네이버 클립 숏폼 자동 제작 대시보드</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">대본과 필요 영상 키워드만 입력하면 [AI더빙 + Pretendard 자막 + 9:16 비디오 컷]이 1초 만에 캡컷에 완성됩니다.</div>', unsafe_allow_html=True)

# -------------------------------------------------------------------
# 사이드바: 마케팅 옵션 세팅
# -------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 마케팅 숏폼 세팅")
    
    product_choice = st.selectbox(
        "📦 타겟 제품 선택",
        options=["다피다 허리 찜질기", "파우리나 전동재활자전거", "기타 커스텀 제품"]
    )
    
    keyword_input = st.text_input(
        "🔍 네이버 SEO 타겟 키워드",
        value="허리아플때" if product_choice == "다피다 허리 찜질기" else ("노인용 하체회복기구" if product_choice == "파우리나 전동재활자전거" else "추천제품")
    )
    
    voice_choice = st.selectbox(
        "🎙️ AI 성우 보이스",
        options=[
            ("여성 - 선희 (또렷하고 신뢰감 있는 톤)", "ko-KR-SunHiNeural"),
            ("남성 - 인준 (지적이고 차분한 톤)", "ko-KR-InJoonNeural")
        ],
        format_func=lambda x: x[0]
    )[1]

    st.markdown("---")
    st.subheader("📐 자막 및 화면 고정 값")
    st.info("""
    - **화면 비율**: 9:16 (1080x1920 세로 숏폼)
    - **자막 폰트**: Pretendard Black (시스템 연동)
    - **글자 크기**: 14.5 (왕글씨 1줄 순차 전환)
    - **데드존 보정**: 하단 UI 안 가리도록 중하단 배치
    - **싱크 보정**: 앞/뒤 무음 0.01초 칼 컷트 적용
    """)

# -------------------------------------------------------------------
# 메인 영역: 대본 입력 및 영상 소스 설명
# -------------------------------------------------------------------
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📝 1. 숏폼 대본 입력")
    
    # 기본 대본 자동 로드 버튼
    if st.button("💡 옵시디언 마케팅 가이드 대본 불러오기"):
        seo_title, script = generate_naver_clip_script(product_choice, keyword_input)
        st.session_state["script_text"] = script
        st.session_state["seo_title"] = seo_title
        st.success("옵시디언 오메클(오프닝-메리트-클로징) 대본이 자동 장착되었습니다!")

    script_input = st.text_area(
        "대본 내용 (문장별로 자연스럽게 읽어드립니다)",
        value=st.session_state.get("script_text", """허리 삐끗했을 때 파스 붙이고 누워만 계셨다면 당장 멈추세요!
갑자기 굳은 척추 속근육은 겉만 따뜻하게 해선 절대 풀리지 않습니다.
핵심은 3파장 근적외선으로 피부 속 3cm 깊은 척추 마디까지 열을 전달하는 건데요.
원적외선과 근적외선이 동시에 나오는 전용 복대를 차주시면 굳어있던 척추 속근육이 사르르 풀리면서 순식간에 편안해집니다.
무선이라 차고 집안일할 때도 OK!
30일간 써보고 마음에 안 들면 100% 환불 보증까지 있으니 안심하고 확인해 보세요."""),
        height=280
    )

with col2:
    st.subheader("🎬 2. 필요한 영상 소스 키워드 설명")
    st.caption("필요한 분위기나 연출 장면 키워드를 영문(콤마 구분)으로 입력하면 고화질 HD 비디오 소스가 자동 수급됩니다.")
    
    video_keywords_input = st.text_input(
        "영상 소스 키워드 (예: back pain, massage, stretching)",
        value="back pain, massage" if product_choice == "다피다 허리 찜질기" else "exercise, elderly"
    )
    
    # 다운로드된 비디오 소스 목록 확인
    stock_dir = os.path.join(os.getcwd(), "stock_videos")
    existing_videos = glob.glob(os.path.join(stock_dir, "*.mp4"))
    
    st.markdown(f"**현재 보유 중인 비디오 소스**: `{len(existing_videos)}개`")
    
    if st.button("📥 스톡 비디오 소스 5개 추가 자동 다운로드"):
        with st.spinner("Mixkit 고화질 스톡 비디오 다운로드 중..."):
            kws = [k.strip() for k in video_keywords_input.split(",") if k.strip()]
            for kw in kws:
                fetch_and_download_mixkit_stock_videos(kw, count=3, output_dir=stock_dir)
            st.rerun()

st.markdown("---")

# -------------------------------------------------------------------
# 3. 🚀 메인 프로젝트 생성 실행 버튼
# -------------------------------------------------------------------
if st.button("🚀 캡컷 9:16 네이버 클립 프로젝트 생성하기"):
    if not script_input.strip():
        st.error("대본을 입력해 주세요!")
    else:
        with st.spinner("AI 더빙 ➡️ 무음 컷트 ➡️ Pretendard 자막 ➡️ 비디오 소스 컷 연동 중..."):
            try:
                # 영상 소스 다운로드 확인
                kws = [k.strip() for k in video_keywords_input.split(",") if k.strip()]
                if kws and len(existing_videos) < 3:
                    for kw in kws:
                        fetch_and_download_mixkit_stock_videos(kw, count=3, output_dir=stock_dir)

                # CapCut 프로젝트 생성 엔진 가동
                project_name, seo_title = build_capcut_project_for_naver_clip(
                    product_name=product_choice,
                    keyword=keyword_input,
                    voice=voice_choice
                )

                st.balloons()
                st.success(f"🎉 성공! CapCut 프로젝트 '{project_name}' 생성이 완료되었습니다!")
                
                st.markdown(f"""
                ### 📱 네이버 클립 게시 가이드
                - **프로젝트 이름**: `{project_name}` (CapCut 앱 열면 바로 보입니다)
                - **네이버 클립 추천 제목**: `{seo_title}`
                - **비율**: 9:16 (1080x1920 세로 숏폼)
                - **자막 폰트**: Pretendard Black (크기 14.5)
                - **더빙 싱크**: 0.01초 칼싱크 적용 완료

                > 💡 **CapCut 실행 안내**: CapCut 앱 화면에서 `뒤로가기(←)`를 누르고 목록을 새로고침하여 `{project_name}`을 열어보세요!
                """)
            except Exception as e:
                st.error(f"프로젝트 생성 중 오류가 발생했습니다: {e}")
