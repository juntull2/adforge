import hashlib
import os
import re
import time
import pandas as pd
import streamlit as st
import requests
from dotenv import load_dotenv
from pathlib import Path

from naver_clip_adforge import (
    build_capcut_project_for_naver_clip,
    plan_script_shots,
    split_script_by_sentences_and_phrases,
    split_sentence_naturally,
    generate_voice_for_text
)
from a_grade_view import render_a_grade_view
from capcut_tracker_view import render_capcut_tracker_view
from reference_editor_view import render_reference_editor

# .env 파일에서 환경 변수 강제 로드
DOTENV_PATH = Path(".env")
if not DOTENV_PATH.exists():
    DOTENV_PATH.touch()
load_dotenv(dotenv_path=DOTENV_PATH, override=True)


def update_dotenv_file(filepath: Path, updates: dict):
    """Windows 파일 잠금(WinError 5)을 방지하며 .env 파일을 안전하게 일괄 업데이트합니다."""
    lines = []
    if filepath.exists():
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            with open(filepath, "r", encoding="utf-8-sig", errors="ignore") as f:
                lines = f.readlines()

    updated_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    for key, val in updates.items():
        if key not in updated_keys:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines.append("\n")
            new_lines.append(f"{key}={val}\n")

    max_retries = 5
    for attempt in range(max_retries):
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            break
        except PermissionError:
            if attempt < max_retries - 1:
                time.sleep(0.15)
            else:
                raise


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
st.markdown('<div class="sub-header">키워드 발굴부터 A급 소재 탐색, 캡컷 프로젝트 생성까지 원스톱!</div>', unsafe_allow_html=True)

# -------------------------------------------------------------------
# 사이드바 - API 키 설정 패널
# -------------------------------------------------------------------
def _env_val(key: str) -> str:
    return os.environ.get(key, "")

