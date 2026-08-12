import os
import re
import uuid
import webbrowser
import pandas as pd
import streamlit as st
import PyPDF2
from naver_clip_adforge import (
    build_capcut_project_for_naver_clip,
    generate_hailuo_prompts_stream,
    generate_image_prompts_stream,
    generate_strategic_script_stream,
    generate_cta_from_script_stream
)

# ─── DB 초기화 ───────────────────────────────────────────────
from db.adforge_db import (
    init_db,
    upsert_project, get_all_projects, get_project_by_name,
    insert_reference, get_references, delete_reference, update_reference_memo,
    insert_content, get_contents,
    insert_scenes, get_scenes, update_scene,
)
from models.project import Project
from models.reference import Reference

init_db()

# 몸편한하루 기본 프로젝트 자동 생성
_default_proj = get_project_by_name("몸편한하루")
if not _default_proj:
    upsert_project(Project.default_mombyon().to_dict())

# -------------------------------------------------------------------
# Streamlit 대시보드 페이지 설정
# -------------------------------------------------------------------
st.set_page_config(page_title="AdForge V2 - 숏폼 콘텐츠 제작 플랫폼", page_icon="🎬", layout="wide")

st.markdown('''
<style>
    .main-header { font-size: 2.2rem; font-weight: 800; color: #00E676; margin-bottom: 0.2rem; }
    .sub-header { font-size: 1.05rem; color: #A0AEC0; margin-bottom: 1.5rem; }
    .prompt-box { background-color: #F0F4F8; color: #1A202C; padding: 1rem; border-radius: 8px; margin-bottom: 1rem; font-family: monospace; white-space: pre-wrap; border: 1px solid #CBD5E0; }
    .comment-box { background-color: #2b1f31; padding: 1rem; border-radius: 8px; margin-bottom: 1rem; border-left: 4px solid #d53f8c; }
    .scene-card { background: #1a1f2e; border: 1px solid #2d3748; border-radius: 10px; padding: 1rem; margin-bottom: 0.75rem; }
    .scene-stock { border-left: 4px solid #00E676; }
    .scene-ai { border-left: 4px solid #F6AD55; }
    .ref-card { background: #1a1f2e; border: 1px solid #2d3748; border-radius: 10px; padding: 1rem; margin-bottom: 0.75rem; }
    .badge-stock { background: #00E676; color: #000; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 700; }
    .badge-ai { background: #F6AD55; color: #000; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 700; }
    .dash-card { background: #1a1f2e; border: 1px solid #2d3748; border-radius: 10px; padding: 1rem; margin-bottom: 0.6rem; }
    .status-draft { border-left: 4px solid #718096; }
    .status-scene { border-left: 4px solid #63B3ED; }
    .status-stock { border-left: 4px solid #68D391; }
    .status-ai { border-left: 4px solid #F6AD55; }
    .status-done { border-left: 4px solid #00E676; }
    .tts-scene-row { background: #1a1f2e; border: 1px solid #2d3748; border-radius: 8px; padding: 0.6rem 1rem; margin-bottom: 0.4rem; font-size: 0.9rem; }
    .kpi-box { background: linear-gradient(135deg, #1a1f2e 0%, #2d3748 100%); border: 1px solid #4A5568; border-radius: 12px; padding: 1.2rem; text-align: center; }
</style>
''', unsafe_allow_html=True)

st.markdown('<div class="main-header">🚀 AdForge V2 :: 숏폼 콘텐츠 제작 플랫폼</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">대본 기획 → Scene 분할 → Stock 검색 → Hailuo → TTS → CapCut 자동화</div>', unsafe_allow_html=True)

# -------------------------------------------------------------------
# 전역 설정 및 API 키 캐싱
# -------------------------------------------------------------------
API_KEY_FILE = "nv_api_key.txt"
cached_api_key = os.environ.get("NVIDIA_API_KEY", "")
if os.path.exists(API_KEY_FILE):
    with open(API_KEY_FILE, "r", encoding="utf-8-sig") as f:
        cached_api_key = f.read().strip()

PEXELS_API_KEY_FILE = "pexels_api_key.txt"
cached_pexels_api_key = ""
if os.path.exists(PEXELS_API_KEY_FILE):
    with open(PEXELS_API_KEY_FILE, "r", encoding="utf-8-sig") as f:
        cached_pexels_api_key = f.read().strip()

PIXABAY_API_KEY_FILE = "pixabay_api_key.txt"
cached_pixabay_api_key = ""
if os.path.exists(PIXABAY_API_KEY_FILE):
    with open(PIXABAY_API_KEY_FILE, "r", encoding="utf-8-sig") as f:
        cached_pixabay_api_key = f.read().strip()

# ─── API 키 입력 (상단 공통 영역) ───────────────────────────
with st.expander("🔑 API 키 설정", expanded=False):
    col_key, col_pexels, col_pixabay, col_model = st.columns([2, 2, 2, 2])
    with col_key:
        nvidia_api_key = st.text_input("🔑 NVIDIA API Key", type="password", value=cached_api_key, placeholder="nvapi-...")
        if nvidia_api_key and nvidia_api_key != cached_api_key:
            with open(API_KEY_FILE, "w", encoding="utf-8") as f:
                f.write(nvidia_api_key)
    with col_pexels:
        pexels_api_key = st.text_input("📷 Pexels API Key", type="password", value=cached_pexels_api_key, placeholder="없으면 Pixabay만 사용")
        if pexels_api_key and pexels_api_key != cached_pexels_api_key:
            with open(PEXELS_API_KEY_FILE, "w", encoding="utf-8") as f:
                f.write(pexels_api_key)
    with col_pixabay:
        pixabay_api_key = st.text_input("🖼️ Pixabay API Key", type="password", value=cached_pixabay_api_key, placeholder="pixabay.com에서 무료 발급")
        if pixabay_api_key and pixabay_api_key != cached_pixabay_api_key:
            with open(PIXABAY_API_KEY_FILE, "w", encoding="utf-8") as f:
                f.write(pixabay_api_key)
    with col_model:
        model_choice = st.selectbox(
            "🧠 NVIDIA 모델",
            options=[
                "mistralai/mistral-nemotron",
                "meta/llama-3.1-70b-instruct",
                "meta/llama-3.1-8b-instruct",
            ]
        )

# ─── Project 선택 ────────────────────────────────────────────
all_projects_raw = get_all_projects()
project_names = [p["project_name"] for p in all_projects_raw]
project_map = {p["project_name"]: p for p in all_projects_raw}

col_proj, col_proj_info = st.columns([3, 7])
with col_proj:
    selected_project_name = st.selectbox("📁 프로젝트 선택", project_names, index=0)
current_project_data = project_map.get(selected_project_name, {})
with col_proj_info:
    if current_project_data:
        st.caption(
            f"🎯 타겟: {current_project_data.get('target_audience', '')} | "
            f"📺 플랫폼: {current_project_data.get('platform', '')} | "
            f"📐 비율: {current_project_data.get('default_video_ratio', '')} | "
            f"🎯 일일 목표: {current_project_data.get('daily_target', 10)}편"
        )

st.markdown("---")

# ===================================================================
# 메인 탭 구조
# ===================================================================
tab_script, tab_step2, tab_ref, tab_scene, tab_stock, tab_ai_video, tab_tts, tab_dashboard = st.tabs([
    "🎯 대본 기획",
    "✏️ 대본 편집 & CapCut",
    "📚 Reference Library",
    "🎬 Scene Planner",
    "📦 Stock & Asset",
    "🤖 AI Video (Hailuo)",
    "🔊 TTS & Hook",
    "🚀 Production Dashboard",
])

