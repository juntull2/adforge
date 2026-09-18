import os
import re
import time
import pandas as pd
import streamlit as st
import requests
from dotenv import load_dotenv

from naver_clip_adforge import (
    build_capcut_project_for_naver_clip,
    split_script_by_sentences_and_phrases,
    split_sentence_naturally,
    generate_voice_for_text
)
from reference_validator_view import render_reference_validator_view
from capcut_tracker_view import render_capcut_tracker_view

# .env 파일에서 환경 변수 강제 로드
load_dotenv(override=True)

# Streamlit Cloud 배포 시 st.secrets 값을 os.environ에 자동 동기화
try:
    if hasattr(st, "secrets"):
        for _sk, _sv in st.secrets.items():
            if isinstance(_sv, str) and not os.environ.get(_sk):
                os.environ[_sk] = _sv
except Exception:
    pass

# -------------------------------------------------------------------
# Streamlit 대시보드 페이지 설정
# -------------------------------------------------------------------
st.set_page_config(
    page_title="AdForge - 4050 숏폼 기획 & 영상 자동화",
    page_icon="🎬",
    layout="wide"
)

st.markdown('''
<style>
    .main-header { font-size: 2.2rem; font-weight: 800; color: #00E676; margin-bottom: 0.2rem; }
    .sub-header { font-size: 1.05rem; color: #A0AEC0; margin-bottom: 1.2rem; }
</style>
''', unsafe_allow_html=True)

st.markdown('<div class="main-header">🚀 AdForge :: 4050 숏폼 기획 & 영상 자동화</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">키워드 발굴부터 레퍼런스 검증, 캡컷 프로젝트 생성까지 원스톱!</div>', unsafe_allow_html=True)

# -------------------------------------------------------------------
# 전역 설정 및 API 키 캐싱
# -------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def get_cached_file_content(filepath: str, default_val: str = "") -> str:
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8-sig") as f:
                return f.read().strip()
        except Exception:
            pass
    return default_val

API_KEY_FILE = "nv_api_key.txt"
cached_api_key = get_cached_file_content(API_KEY_FILE, os.environ.get("NVIDIA_API_KEY", ""))

PEXELS_API_KEY_FILE = "pexels_api_key.txt"
cached_pexels_api_key = get_cached_file_content(PEXELS_API_KEY_FILE, "")

PIXABAY_API_KEY_FILE = "pixabay_api_key.txt"
cached_pixabay_api_key = get_cached_file_content(PIXABAY_API_KEY_FILE, "")