with st.sidebar:
    st.markdown("## ⚙️ API 설정")
    st.caption(".env 파일에 저장됩니다")

    with st.expander("🧠 LLM 제공자", expanded=not bool(_env_val("OPENROUTER_API_KEY"))):
        sb_openrouter = st.text_input("OpenRouter API Key", type="password",
            value=_env_val("OPENROUTER_API_KEY"), placeholder="sk-or-v1-...",
            key="sb_openrouter")
        sb_anthropic = st.text_input("Anthropic API Key", type="password",
            value=_env_val("ANTHROPIC_API_KEY"), placeholder="sk-ant-...",
            key="sb_anthropic")
        sb_nvidia = st.text_input("NVIDIA API Key", type="password",
            value=_env_val("NVIDIA_API_KEY"), placeholder="nvapi-...",
            key="sb_nvidia")

    with st.expander("📷 스톡 영상", expanded=False):
        sb_pexels = st.text_input("Pexels API Key", type="password",
            value=_env_val("PEXELS_API_KEY"), placeholder="Pexels API Key",
            key="sb_pexels")
        sb_pixabay = st.text_input("Pixabay API Key", type="password",
            value=_env_val("PIXABAY_API_KEY"), placeholder="Pixabay API Key",
            key="sb_pixabay")

    with st.expander("🔍 네이버 Search Advisor", expanded=False):
        sb_naver_cid = st.text_input("Customer ID", type="password",
            value=_env_val("NAVER_CUSTOMER_ID"), placeholder="네이버 고객 ID",
            key="sb_naver_cid")
        sb_naver_license = st.text_input("Access License", type="password",
            value=_env_val("NAVER_ACCESS_LICENSE"), placeholder="Access License",
            key="sb_naver_license")
        sb_naver_secret = st.text_input("Secret Key", type="password",
            value=_env_val("NAVER_SECRET_KEY"), placeholder="Secret Key",
            key="sb_naver_secret")

    with st.expander("📈 네이버 DataLab", expanded=False):
        sb_naver_client_id = st.text_input("Client ID", type="password",
            value=_env_val("NAVER_CLIENT_ID"), placeholder="네이버 Client ID",
            key="sb_naver_client_id")
        sb_naver_client_secret = st.text_input("Client Secret", type="password",
            value=_env_val("NAVER_CLIENT_SECRET"), placeholder="네이버 Client Secret",
            key="sb_naver_client_secret")

    with st.expander("📝 Notion", expanded=False):
        sb_notion_token = st.text_input("Notion Integration Token", type="password",
            value=_env_val("NOTION_TOKEN"), placeholder="secret_...",
            key="sb_notion_token")
        sb_notion_db = st.text_input("Database ID", type="default",
            value=_env_val("NOTION_DATABASE_ID"), placeholder="Notion DB ID",
            key="sb_notion_db")

    with st.expander("☁️ Google Drive", expanded=False):
        sb_gdrive_url = st.text_input("Drive 폴더 URL", type="default",
            value=_env_val("GOOGLE_DRIVE_FOLDER_URL"),
            placeholder="https://drive.google.com/drive/folders/...",
            key="sb_gdrive_url")
        sb_gdrive_sa = st.text_input("Service Account JSON 경로", type="default",
            value=_env_val("GOOGLE_SERVICE_ACCOUNT_JSON"),
            placeholder="service_account.json",
            key="sb_gdrive_sa")

    st.markdown("")
    if st.button("💾 저장하기", use_container_width=True, type="primary", key="btn_save_env"):
        _keys_vals = {
            "OPENROUTER_API_KEY": sb_openrouter,
            "ANTHROPIC_API_KEY": sb_anthropic,
            "NVIDIA_API_KEY": sb_nvidia,
            "PEXELS_API_KEY": sb_pexels,
            "PIXABAY_API_KEY": sb_pixabay,
            "NAVER_CUSTOMER_ID": sb_naver_cid,
            "NAVER_ACCESS_LICENSE": sb_naver_license,
            "NAVER_SECRET_KEY": sb_naver_secret,
            "NAVER_CLIENT_ID": sb_naver_client_id,
            "NAVER_CLIENT_SECRET": sb_naver_client_secret,
            "NOTION_TOKEN": sb_notion_token,
            "NOTION_DATABASE_ID": sb_notion_db,
            "GOOGLE_DRIVE_FOLDER_URL": sb_gdrive_url,
            "GOOGLE_SERVICE_ACCOUNT_JSON": sb_gdrive_sa,
        }
        try:
            update_dotenv_file(DOTENV_PATH, _keys_vals)
            for k, v in _keys_vals.items():
                if v:
                    os.environ[k] = v
            st.success("✅ .env에 저장 완료!")
            st.rerun()
        except Exception as e:
            st.error(f"❌ 저장 중 오류 발생: {e}")

    st.markdown("---")
    # .env 파일 현재 설정 여부 요약
    _configured = [k for k in [
        "OPENROUTER_API_KEY", "NVIDIA_API_KEY", "PEXELS_API_KEY",
        "NAVER_CUSTOMER_ID", "NOTION_TOKEN", "GOOGLE_DRIVE_FOLDER_URL"
    ] if _env_val(k)]
    st.caption(f"✅ {len(_configured)}/6 주요 API 설정됨")

# -------------------------------------------------------------------
# 전역 설정 및 API 키 (사이드바 저장값 기반)
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

# LLM API 키: OpenRouter > NVIDIA 우선순위
nvidia_api_key = _env_val("OPENROUTER_API_KEY") or _env_val("NVIDIA_API_KEY")
pexels_api_key = _env_val("PEXELS_API_KEY")
pixabay_api_key = _env_val("PIXABAY_API_KEY")