# ===================================================================
# TAB 1: 대본 기획 (기존 STEP 1 — 완전 유지)
# ===================================================================
with tab_script:
    # -------------------------------------------------------------------
    # 구글 시트 연동 (키워드 추천)
    # -------------------------------------------------------------------

    @st.cache_data(ttl=3600)
    def load_keyword_data():
        sheet_url = "https://docs.google.com/spreadsheets/d/1-xfToD-ns9nBwj7Eh0URGOKc_YWcxxt5a3vJXgRqz9Q/export?format=csv"
        try:
            df = pd.read_csv(sheet_url)
            df.columns = df.columns.str.replace(r'\n', ' ', regex=True).str.strip()

            if '키워드' in df.columns:
                df = df.dropna(subset=['키워드'])
                if len(df) > 0 and df.iloc[0]['키워드'] == '고유번호':
                    df = df.iloc[1:]

            tab_cols = ['1탭', '2탭', '3탭', '4탭', '5탭', '6탭']
            mask = pd.Series([False] * len(df), index=df.index)
            for col in tab_cols:
                if col in df.columns:
                    mask = mask | df[col].astype(str).str.contains('네이버 클립', na=False)
            df = df[mask]

            display_cols = []
            target_cols = ['키워드', '전체  검색량', 'MB  검색량', '블로그  글개수', '1탭', '2탭', '3탭', '4탭', '5탭', '6탭']
            for c in target_cols:
                if c in df.columns:
                    display_cols.append(c)
                elif c.replace('  ', ' ') in df.columns:
                    display_cols.append(c.replace('  ', ' '))

            return df[display_cols] if display_cols else df
        except Exception as e:
            st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")
            return None

    col_sheet_title, col_sheet_btn = st.columns([8, 2])
    with col_sheet_title:
        st.subheader("📊 타겟 키워드 분석 데이터 (Google Sheet 연동)")
    with col_sheet_btn:
        if st.button("🔄 데이터 최신화", use_container_width=True):
            load_keyword_data.clear()
            st.rerun()

    df_keywords = load_keyword_data()

    selected_keyword = ""
    if df_keywords is not None and not df_keywords.empty:
        st.markdown("아래 표에서 키워드를 선택하면 **'세부 주제'**에 자동으로 입력됩니다.")

        def highlight_clip(val):
            if '네이버 클립' in str(val):
                return 'background-color: #00C73C; color: white; font-weight: bold;'
            return ''

        tab_cols_kw = [c for c in df_keywords.columns if '탭' in c]
        styled_df = df_keywords.style.map(highlight_clip, subset=tab_cols_kw)

        col_table, col_side = st.columns([4, 1])

        with col_table:
            event = st.dataframe(
                styled_df,
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row"
            )

        with col_side:
            st.markdown("### 🔍 모바일 검색")
            search_kw = st.text_input("🔍 검색어 필터", key="mobile_search_filter")
            st.caption("아래 링크를 우클릭해서 시크릿 창으로 엽니다.")
            with st.container(height=400):
                for _, row in df_keywords.iterrows():
                    kw = row['키워드']
                    if search_kw and search_kw.lower() not in str(kw).lower():
                        continue
                    url = f"https://m.search.naver.com/search.naver?query={kw}"
                    st.markdown(f"👉 **[{kw}]({url})**")

        if len(event.selection.rows) > 0:
            selected_idx = event.selection.rows[0]
            selected_keyword = df_keywords.iloc[selected_idx]['키워드']

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
        sub_topic = st.text_input("✏️ 세부 주제", value=selected_keyword, placeholder="예) 일상 속 허리를 보호하는 법")

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

    st.markdown("##### 🧪 콘텐츠 실험 변수 (A/B 테스트)")
    col_hook, col_visual, col_expert = st.columns([2, 2, 1])
    with col_hook:
        hook_type = st.selectbox(
            "🪝 Hook 유형 (Verbal)",
            ["DESIRE (욕망형) - 이런 몸 만들고 싶다면?",
             "PROBLEM (문제형) - 이럴 때 여기부터 잡는다면?",
             "WARNING (금지형) - 이 운동 당장 멈추세요!",
             "CONTRARIAN (반전형) - 매일 걷는데 약해지는 이유?",
             "COMPARISON (비교형) - 왜 몸이 이렇게 다를까요?",
             "RESULT (결과형) - 1분으로 이런 움직임을!"]
        )
        hook_type_val = hook_type.split(" ")[0]

    with col_visual:
        visual_hook = st.selectbox(
            "👀 Visual Hook (시각적 자극)",
            ["BODY (워너비 몸매/탄탄한 하체)",
             "MOVEMENT (유연한/완벽한 동작)",
             "BEFORE_AFTER (비포/애프터)",
             "PROBLEM_SITUATION (문제/통증 묘사)",
             "EXPERT (전문가 등장/진찰)",
             "EXERCISE_RESULT (운동 직후 땀/결과)"]
        )
        visual_hook_val = visual_hook.split(" ")[0]

    with col_expert:
        st.write("👨‍⚕️ 전문가 검증")
        expert_present = st.checkbox("전문의/트레이너 인용 문장 포함", value=True)

    with st.expander("⚙️ 고급 대본 기획 설정 (프롬프트 & 벤치마킹)", expanded=False):
        st.markdown("AI에게 역할을 부여하는 프롬프트와, 따라 하고 싶은 대박 숏폼 대본(벤치마킹)을 직접 입력하여 생성 퀄리티를 비약적으로 높여보세요.")

        if "포맷 A" in video_format:
            default_system_prompt = """당신은 100만 바이럴을 만드는 숏폼 건강 정보 크리에이터입니다.
[포맷 A: 순수 정보형] — 제품명은 절대 언급하지 마세요. 오직 유익한 건강 꿀팁만 제공합니다.

핵심 규칙 (1M Viral & Twist Formula):
1. 미드롤 CTA: 비법을 공개하기 직전에 \"좋아요 먼저 누르고 따라하세요!\"를 삽입하세요.
2. 구체적 넘버링: \"1단계\", \"2단계\" 형식으로 따라하기 쉽게 분해하세요.
3. 강력한 효과 시각화: \"시원합니다\" 대신 \"혈류가 심장으로 솟구치고\" 등 감각적으로 묘사하세요.
4. 지정 댓글 유도: \"좋아요 부탁드려요\" 금지. \"댓글에 '시원해요'라고 남겨주세요\"처럼 구체적 키워드를 제시하세요."""
        elif "포맷 B" in video_format:
            default_system_prompt = """당신은 100만 바이럴을 만드는 숏폼 마케터이자 일반인 크리에이터입니다.
[포맷 B: 간접 홍보형] — 영상의 80%는 순수 꿀팁, 마지막 20%에서 \"제가 쓰는 기구는 댓글에 남길게요!\"라고 자연스럽게 유도합니다. 영상 안에서 제품명은 절대 말하지 마세요.

핵심 규칙 (1M Viral & Twist Formula):
1. 미드롤 CTA: 꿀팁 공개 직전 \"좋아요 먼저 누르고 따라하세요!\" 삽입.
2. 매몰비용 자극: \"안 그래도 돈 쓴 것도 억울한데\" 등으로 공감 극대화.
3. 간접 제품 유도: 꿀팁 제공 후 \"그냥 손으로 하긴 힘들어서 저는 기구 하나 쓰는데, 댓글에 올릴게요!\"처럼 자연스럽게 연결.
4. 지정 댓글 유도: \"댓글에 '기구 궁금'라고 남겨주세요!\"처럼 제품 수요를 댓글로 모으세요."""
        else:
            default_system_prompt = """당신은 100만 바이럴을 만드는 제품 리뷰어이자 숏폼 마케터입니다.
[포맷 C: 직접 홍보형] — 제품명을 당당하게 언급하며 대안재(비싼 안마의자, 비싼 도수치료 등)와 비교하여 압도적인 가성비를 어필합니다.

핵심 규칙 (1M Viral & Twist Formula):
1. 대안재 비교: \"거대하고 비싼 안마의자 대신\", \"도수치료비 쏟아붓다가\" 등으로 기존 대체재의 단점을 먼저 부각시키세요.
2. 미드롤 CTA: 제품 공개 직전 \"좋아요 먼저 누르세요!\" 삽입.
3. 매몰비용 자극 + 가성비 앵커링: \"올해 또 예쁜 쓰레기 사실 건가요?\" → \"월 만원대로 평생 뽕뽑는다\"처럼 손실 회피와 가성비를 동시에 찌르세요.
4. 지정 댓글 + 한정성 마감: \"댓글에 '할인 링크'라고 남겨주세요!\"처럼 구매 의향자를 댓글로 집결시키세요."""

        custom_system_prompt = st.text_area("🔧 시스템 프롬프트 (포맷별 자동 변경)", value=default_system_prompt, height=250)
        benchmark_script = st.text_area("📈 벤치마킹 대본 (참고할 타사 대박 숏폼 대본 원문)", value="", placeholder="예: 이거 모르면 평생 후회합니다! 매일 아침 얼굴 붓기 1분만에 빼는 비법...", height=150)

        st.markdown("---")
        st.markdown("##### 📄 전문성 더하기 (NotebookLM 스타일)")
        uploaded_file = st.file_uploader("운동 관련 논문, 전문 칼럼 등 PDF/TXT/MD 파일을 업로드하면 AI가 분석하여 전문성을 갖춘 대본을 작성합니다.", type=["pdf", "txt", "md"])
        reference_document = ""
        if uploaded_file is not None:
            try:
                if uploaded_file.name.lower().endswith('.pdf'):
                    pdf_reader = PyPDF2.PdfReader(uploaded_file)
                    for page in pdf_reader.pages:
                        text = page.extract_text()
                        if text:
                            reference_document += text + "\n"
                else:
                    reference_document = uploaded_file.getvalue().decode("utf-8")
                st.success("✅ 전문 자료 분석 완료! 팩트와 인사이트가 대본에 반영됩니다.")
            except Exception as e:
                st.error(f"파일 분석 중 오류가 발생했습니다: {str(e)}")

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
                        topic_category,
                        sub_topic,
                        video_format,
                        product_name,
                        nvidia_api_key,
                        model_choice,
                        custom_system_prompt,
                        benchmark_script,
                        reference_document,
                        hook_type_val,
                        visual_hook_val,
                        expert_present
                    ):
                        yield chunk

                raw_output = st.write_stream(script_stream_generator())
                st.session_state["raw_script_output"] = raw_output

                visual_part = ""
                script_part = raw_output
                comment_part = ""
                dm_part = ""
                desc_part = ""

                pattern = r'={2,}\s*(VISUAL_HOOK|SCRIPT|COMMENT|DM[_\s]*MESSAGE|DESCRIPTION)\s*={2,}'
                matches = list(re.finditer(pattern, raw_output, re.IGNORECASE))

                if matches:
                    sections = {}
                    for i, match in enumerate(matches):
                        key = match.group(1).upper().replace(" ", "_")
                        if key.startswith("DM"):
                            key = "DM_MESSAGE"
                        elif key.startswith("VISUAL"):
                            key = "VISUAL_HOOK"

                        start_idx = match.end()
                        end_idx = matches[i+1].start() if i + 1 < len(matches) else len(raw_output)
                        sections[key] = raw_output[start_idx:end_idx].strip()

                    visual_part = sections.get("VISUAL_HOOK", "")
                    script_part = sections.get("SCRIPT", "")
                    comment_part = sections.get("COMMENT", "")
                    dm_part = sections.get("DM_MESSAGE", "")
                    desc_part = sections.get("DESCRIPTION", "")

                script_part = re.sub(r'([.?!])\s+', r'\1\n', script_part)

                st.session_state["parsed_visual"] = visual_part
                st.session_state["parsed_script"] = script_part
                st.session_state["parsed_comment"] = comment_part
                st.session_state["parsed_dm"] = dm_part
                st.session_state["parsed_description"] = desc_part

                try:
                    from performance_logger import log_performance
                    log_performance({
                        "content_id": "temp_" + pd.Timestamp.now().strftime("%Y%m%d%H%M%S"),
                        "topic": topic_category,
                        "hook_type": hook_type_val,
                        "visual_hook": visual_hook_val,
                        "expert_present": expert_present,
                        "title": sub_topic,
                        "duration": 45,
                        "upload_datetime": pd.Timestamp.now().isoformat()
                    })
                except Exception:
                    pass

                st.success("✨ 대본 기획이 완료되었습니다!")

    st.markdown("---")
    st.subheader("📝 기획된 대본 결과")

    visual_output = st.session_state.get("parsed_visual", "")
    if visual_output:
        st.info(f"**👀 추천 Visual Hook 영상 (첫 3초):** {visual_output}")

    col_out1, col_out2, col_out3 = st.columns(3)
    with col_out1:
        st.markdown("##### 💬 유튜브/클립용 고정 댓글")
        c_val = st.session_state.get("parsed_comment", "")
        st.text_area("댓글 복사", value=c_val, height=150, label_visibility="collapsed")
    with col_out2:
        st.markdown("##### 💌 발송용 DM 메세지")
        dm_val = st.session_state.get("parsed_dm", "")
        st.text_area("DM 복사", value=dm_val, height=150, label_visibility="collapsed")
    with col_out3:
        st.markdown("##### 📝 영상 본문 설명 & 해시태그")
        d_val = st.session_state.get("parsed_description", "")
        st.text_area("설명 복사", value=d_val, height=150, label_visibility="collapsed")


