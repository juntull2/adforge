import os
import glob
import urllib.parse
import streamlit as st
from naver_clip_adforge import (
    build_capcut_project_for_naver_clip,
    PRODUCTS_DB,
    generate_naver_clip_script,
    apply_user_feedback_to_script,
    SCRIPT_FORMAT_NAMES,
    NAVER_CLIP_TOP_KEYWORDS,
    OBSIDIAN_VAULT_PATH
)
from auto_stock_downloader import fetch_and_download_mixkit_stock_videos

# -------------------------------------------------------------------
# Streamlit 대시보드 페이지 설정 (다크 테마 & 넓은 레이아웃)
# -------------------------------------------------------------------
st.set_page_config(
    page_title="AdForge - 옵시디언 연동 네이버 클립 숏폼 자동 제작 시스템",
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
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #A0AEC0;
        margin-bottom: 1.5rem;
    }
    .stButton>button {
        background: linear-gradient(135deg, #00C853 0%, #00E676 100%);
        color: #000000;
        font-size: 1.15rem;
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
        padding: 1.2rem;
        border-radius: 10px;
        border: 1px solid #2D3748;
        margin-bottom: 1rem;
    }
    .badge-obsidian {
        background-color: #7C3AED;
        color: #FFFFFF;
        padding: 0.2rem 0.6rem;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# 헤더 영역 및 옵시디언 상태 뱃지
st.markdown('<div class="main-header">🚀 AdForge :: 네이버 클립 숏폼 자동 제작 시스템</div>', unsafe_allow_html=True)
st.markdown(f'<div class="sub-header">대본과 필요 영상 키워드만 입력하면 [AI더빙 + Pretendard 자막 + 9:16 비디오 컷]이 1초 만에 캡컷에 완성됩니다. <span class="badge-obsidian">🔮 노리몰 업무가이드 & Obsidian Vault 연동 완료 (일 유입 150명 목표)</span></div>', unsafe_allow_html=True)

# -------------------------------------------------------------------
# 사이드바: 마케팅 옵션 세팅
# -------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 마케팅 숏폼 세팅")
    
    product_options = list(PRODUCTS_DB.keys())
    product_choice = st.selectbox(
        "📦 타겟 제품 선택 (Obsidian DB 연동)",
        options=product_options
    )
    
    selected_prod_info = PRODUCTS_DB.get(product_choice, {})
    default_kw = selected_prod_info.get("hub_keyword", "허리아플때")
    
    keyword_input = st.text_input(
        "🔍 네이버 SEO 타겟 키워드",
        value=default_kw
    )
    
    st.markdown("---")
    st.subheader("🎬 대본 포맷 선택 (레퍼런스 DB)")
    format_choice = st.selectbox(
        "마케팅 스토리라인 포맷",
        options=list(SCRIPT_FORMAT_NAMES.keys()),
        format_func=lambda x: SCRIPT_FORMAT_NAMES[x]
    )
    
    st.markdown("---")
    voice_choice = st.selectbox(
        "🎙️ AI 성우 보이스 & 릴스 톤 선택",
        options=[
            ("🐸 릴스 개구리/캐주얼 톤 (톡톡 튀는 릴스 캐릭터)", {"voice": "ko-KR-SunHiNeural", "rate": "+15%", "pitch": "+25Hz"}),
            ("⚡ 릴스 숏폼 빠른 톤 (경쾌한 릴스 리뷰어)", {"voice": "ko-KR-InJoonNeural", "rate": "+20%", "pitch": "+15Hz"}),
            ("✨ 릴스 귀여운 아기 톤 (앙증맞은 숏폼 톤)", {"voice": "ko-KR-SunHiNeural", "rate": "+10%", "pitch": "+40Hz"}),
            ("🎧 릴스 청년 유튜버 톤 (친근하고 밝은 톤)", {"voice": "ko-KR-HyunsuNeural", "rate": "+8%", "pitch": "+5Hz"}),
            ("👩‍💼 마케팅 여성 - 선희 (또렷하고 신뢰감 있는 톤)", {"voice": "ko-KR-SunHiNeural", "rate": "+0%", "pitch": "+0Hz"}),
            ("👨‍💼 마케팅 남성 - 인준 (지적이고 차분한 톤)", {"voice": "ko-KR-InJoonNeural", "rate": "+0%", "pitch": "+0Hz"})
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
    
    with st.expander("🎯 노리몰 영상팀 업무가이드 & KPI"):
        st.markdown("""
        * **핵심 행동 목표**: 일 유효 고객 **150명 유입** 달성
        * **전환율 목표 (CVR)**: **5%** (100명 중 5명 구매)
        * **프로 마케터 마인드셋**: "단순 영상 제작 X ➡️ 특정 키워드/후킹으로 유입 및 매출 증명"
        * **편집 원칙**: 15~30초 완독률, 2~3초 화면 컷 전환, 첫 3초 강력한 훅 헤드라인
        """)

# -------------------------------------------------------------------
# 메인 영역: 탭 구성 (1. 숏폼 제작 / 2. 네이버 클립 상위 레퍼런스 / 3. 완성 영상 검증)
# -------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs([
    "🎬 1. 숏폼 프로젝트 1초 자동 생성", 
    "🔥 2. 네이버 클립 6탭 상위 키워드 & 레퍼런스 1클릭 관찰",
    "✅ 3. 완성 영상 검증 & 네이버 클립 업로드 체크리스트"
])

with tab1:
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("📝 숏폼 대본 추출 및 편집")
        
        # 대본 생성 및 초기화 버튼들
        col_b1, col_b2 = st.columns([1.5, 1])
        with col_b1:
            if st.button("💡 선택한 포맷 대본 자동 생성 불러오기"):
                seo_title, script = generate_naver_clip_script(product_choice, keyword_input, format_type=format_choice)
                st.session_state["script_text"] = script
                st.session_state["seo_title"] = seo_title
                st.success(f"[{SCRIPT_FORMAT_NAMES[format_choice]}] 대본이 자동 생성되었습니다!")
        with col_b2:
            if st.button("🔄 대본 초기화 (새 프로젝트)"):
                if "script_text" in st.session_state:
                    del st.session_state["script_text"]
                if "seo_title" in st.session_state:
                    del st.session_state["seo_title"]
                st.rerun()

        script_input = st.text_area(
            "대본 내용 (문장별로 자연스럽게 읽어드립니다)",
            value=st.session_state.get("script_text", ""),
            placeholder="💡 좌측 [선택한 포맷 대본 자동 생성 불러오기] 버튼을 누르시거나, 원하시는 대본 텍스트를 직접 입력해 주세요...",
            height=240
        )

        col_fb1, col_fb2 = st.columns([2.5, 1])
        with col_fb1:
            user_feedback_in = st.text_input("💡 마케터 수정 피드백 (예: 부모님 선물 톤으로 변경해 줘, 30일 환불 강조해 줘 등):", key="in_script_fb", placeholder="예: 부모님 선물 톤으로 변경해 줘, 30일 환불 보증 문구 강조해 줘 등")
        with col_fb2:
            st.write("")
            st.write("")
            if st.button("✨ 마케터 피드백 반영 AI 대본 수정", key="btn_apply_script_fb"):
                if user_feedback_in.strip() and script_input.strip():
                    new_title, updated_script = apply_user_feedback_to_script(script_input, user_feedback_in, product_choice)
                    st.session_state["script_text"] = updated_script
                    st.session_state["seo_title"] = new_title
                    st.success("🎉 입력하신 마케터 피드백이 반영되어 대본이 실시간으로 수정되었습니다!")
                    st.rerun()
                else:
                    st.warning("수정 피드백 멘트와 대본 텍스트를 확인해 주세요.")
        
        # 선택한 제품의 옵시디언 상세페이지 리뷰/특징 프리뷰
        with st.expander(f"📌 [{product_choice}] 스마트스토어 상세페이지 특징 & 구매자 후기 보기"):
            store_url = selected_prod_info.get("smartstore_url", "")
            if store_url:
                st.markdown(f"🛒 **스마트스토어 공식 상세페이지**: [바로가기 링크]({store_url})")
            st.write(f"**USP (핵심 차별점)**: {selected_prod_info.get('usp', '없음')}")
            st.write(f"**타깃 페르소나**: {selected_prod_info.get('target', '없음')}")
            st.write("**구매 고객 실제 후기 파싱**: ")
            for r in selected_prod_info.get("reviews", []):
                st.markdown(f"- 💬 *\"{r}\"*")

    with col2:
        st.subheader("🎬 영상 소스 키워드 세팅")
        st.caption("필요한 분위기나 연출 장면 키워드를 영문(콤마 구분)으로 입력하면 고화질 HD 비디오 소스가 자동 수급됩니다.")
        
        default_stock_kw = ", ".join(selected_prod_info.get("stock_keywords", ["back pain", "massage"]))
        video_keywords_input = st.text_input(
            "영상 소스 키워드 (예: back pain, massage, stretching)",
            value=default_stock_kw
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

    # 메인 생성 실행 버튼
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
                        voice=voice_choice,
                        format_type=format_choice
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

with tab2:
    st.subheader(f"🔥 네이버 클립 6탭 이내 상위 노출 황금 키워드 ({len(NAVER_CLIP_TOP_KEYWORDS)}개 정밀 스캔 완료)")
    st.caption("제공해 주신 키워드 데이터 시트에서 네이버 검색 1~6탭 이내에 '네이버 클립'이 실제 노출 중인 황금 검색어들입니다.")
    
    st.warning("🕶️ **회사 계정 알고리즘 오염 방지 팁**: 링크를 누르실 때 **`마우스 우클릭 ➡️ 시크릿 창에서 링크 열기 (Incognito Window)`**로 접속하시면 개인/회사 계정에 검색 쿠키나 알고리즘이 남지 않아 가장 깨끗한 상태로 레퍼런스를 관찰하실 수 있습니다!")

    # -------------------------------------------------------------------
    # A. 실제 네이버 클립 영상 링크 URL 또는 자막 텍스트 직접 분석기 (신규)
    # -------------------------------------------------------------------
    with st.expander("🎯 실제 네이버 클립 영상 링크 URL 또는 자막 텍스트 AI 분석기 (클릭하여 직접 입력)", expanded=True):
        st.caption("네이버 모바일에서 관찰하신 실제 클립 영상의 [링크 URL]이나 [자막/대본 텍스트]를 여기에 입력해 주세요. AI가 즉시 [첫 3초 훅 / 결핍 / USP / CTA / 트위스트 대입법]을 정밀 분석하여 옵시디언 01~017번 표준 양식 카드로 작성해 드립니다.")
        
        col_in1, col_in2 = st.columns([3, 1])
        with col_in1:
            input_kw = st.text_input("타깃 카테고리/키워드 (예: 허리통증, 부모님선물 등):", value="", placeholder="분석할 키워드를 직접 입력하세요 (예: 허리통증, 부모님선물 등)", key="input_kw_custom")
            custom_input_text = st.text_area("네이버 클립 실제 영상 링크 URL 또는 자막 텍스트 입력:", 
                value="",
                placeholder="예: https://m.naver.com/shorts/... 또는 실제 영상 자막 텍스트를 입력해 주세요.",
                height=100, key="input_custom_text")
            chk_no_audio = st.checkbox("🔇 영상에 음성 나레이션 없음 (BGM 및 자막/시각 연출 중심 소재인 경우 체크)", value=False)
        with col_in2:
            st.write("")
            st.write("")
            st.write("")
            st.write("")
            if st.button("⚡ AI 마케팅 카드 생성", key="btn_custom_analyze"):
                if custom_input_text.strip():
                    import importlib
                    import clip_reference_scraper
                    importlib.reload(clip_reference_scraper)
                    analyzed_res = clip_reference_scraper.analyze_custom_clip_link_or_text(
                        custom_input_text, keyword=input_kw, no_narration=chk_no_audio
                    )
                    st.session_state["custom_clip_analysis_result"] = analyzed_res
                    st.success("✅ 실제 클립 AI 마케팅 분석이 완료되었습니다! (아래 표를 확인해 보세요)")
                else:
                    st.error("분석할 영상 링크나 자막 텍스트를 입력해 주세요.")

    # 직접 분석 결과 미리보기 (NoneType 및 키 오류 방어 보정)
    if "custom_clip_analysis_result" in st.session_state and isinstance(st.session_state["custom_clip_analysis_result"], dict):
        c_res = st.session_state["custom_clip_analysis_result"]
        kw_display = c_res.get("keyword", c_res.get("auto_keyword", "네이버클립"))
        
        with st.container():
            st.markdown(f"""
            <div style='background-color: #1E2640; padding: 15px; border-radius: 12px; margin: 15px 0; border: 1px solid #10B981;'>
                <h3 style='color: #34D399; margin-top:0;'>🧠 [{kw_display}] 실제 클립 AI 마케팅 분석 결과</h3>
            </div>
            """, unsafe_allow_html=True)
            
            c_close, _ = st.columns([1, 4])
            with c_close:
                if st.button("❌ 분석창 접기", key="close_custom_analysis"):
                    del st.session_state["custom_clip_analysis_result"]
                    st.rerun()

            if "script_table" in c_res:
                st.markdown("#### 📜 4단계 대본 및 화면 분석 표")
                st.table(c_res["script_table"])

            if "marketer_notes" in c_res:
                st.markdown("#### 💡 마케터 복기 & 소구점 (자사 제품 트위스트 팁)")
                for note in c_res["marketer_notes"]:
                    st.markdown(f"* 💡 {note}")

                st.markdown("---")
                if st.button("💾 이 레퍼런스 카드를 옵시디언 04_광고 소재 DB에 저장하기 (양식 100% 일치)", key="save_custom_to_obsidian"):
                    import clip_reference_scraper
                    saved_path = clip_reference_scraper.save_reference_to_obsidian(c_res)
                    st.balloons()
                    st.success(f"🎉 기존 01~017번 표준 양식과 100% 동일한 양식으로 파일이 저장되었습니다!\n\n📄 **저장 경로**: `{saved_path}`")

    st.markdown("---")

    # -------------------------------------------------------------------
    # B. 황금 키워드 목록 및 실시간 탐색 영역
    # -------------------------------------------------------------------
    kw_filter = st.text_input("🔍 황금 키워드 검색 (예: 허리, 선물, 디스크 등):", "")

    filtered_keywords = [
        item for item in NAVER_CLIP_TOP_KEYWORDS
        if not kw_filter or kw_filter.strip().lower() in item["keyword"].lower()
    ]

    st.markdown(f"**총 `{len(filtered_keywords)}개` 키워드 검색됨**")
    st.markdown("---")

    # 6탭 이내 키워드 표 및 스크랩 렌더링
    for item in filtered_keywords:
        kw = item["keyword"]
        vol = item["volume"]
        rank = item["clip_tab_rank"]
        
        encoded_kw = urllib.parse.quote(kw)
        naver_pc_url = f"https://search.naver.com/search.naver?query={encoded_kw}"
        naver_mobile_url = f"https://m.search.naver.com/search.naver?query={encoded_kw}"

        # 1. 키워드 행 헤더 (PC/모바일 시크릿 모드 검색 링크 중심)
        c1, c2, c3, c4 = st.columns([3, 2, 2, 4])
        with c1:
            st.markdown(f"#### 🔍 **{kw}**")
        with c2:
            st.markdown(f"월 검색량: **`{vol}회`**")
        with c3:
            st.markdown(f"클립 탭 순위: **`상위 {rank}탭`**")
        with c4:
            st.markdown(f"[🖥️ PC 네이버 검색]({naver_pc_url}) &nbsp;|&nbsp; [📱 모바일 네이버 검색]({naver_mobile_url})", unsafe_allow_html=True)

        st.markdown("<hr style='margin: 0.5rem 0; border-color: #2D3748;'>", unsafe_allow_html=True)

# -------------------------------------------------------------------
# 3번 탭: 완성 영상/대본 AI 분석 & 네이버 클립 SEO 진단기 (고도화)
# -------------------------------------------------------------------
with tab3:
    st.subheader("🚀 완성 영상 & 제작 대본 AI 실시간 분석 & 네이버 클립 SEO 진단기")
    st.caption("제작 완료된 MP4 동영상 파일을 직접 업로드하시거나 대본 텍스트를 입력하시면, AI가 [100% 음성 대본 추출 / 옵시디언 4컬럼 구조분해 / 마케터 복기 소구점 / SEO 복붙 템플릿]을 자동으로 완성해 드립니다.")
    
    analysis_mode = st.radio(
        "분석 방식을 선택하세요:",
        options=[
            "📹 [모드 1] MP4 동영상 파일 직접 업로드 (AI 음성STT 100% 추출 & 시각 검수)",
            "📝 [모드 2] 제작 대본 텍스트 직접 입력 (사전 카피라이팅 검증)"
        ],
        horizontal=True
    )
    
    st.markdown("---")

    # -------------------------------------------------------------------
    # 모드 1: MP4 동영상 파일 직접 업로드 (Whisper AI 100% 실시간 음성 추출)
    # -------------------------------------------------------------------
    if "모드 1" in analysis_mode:
        col_v1, col_v2 = st.columns([1.2, 1.8])
        
        with col_v1:
            st.markdown("### 1️⃣ MP4 동영상 파일 업로드 & 시각 검수")
            uploaded_video = st.file_uploader("분석할 숏폼 MP4 동영상 파일 선택:", type=["mp4", "mov", "avi"], key="v_file_uploader")
            target_prod_v = st.selectbox("분석 대상 제품 선택:", options=["다피다 허리 찜질기", "파우리나 전동재활자전거"], key="v_target_prod")
            
            if uploaded_video is not None:
                st.video(uploaded_video)
                st.success(f"🎥 영상 로드 완료: `{uploaded_video.name}` ({round(uploaded_video.size / (1024*1024), 2)} MB)")
                
                if st.button("⚡ MP4 영상 AI 음성 대본 추출 & SEO 진단", key="btn_run_v_analysis"):
                    with st.spinner("Whisper AI가 영상 속 실제 오디오를 100% 음성 인식(STT)하여 대본을 직접 추출하고 있습니다..."):
                        import importlib
                        import clip_reference_scraper
                        importlib.reload(clip_reference_scraper)
                        
                        v_bytes = uploaded_video.read()
                        res_v = clip_reference_scraper.analyze_real_uploaded_video_file(v_bytes, target_prod_v)
                        st.session_state["v_analysis_result"] = res_v
                        st.success("✅ 실제 음성 대본 100% 추출 및 마케팅 분석이 완료되었습니다!")
            else:
                st.info("💡 검수할 mp4 동영상 파일을 드래그하여 올려주세요.")

        with col_v2:
            st.markdown("### 2️⃣ 🤖 AI 마케터 빡센 자동 심사 결과표 (칼같은 검수)")
            st.caption("※ AI가 대본/영상 오디오를 파싱하여 5대 핵심 마케팅 지표를 빡세게 직접 심사합니다.")
            
            if "v_analysis_result" in st.session_state and "ai_audit" in st.session_state["v_analysis_result"]:
                audit_data = st.session_state["v_analysis_result"]["ai_audit"]
                score = audit_data["score"]
                st.markdown(f"### 📊 AI 마케터 종합 평가 점수: **`{score}점 / 100점`**")
                st.markdown(audit_data["verdict"])
                
                st.markdown("#### 🔍 5대 마케팅 품질 세부 심사 결과:")
                st.table(audit_data["audits"])
            else:
                st.info("👈 왼쪽에서 MP4 영상을 올리고 [⚡ MP4 영상 AI 음성 대본 추출 & SEO 진단] 버튼을 누르시면 AI 마케터의 빡센 정밀 채점표가 도출됩니다.")

        # 결과 미리보기 (모드 1)
        if "v_analysis_result" in st.session_state:
            v_res = st.session_state["v_analysis_result"]
            st.markdown("---")
            
            st.markdown("### 🎙️ 100% Whisper AI가 실제 영상에서 직접 추출한 음성 대본")
            st.info(f"\"{v_res['user_script']}\"")

            st.markdown("### 🎬 옵시디언 표준 4컬럼 대본 구조분해 분석")
            if "script_table" in v_res:
                st.table(v_res["script_table"])

            st.markdown("### 💡 마케터 복기 & 소구점 (자사 제품 트위스트 팁)")
            if "marketer_notes" in v_res:
                for note in v_res["marketer_notes"]:
                    st.markdown(f"* {note}")

            st.markdown("---")
            st.markdown("### 3️⃣ 네이버 클립 업로드용 SEO 복붙 템플릿")
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                st.text_input(f"📌 업로드 추천 제목 (네이버 24자 제한 준수: {len(v_res['seo_title'])}자):", value=v_res["seo_title"], key="vt_title")
                st.text_area(f"📝 업로드 본문 설명 (네이버 200자 제한 준수: {len(v_res['seo_desc'])}자):", value=v_res["seo_desc"], height=140, key="vt_desc")
            with col_t2:
                st.text_input("🔍 자동 타게팅 황금 키워드:", value=v_res["auto_keyword"], key="vt_kw")
                st.text_area("🏷️ SEO 상위 노출 해시태그 (최대 10개 제한 준수):", value=v_res["seo_tags"], height=80, key="vt_tags")
                st.text_input("🔗 연동 스마트스토어 상품 스티커 URL:", value=v_res["store_link"], key="vt_store")

    # -------------------------------------------------------------------
    # 모드 2: 제작 대본 텍스트 직접 입력 사전 검증
    # -------------------------------------------------------------------
    else:
        col_s1, col_s2 = st.columns([1.2, 1.8])
        
        with col_s1:
            st.markdown("### 1️⃣ 대상 제품 선택 & 대본 텍스트 입력")
            target_prod_s = st.selectbox("분석 대상 제품 선택:", options=["다피다 허리 찜질기", "파우리나 전동재활자전거"], key="s_target_prod")
            
            user_script_input = st.text_area(
                "📝 제작하신 숏폼 영상의 실제 대본(또는 자막 텍스트) 입력:",
                value="",
                placeholder="제작하신 숏폼 영상의 실제 대본 또는 자막 텍스트를 이곳에 직접 입력해 주세요...",
                height=160,
                key="s_text_area"
            )
            
            col_btn1, col_btn2 = st.columns([2, 1])
            with col_btn1:
                btn_run = st.button("⚡ 대본 AI 구조분해 & SEO 템플릿 생성", key="btn_run_s_analysis")
            with col_btn2:
                if st.button("🔄 새로 작성하기 (초기화)", key="btn_reset_s"):
                    if "user_script_seo_res" in st.session_state:
                        del st.session_state["user_script_seo_res"]
                    st.rerun()

            if btn_run:
                if user_script_input.strip():
                    import importlib
                    import clip_reference_scraper
                    importlib.reload(clip_reference_scraper)
                    
                    seo_res = clip_reference_scraper.generate_seo_and_marketing_from_user_script(user_script_input, target_prod_s)
                    st.session_state["user_script_seo_res"] = seo_res
                    st.success("✅ 대본 AI 분석 및 SEO 템플릿 생성이 완료되었습니다!")
                else:
                    st.error("분석할 영상 대본 텍스트를 입력해 주세요.")

        with col_s2:
            st.markdown("### 2️⃣ 🤖 AI 마케터 빡센 자동 심사 결과표 (칼같은 검수)")
            st.caption("※ AI가 입력된 대본을 파싱하여 5대 핵심 마케팅 지표를 빡세게 직접 심사합니다.")
            
            if "user_script_seo_res" in st.session_state and "ai_audit" in st.session_state["user_script_seo_res"]:
                audit_data_s = st.session_state["user_script_seo_res"]["ai_audit"]
                score_s = audit_data_s["score"]
                st.markdown(f"### 📊 AI 마케터 종합 평가 점수: **`{score_s}점 / 100점`**")
                st.markdown(audit_data_s["verdict"])
                
                st.markdown("#### 🔍 5대 마케팅 품질 세부 심사 결과:")
                st.table(audit_data_s["audits"])
            else:
                st.info("👈 왼쪽에서 대본 텍스트를 입력하고 [⚡ 대본 AI 구조분해 & SEO 템플릿 생성] 버튼을 누르시면 AI 마케터의 빡센 정밀 채점표가 도출됩니다.")

        # 결과 미리보기 (모드 2)
        if "user_script_seo_res" in st.session_state:
            s_res = st.session_state["user_script_seo_res"]
            st.markdown("---")
            
            st.markdown("### 🎬 옵시디언 표준 4컬럼 대본 구조분해 분석")
            if "script_table" in s_res:
                st.table(s_res["script_table"])

            st.markdown("### 💡 마케터 복기 & 소구점 (자사 제품 트위스트 팁)")
            if "marketer_notes" in s_res:
                for note in s_res["marketer_notes"]:
                    st.markdown(f"* {note}")

            st.markdown("---")
            st.markdown("### 3️⃣ 네이버 클립 업로드용 SEO 복붙 템플릿")
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                st.text_input(f"📌 업로드 추천 제목 (네이버 24자 제한 준수: {len(s_res['seo_title'])}자):", value=s_res["seo_title"], key="st_title")
                st.text_area(f"📝 업로드 본문 설명 (네이버 200자 제한 준수: {len(s_res['seo_desc'])}자):", value=s_res["seo_desc"], height=140, key="st_desc")
            with col_t2:
                st.text_input("🔍 자동 타게팅 황금 키워드:", value=s_res["auto_keyword"], key="st_kw")
                st.text_area("🏷️ SEO 상위 노출 해시태그 (최대 10개 제한 준수):", value=s_res["seo_tags"], height=80, key="st_tags")
                st.text_input("🔗 연동 스마트스토어 상품 스티커 URL:", value=s_res["store_link"], key="st_store")

            st.markdown("---")
            st.markdown("### 🧠 Creative Memory Engine (AdForge 시그니처 차별화 파이프라인)")
            if "memory_insights" in s_res:
                mem = s_res["memory_insights"]
                st.info(f"💡 **Creative Memory 축적 현황**: 현재 총 `{mem['total_remembered_logs']}건`의 성과 로그 및 고효율 훅/CTA 조합이 AI 기억 엔진에 아카이빙되어 생성 가중치에 동적 반영 중입니다.")
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    st.markdown("#### 🏆 성과 우수 기억 훅 (Top Memory Hooks):")
                    for h_item in mem["top_hooks"][:3]:
                        st.markdown(f"* `{h_item['hook']}` *(CTR 평균 {h_item['ctr_avg']})*")
                with col_m2:
                    st.markdown("#### 🎯 성과 우수 기억 CTA (Top Memory CTAs):")
                    for c_item in mem["top_ctas"][:2]:
                        st.markdown(f"* `{c_item['cta']}` *(CVR 평균 {c_item['cvr_avg']})*")

    st.markdown("---")
    st.markdown("### 📌 네이버 클립 스마트스토어 상품 스티커 10초 등록 방법 (PC & 모바일)")
    
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        st.markdown("""
        #### 💻 PC (네이버 블로그/클립 글쓰기) 100% 접속 경로:
        1. PC에서 **[내 네이버 블로그 접속(MyBlog)](https://blog.naver.com/MyBlog.naver)** 클릭 ➡️ 프로필 아래 **`[글쓰기]`** 클릭!
        2. 동영상(.mp4) 업로드 후 오른쪽 상단 **`[발행]`** 버튼 ➡️ **`[클립으로 발행]`** 체크!
        3. 동영상 업로드 창 또는 에디터 도구함의 **`[🏷️ 스티커]` ➡️ `[쇼핑 스티커]`** 선택 후 스마트스토어 URL 붙여넣기(Ctrl+V)
        """)
    with col_g2:
        st.markdown("""
        #### 📱 모바일 (네이버 앱):
        1. 네이버 앱 하단 **`[+]`** 버튼 ➡️ **`[클립 만들기]`** 터치
        2. 동영상 선택 후 상단 툴바의 **`[🏷️ 스티커]`** 아이콘 터치
        3. **`[쇼핑 스티커]`** 선택 후 스마트스토어 상품 URL 붙여넣기
        4. 상품 정보가 나타나면 **[등록]** 누르고 완료!
        """)

    st.markdown("🚀 **[네이버 블로그 PC 글쓰기 바로가기](https://blog.naver.com)** 로 이동하여 10초 만에 상위 노출 클립 발행을 완료하세요!")