col_key_info, col_model = st.columns([2, 2])
with col_key_info:
    _llm_set = bool(nvidia_api_key)
    _pexels_set = bool(pexels_api_key)
    _pixabay_set = bool(pixabay_api_key)
    _key_label = ("✅ LLM API 설정됨" if _llm_set else "⚠️ LLM API 미설정 (사이드바에서 입력)")
    st.info(_key_label)
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
        # NVIDIA가 종료한 모델은 410 Gone을 돌려준다. mistral-nemotron은 2026-09-28에 종료됐고
        # llama-3.1-70b/8b는 NVIDIA 모델 목록에서 빠졌다. 아래는 2026-09-29에 응답을 확인한 모델이다.
        model_opts = {
            "moonshotai/kimi-k3": "🌙 Kimi K3 (추천/무료)",
            "nvidia/nemotron-3-super-120b-a12b": "🌟 Nemotron 3 Super 120B (무료)",
            "nvidia/nemotron-3-ultra-550b-a55b": "🔥 Nemotron 3 Ultra 550B (무료)",
            "deepseek-ai/deepseek-v4.1-flash": "🐋 DeepSeek V4.1 Flash (무료)",
            "openai/gpt-oss-20b": "💡 GPT-OSS 20B (무료)",
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
tab_keyword, tab_a_grade, tab_video, tab_tracker = st.tabs([
    "📊 키워드 발굴 & 대량 분석",
    "🏆 A급 소재 탐색",
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
        st.markdown("아래 표에서 키워드를 선택하면 **캡컷 제작**에 자동 연동됩니다.")
        
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
# [탭 2] A급 소재 탐색 & 브랜드 연결 계정 추적
# ===================================================================
with tab_a_grade:
    render_a_grade_view()


# ===================================================================
# [탭 3] 캡컷 영상 자동 생성
# ===================================================================
with tab_video:
    mode = st.radio("편집 방식", ["레퍼런스 기반 편집", "기존 자동 생성"], horizontal=True, key="re_edit_mode")
    if mode == "레퍼런스 기반 편집":
        render_reference_editor()
    else:
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
                    "model": model if model else "moonshotai/kimi-k3",
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
        default_source_folders = [
            r"C:\Users\5700G\Desktop\윤라영님모델_소스",
            r"C:\Users\5700G\Desktop\샤오홍슈 소스",
        ]
        default_source_folders = [path for path in default_source_folders if os.path.isdir(path)]
        source_folder_text = st.text_area(
            "📁 로컬 미디어 소스 폴더 (한 줄에 하나씩)",
            value="\n".join(default_source_folders),
            height=90,
        )
        local_media_folders = [line.strip().strip('"') for line in source_folder_text.splitlines() if line.strip()]
        local_media_folder = local_media_folders[0] if local_media_folders else ""

        @st.cache_data(show_spinner=False)
        def _audio_seconds(path: str, mtime: float) -> float:
            from pycapcut import AudioMaterial
            return AudioMaterial(path).duration / 1_000_000

        def _measured_sentence_seconds(sentence_key: tuple) -> dict:
            """문장별 오디오 검수에서 미리 만든 음성이 있으면 그 실제 길이로 컷을 계획한다."""
            if st.session_state.get("precomputed_audio_script_key") != sentence_key:
                return {}
            measured = {}
            for idx, path in (st.session_state.get("precomputed_audio") or {}).items():
                if path and os.path.exists(path):
                    try:
                        measured[idx] = _audio_seconds(path, os.path.getmtime(path))
                    except Exception:
                        pass
            return measured

        media_mapping = {}
        shot_source_plan = {}  # {문장 인덱스: [{"text", "weight", "sources": [선택 소스, 대체 후보...]}]}
        if local_media_folders and all(os.path.isdir(folder) for folder in local_media_folders):
            try:
                from pipeline.local_media_selector import ROLE_LABELS, build_media_catalog, rank_shot_sources
                from pipeline.context_media_planner import merge_ai_picks, pick_sources_with_llm
                from pipeline.shot_planner import MAX_SHOT_SEC

                media_catalog = build_media_catalog(local_media_folders)
                if media_catalog:
                    auto_media = st.checkbox(
                        f"대본 문맥에 맞는 로컬 소스 자동 배치 (컷당 최대 {MAX_SHOT_SEC:g}초)", value=True
                    )
                    llm_key = nvidia_api_key or os.environ.get("OPENROUTER_API_KEY", "")
                    llm_model = model_choice if nvidia_api_key else ""
                    use_ai_context = st.checkbox(
                        "🤖 AI가 대본 전체 문맥을 읽고 컷별 소스 고르기",
                        value=bool(llm_key),
                        disabled=not (auto_media and llm_key),
                        help="대본과 소스의 폴더·파일 이름(PC 전체 경로 제외)을 위에서 선택한 LLM에 보내 문맥에 맞는 소스를 고릅니다. "
                             "실패하면 파일명 규칙 기반 추천을 씁니다.",
                    )
                    with st.expander("🎬 컷별 소스 추천 및 수정", expanded=True):
                        st.caption(
                            f"문장을 의미 단위 컷으로 나누고, 소스 하나가 {MAX_SHOT_SEC:g}초를 넘지 않게 배치합니다. "
                            "추천은 컷의 단어, 같은 문장과 앞뒤 문장의 흐름, 장면 역할(후킹·문제·결과·구매 유도)을 함께 봅니다. "
                            f"실제 음성이 길어져 {MAX_SHOT_SEC:g}초를 넘는 컷은 생성할 때 다음 추천 소스로 한 번 더 나눕니다."
                        )
                        sentence_key = tuple(
                            s["full_sentence"] for s in split_script_by_sentences_and_phrases(script_text, max_chars_per_phrase=18)
                        )
                        script_shots = plan_script_shots(
                            script_text,
                            speech_speed=st.session_state.get("sb_speech_speed", 1.0),
                            measured_seconds=_measured_sentence_seconds(sentence_key),
                        )
                        ranking = rank_shot_sources(script_shots, media_catalog) if auto_media else []

                        if auto_media and use_ai_context and llm_key and script_shots:
                            ai_request_key = (
                                tuple((s["sentence"], tuple(shot["text"] for shot in s["shots"])) for s in script_shots),
                                tuple(item.path for item in media_catalog),
                                llm_model,
                            )
                            refresh_ai = st.button("🔄 AI 문맥 분석 다시 하기", key="btn_ai_shot_refresh")
                            if refresh_ai or st.session_state.get("ai_shot_request_key") != ai_request_key:
                                with st.spinner("🤖 AI가 대본 문맥을 읽고 컷별 소스를 고르는 중..."):
                                    try:
                                        picks, used_model = pick_sources_with_llm(
                                            script_shots, media_catalog, llm_key, llm_model
                                        )
                                        st.session_state["ai_shot_picks"] = picks
                                        st.session_state["ai_shot_model"] = used_model
                                        st.session_state["ai_shot_error"] = ""
                                    except Exception as err:
                                        st.session_state["ai_shot_picks"] = {}
                                        st.session_state["ai_shot_model"] = ""
                                        st.session_state["ai_shot_error"] = str(err)[:300]
                                st.session_state["ai_shot_request_key"] = ai_request_key
                            ai_picks = st.session_state.get("ai_shot_picks") or {}
                            used_model = st.session_state.get("ai_shot_model", "")
                            if st.session_state.get("ai_shot_error"):
                                st.warning(f"AI 문맥 분석에 실패해 규칙 기반 추천을 씁니다: {st.session_state['ai_shot_error']}")
                            else:
                                total_cuts = sum(len(s["shots"]) for s in script_shots)
                                fallback_note = (f" 선택한 모델이 응답하지 않아 {used_model}로 분석했습니다."
                                                 if llm_model and used_model and used_model != llm_model else "")
                                st.caption(f"AI({used_model})가 전체 {total_cuts}컷 중 {len(ai_picks)}컷의 소스를 골랐습니다."
                                           f"{fallback_note}")
                            ranking = merge_ai_picks(ranking, ai_picks, script_shots)

                        media_labels = {item.path: item.label for item in media_catalog}
                        media_options = ["(소스 없음)"] + [item.path for item in media_catalog]
                        option_index = {path: idx for idx, path in enumerate(media_options)}
                        for s_plan in script_shots:
                            s_idx = s_plan["index"]
                            timing = "실측" if s_plan["measured"] else "예상"
                            st.markdown(
                                f"**문장 {s_idx + 1}** · {ROLE_LABELS.get(s_plan['role'], s_plan['role'])} · "
                                f"{timing} {s_plan['duration_sec']:.1f}초 → 컷 {len(s_plan['shots'])}개"
                            )
                            for k, shot in enumerate(s_plan["shots"]):
                                candidates = ranking[s_idx][k] if s_idx < len(ranking) and k < len(ranking[s_idx]) else []
                                recommended = candidates[0]["path"] if candidates else None
                                widget_digest = hashlib.md5(f"{shot['text']}|{recommended}".encode("utf-8")).hexdigest()[:10]
                                selected_file = st.selectbox(
                                    f"컷 {k + 1} · 약 {shot['duration_sec']:.1f}초 · {shot['text']}",
                                    options=media_options,
                                    index=option_index.get(recommended, 0),
                                    format_func=lambda path: media_labels.get(path, path),
                                    key=f"shot_src_{s_idx}_{k}_{widget_digest}",
                                )
                                notes = [f"추천 근거: {candidates[0]['reason']}"] if candidates else ["추천 소스 없음"]
                                if shot["duration_sec"] > MAX_SHOT_SEC:
                                    notes.append(f"{MAX_SHOT_SEC:g}초를 넘으면 다음 추천 소스로 컷을 나눕니다")
                                st.caption(" · ".join(notes))
                                if selected_file == "(소스 없음)":
                                    sources = []
                                else:
                                    sources = [selected_file] + [c["path"] for c in candidates if c["path"] != selected_file]
                                shot_source_plan.setdefault(s_idx, []).append(
                                    {"text": shot["text"], "weight": shot["weight"], "sources": sources}
                                )
                else:
                    st.warning("입력하신 폴더에 영상이나 이미지 파일(.mp4, .mov, .jpg, .png)이 없습니다.")
            except Exception as e:
                st.error(f"폴더를 읽는 중 오류가 발생했습니다: {e}")
        elif local_media_folders:
            st.warning("소스 폴더 경로 중 존재하지 않는 항목이 있습니다.")

        # -------------------------------------------------------------------
        # 🎧 문장별 오디오 검수 & 부분 재생성 (선택)
        # -------------------------------------------------------------------
        sentence_structures = []
        if script_text.strip():
            sentence_structures = split_script_by_sentences_and_phrases(script_text, max_chars_per_phrase=18)

        if sentence_structures:
            audio_script_key = tuple(item["full_sentence"] for item in sentence_structures)
            if st.session_state.get("precomputed_audio_script_key") != audio_script_key:
                st.session_state["precomputed_audio"] = {}
                st.session_state["precomputed_audio_script_key"] = audio_script_key
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
                                ("🐟 보이스1 (남성, 중년, 대화체)", "fish_8cf5ee4cb0224c109852a206f185a05f"),
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
                    ("🐟 [Fish Audio] 라영님", "fish_acd596a6cb6a43d6bf4b2a5585743c2c"),
                    ("🐟 [Fish Audio] 맑고 생기 있는 여성", "fish_ff61737dc0614062ba8bc5d0abb63b3a"),
                    ("🐟 [Fish Audio] 보이스1 (남성, 중년, 대화체)", "fish_8cf5ee4cb0224c109852a206f185a05f"),
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
        from pipeline.capcut_font_catalog import available_user_fonts

        installed_fonts = available_user_fonts()
        font_options = list(installed_fonts) or ["Pretendard"]
        font_col1, font_col2 = st.columns(2)
        with font_col1:
            hook_font_name = st.selectbox(
                "훅 자막 폰트", font_options,
                index=font_options.index("양굵은구조폰트") if "양굵은구조폰트" in font_options else 0,
            )
        with font_col2:
            body_font_name = st.selectbox(
                "본문 자막 폰트", font_options,
                index=font_options.index("메모먼트꾹꾹체") if "메모먼트꾹꾹체" in font_options else 0,
            )
        result_col, cta_col = st.columns(2)
        with result_col:
            result_font_name = st.selectbox(
                "결과·만족 자막 폰트", font_options,
                index=font_options.index("상상토끼 꽃집막내딸") if "상상토끼 꽃집막내딸" in font_options else 0,
            )
        with cta_col:
            cta_font_name = st.selectbox(
                "구매 안내 자막 폰트", font_options,
                index=font_options.index("김씨와일드각체") if "김씨와일드각체" in font_options else 0,
            )
        st.caption("기본 위치: X 0, Y -200. 속초바다 돋움체는 오른쪽으로 8° 기울입니다.")
        reference_sfx_project = os.path.join(
            os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local"),
            "CapCut", "User Data", "Projects", "com.lveditor.draft", "0928 (3)",
        )
        use_reference_sfx = st.checkbox(
            "0928 (3)의 CapCut 내장 효과음 배치",
            value=os.path.isfile(os.path.join(reference_sfx_project, "draft_content.json")),
            help="훅·문제·결과·구매 안내에 샘플 프로젝트의 내장 효과음을 최대 4개 배치합니다.",
        )
        if "상상토끼 꽃집막내딸" not in installed_fonts:
            st.caption("상상토끼 꽃집막내딸 폰트 파일은 현재 PC에서 찾지 못해 선택 목록에서 제외했습니다.")

        saved_presets = capcut_tracker.load_presets()
        col_preset, col_preset_info = st.columns([2, 2])
        with col_preset:
            preset_options = [("기본 AdForge 스타일 (선택한 폰트 + 기본 효과)", None)]
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
                    if curr_p.get("animations"):
                        desc_parts.append("자막 애니메이션")
                    st.caption("✨ **적용될 에셋:** " + (" / ".join(desc_parts) if desc_parts else "자막 디자인 적용"))
            else:
                st.caption("기본 스타일은 CapCut 내장 전환·영상 효과·자막 애니메이션을 장면별로 배치합니다.")

        st.markdown("---")

        # 🎬 캡컷 프로젝트 생성 실행
        if st.button("🎬 캡컷 편집 초안 생성", use_container_width=True, type="primary"):
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
                                shot_plan=shot_source_plan,
                                speech_speed=speech_speed,
                                voice_overrides=st.session_state.get("voice_overrides", {}),
                                precomputed_audio=st.session_state.get("precomputed_audio", {}),
                                preset_id=selected_preset_id,
                                hook_font_name=hook_font_name,
                                body_font_name=body_font_name,
                                result_font_name=result_font_name,
                                cta_font_name=cta_font_name,
                                reference_sfx_project=reference_sfx_project if use_reference_sfx else "",
                            )
                            st.success(f"🎉 성공적으로 캡컷 프로젝트 '{project_name}' 초안을 생성했습니다!")
                            from pipeline.capcut_draft_audit import audit_draft

                            draft_root = os.path.join(
                                os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local"),
                                "CapCut", "User Data", "Projects", "com.lveditor.draft", project_name,
                            )
                            audit = audit_draft(draft_root)
                            clips = audit["clips"]
                            effects = audit["effects"]
                            st.caption(
                                f"타임라인 연결 확인: 영상 {clips['video']}개 · 음성 {clips['audio']}개 · "
                                f"내장 효과음 {clips['sfx']}개 · 자막 {clips['text']}개 · 전환 {effects['transitions']}개 · "
                                f"영상 효과 {effects['video_effects']}개 · "
                                f"자막 애니메이션 {effects['material_animations']}개 · "
                                f"가장 긴 컷 {audit['longest_video_clip_sec']:.2f}초"
                            )
                            if clips["video"] == 0:
                                st.warning("영상 소스가 배치되지 않았습니다. 컷별 소스 선택을 확인해주세요.")
                            if selected_preset_id:
                                st.info("선택한 프리셋의 자막 스타일·일부 효과·전환 적용을 시도했습니다. CapCut에서 실제 표시를 확인해주세요.")
                            st.info("💡 PC의 캡컷(CapCut) 프로그램을 열면 임시 보관함에서 새로 생성된 프로젝트를 즉시 확인하실 수 있습니다.")
                    except Exception as e:
                        st.error(f"오류 발생: {e}")

    # ===================================================================
    # [탭 4] 캡컷 로컬 프로젝트 실시간 추적 및 스타일 추출
    # ===================================================================
with tab_tracker:
    render_capcut_tracker_view()