# ===================================================================
# TAB 2: 대본 편집 & CapCut (기존 STEP 2 — 완전 유지)
# ===================================================================
with tab_step2:
    st.subheader("STEP 2: 캡컷 연동 & Hailuo 프롬프트 추출")

    default_script = st.session_state.get("parsed_script", "")
    script_text = st.text_area("📝 영상 자막(대본) 전문 (STEP 1에서 생성 시 자동 입력됨 / 직접 붙여넣기 가능)", value=default_script, height=200)

    def auto_format_subtitle(text: str, max_chars: int = 8) -> str:
        """한국어 자막 텍스트를 6~8자 단위로 자동 줄바꿈"""
        paragraphs = re.split(r'\n{2,}', text.strip())
        result_lines = []

        for para in paragraphs:
            flat = re.sub(r'\n', ' ', para).strip()
            flat = re.sub(r' {2,}', ' ', flat)

            if not flat:
                continue

            sentences = re.split(r'(?<=[.!?])\s*', flat)

            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue

                if len(sentence) <= max_chars:
                    result_lines.append(sentence)
                    continue

                tokens = sentence.split(' ')
                current_line = ""

                for token in tokens:
                    test = (current_line + token).strip()
                    if len(test) <= max_chars:
                        current_line = test + " "
                    else:
                        if current_line.strip():
                            result_lines.append(current_line.strip())
                        if len(token) > max_chars:
                            for i in range(0, len(token), max_chars):
                                result_lines.append(token[i:i+max_chars])
                            current_line = ""
                        else:
                            current_line = token + " "

                if current_line.strip():
                    result_lines.append(current_line.strip())

            result_lines.append("")

        return "\n".join(result_lines).strip()

    col_fmt1, col_fmt2 = st.columns([1, 3])
    with col_fmt1:
        fmt_chars = st.number_input("줄당 최대 글자 수", min_value=4, max_value=20, value=8, step=1)
    with col_fmt2:
        if st.button("🔀 자막 줄바꿈 자동 정리 (붙여넣은 대본 → 자막 포맷)", use_container_width=True):
            if not script_text.strip():
                st.error("대본이 비어있습니다!")
            else:
                formatted = auto_format_subtitle(script_text, max_chars=fmt_chars)
                st.session_state["parsed_script"] = formatted
                st.rerun()

    if st.button("✨ 대본으로 고정댓글 + DM + 영상설명 자동 생성", use_container_width=True, type="primary"):
        if not script_text.strip():
            st.error("대본이 비어있습니다! 대본을 먼저 붙여넣어 주세요.")
        elif not nvidia_api_key:
            st.error("NVIDIA API Key를 입력해주세요.")
        else:
            with st.spinner(f"대본 분석 중... ({model_choice})"):
                cta_raw = ""
                def cta_stream_gen():
                    for chunk in generate_cta_from_script_stream(script_text, nvidia_api_key, model_choice):
                        yield chunk
                cta_raw = st.write_stream(cta_stream_gen())

                import re as _re
                _pattern = r'={2,}\s*(COMMENT|DM[_\s]*MESSAGE|DESCRIPTION)\s*={2,}'
                _matches = list(_re.finditer(_pattern, cta_raw, _re.IGNORECASE))
                if _matches:
                    _sections = {}
                    for _i, _m in enumerate(_matches):
                        _key = _m.group(1).upper().replace(" ", "_")
                        if _key.startswith("DM"): _key = "DM_MESSAGE"
                        _start = _m.end()
                        _end = _matches[_i+1].start() if _i + 1 < len(_matches) else len(cta_raw)
                        _sections[_key] = cta_raw[_start:_end].strip()
                    st.session_state["parsed_comment"] = _sections.get("COMMENT", "")
                    st.session_state["parsed_dm"] = _sections.get("DM_MESSAGE", "")
                    st.session_state["parsed_description"] = _sections.get("DESCRIPTION", "")
                    st.success("✅ 생성 완료! 아래 STEP 1 결과 영역에서 복사하세요.")
                    st.rerun()

    col_v1, col_v2 = st.columns(2)

    EL_API_KEY_FILE = "el_api_key.txt"
    cached_el_api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if os.path.exists(EL_API_KEY_FILE):
        with open(EL_API_KEY_FILE, "r", encoding="utf-8-sig") as f:
            cached_el_api_key = f.read().strip()

    with col_v1:
        selected_voice = st.selectbox(
            "🎙️ AI 성우 보이스 선택",
            options=[
                ("🌟 [프리미엄] 매력적인 여성 - Rachel", "el_21m00Tcm4TlvDq8ikWAM"),
                ("🌟 [프리미엄] 다이내믹 남성 - Drew", "el_29vD33N1CtxCmqQRPOHJ"),
                ("🌟 [프리미엄] 발랄한 여성 - Bella", "el_EXAVITQu4vr4xnSDxMaL"),
                ("🌟 [프리미엄] 묵직한 중년 남성 - Antoni", "el_ErXwobaYiN019PkySvjV"),
                ("---", ""),
                ("🐟 [Fish Audio] 건강한 여성 목소리", "fish_0340360282524779a06c68b76d80f773"),
                ("🐟 [Fish Audio] 3040 건강정보 단호한 아내", "fish_d93d9edfdc7649ce9fa573cfa7be504f"),
                ("🐟 [Fish Audio] 활기찬 건강 보이스", "fish_88790aeef3ab48c0a88f9c5676362ed3"),
                ("🐟 [Fish Audio] 커스텀 보이스 (Reference ID 직접 입력)", "fish_custom"),
                ("---", ""),
                ("👩‍💼 [무료] 마케팅 여성 - 선희", "ko-KR-SunHiNeural"),
                ("👩‍🏫 [무료] 아나운서 여성 - 지민", "ko-KR-JiMinNeural"),
                ("👵 [무료] 다정한 아주머니 - 순복", "ko-KR-SoonBokNeural"),
                ("👨‍💼 [무료] 마케팅 남성 - 인준", "ko-KR-InJoonNeural"),
                ("👨‍🏫 [무료] 신뢰감 남성 - 봉진", "ko-KR-BongJinNeural"),
                ("🎧 [무료] 유튜버 청년 - 현수", "ko-KR-HyunsuNeural")
            ],
            format_func=lambda x: x[0]
        )[1]

    with col_v2:
        el_api_key = st.text_input("🔑 ElevenLabs API Key", type="password", value=cached_el_api_key, placeholder="sk_...")
        if el_api_key and el_api_key != cached_el_api_key:
            with open(EL_API_KEY_FILE, "w", encoding="utf-8") as f:
                f.write(el_api_key)

        FISH_API_KEY_FILE = "fish_api_key.txt"
        cached_fish_api_key = os.environ.get("FISH_API_KEY", "")
        if os.path.exists(FISH_API_KEY_FILE):
            with open(FISH_API_KEY_FILE, "r", encoding="utf-8-sig") as f:
                cached_fish_api_key = f.read().strip()

        fish_api_key = st.text_input("🔑 Fish Audio API Key", type="password", value=cached_fish_api_key)
        if fish_api_key and fish_api_key != cached_fish_api_key:
            with open(FISH_API_KEY_FILE, "w", encoding="utf-8") as f:
                f.write(fish_api_key)

        if selected_voice == "fish_custom":
            fish_reference_id = st.text_input("🐟 Fish Audio Reference ID", placeholder="예: 62243d5...")
            actual_voice_choice = f"fish_{fish_reference_id}" if fish_reference_id else "fish_"
        else:
            actual_voice_choice = selected_voice

    col1, col2 = st.columns(2)

    with col1:
        from naver_clip_adforge import get_capcut_projects, build_capcut_project_for_naver_clip
        templates = get_capcut_projects()
        template_options = [("none", "템플릿 안 함 (맨땅에서 자동 생성)")] + [(t[1], f"🎬 {t[0]}") for t in templates]

        selected_template = st.selectbox(
            "🛠️ 캡컷 템플릿 선택 (디자인/효과 훔쳐오기)",
            options=template_options,
            format_func=lambda x: x[1]
        )[0]

        if st.button("🎬 캡컷 프로젝트 1초 자동 생성", use_container_width=True):
            if not script_text.strip():
                st.error("대본이 비어있습니다!")
            else:
                with st.spinner("CapCut 초안 프로젝트 렌더링 중..."):
                    try:
                        if actual_voice_choice == "":
                            st.error("올바른 성우를 선택해주세요.")
                        elif actual_voice_choice.startswith("el_") and not el_api_key:
                            st.error("ElevenLabs 성우를 사용하려면 API Key를 입력해야 합니다.")
                        elif actual_voice_choice.startswith("fish_") and not fish_api_key:
                            st.error("Fish Audio API Key를 입력해야 합니다.")
                        elif actual_voice_choice == "fish_":
                            st.error("Fish Audio Reference ID를 입력해야 합니다.")
                        else:
                            os.environ["FISH_API_KEY"] = fish_api_key
                            project_name = build_capcut_project_for_naver_clip(
                                script_text=script_text,
                                voice=actual_voice_choice,
                                el_api_key=el_api_key,
                                template_folder=selected_template
                            )
                            st.success(f"성공적으로 캡컷 프로젝트 '{project_name}' 초안을 생성했습니다!")
                            st.info("PC의 캡컷(CapCut) 프로그램을 열면 임시 보관함에서 확인하실 수 있습니다.")
                    except Exception as e:
                        st.error(f"오류 발생: {e}")

    with col2:
        if st.button("🖼️ 이미지 프롬프트 먼저 추출 (Hailuo AI용)", use_container_width=True):
            if not script_text.strip():
                st.error("대본이 비어있습니다!")
            elif not nvidia_api_key:
                st.error("NVIDIA API Key를 입력해주세요.")
            else:
                with st.spinner(f"이미지 프롬프트 분석 중... ({model_choice})"):
                    st.markdown("##### 💡 추출 중인 이미지 프롬프트 (실시간)")
                    def img_stream_generator():
                        for chunk in generate_image_prompts_stream(script_text, nvidia_api_key, model_choice):
                            yield chunk

                    img_result = st.write_stream(img_stream_generator())
                    st.session_state["image_prompts"] = img_result

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

    if "image_prompts" in st.session_state and st.session_state["image_prompts"]:
        st.markdown("---")
        st.subheader("💡 추출된 이미지 프롬프트 전문 (Hailuo AI용)")
        st.markdown(f'<div class="prompt-box">{st.session_state["image_prompts"]}</div>', unsafe_allow_html=True)

    if "hailuo_prompts" in st.session_state and st.session_state["hailuo_prompts"]:
        st.markdown("---")
        st.subheader("💡 추출된 Hailuo AI 프롬프트 전문")
        st.markdown(f'<div class="prompt-box">{st.session_state["hailuo_prompts"]}</div>', unsafe_allow_html=True)