col_key, col_pexels, col_pixabay, col_model = st.columns([1.5, 1.5, 1.5, 1.5])
with col_key:
    nvidia_api_key = st.text_input("🔑 LLM API Key", type="password", value=cached_api_key, placeholder="nvapi- / sk-or-")
    if nvidia_api_key and nvidia_api_key != cached_api_key:
        with open(API_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(nvidia_api_key)
        get_cached_file_content.clear()
with col_pexels:
    pexels_api_key = st.text_input("📷 Pexels API", type="password", value=cached_pexels_api_key, placeholder="Pexels (선택)")
    if pexels_api_key and pexels_api_key != cached_pexels_api_key:
        with open(PEXELS_API_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(pexels_api_key)
        get_cached_file_content.clear()
with col_pixabay:
    pixabay_api_key = st.text_input("📷 Pixabay API", type="password", value=cached_pixabay_api_key, placeholder="Pixabay (선택)")
    if pixabay_api_key and pixabay_api_key != cached_pixabay_api_key:
        with open(PIXABAY_API_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(pixabay_api_key)
        get_cached_file_content.clear()
with col_model:
    is_openrouter = nvidia_api_key.startswith("sk-or-")
    if is_openrouter:
        model_opts = {
            "nvidia/nemotron-3-super-120b-a12b:free": "🌟 120B 스위트스팟 (무료)",
            "nvidia/nemotron-3-ultra-550b-a55b:free": "🔥 550B 초거대 (무료)",
            "meta-llama/llama-3.1-70b-instruct": "💡 Llama 3.1 70B (유료)",
            "anthropic/claude-3.5-sonnet": "💎 Claude 3.5 Sonnet (유료)",
            "openai/gpt-4o-mini": "🚀 GPT-4o Mini (유료)"
        }
    else:
        model_opts = {
            "mistralai/mistral-nemotron": "🥇 Mistral Nemotron (추천/무료)",
            "meta/llama-3.1-70b-instruct": "💡 Llama 3.1 70B (무료)",
            "meta/llama-3.1-8b-instruct": "⚡ Llama 3.1 8B (무료)"
        }

    model_choice = st.selectbox(
        "🧠 AI 언어모델 선택",
        options=list(model_opts.keys()),
        format_func=lambda x: model_opts[x]
    )

st.markdown("---")

# -------------------------------------------------------------------
# 상단 4개 탭 구조화
# -------------------------------------------------------------------
tab_keyword, tab_reference, tab_video, tab_tracker = st.tabs([
    "📊 키워드 발굴 & 대량 분석",
    "🎯 인스타 광고 레퍼런스 검증",
    "🎬 캡컷 영상 자동 생성",
    "🎨 캡컷 프로젝트 추적 & 스타일 추출"
])

# ===================================================================
# [탭 1] 키워드 발굴 및 대량 분석
# ===================================================================
with tab_keyword:
    @st.cache_data(ttl=3600)
    def load_keyword_data():
        sheet_url = "https://docs.google.com/spreadsheets/d/1-xfToD-ns9nBwj7Eh0URGOKc_YWcxxt5a3vJXgRqz9Q/export?format=csv&gid=1956992404"
        try:
            df = pd.read_csv(sheet_url)
            df.columns = df.columns.str.replace(r'\n', ' ', regex=True).str.strip()
            
            if '키워드' in df.columns:
                df = df.dropna(subset=['키워드'])
                if len(df) > 0 and df.iloc[0]['키워드'] == '고유번호':
                    df = df.iloc[1:]
                    
            if '접촉지점' in df.columns:
                df['접촉지점'] = pd.to_numeric(df['접촉지점'], errors='coerce').fillna(0)
                    
            display_cols = []
            target_cols = ['키워드', '전체  검색량', 'MB  검색량', '블로그  글개수', '1탭', '2탭', '3탭', '4탭', '5탭', '6탭', '접촉지점']
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
        if st.button("🔄 데이터 최신화", width="stretch", key="btn_refresh_sheet"):
            load_keyword_data.clear()
            st.session_state.pop("cached_styled_df", None)
            st.rerun()

    df_keywords = load_keyword_data()

    selected_keyword = st.session_state.get("selected_keyword", "")
    if df_keywords is not None and not df_keywords.empty:
        st.markdown("아래 표에서 키워드를 선택하면 **레퍼런스 검증 및 캡컷 제작**에 자동 연동됩니다.")
        
        if "cached_styled_df" not in st.session_state or st.session_state.get("cached_styled_df_len") != len(df_keywords):
            def highlight_clip(val):
                if '네이버 클립' in str(val):
                    return 'background-color: #00C73C; color: white; font-weight: bold;'
                return ''
            tab_cols = [c for c in df_keywords.columns if '탭' in c]
            st.session_state["cached_styled_df"] = df_keywords.style.map(highlight_clip, subset=tab_cols)
            st.session_state["cached_styled_df_len"] = len(df_keywords)
        
        styled_df = st.session_state["cached_styled_df"]
        
        col_table, col_side = st.columns([4, 1])
        
        with col_table:
            event = st.dataframe(
                styled_df, 
                width="stretch", 
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row"
            )
            
        with col_side:
            st.markdown("### 🔍 모바일 검색")
            search_kw = st.text_input("검색어 필터", key="mobile_search_filter").strip()
            st.caption("우클릭하여 시크릿 창으로 엽니다.")
            with st.container(height=380):
                if search_kw:
                    mask = df_keywords['키워드'].astype(str).str.contains(search_kw, case=False, na=False)
                    filtered_kws = df_keywords.loc[mask, '키워드'].tolist()
                else:
                    filtered_kws = df_keywords['키워드'].head(50).tolist()
                
                if filtered_kws:
                    links_md = "\n\n".join([f"👉 **[{kw}](https://m.search.naver.com/search.naver?query={kw})**" for kw in filtered_kws[:50]])
                    st.markdown(links_md)
                    if len(filtered_kws) > 50:
                        st.caption(f"💡 상위 50개 표시 중 (전체 {len(filtered_kws):,}개)")
                else:
                    st.caption("일치하는 키워드가 없습니다.")
                
        if len(event.selection.rows) > 0:
            selected_idx = event.selection.rows[0]
            selected_keyword = df_keywords.iloc[selected_idx]['키워드']
            if selected_keyword and st.session_state.get("_prev_sheet_selected_kw") != selected_keyword:
                st.session_state["_prev_sheet_selected_kw"] = selected_keyword
                st.session_state["selected_keyword"] = selected_keyword
                st.session_state["ig_ad_keyword"] = selected_keyword
                st.session_state["root_ad_keyword"] = selected_keyword
                st.session_state["trigger_search_auto"] = True

    # ── 실시간 단일 키워드 탭 순위 및 검색량 ──
    st.markdown("---")
    st.subheader("🔍 실시간 단일 키워드 탭 순위 및 검색량 조회")
    col_kw1, col_kw2 = st.columns([3, 1])

    with col_kw1:
        default_rt_kw = selected_keyword or st.session_state.get("rt_keyword", "")
        rt_keyword = st.text_input("분석할 키워드를 입력하세요", value=default_rt_kw, placeholder="예: 허리찜질기", key="rt_kw_input")

    with col_kw2:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        if st.button("📊 실시간 조회", width="stretch", type="primary", key="btn_check_rt_kw"):
            if not rt_keyword.strip():
                st.error("키워드를 입력해주세요.")
            else:
                with st.spinner("네이버 모바일 탭 순위 및 검색량 조회 중..."):
                    from naver_scraper import get_naver_clip_rank, get_naver_search_volume
                    
                    cust_id = os.environ.get("NAVER_CUSTOMER_ID", "")
                    acc_lic = os.environ.get("NAVER_ACCESS_LICENSE", "")
                    sec_key = os.environ.get("NAVER_SECRET_KEY", "")
                    
                    rank = get_naver_clip_rank(rt_keyword.strip())
                    vol = get_naver_search_volume(rt_keyword.strip(), cust_id, acc_lic, sec_key)
                    
                    st.session_state["rt_rank"] = rank
                    st.session_state["rt_vol"] = vol
                    st.session_state["rt_keyword"] = rt_keyword.strip()

    if "rt_rank" in st.session_state and st.session_state.get("rt_keyword") == rt_keyword.strip():
        rank = st.session_state["rt_rank"]
        vol = st.session_state["rt_vol"]
        
        col_res1, col_res2 = st.columns(2)
        with col_res1:
            if rank > 0 and rank <= 6:
                st.success(f"✅ **[클립] 탭 노출 순위: {rank}번째 (합격)**")
            elif rank > 6:
                st.warning(f"⚠️ **[클립] 탭 노출 순위: {rank}번째 (6탭 밖)**")
            else:
                st.error("❌ **[클립] 탭을 찾을 수 없습니다.**")
                
        with col_res2:
            if vol.get("total", 0) > 0:
                st.info(f"📊 월간 검색량: **{vol['total']:,}** (PC: {vol.get('pc',0):,} | 모바일: {vol.get('mobile',0):,})")
            else:
                st.warning("⚠️ 검색량 데이터 없음 (API 키 미설정 또는 조회 결과 0)")

    # ── 대량 키워드 일괄 분석 ──
    st.markdown("---")
    st.subheader("🚀 대량 키워드 실시간 분석 옵션 설정")
    st.caption("구글 시트에 기재된 키워드를 기반으로 실시간 탭 순위와 최신 검색량을 일괄 조회합니다.")

    col_opt1, col_opt2 = st.columns(2)
    with col_opt1:
        min_contact = st.number_input("최소 접촉지점 점수", min_value=0, max_value=10, value=4, step=1, help="시트의 접촉지점이 이 점수 이상인 키워드만 1차로 필터링합니다.")
    with col_opt2:
        min_volume = st.number_input("최소 총 검색량 (PC+모바일)", min_value=0, value=1000, step=100, help="API로 불러온 실시간 검색량이 이 수치 이상인 키워드만 최종 결과에 보여줍니다.")

    if st.button("설정한 조건으로 키워드 일괄 분석 시작", width="stretch", key="btn_bulk_sheet_analysis"):
        if df_keywords is None or df_keywords.empty:
            st.error("데이터를 불러올 수 없거나 키워드가 없습니다.")
        elif '접촉지점' not in df_keywords.columns:
            st.error("'접촉지점' 열을 찾을 수 없습니다. 구글 시트 형식을 확인해주세요.")
        else:
            target_df = df_keywords[df_keywords['접촉지점'] >= min_contact].copy()
            if target_df.empty:
                st.warning(f"접촉지점이 {min_contact}점 이상인 키워드가 없습니다.")
            else:
                with st.spinner(f"총 {len(target_df)}개 키워드를 분석 중입니다. 잠시만 기다려주세요..."):
                    from naver_scraper import get_naver_clip_rank, get_naver_search_volume
                    
                    cust_id = os.environ.get("NAVER_CUSTOMER_ID", "")
                    acc_lic = os.environ.get("NAVER_ACCESS_LICENSE", "")
                    sec_key = os.environ.get("NAVER_SECRET_KEY", "")
                    
                    results = []
                    progress_bar = st.progress(0)
                    
                    for i, row in enumerate(target_df.itertuples()):
                        kw = getattr(row, '키워드')
                        time.sleep(0.3)
                        
                        rank = get_naver_clip_rank(kw)
                        vol = get_naver_search_volume(kw, cust_id, acc_lic, sec_key)
                        
                        if vol["total"] >= min_volume:
                            results.append({
                                "키워드": kw,
                                "접촉지점": getattr(row, '접촉지점'),
                                "실시간 클립 탭 순위": f"{rank}위" if (rank > 0 and rank <= 6) else (f"{rank}위 (위험)" if rank > 6 else "미노출"),
                                "총 검색량": vol["total"],
                                "PC 검색량": vol["pc"],
                                "모바일 검색량": vol["mobile"]
                            })
                        progress_bar.progress((i + 1) / len(target_df))
                    
                    if not results:
                        st.warning("분석 결과, 설정한 최소 검색량 조건을 만족하는 키워드가 없습니다.")
                    else:
                        st.session_state["bulk_results"] = pd.DataFrame(results)

    if "bulk_results" in st.session_state:
        st.success("✅ 대량 분석이 완료되었습니다!")
        res_df = st.session_state["bulk_results"]
        st.dataframe(res_df, width="stretch")


# ===================================================================
# [탭 2] 인스타 광고 레퍼런스 검증기
# ===================================================================
with tab_reference:
    render_reference_validator_view(selected_keyword=selected_keyword)


# ===================================================================
# [탭 3] 캡컷 영상 자동 생성
# ===================================================================
with tab_video:
    st.subheader("🎬 캡컷 연동 및 자동 숏폼 생성")
    st.caption("대본 입력, 스마트 호흡 단위 줄바꿈, 로컬 미디어 배치, AI 성우 선택을 통해 원클릭으로 캡컷 프로젝트를 생성합니다.")

    # 🔀 자막 줄바꿈 자동 정리 함수
    def auto_format_subtitle(text: str, max_chars: int = 16) -> str:
        """한국어 대본을 문맥 및 호흡 단위에 맞게 자동 줄바꿈"""
        if not text or not text.strip():
            return ""
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        text = re.sub(r'([요죠다네함음임])\s+(?=(?:차기만|왜냐하면|그래서|하지만|그러니|지금|당장|30일|특허|대기))', r'\1. ', text)
        
        paragraphs = re.split(r'\n{2,}', text.strip())
        result_lines = []
        
        for para in paragraphs:
            flat = re.sub(r'\s+', ' ', para).strip()
            if not flat:
                continue
            sentences = [s.strip() for s in re.split(r'(?<=[.!?…~])\s+', flat) if s.strip()]
            for sent in sentences:
                lines = split_sentence_naturally(sent, max_chars=max_chars)
                result_lines.extend(lines)
            result_lines.append("")
        
        return "\n".join(result_lines).strip()

    def format_subtitle_with_ai(text: str, api_key: str, model: str = "", max_chars: int = 16) -> str:
        """LLM을 이용해 광고 카피 자막을 최적의 호흡 단위로 줄바꿈"""
        if not text or not text.strip() or not api_key:
            return text
        
        prompt = f"""당신은 숏폼(9:16) 영상 자막 전문 카피라이터입니다.
주어진 광고 대본을 시청자가 1~2초 안에 한눈에 읽을 수 있도록 가장 자연스러운 '의미 단위(호흡 덩어리)'로 1줄씩 줄바꿈(엔터)하세요.

[필수 규칙]
1. 1줄당 글자 수는 약 10~{max_chars}자 내외로 조절하세요.
2. 단어/명사구가 어색하게 쪼개지지 않도록 연결어미(~고, ~면, ~아서), 쉼표, 호흡 단위에서 줄바꿈하세요.
3. 원문의 글자, 단어, 어순을 절대 변경/삭제/추가하지 마세요. 오직 줄바꿈(\\n) 위치만 결정하세요.
4. 설명이나 따옴표 없이 오직 줄바꿈된 대본 텍스트만 출력하세요.

[대본]
{text}"""

        if api_key.startswith("sk-or-"):
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            body = {
                "model": model if model else "openai/gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2
            }
        else:
            url = "https://integrate.api.nvidia.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            body = {
                "model": model if model else "mistralai/mistral-nemotron",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2
            }
            
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=20)
            if resp.status_code == 200:
                res_json = resp.json()
                out_text = res_json['choices'][0]['message']['content'].strip()
                if out_text.startswith("```"):
                    out_text = re.sub(r'^```[a-zA-Z]*\n', '', out_text)
                    out_text = re.sub(r'\n```$', '', out_text)
                return out_text.strip()
        except Exception as e:
            print(f"AI format failed: {e}")
        return text

    if "script_text_area" not in st.session_state:
        st.session_state["script_text_area"] = st.session_state.get("parsed_script", "")

    def apply_auto_format():
        raw = st.session_state.get("script_text_area", "")
        if raw and raw.strip():
            limit = st.session_state.get("fmt_chars_input", 16)
            formatted = auto_format_subtitle(raw, max_chars=limit)
            st.session_state["script_text_area"] = formatted
            st.session_state["parsed_script"] = formatted

    def apply_ai_format():
        raw = st.session_state.get("script_text_area", "")
        if raw and raw.strip():
            or_api_key = os.environ.get("OPENROUTER_API_KEY", nvidia_api_key)
            limit = st.session_state.get("fmt_chars_input", 16)
            with st.spinner("🤖 AI가 문맥과 호흡 단위로 최적의 자막 줄바꿈을 생성 중..."):
                formatted = format_subtitle_with_ai(raw, api_key=or_api_key, model=model_choice, max_chars=limit)
            st.session_state["script_text_area"] = formatted
            st.session_state["parsed_script"] = formatted

    col_fmt1, col_fmt2, col_fmt3 = st.columns([1.2, 2.4, 2.4])
    with col_fmt1:
        st.number_input("줄당 글자 수", min_value=8, max_value=30, value=16, step=1, key="fmt_chars_input", help="숏폼 자막은 14~18자가 한눈에 읽히는 최적 폭입니다.")
    with col_fmt2:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        st.button("⚡ 문맥 맞춤 줄바꿈 (스마트 규칙)", on_click=apply_auto_format, use_container_width=True, help="어절, 연결어미, 쉼표 등 문맥 호흡에 맞게 즉시 줄바꿈합니다.")
    with col_fmt3:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        st.button("🤖 AI 문맥 줄바꿈 (LLM 카피)", on_click=apply_ai_format, use_container_width=True, help="AI가 문맥을 분석하여 시청자 호흡에 최적화된 1줄 자막으로 정리합니다.")

    script_text = st.text_area("📝 영상 자막(대본) 전문", key="script_text_area", height=220, placeholder="영상의 자막으로 사용될 대본을 입력하세요.")

    # 로컬 미디어 소스 폴더 입력
    local_media_folder = st.text_input("📁 로컬 미디어 소스 폴더 경로 (선택)", placeholder=r"예: C:\Users\User\Videos\Product")

    media_mapping = {}
    if local_media_folder and os.path.isdir(local_media_folder):
        try:
            valid_exts = ['.mp4', '.mov', '.jpg', '.jpeg', '.png']
            local_files = [f for f in os.listdir(local_media_folder) if os.path.splitext(f)[1].lower() in valid_exts]
            local_files.sort()
            
            if local_files:
                with st.expander("🎬 로컬 미디어 문장별 수동 매핑 (선택)", expanded=False):
                    st.info("각 문장 재생 시 배경으로 표시될 로컬 미디어(영상/사진)를 선택하세요.")
                    sentence_structures = split_script_by_sentences_and_phrases(script_text, max_chars_per_phrase=18)
                    media_options = ["(자동 배치 / 스톡 비디오)"] + local_files
                    
                    for i, struct in enumerate(sentence_structures):
                        sentence = struct["full_sentence"]
                        if not sentence.strip():
                            continue
                            
                        selected_file = st.selectbox(
                            f"문장 {i+1}: {sentence}",
                            options=media_options,
                            key=f"media_mapping_{i}"
                        )
                        if selected_file != "(자동 배치 / 스톡 비디오)":
                            media_mapping[i] = selected_file
            else:
                st.warning("입력하신 폴더에 영상이나 이미지 파일(.mp4, .mov, .jpg, .png)이 없습니다.")
        except Exception as e:
            st.error(f"폴더를 읽는 중 오류가 발생했습니다: {e}")

    # -------------------------------------------------------------------
    # 🎧 문장별 오디오 검수 & 부분 재생성 (선택)
    # -------------------------------------------------------------------
    sentence_structures = []
    if script_text.strip():
        sentence_structures = split_script_by_sentences_and_phrases(script_text, max_chars_per_phrase=18)

    if sentence_structures:
        with st.expander(f"🎧 문장별 오디오 검수 & 부분 재생성 ({len(sentence_structures)}문장)", expanded=False):
            st.markdown("전체 오디오를 미리 들어보고, **발음이나 톤이 어색한 문장만 골라서 다시 생성(부분 재생성)**할 수 있습니다.")

            if "precomputed_audio" not in st.session_state:
                st.session_state["precomputed_audio"] = {}
            if "voice_overrides" not in st.session_state:
                st.session_state["voice_overrides"] = {}

            col_all_gen, col_clear = st.columns([3, 1])
            with col_all_gen:
                if st.button("🎙️ 전체 문장 오디오 한 번에 미리 생성하기", use_container_width=True, key="btn_gen_all_sentences"):
                    # 실제 선택된 보이스 결정
                    v_choice = st.session_state.get("actual_voice_choice_state", "ko-KR-SunHiNeural")
                    el_key = st.session_state.get("el_api_key_state", "")
                    fish_key = st.session_state.get("fish_api_key_state", "")
                    spd = st.session_state.get("speech_speed_state", 1.0)
                    with st.spinner("전체 문장 TTS 음성 생성 중..."):
                        temp_preview_dir = os.path.join(os.getcwd(), "temp_audio", "previews")
                        os.makedirs(temp_preview_dir, exist_ok=True)
                        for idx, st_item in enumerate(sentence_structures):
                            s_text = st_item["full_sentence"]
                            s_v = st.session_state["voice_overrides"].get(idx) or v_choice
                            out_p = os.path.join(temp_preview_dir, f"preview_s{idx}_{int(time.time())}.mp3")
                            try:
                                generate_voice_for_text(
                                    text=s_text,
                                    output_path=out_p,
                                    voice=s_v,
                                    speed=spd,
                                    el_api_key=el_key,
                                    fish_api_key=fish_key
                                )
                                st.session_state["precomputed_audio"][idx] = out_p
                            except Exception as err:
                                st.error(f"문장 {idx+1} 생성 실패: {err}")
                        st.success("🎉 모든 문장의 오디오 생성이 완료되었습니다! 아래 플레이어에서 확인하세요.")
                        st.rerun()

            with col_clear:
                if st.button("🧹 오디오 캐시 초기화", use_container_width=True, key="btn_clear_audio_cache"):
                    st.session_state["precomputed_audio"] = {}
                    st.session_state["voice_overrides"] = {}
                    st.rerun()

            st.markdown("---")
            for idx, st_item in enumerate(sentence_structures):
                s_text = st_item["full_sentence"]
                audio_path = st.session_state["precomputed_audio"].get(idx)

                with st.container(border=True):
                    row_col1, row_col2, row_col3 = st.columns([5, 3, 2])
                    with row_col1:
                        st.markdown(f"**[문장 {idx+1}]** {s_text}")
                        if audio_path and os.path.exists(audio_path):
                            st.audio(audio_path, format="audio/mp3")
                        else:
                            st.caption("⏳ 아직 생성되지 않은 문장입니다. (오른쪽 버튼으로 개별 생성 가능)")
                    with row_col2:
                        cur_override = st.session_state["voice_overrides"].get(idx, "")
                        voice_sub_opts = [
                            ("(기본 설정 성우 사용)", ""),
                            ("🐟 활기찬 젊은 여성 (차분/설득)", "fish_117e42c2a0af45889eed4a0d564a16d9"),
                            ("🐟 20대 여성 쇼츠", "fish_54f52a4d2b994612a30306b4a2a95758"),
                            ("🐟 진우-기쁨-", "fish_a9574d6184714eac96a0a892b719289f"),
                            ("🐟 봉미선 (짱구엄마)", "fish_b6198ce983784d8db3456c062250cc5a"),
                            ("👩‍💼 [무료] 선희", "ko-KR-SunHiNeural"),
                            ("👨‍💼 [무료] 인준", "ko-KR-InJoonNeural")
                        ]
                        override_voice = st.selectbox(
                            f"성우 개별 변경 (문장 {idx+1})",
                            options=voice_sub_opts,
                            format_func=lambda x: x[0],
                            key=f"voice_override_sel_{idx}"
                        )[1]
                        if override_voice:
                            st.session_state["voice_overrides"][idx] = override_voice
                        elif idx in st.session_state["voice_overrides"]:
                            del st.session_state["voice_overrides"][idx]
                    with row_col3:
                        st.markdown("<div style='height: 25px;'></div>", unsafe_allow_html=True)
                        if st.button(f"🔄 이 문장만 재생성", key=f"btn_regen_{idx}", use_container_width=True):
                            v_choice = st.session_state.get("actual_voice_choice_state", "ko-KR-SunHiNeural")
                            el_key = st.session_state.get("el_api_key_state", "")
                            fish_key = st.session_state.get("fish_api_key_state", "")
                            spd = st.session_state.get("speech_speed_state", 1.0)
                            target_voice = st.session_state["voice_overrides"].get(idx) or v_choice
                            with st.spinner(f"문장 {idx+1} 음성 재생성 중..."):
                                temp_preview_dir = os.path.join(os.getcwd(), "temp_audio", "previews")
                                os.makedirs(temp_preview_dir, exist_ok=True)
                                out_p = os.path.join(temp_preview_dir, f"preview_s{idx}_{int(time.time())}.mp3")
                                try:
                                    generate_voice_for_text(
                                        text=s_text,
                                        output_path=out_p,
                                        voice=target_voice,
                                        speed=spd,
                                        el_api_key=el_key,
                                        fish_api_key=fish_key
                                    )
                                    st.session_state["precomputed_audio"][idx] = out_p
                                    st.success(f"문장 {idx+1} 재생성 완료!")
                                    st.rerun()
                                except Exception as err:
                                    st.error(f"재생성 실패: {err}")

    # 성우 보이스 선택 및 키 입력
    col_v1, col_v2 = st.columns(2)

    EL_API_KEY_FILE = "el_api_key.txt"
    cached_el_api_key = get_cached_file_content(EL_API_KEY_FILE, os.environ.get("ELEVENLABS_API_KEY", ""))

    with col_v1:
        selected_voice = st.selectbox(
            "🎙️ AI 성우 보이스 선택",
            options=[
                ("🌟 [프리미엄] 매력적인 여성 - Rachel", "el_21m00Tcm4TlvDq8ikWAM"),
                ("🌟 [프리미엄] 다이내믹 남성 - Drew", "el_29vD33N1CtxCmqQRPOHJ"),
                ("🌟 [프리미엄] 발랄한 여성 - Bella", "el_EXAVITQu4vr4xnSDxMaL"),
                ("🌟 [프리미엄] 묵직한 중년 남성 - Antoni", "el_ErXwobaYiN019PkySvjV"),
                ("---", ""),
                ("🐟 [Fish Audio] 활기찬 젊은 여성 (차분 & 설득력 있는 톤)", "fish_117e42c2a0af45889eed4a0d564a16d9"),
                ("🐟 [Fish Audio] 20대 여성 쇼츠 (인플루언서 스타일)", "fish_54f52a4d2b994612a30306b4a2a95758"),
                ("🐟 [Fish Audio] 20대 여성 내돈내산 쇼츠 (리뷰 톤)", "fish_46939387dd944a45a399bd92b8de52cb"),
                ("🐟 [Fish Audio] 해짜 보이스3 (남성 내레이션/설명)", "fish_136a377398bc4f5dba0101259a9b3eea"),
                ("🐟 [Fish Audio] 건강한 여성 목소리", "fish_0340360282524779a06c68b76d80f773"),
                ("🐟 [Fish Audio] 3040 건강정보 단호한 아내", "fish_d93d9edfdc7649ce9fa573cfa7be504f"),
                ("🐟 [Fish Audio] 활기찬 건강 보이스", "fish_88790aeef3ab48c0a88f9c5676362ed3"),
                ("🐟 [Fish Audio] 신규 보이스", "fish_ed763b05d90b470284150bbc49a8d9e1"),
                ("🐟 [Fish Audio] 진우-기쁨-", "fish_a9574d6184714eac96a0a892b719289f"),
                ("🐟 [Fish Audio] 링 아나운서", "fish_dc90eb64548d4a758642d806bce75a51"),
                ("🐟 [Fish Audio] 봉미선 (짱구 엄마) (개성 넘치는 훅)", "fish_b6198ce983784d8db3456c062250cc5a"),
                ("🐟 [Fish Audio] 소심한 개구리", "fish_eaa6afb386c84964b8347eea590f7064"),
                ("🐟 [Fish Audio] 케로로 나레이션", "fish_da6796ba493b43828ff4107889937fe6"),
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
            get_cached_file_content.clear()
                
        FISH_API_KEY_FILE = "fish_api_key.txt"
        cached_fish_api_key = get_cached_file_content(FISH_API_KEY_FILE, os.environ.get("FISH_API_KEY", ""))
                
        fish_api_key = st.text_input("🔑 Fish Audio API Key", type="password", value=cached_fish_api_key)
        if fish_api_key and fish_api_key != cached_fish_api_key:
            with open(FISH_API_KEY_FILE, "w", encoding="utf-8") as f:
                f.write(fish_api_key)
            get_cached_file_content.clear()
                
        if selected_voice == "fish_custom":
            fish_reference_id = st.text_input("🐟 Fish Audio Reference ID", placeholder="예: 62243d5...")
            actual_voice_choice = f"fish_{fish_reference_id}" if fish_reference_id else "fish_"
        else:
            actual_voice_choice = selected_voice

    st.session_state["actual_voice_choice_state"] = actual_voice_choice
    st.session_state["el_api_key_state"] = el_api_key
    st.session_state["fish_api_key_state"] = fish_api_key

    # ⚡ TTS 발화 속도(배속) 조절 슬라이더
    col_speed, col_speed_tip = st.columns([1.5, 2.5])
    with col_speed:
        speech_speed = st.slider(
            "⚡ TTS 말하기 속도 (배속)",
            min_value=0.7,
            max_value=1.5,
            value=1.0,
            step=0.05,
            format="%.2fx",
            key="sb_speech_speed",
            help="음성의 발화 속도를 조절합니다. 숏폼 영상에서는 1.1x ~ 1.2x 속도가 시청 집중도를 높입니다."
        )
        st.session_state["speech_speed_state"] = speech_speed
    with col_speed_tip:
        st.markdown("<div style='height: 25px;'></div>", unsafe_allow_html=True)
        st.caption("💡 **속도 가이드:** `1.00x`(기본 속도) | `1.10x ~ 1.20x`(빠른 템포의 바이럴 숏폼 추천)")

    st.markdown("---")

    # 🎨 스타일 프리셋 선택
    import capcut_tracker
    saved_presets = capcut_tracker.load_presets()
    col_preset, col_preset_info = st.columns([2, 2])
    with col_preset:
        preset_options = [("기본 AdForge 스타일 (Pretendard + 블랙한산스)", None)]
        for p in saved_presets:
            preset_options.append((f"🎨 {p.get('name', '프리셋')} ({p.get('source_project', '')})", p.get("id")))

        selected_preset_tuple = st.selectbox(
            "🎨 캡컷 효과 & 자막 스타일 프리셋",
            options=preset_options,
            format_func=lambda x: x[0],
            help="사용자의 기존 캡컷 프로젝트에서 추출한 효과, 전환, 자막 스타일을 신규 프로젝트에 그대로 적용합니다."
        )
        selected_preset_id = selected_preset_tuple[1]

    with col_preset_info:
        if selected_preset_id:
            curr_p = next((p for p in saved_presets if p.get("id") == selected_preset_id), None)
            if curr_p:
                eff_names = [e.get("name") for e in curr_p.get("effects", [])[:2]]
                trans_names = [t.get("name") for t in curr_p.get("transitions", [])[:2]]
                desc_parts = []
                if eff_names:
                    desc_parts.append(f"효과: {', '.join(eff_names)}")
                if trans_names:
                    desc_parts.append(f"전환: {', '.join(trans_names)}")
                st.caption("✨ **적용될 에셋:** " + (" / ".join(desc_parts) if desc_parts else "자막 디자인 적용"))
        else:
            st.caption("💡 '🎨 캡컷 프로젝트 추적 & 스타일 추출' 탭에서 내 캡컷 프로젝트의 효과를 프리셋으로 등록할 수 있습니다.")

    st.markdown("---")

    # 🎬 캡컷 프로젝트 생성 실행
    if st.button("🎬 캡컷 프로젝트 1초 자동 생성", use_container_width=True, type="primary"):
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
                        
                        target_kw = selected_keyword or st.session_state.get("selected_keyword", "")

                        project_name = build_capcut_project_for_naver_clip(
                            script_text=script_text,
                            keyword=target_kw,
                            pexels_api_key=pexels_api_key,
                            pixabay_api_key=pixabay_api_key,
                            voice=actual_voice_choice,
                            el_api_key=el_api_key,
                            local_media_folder=local_media_folder,
                            media_mapping=media_mapping,
                            speech_speed=speech_speed,
                            voice_overrides=st.session_state.get("voice_overrides", {}),
                            precomputed_audio=st.session_state.get("precomputed_audio", {}),
                            preset_id=selected_preset_id
                        )
                        st.success(f"🎉 성공적으로 캡컷 프로젝트 '{project_name}' 초안을 생성했습니다!")
                        if selected_preset_id:
                            st.info(f"✨ 선택하신 스타일 프리셋의 캡컷 효과 및 전환이 성공적으로 반영되었습니다.")
                        st.info("💡 PC의 캡컷(CapCut) 프로그램을 열면 임시 보관함에서 새로 생성된 프로젝트를 즉시 확인하실 수 있습니다.")
                except Exception as e:
                    st.error(f"오류 발생: {e}")

# ===================================================================
# [탭 4] 캡컷 로컬 프로젝트 실시간 추적 및 스타일 추출
# ===================================================================
with tab_tracker:
    render_capcut_tracker_view()