# ===================================================================
# TAB 3: Reference Library (NEW)
# ===================================================================
with tab_ref:
    st.subheader("📚 Reference Library")
    st.caption("네이버 클립 등 레퍼런스 링크를 저장합니다. 영상 파일은 다운로드하지 않습니다.")

    # ─── 레퍼런스 추가 폼 ────────────────────────────────
    with st.expander("➕ 레퍼런스 추가", expanded=False):
        with st.form("add_reference_form", clear_on_submit=True):
            col_r1, col_r2 = st.columns(2)
            with col_r1:
                ref_platform = st.selectbox("플랫폼", ["Naver Clip", "YouTube", "Instagram", "TikTok", "기타"])
                ref_url = st.text_input("URL *", placeholder="https://...")
                ref_category = st.selectbox("카테고리", ["건강 운동", "건강 정보", "골프", "미용", "생활정보", "기타"])
            with col_r2:
                ref_title = st.text_input("제목 (선택)")
                ref_topic = st.text_input("세부 주제", placeholder="예) 혈당 관리 운동")
                ref_tags = st.text_input("태그 (쉼표 구분)", placeholder="혈당, 걷기, 시니어, 훅")

            ref_memo = st.text_area("메모", placeholder="예) 첫 3초 훅 참고, 영상 구조 참고", height=80)
            ref_project_id = current_project_data.get("project_id", "")

            submitted = st.form_submit_button("💾 저장", use_container_width=True)
            if submitted:
                if not ref_url.strip():
                    st.error("URL을 입력해주세요.")
                else:
                    tags_list = [t.strip() for t in ref_tags.split(",") if t.strip()]
                    ref = Reference(
                        project_id=ref_project_id,
                        url=ref_url.strip(),
                        platform=ref_platform,
                        title=ref_title.strip(),
                        category=ref_category,
                        topic=ref_topic.strip(),
                        memo=ref_memo.strip(),
                        tags=tags_list,
                    )
                    insert_reference(ref.to_dict())
                    st.success("✅ 레퍼런스가 저장되었습니다!")
                    st.rerun()

    # ─── 레퍼런스 목록 ────────────────────────────────────
    st.markdown("---")

    col_ref_filter1, col_ref_filter2, col_ref_filter3 = st.columns([2, 2, 2])
    with col_ref_filter1:
        ref_filter_project = st.checkbox("현재 프로젝트만 보기", value=True)
    with col_ref_filter2:
        ref_search = st.text_input("🔍 검색", placeholder="주제, 메모, 태그")
    with col_ref_filter3:
        ref_platform_filter = st.selectbox("플랫폼 필터", ["전체", "Naver Clip", "YouTube", "Instagram", "TikTok", "기타"])

    project_id_filter = current_project_data.get("project_id") if ref_filter_project else None
    refs = get_references(project_id=project_id_filter)

    # 검색 필터
    if ref_search:
        search_lower = ref_search.lower()
        refs = [r for r in refs if (
            search_lower in r.get("topic", "").lower() or
            search_lower in r.get("memo", "").lower() or
            search_lower in r.get("tags", "").lower() or
            search_lower in r.get("title", "").lower()
        )]
    if ref_platform_filter != "전체":
        refs = [r for r in refs if r.get("platform") == ref_platform_filter]

    if not refs:
        st.info("저장된 레퍼런스가 없습니다. 위 버튼을 눌러 추가해주세요.")
    else:
        st.caption(f"총 {len(refs)}개의 레퍼런스")
        for ref_data in refs:
            ref_id = ref_data["reference_id"]
            ref_platform_d = ref_data.get("platform", "")
            ref_title_d = ref_data.get("title") or ref_data.get("topic") or ref_data.get("url", "")
            ref_tags_d = ref_data.get("tags", "")
            ref_memo_d = ref_data.get("memo", "")
            ref_url_d = ref_data.get("url", "")
            ref_topic_d = ref_data.get("topic", "")
            ref_category_d = ref_data.get("category", "")

            with st.container():
                st.markdown(f"""
<div class="ref-card">
  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.4rem;">
    <span style="font-size:0.85rem; color:#718096;">{ref_platform_d} · {ref_category_d}</span>
    <span style="font-size:0.8rem; color:#4A5568;">{ref_data.get('created_at','')[:10]}</span>
  </div>
  <div style="font-size:1rem; font-weight:600; margin-bottom:0.3rem;">{ref_title_d}</div>
  <div style="font-size:0.85rem; color:#A0AEC0; margin-bottom:0.3rem;">🏷️ {ref_topic_d}</div>
  <div style="font-size:0.8rem; color:#718096; font-family:monospace; margin-bottom:0.5rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">{ref_url_d}</div>
  {f'<div style="font-size:0.85rem; color:#CBD5E0; margin-bottom:0.4rem;">📝 {ref_memo_d}</div>' if ref_memo_d else ''}
  {f'<div style="font-size:0.8rem; color:#4A5568;"># {ref_tags_d.replace(",", " #")}</div>' if ref_tags_d else ''}
</div>
                """, unsafe_allow_html=True)

                col_btn1, col_btn2, col_btn3, col_btn4 = st.columns([2, 2, 2, 1])
                with col_btn1:
                    if st.button("🔗 클립 열기", key=f"open_{ref_id}", use_container_width=True):
                        st.markdown(f'<meta http-equiv="refresh" content="0; url={ref_url_d}">', unsafe_allow_html=True)
                        st.link_button("클릭해서 열기", ref_url_d)
                with col_btn2:
                    if st.button("🎯 이 레퍼런스로 콘텐츠 만들기", key=f"use_{ref_id}", use_container_width=True):
                        st.session_state["ref_to_script_topic"] = ref_topic_d
                        st.session_state["ref_to_script_category"] = ref_category_d
                        st.success(f"✅ '{ref_topic_d}' 주제가 대본 기획 탭에 입력됩니다. 탭 1로 이동하세요.")
                with col_btn3:
                    pass
                with col_btn4:
                    if st.button("🗑️", key=f"del_{ref_id}", help="삭제"):
                        delete_reference(ref_id)
                        st.rerun()


# ===================================================================
# TAB 4: Scene Planner (NEW)
# ===================================================================
with tab_scene:
    st.subheader("🎬 Scene Planner")
    st.caption("GPTs에서 검수 완료된 대본을 붙여넣으면 자동으로 장면을 분리합니다.")

    if not nvidia_api_key:
        st.warning("⚠️ NVIDIA API Key가 필요합니다. 상단 API 키 설정에서 입력해주세요.")

    scene_script = st.text_area(
        "📝 검수 완료된 대본 입력",
        value=st.session_state.get("parsed_script", ""),
        height=200,
        placeholder="GPTs에서 검수 완료된 대본을 여기에 붙여넣으세요."
    )

    col_sp1, col_sp2 = st.columns(2)
    with col_sp1:
        scene_content_title = st.text_input("콘텐츠 제목 (저장용)", placeholder="예) 혈당 관리 운동")
    with col_sp2:
        scene_project_id = current_project_data.get("project_id", "")

    if st.button("🎬 장면 자동 분할 시작", use_container_width=True, type="primary"):
        if not scene_script.strip():
            st.error("대본을 입력해주세요.")
        elif not nvidia_api_key:
            st.error("NVIDIA API Key를 입력해주세요.")
        else:
            content_id = str(uuid.uuid4())
            st.session_state["current_content_id"] = content_id

            with st.spinner("장면 분석 중... (NVIDIA mistral-nemotron)"):
                from scene_planner import plan_scenes
                try:
                    scenes, hook, total_dur = plan_scenes(
                        script=scene_script,
                        nvidia_api_key=nvidia_api_key,
                        model=model_choice,
                        content_id=content_id,
                    )

                    # DB 저장
                    from db.adforge_db import insert_content
                    import datetime as _dt
                    insert_content({
                        "content_id": content_id,
                        "project_id": scene_project_id,
                        "reference_id": "",
                        "title": scene_content_title or "제목 없음",
                        "category": current_project_data.get("content_category", ""),
                        "script": scene_script,
                        "status": "scene_planning",
                        "created_at": _dt.datetime.now().isoformat(),
                    })
                    insert_scenes([s.to_dict() for s in scenes])

                    st.session_state["current_scenes"] = scenes
                    st.session_state["current_hook"] = hook
                    st.session_state["current_total_duration"] = total_dur
                    st.success(f"✅ 총 {len(scenes)}개 장면으로 분리 완료! (예상 총 길이: {total_dur:.1f}초)")

                except Exception as e:
                    st.error(f"Scene 분할 오류: {e}")

    # 장면 결과 표시
    scenes_result = st.session_state.get("current_scenes", [])
    hook_result = st.session_state.get("current_hook", "")
    total_dur_result = st.session_state.get("current_total_duration", 0)

    if scenes_result:
        if hook_result:
            st.info(f"🪝 **추출된 Hook:** {hook_result}")

        stock_count = sum(1 for s in scenes_result if not s.ai_video_required)
        ai_count = sum(1 for s in scenes_result if s.ai_video_required)
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("총 장면 수", f"{len(scenes_result)}개")
        col_m2.metric("Stock 사용 장면", f"{stock_count}개", delta=f"Hailuo 절약")
        col_m3.metric("Hailuo 필요 장면", f"{ai_count}개", delta=f"{ai_count/len(scenes_result)*100:.0f}%" if scenes_result else "0%")

        st.markdown("---")
        for scene in scenes_result:
            badge = '<span class="badge-stock">📦 Stock</span>' if not scene.ai_video_required else '<span class="badge-ai">🤖 Hailuo</span>'
            card_class = "scene-card scene-stock" if not scene.ai_video_required else "scene-card scene-ai"
            kw_str = " · ".join(scene.search_keywords)
            st.markdown(f"""
<div class="{card_class}">
  <div style="display:flex; justify-content:space-between; margin-bottom:0.4rem;">
    <span style="font-weight:700;">Scene {scene.order:02d}</span>
    <span>{badge} &nbsp; ⏱️ {scene.start_time:.1f}s ~ {scene.end_time:.1f}s</span>
  </div>
  <div style="margin-bottom:0.3rem;">🗣️ <em>{scene.narration}</em></div>
  <div style="color:#A0AEC0; margin-bottom:0.3rem;">🎥 {scene.visual_description}</div>
  <div style="font-size:0.8rem; color:#718096;">🔍 {kw_str}</div>
</div>
            """, unsafe_allow_html=True)

        st.markdown("---")
        if st.button("📦 Stock 검색 시작 → Stock & Asset 탭으로 이동", use_container_width=True):
            st.info("Stock & Asset 탭으로 이동해서 검색을 시작하세요.")


# ===================================================================
# TAB 5: Stock & Asset (NEW)
# ===================================================================
with tab_stock:
    st.subheader("📦 Stock & Asset 검색")

    scenes_for_stock = st.session_state.get("current_scenes", [])
    if not scenes_for_stock:
        st.info("Scene Planner 탭에서 먼저 장면을 분리해주세요.")
    else:
        st.caption(f"총 {len(scenes_for_stock)}개 장면 · Stock 장면: {sum(1 for s in scenes_for_stock if not s.ai_video_required)}개")

        has_pexels = bool(pexels_api_key)
        has_pixabay = bool(pixabay_api_key)

        if not has_pexels and not has_pixabay:
            st.warning("⚠️ Pexels 또는 Pixabay API Key가 필요합니다. 상단 API 키 설정에서 입력해주세요.")

        col_st1, col_st2 = st.columns(2)
        with col_st1:
            search_per_scene = st.number_input("장면당 검색 결과 수", min_value=5, max_value=30, value=15)
        with col_st2:
            stock_dest_dir = st.text_input("다운로드 폴더", value="stock_videos/v2")

        stock_scenes = [s for s in scenes_for_stock if not s.ai_video_required]

        if st.button("🔍 Stock 영상 자동 검색", use_container_width=True, type="primary", disabled=(not has_pexels and not has_pixabay)):
            from stock_engine.pexels_provider import PexelsProvider
            from stock_engine.pixabay_provider import PixabayProvider
            from stock_engine.scorer import rank_results

            providers = []
            if has_pexels:
                providers.append(PexelsProvider(pexels_api_key))
            if has_pixabay:
                providers.append(PixabayProvider(pixabay_api_key))

            all_search_results = {}
            progress = st.progress(0)
            for idx, scene in enumerate(stock_scenes):
                progress.progress((idx + 1) / len(stock_scenes), text=f"Scene {scene.order} 검색 중...")
                scene_results = []
                for provider in providers:
                    try:
                        results = provider.search(scene.search_keywords, per_page=search_per_scene)
                        scene_results.extend(results)
                    except Exception as e:
                        st.warning(f"Scene {scene.order} — {provider.name} 검색 오류: {e}")

                ranked = rank_results(scene_results, scene.search_keywords, top_k=5)
                all_search_results[scene.scene_id] = ranked

            st.session_state["stock_search_results"] = all_search_results
            progress.progress(1.0, text="검색 완료!")
            st.success(f"✅ {len(stock_scenes)}개 장면 검색 완료!")

        # 검색 결과 표시
        search_results = st.session_state.get("stock_search_results", {})
        if search_results:
            st.markdown("---")
            st.markdown("### 🎯 검색 결과")
            for scene in stock_scenes:
                results = search_results.get(scene.scene_id, [])
                with st.expander(f"Scene {scene.order:02d}: {scene.narration[:40]}... ({len(results)}개 결과)"):
                    if not results:
                        st.warning("검색 결과 없음 — Hailuo로 전환 고려")
                    else:
                        for r in results:
                            col_r1, col_r2, col_r3 = st.columns([1, 3, 1])
                            with col_r1:
                                if r.thumbnail_url:
                                    st.image(r.thumbnail_url, width=100)
                            with col_r2:
                                st.markdown(f"**{r.provider.upper()}** · {r.width}×{r.height} · {r.duration:.1f}s")
                                st.caption(f"Score: {r.score}/100 · {r.resolution_label} · {'세로' if r.is_vertical else '가로'}")
                                st.caption(f"🔗 {r.url}")
                            with col_r3:
                                if st.button("⬇️ 다운로드", key=f"dl_{scene.scene_id}_{r.video_id}"):
                                    with st.spinner("다운로드 중..."):
                                        try:
                                            from stock_engine.pexels_provider import PexelsProvider
                                            from stock_engine.pixabay_provider import PixabayProvider
                                            from stock_engine.asset_manager import save_asset

                                            if r.provider == "pexels" and has_pexels:
                                                provider_dl = PexelsProvider(pexels_api_key)
                                            elif r.provider == "pixabay" and has_pixabay:
                                                provider_dl = PixabayProvider(pixabay_api_key)
                                            else:
                                                st.error("해당 Provider API Key가 없습니다.")
                                                provider_dl = None

                                            if provider_dl:
                                                local_path = provider_dl.download(r, stock_dest_dir)
                                                asset = save_asset(r, local_path)
                                                update_scene(scene.scene_id, stock_asset_id=asset.asset_id, stock_search_status="found", status="stock_assigned")
                                                st.success(f"✅ 저장됨: {local_path}")
                                        except Exception as e:
                                            st.error(f"다운로드 오류: {e}")


# ===================================================================
# TAB 6: AI Video — Hailuo (NEW)
# ===================================================================
with tab_ai_video:
    st.subheader("🤖 AI Video — Hailuo 프롬프트 생성")
    st.caption("Stock으로 표현하기 어려운 장면만 Hailuo 프롬프트를 자동 생성합니다.")

    scenes_for_ai = st.session_state.get("current_scenes", [])
    ai_scenes = [s for s in scenes_for_ai if s.ai_video_required]

    if not scenes_for_ai:
        st.info("Scene Planner 탭에서 먼저 장면을 분리해주세요.")
    elif not ai_scenes:
        st.success("✅ 모든 장면이 Stock으로 처리 가능합니다. Hailuo가 필요하지 않습니다!")
    else:
        st.info(f"🤖 Hailuo가 필요한 장면: {len(ai_scenes)}개 / 전체 {len(scenes_for_ai)}개")

        target_audience_prompt = current_project_data.get("target_audience", "50~70대 한국 시니어 여성")

        if st.button("🤖 Hailuo 프롬프트 자동 생성", use_container_width=True, type="primary"):
            from hailuo_prompt_generator import generate_prompts_for_content
            with st.spinner("프롬프트 생성 중..."):
                from models.scene import Scene as SceneModel
                prompt_results = generate_prompts_for_content(
                    scenes=ai_scenes,
                    nvidia_api_key=nvidia_api_key if nvidia_api_key else None,
                    model=model_choice,
                    project_target_audience=target_audience_prompt,
                )
                st.session_state["hailuo_scene_prompts"] = prompt_results

                # DB 업데이트
                for scene in ai_scenes:
                    prompt = prompt_results.get(scene.scene_id, "")
                    if prompt:
                        update_scene(scene.scene_id, ai_video_prompt=prompt, status="ai_assigned")

                st.success(f"✅ {len(prompt_results)}개 프롬프트 생성 완료!")

        # 프롬프트 결과 표시
        hailuo_prompts = st.session_state.get("hailuo_scene_prompts", {})
        if hailuo_prompts:
            st.markdown("---")
            for scene in ai_scenes:
                prompt = hailuo_prompts.get(scene.scene_id, "")
                with st.expander(f"Scene {scene.order:02d}: {scene.narration[:40]}..."):
                    st.markdown(f"**화면:** {scene.visual_description}")
                    st.markdown("**Hailuo 프롬프트:**")
                    st.code(prompt, language="text")
                    col_cp1, col_cp2 = st.columns(2)
                    with col_cp1:
                        st.button("📋 복사", key=f"copy_prompt_{scene.scene_id}", help="프롬프트를 클립보드에 복사")
                    with col_cp2:
                        if st.button("✏️ 수정", key=f"edit_prompt_{scene.scene_id}"):
                            st.session_state[f"edit_mode_{scene.scene_id}"] = True

                    if st.session_state.get(f"edit_mode_{scene.scene_id}"):
                        new_prompt = st.text_area("프롬프트 수정", value=prompt, key=f"prompt_edit_{scene.scene_id}")
                        if st.button("💾 저장", key=f"save_prompt_{scene.scene_id}"):
                            hailuo_prompts[scene.scene_id] = new_prompt
                            st.session_state["hailuo_scene_prompts"] = hailuo_prompts
                            update_scene(scene.scene_id, ai_video_prompt=new_prompt)
                            st.session_state[f"edit_mode_{scene.scene_id}"] = False
                            st.success("저장됨!")
                            st.rerun()


# ===================================================================
# TAB 7: TTS & Hook (Phase 7)
# ===================================================================
with tab_tts:
    st.subheader("🔊 TTS & Hook — Scene 기반 자동 생성")
    st.caption("Scene Planner에서 분리된 장면의 나레이션을 순서대로 합쳐 TTS를 생성하고, Hook을 추출합니다.")

    scenes_for_tts = st.session_state.get("current_scenes", [])
    hook_for_tts = st.session_state.get("current_hook", "")

    if not scenes_for_tts:
        st.info("Scene Planner 탭에서 먼저 장면을 분리해주세요.")
    else:
        # ─── Hook 섹션 ─────────────────────────────────────────────
        st.markdown("### 🪝 Hook 추출 결과")
        detected_hook = hook_for_tts or "아직 Hook이 추출되지 않았습니다."
        col_hook_disp, col_hook_edit = st.columns([3, 1])
        with col_hook_disp:
            st.info(f"**자동 추출 Hook:** {detected_hook}")
        with col_hook_edit:
            if st.button("✏️ Hook 직접 입력", key="hook_manual_edit"):
                st.session_state["hook_edit_mode"] = True

        if st.session_state.get("hook_edit_mode"):
            manual_hook = st.text_input("Hook 문장 (직접 수정)", value=detected_hook, key="hook_manual_input")
            if st.button("💾 Hook 확정", key="hook_save"):
                st.session_state["current_hook"] = manual_hook
                st.session_state["hook_edit_mode"] = False
                st.success("Hook이 업데이트됐습니다!")
                st.rerun()

        st.markdown("---")

        # ─── Scene 나레이션 → 대본 자동 조합 ─────────────────────
        st.markdown("### 📝 Scene 나레이션 → TTS 대본")
        st.caption("각 Scene의 나레이션을 순서대로 조합합니다. 수정 후 TTS를 생성하세요.")

        combined_narration = "\n".join(
            f"{s.narration}" for s in sorted(scenes_for_tts, key=lambda x: x.order)
        )

        col_narr_view, col_narr_opt = st.columns([3, 1])
        with col_narr_view:
            tts_script = st.text_area(
                "TTS 대본 (Scene 나레이션 자동 조합 / 수정 가능)",
                value=st.session_state.get("tts_combined_script", combined_narration),
                height=250,
                key="tts_script_area"
            )
        with col_narr_opt:
            st.markdown("**장면 목록**")
            for s in sorted(scenes_for_tts, key=lambda x: x.order):
                badge = "🟢" if not s.ai_video_required else "🟡"
                st.markdown(f"""<div class="tts-scene-row">{badge} <b>S{s.order:02d}</b> {s.narration[:25]}...</div>""", unsafe_allow_html=True)

        col_tts_action1, col_tts_action2 = st.columns(2)
        with col_tts_action1:
            if st.button("📤 TTS 대본을 'STEP 2 탭'으로 보내기", use_container_width=True, type="primary"):
                st.session_state["parsed_script"] = tts_script
                st.session_state["tts_combined_script"] = tts_script
                st.success("✅ STEP 2 탭의 대본 입력창에 적용됐습니다! '대본 편집 & CapCut' 탭으로 이동하세요.")
        with col_tts_action2:
            if st.button("🔀 자막 포맷 자동 정리 (8자 줄바꿈)", use_container_width=True):
                import re as _re_tts
                paragraphs = _re_tts.split(r'\n{2,}', tts_script.strip())
                result_lines = []
                for para in paragraphs:
                    flat = _re_tts.sub(r'\n', ' ', para).strip()
                    if not flat:
                        continue
                    sentences = _re_tts.split(r'(?<=[.!?])\s*', flat)
                    for sentence in sentences:
                        sentence = sentence.strip()
                        if not sentence:
                            continue
                        if len(sentence) <= 8:
                            result_lines.append(sentence)
                            continue
                        tokens = sentence.split(' ')
                        current_line = ""
                        for token in tokens:
                            test = (current_line + token).strip()
                            if len(test) <= 8:
                                current_line = test + " "
                            else:
                                if current_line.strip():
                                    result_lines.append(current_line.strip())
                                if len(token) > 8:
                                    for i in range(0, len(token), 8):
                                        result_lines.append(token[i:i+8])
                                    current_line = ""
                                else:
                                    current_line = token + " "
                        if current_line.strip():
                            result_lines.append(current_line.strip())
                    result_lines.append("")
                formatted = "\n".join(result_lines).strip()
                st.session_state["tts_combined_script"] = formatted
                st.session_state["parsed_script"] = formatted
                st.rerun()

        st.markdown("---")

        # ─── 9:16 변환 섹션 ────────────────────────────────────────
        st.markdown("### 📐 9:16 영상 변환")
        st.caption("다운로드된 Stock 영상을 1080×1920으로 자동 변환합니다.")

        from db.adforge_db import get_all_assets
        assets_list = get_all_assets()
        convertible_assets = [a for a in assets_list if a.get("source") in ("pexels", "pixabay", "local")]

        if not convertible_assets:
            st.info("아직 다운로드된 Stock 영상이 없습니다. 'Stock & Asset' 탭에서 먼저 다운로드하세요.")
        else:
            col_conv1, col_conv2 = st.columns(2)
            with col_conv1:
                conv_dest = st.text_input("변환 저장 폴더", value="stock_videos/converted_916")
            with col_conv2:
                overwrite_existing = st.checkbox("기존 파일 덮어쓰기", value=False)

            if st.button(f"📐 전체 {len(convertible_assets)}개 영상 9:16 변환", use_container_width=True, type="primary"):
                from video_pipeline.converter import convert_to_916, get_video_dimensions
                progress_bar = st.progress(0)
                results_log = []
                for i, asset in enumerate(convertible_assets):
                    src = asset.get("local_path", "")
                    if not src or not os.path.exists(src):
                        results_log.append((src, False, "파일 없음"))
                        continue
                    try:
                        progress_bar.progress((i + 1) / len(convertible_assets), text=f"변환 중: {os.path.basename(src)}")
                        dest = convert_to_916(src, conv_dest, overwrite=overwrite_existing)
                        results_log.append((src, True, dest))
                    except Exception as e:
                        results_log.append((src, False, str(e)))

                progress_bar.progress(1.0, text="변환 완료!")
                ok = sum(1 for _, success, _ in results_log if success)
                fail = len(results_log) - ok
                st.success(f"✅ 변환 완료: {ok}개 성공 / {fail}개 실패")
                for src, success, msg in results_log:
                    if success:
                        st.caption(f"✅ {os.path.basename(src)} → {msg}")
                    else:
                        st.caption(f"❌ {os.path.basename(src)}: {msg}")

        st.markdown("---")

        # ─── Preview & Export 섹션 (Phase 8) ──────────────────────
        st.markdown("### 🎬 Preview & Export")
        st.caption("현재 준비된 소스로 미리보기 영상을 생성합니다. Stock 없는 장면은 플레이스홀더로 대체됩니다.")

        _preview_scenes = st.session_state.get("current_scenes", [])

        # Scene 준비 현황
        if _preview_scenes:
            col_prev_info, col_prev_opt = st.columns([2, 1])
            with col_prev_info:
                st.markdown("**장면별 소스 현황**")
                for _ps in sorted(_preview_scenes, key=lambda x: x.order):
                    _dur = max(_ps.end_time - _ps.start_time, 2.5)
                    if getattr(_ps, "stock_asset_id", None):
                        _src_icon, _src_color = "✅ Stock", "#00E676"
                    elif _ps.ai_video_required:
                        _src_icon, _src_color = "🟡 AI 플레이스홀더", "#F6AD55"
                    else:
                        _src_icon, _src_color = "❌ 소스 없음", "#FC8181"
                    st.markdown(
                        f'<div style="display:flex;justify-content:space-between;padding:4px 8px;'
                        f'border-left:3px solid {_src_color};margin-bottom:3px;font-size:0.85rem;">'
                        f'<span>S{_ps.order:02d} · {_ps.narration[:30]}...</span>'
                        f'<span style="color:{_src_color};">{_src_icon} · {_dur:.1f}s</span></div>',
                        unsafe_allow_html=True
                    )

            with col_prev_opt:
                prev_output_dir = st.text_input("미리보기 저장 폴더", value="previews", key="preview_output_dir")
                prev_converted_dir = st.text_input("변환된 9:16 폴더", value="stock_videos/converted_916", key="preview_conv_dir")
                prev_add_subtitles = st.checkbox("자막 오버레이", value=True, key="preview_subtitles")

            col_gen1, col_gen2 = st.columns(2)
            with col_gen1:
                gen_preview_btn = st.button("🎬 미리보기 영상 생성", use_container_width=True, type="primary", key="gen_preview_btn")
            with col_gen2:
                if st.button("🗑️ 기존 미리보기 삭제", use_container_width=True, key="del_preview_btn"):
                    _prev_path_to_del = st.session_state.get("preview_output_path", "")
                    if _prev_path_to_del and os.path.exists(_prev_path_to_del):
                        try:
                            os.remove(_prev_path_to_del)
                        except Exception:
                            pass
                    st.session_state.pop("preview_output_path", None)
                    st.rerun()

            if gen_preview_btn:
                from video_pipeline.preview_generator import generate_preview
                import datetime as _dt_prev
                ts = _dt_prev.datetime.now().strftime("%Y%m%d_%H%M%S")
                out_path = os.path.join(prev_output_dir, f"preview_{ts}.mp4")
                _prev_progress_bar = st.progress(0)
                _prev_status = st.empty()

                def _prev_cb(i, total, msg):
                    _prev_progress_bar.progress((i + 1) / max(total, 1), text=msg)
                    _prev_status.caption(msg)

                try:
                    with st.spinner("미리보기 생성 중... Scene 수에 따라 수 분 소요될 수 있습니다."):
                        _prev_result = generate_preview(
                            scenes=_preview_scenes,
                            output_path=out_path,
                            converted_dir=prev_converted_dir,
                            raw_dir="stock_videos/v2",
                            add_subtitles=prev_add_subtitles,
                            progress_callback=_prev_cb,
                        )
                    _prev_progress_bar.progress(1.0, text="완료!")
                    st.session_state["preview_output_path"] = _prev_result["output_path"]
                    _stock_ok = sum(1 for _, t in _prev_result["scene_results"] if t == "stock")
                    _ai_ph   = sum(1 for _, t in _prev_result["scene_results"] if "ai" in t)
                    _miss_ph = sum(1 for _, t in _prev_result["scene_results"] if "missing" in t or "error" in t)
                    col_pr1, col_pr2, col_pr3 = st.columns(3)
                    col_pr1.metric("✅ Stock", _stock_ok)
                    col_pr2.metric("🟡 AI 플레이스홀더", _ai_ph)
                    col_pr3.metric("❌ 미준비", _miss_ph)
                    st.success(f"✅ 미리보기 생성 완료! → {_prev_result['output_path']}")
                except Exception as _prev_e:
                    st.error(f"미리보기 생성 오류: {_prev_e}")

            # 생성된 미리보기 영상 표시
            _prev_path = st.session_state.get("preview_output_path", "")
            if _prev_path and os.path.exists(_prev_path):
                st.markdown("---")
                st.markdown("#### 🎥 미리보기 플레이어")
                from video_pipeline.preview_generator import get_video_info_simple
                _vinfo = get_video_info_simple(_prev_path)
                col_vi1, col_vi2 = st.columns(2)
                col_vi1.caption(f"📁 {os.path.basename(_prev_path)}")
                col_vi2.caption(f"⏱️ {_vinfo['duration']:.1f}초 | 📦 {_vinfo['size_mb']:.1f} MB")
                with open(_prev_path, "rb") as _vf:
                    _video_bytes = _vf.read()
                st.video(_video_bytes)
                st.download_button(
                    label="⬇️ 미리보기 MP4 다운로드",
                    data=_video_bytes,
                    file_name=os.path.basename(_prev_path),
                    mime="video/mp4",
                    use_container_width=True,
                    key="preview_download_btn",
                )

            st.markdown("---")

            # CapCut Export 가이드
            st.markdown("### 📋 CapCut Export 가이드")
            st.caption("장면 순서대로 CapCut에서 영상을 배치할 때 참고하세요.")
            _export_lines = []
            for _es in sorted(_preview_scenes, key=lambda x: x.order):
                _dur = max(_es.end_time - _es.start_time, 2.5)
                _label = (
                    "📦 Stock 영상 삽입" if getattr(_es, "stock_asset_id", None)
                    else "🤖 Hailuo 생성 후 삽입" if _es.ai_video_required
                    else "⚠️ 소스 준비 필요"
                )
                _export_lines.append(f"S{_es.order:02d} ({_dur:.1f}s) → {_label}\n  📝 {_es.narration[:50]}")
            st.text_area("CapCut 작업 순서", value="\n".join(_export_lines), height=180, key="capcut_guide_text")

            _hailuo_cnt = sum(1 for _es in _preview_scenes if _es.ai_video_required)
            if _hailuo_cnt > 0:
                st.warning(f"⚠️ Hailuo 생성 필요 장면 {_hailuo_cnt}개 — 'AI Video' 탭에서 프롬프트를 확인하세요.")
            else:
                st.success("🎉 모든 장면에 Stock 소스가 준비됐습니다!")

        else:
            st.info("Scene Planner 탭에서 먼저 장면을 분리해주세요.")


# ===================================================================
# TAB 8: Production Dashboard (Phase 9)
# ===================================================================
with tab_dashboard:
    st.subheader("🚀 Production Dashboard")
    st.caption("콘텐츠 제작 현황을 한눈에 확인합니다.")

    # ─── 오늘 KPI ─────────────────────────────────────────────────
    from db.adforge_db import get_contents, get_scenes, get_all_assets
    import datetime as _dt_dash

    all_contents = get_contents(project_id=current_project_data.get("project_id"))
    daily_target = current_project_data.get("daily_target", 10)

    today_str = _dt_dash.date.today().isoformat()
    today_contents = [c for c in all_contents if c.get("created_at", "").startswith(today_str)]
    done_contents = [c for c in all_contents if c.get("status") == "completed"]
    total_assets = get_all_assets()

    col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)
    with col_kpi1:
        st.markdown(f"""
        <div class="kpi-box">
          <div style="font-size:2rem; font-weight:800; color:#00E676;">{len(today_contents)}</div>
          <div style="color:#A0AEC0; font-size:0.85rem;">오늘 생성</div>
          <div style="color:#718096; font-size:0.75rem;">목표: {daily_target}편</div>
        </div>
        """, unsafe_allow_html=True)
    with col_kpi2:
        st.markdown(f"""
        <div class="kpi-box">
          <div style="font-size:2rem; font-weight:800; color:#63B3ED;">{len(all_contents)}</div>
          <div style="color:#A0AEC0; font-size:0.85rem;">전체 콘텐츠</div>
        </div>
        """, unsafe_allow_html=True)
    with col_kpi3:
        st.markdown(f"""
        <div class="kpi-box">
          <div style="font-size:2rem; font-weight:800; color:#F6AD55;">{len(total_assets)}</div>
          <div style="color:#A0AEC0; font-size:0.85rem;">다운로드 Asset</div>
        </div>
        """, unsafe_allow_html=True)
    with col_kpi4:
        progress_pct = int(len(today_contents) / daily_target * 100) if daily_target > 0 else 0
        st.markdown(f"""
        <div class="kpi-box">
          <div style="font-size:2rem; font-weight:800; color:#9F7AEA;">{progress_pct}%</div>
          <div style="color:#A0AEC0; font-size:0.85rem;">오늘 달성률</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # ─── 진행률 바 ─────────────────────────────────────────────────
    if daily_target > 0:
        st.markdown(f"**오늘 목표: {len(today_contents)} / {daily_target}편**")
        st.progress(min(len(today_contents) / daily_target, 1.0))

    st.markdown("---")

    # ─── 콘텐츠 목록 ───────────────────────────────────────────────
    STATUS_LABELS = {
        "draft":          ("📝 초안", "status-draft"),
        "scene_planning": ("🎬 장면분할", "status-scene"),
        "stock_searching":("📦 Stock 검색중", "status-stock"),
        "composing":      ("🎵 편집중", "status-ai"),
        "qa":             ("🔍 QA", "status-ai"),
        "completed":      ("✅ 완료", "status-done"),
    }

    col_dash_filter1, col_dash_filter2 = st.columns([2, 2])
    with col_dash_filter1:
        dash_show_all = st.checkbox("전체 프로젝트 콘텐츠 보기", value=False)
    with col_dash_filter2:
        dash_status_filter = st.selectbox("상태 필터", ["전체", "draft", "scene_planning", "stock_searching", "composing", "completed"])

    display_contents = get_contents() if dash_show_all else all_contents
    if dash_status_filter != "전체":
        display_contents = [c for c in display_contents if c.get("status") == dash_status_filter]

    if not display_contents:
        st.info("콘텐츠가 없습니다. Scene Planner에서 대본을 분석하면 여기에 표시됩니다.")
    else:
        st.caption(f"총 {len(display_contents)}개 콘텐츠")
        for content in display_contents:
            cid = content["content_id"]
            status = content.get("status", "draft")
            label, css_class = STATUS_LABELS.get(status, ("❓ 알 수 없음", "status-draft"))
            content_scenes = get_scenes(cid)
            stock_done = sum(1 for s in content_scenes if s.get("status") == "stock_assigned")
            ai_done = sum(1 for s in content_scenes if s.get("status") == "ai_assigned")
            total_s = len(content_scenes)

            created_at = content.get("created_at", "")[:16].replace("T", " ")

            st.markdown(f"""
<div class="dash-card {css_class}">
  <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:0.4rem;">
    <span style="font-size:1rem; font-weight:700;">{content.get('title','제목 없음')}</span>
    <span style="font-size:0.8rem; background:#2d3748; padding:2px 8px; border-radius:8px;">{label}</span>
  </div>
  <div style="font-size:0.8rem; color:#718096; margin-bottom:0.4rem;">{content.get('category','')} · {created_at}</div>
  <div style="font-size:0.8rem; color:#A0AEC0;">
    📸 Scene: {total_s}개 &nbsp;|&nbsp;
    📦 Stock: {stock_done}개 &nbsp;|&nbsp;
    🤖 AI: {ai_done}개
  </div>
</div>
            """, unsafe_allow_html=True)

            col_d1, col_d2, col_d3 = st.columns([2, 2, 1])
            with col_d1:
                if st.button("🎬 이 콘텐츠 Scene 보기", key=f"view_scenes_{cid}"):
                    if content_scenes:
                        from models.scene import Scene as SceneModel
                        loaded_scenes = [SceneModel.from_dict(s) for s in content_scenes]
                        st.session_state["current_scenes"] = loaded_scenes
                        st.session_state["current_content_id"] = cid
                        st.info("Scene Planner 탭으로 이동하면 이 콘텐츠의 Scene을 확인할 수 있습니다.")
            with col_d2:
                new_status = st.selectbox(
                    "상태 변경",
                    ["draft", "scene_planning", "stock_searching", "composing", "qa", "completed"],
                    index=list(STATUS_LABELS.keys()).index(status) if status in STATUS_LABELS else 0,
                    key=f"status_select_{cid}",
                    label_visibility="collapsed"
                )
                if st.button("🔄 상태 저장", key=f"update_status_{cid}"):
                    from db.adforge_db import update_content_status
                    update_content_status(cid, new_status)
                    st.rerun()
            with col_d3:
                pass

    st.markdown("---")

    # ─── 빠른 액션 ──────────────────────────────────────────────────
    st.markdown("### ⚡ 빠른 액션")
    col_qa1, col_qa2, col_qa3 = st.columns(3)
    with col_qa1:
        if st.button("🎯 새 콘텐츠 만들기", use_container_width=True):
            st.info("'대본 기획' 탭에서 새 대본을 생성하세요.")
    with col_qa2:
        if st.button("🔄 DB 새로고침", use_container_width=True):
            st.rerun()
    with col_qa3:
        st.metric("Stock 캐시", f"{len(get_all_assets())}개", help="다운로드된 Asset 수")
