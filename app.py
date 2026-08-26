import os
import re
import pandas as pd
import streamlit as st
from naver_clip_adforge import build_capcut_project_for_naver_clip, split_script_by_sentences_and_phrases

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
st.markdown('<div class="sub-header">대본 기획부터 캡컷 프로젝트 생성까지 원스톱!</div>', unsafe_allow_html=True)



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

col_key, col_pexels, col_pixabay, col_model = st.columns([1.5, 1.5, 1.5, 1.5])
with col_key:
    nvidia_api_key = st.text_input("🔑 LLM API Key", type="password", value=cached_api_key, placeholder="nvapi- / sk-or-")
    if nvidia_api_key and nvidia_api_key != cached_api_key:
        with open(API_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(nvidia_api_key)
with col_pexels:
    pexels_api_key = st.text_input("📷 Pexels API", type="password", value=cached_pexels_api_key, placeholder="Pexels (선택)")
    if pexels_api_key and pexels_api_key != cached_pexels_api_key:
        with open(PEXELS_API_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(pexels_api_key)
with col_pixabay:
    pixabay_api_key = st.text_input("📷 Pixabay API", type="password", value=cached_pixabay_api_key, placeholder="Pixabay (선택)")
    if pixabay_api_key and pixabay_api_key != cached_pixabay_api_key:
        with open(PIXABAY_API_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(pixabay_api_key)
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
# 구글 시트 연동 (키워드 추천)
# -------------------------------------------------------------------

@st.cache_data(ttl=3600)
def load_keyword_data():
    sheet_url = "https://docs.google.com/spreadsheets/d/1-xfToD-ns9nBwj7Eh0URGOKc_YWcxxt5a3vJXgRqz9Q/export?format=csv&gid=1956992404"
    try:
        df = pd.read_csv(sheet_url)
        # 컬럼명의 개행문자 제거 및 공백 정리
        df.columns = df.columns.str.replace(r'\n', ' ', regex=True).str.strip()
        
        if '키워드' in df.columns:
            df = df.dropna(subset=['키워드'])
            # 첫 번째 데이터 행이 고유번호 안내인 경우 제외
            if len(df) > 0 and df.iloc[0]['키워드'] == '고유번호':
                df = df.iloc[1:]
                
        if '접촉지점' in df.columns:
            df['접촉지점'] = pd.to_numeric(df['접촉지점'], errors='coerce').fillna(0)
                
        # (기존 클립 6탭 이내 필터링 제거됨 - 모든 키워드 분석용)
        
        # 필터링할 주요 컬럼만 추출 (정규화된 이름에 맞춰서)
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
    if st.button("🔄 데이터 최신화", width="stretch"):
        load_keyword_data.clear()
        st.rerun()

df_keywords = load_keyword_data()

selected_keyword = ""
if df_keywords is not None and not df_keywords.empty:
    st.markdown("아래 표에서 키워드를 선택하면 **'세부 주제'**에 자동으로 입력됩니다.")
    
    # '네이버 클립' 셀 강조 스타일링
    def highlight_clip(val):
        if '네이버 클립' in str(val):
            return 'background-color: #00C73C; color: white; font-weight: bold;'
        return ''
    
    tab_cols = [c for c in df_keywords.columns if '탭' in c]
    styled_df = df_keywords.style.map(highlight_clip, subset=tab_cols)
    
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
        search_kw = st.text_input("🔍 검색어 필터", key="mobile_search_filter")
        st.caption("아래 링크를 우클릭해서 시크릿 창으로 엽니다.")
        with st.container(height=400):
            for _, row in df_keywords.iterrows():
                kw = row['키워드']
                if search_kw and search_kw.lower() not in str(kw).lower():
                    continue
                url = f"https://m.search.naver.com/search.naver?query={kw}"
                st.markdown(f"👉 **[{kw}]({url})**")
            
    # 호환성을 위해 선택된 키워드를 전역 변수처럼 처리
    if len(event.selection.rows) > 0:
        selected_idx = event.selection.rows[0]
        selected_keyword = df_keywords.iloc[selected_idx]['키워드']

# -------------------------------------------------------------------
# STEP 1.5: 실시간 키워드 분석 및 대본 생성 (신규)
# -------------------------------------------------------------------
st.markdown("---")
st.subheader("🔍 실시간 키워드 탭 분석 및 자동 대본")
col_kw1, col_kw2 = st.columns([2, 1])

with col_kw1:
    rt_keyword = st.text_input("분석할 키워드를 입력하세요", placeholder="예: 허리찜질기")

with col_kw2:
    st.markdown(" ") # 여백
    st.markdown(" ")
    if st.button("분석 및 대본 자동 생성 준비", width="stretch"):
        if not rt_keyword:
            st.error("키워드를 입력해주세요.")
        else:
            with st.spinner("네이버 모바일 탭 순위 및 검색량 조회 중..."):
                from naver_scraper import get_naver_clip_rank, get_naver_search_volume
                from dotenv import load_dotenv
                import os
                
                load_dotenv()
                cust_id = os.environ.get("NAVER_CUSTOMER_ID", "")
                acc_lic = os.environ.get("NAVER_ACCESS_LICENSE", "")
                sec_key = os.environ.get("NAVER_SECRET_KEY", "")
                
                rank = get_naver_clip_rank(rt_keyword)
                vol = get_naver_search_volume(rt_keyword, cust_id, acc_lic, sec_key)
                
                st.session_state["rt_rank"] = rank
                st.session_state["rt_vol"] = vol
                st.session_state["rt_keyword"] = rt_keyword

if "rt_rank" in st.session_state:
    rank = st.session_state["rt_rank"]
    vol = st.session_state["rt_vol"]
    
    col_res1, col_res2 = st.columns(2)
    with col_res1:
        if rank > 0 and rank <= 6:
            st.success(f"✅ **[클립] 탭 노출 순위: {rank}번째 (합격)**")
        elif rank > 6:
            st.warning(f"⚠️ **[클립] 탭 노출 순위: {rank}번째 (6탭 밖)**")
        else:
            st.error(f"❌ **[클립] 탭을 찾을 수 없습니다.**")
            
    with col_res2:
        if vol["total"] > 0:
            st.info(f"📊 월간 검색량: {vol['total']:,} (모바일: {vol['mobile']:,})")
        else:
            st.warning("⚠️ 검색량 데이터 없음 (API 키 미설정 또는 조회 실패)")
            
    # 대본 생성 (제품 고정: 다피다 허리찜질기)
    st.markdown("#### ✨ AI 자동 대본 생성 (타겟: 4050, 제품: 다피다 허리찜질기 기준)")
    
    touchpoint_options = [
        "자동 판별 (키워드 기반)", "SEARCH_EXERCISE", "SEARCH_SYMPTOM", "SEARCH_PROBLEM",
        "SEARCH_PRODUCT", "SEARCH_ALTERNATIVE_PRODUCT", "SEARCH_COMPETITOR",
        "SEARCH_INFORMATION", "SEARCH_COMPARISON", "SEARCH_GIFT", "SEARCH_REVIEW",
        "SEARCH_LIFESTYLE", "DIRECT_PRODUCT", "CURIOSITY"
    ]
    user_tp = st.selectbox("🎯 Touchpoint 선택 (옵션)", touchpoint_options, index=0)
    
    if st.button("이 키워드로 대본 즉시 생성", type="primary", use_container_width=True):
        if not os.environ.get("OPENROUTER_API_KEY"):
            st.error("OPENROUTER_API_KEY 환경변수가 설정되지 않았습니다. .env 파일을 확인해주세요.")
        else:
            from script_engine import run_script_pipeline
            
            status_box = st.status("🚀 AI 대본 생성 파이프라인 가동 중...", expanded=True)
            pipeline = run_script_pipeline(
                keyword=rt_keyword,
                user_touchpoint=user_tp,
                product="다피다 허리찜질기",
                target="40~60대 허리 불편 사용자",
                content_goal="PRODUCT_CONVERSION",
                duration=45
            )
            
            final_result = None
            for update in pipeline:
                if update["step"] != "완료":
                    status_box.write(f"⏳ **{update['step']}** \n{update['detail']}")
                else:
                    final_result = update
                    
            status_box.update(label="대본 생성 완료!", state="complete", expanded=False)
            
            if final_result:
                st.session_state["generated_scripts"] = final_result["result"]
                st.session_state["intent_data"] = final_result["intent_data"]
                
    if "generated_scripts" in st.session_state:
        st.markdown("### 📝 생성된 대본 (A/B/C)")
        
        with st.expander("🔍 검색 의도 분석 결과 보기"):
            st.json(st.session_state["intent_data"])
            
        import re
        scripts_text = st.session_state["generated_scripts"]
        parts = re.split(r'(?=\[[A-C]안\s*\|.*\])', scripts_text)
        
        cols = st.columns(3)
        col_idx = 0
        
        def set_capcut_script(script_text):
            st.session_state["parsed_script"] = script_text
            
        for part in parts:
            part = part.strip()
            if not part: continue
            
            with cols[col_idx % 3]:
                # 컨테이너와 버튼 UI 정리
                st.text_area(f"버전 {col_idx+1}", value=part, height=350, key=f"disp_ta_{col_idx}")
                
                if st.button("🎬 캡컷 조립 (텍스트 넘기기)", key=f"capcut_btn_{col_idx}", on_click=set_capcut_script, args=(part,), use_container_width=True):
                    pass # Callback handles the state update
            col_idx += 1
st.markdown("---")
st.subheader("🚀 대량 키워드 실시간 분석 옵션 설정")
st.caption("구글 시트에 기재된 키워드를 기반으로 실시간 탭 순위와 최신 검색량을 조회합니다.")

col_opt1, col_opt2 = st.columns(2)
with col_opt1:
    min_contact = st.number_input("최소 접촉지점 점수", min_value=0, max_value=10, value=4, step=1, help="시트의 접촉지점이 이 점수 이상인 키워드만 1차로 필터링합니다.")
with col_opt2:
    min_volume = st.number_input("최소 총 검색량 (PC+모바일)", min_value=0, value=1000, step=100, help="API로 불러온 실시간 검색량이 이 수치 이상인 키워드만 최종 결과에 보여줍니다.")

if st.button("설정한 조건으로 키워드 일괄 분석 시작", width="stretch"):
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
                from dotenv import load_dotenv
                import os
                import time
                
                load_dotenv()
                cust_id = os.environ.get("NAVER_CUSTOMER_ID", "")
                acc_lic = os.environ.get("NAVER_ACCESS_LICENSE", "")
                sec_key = os.environ.get("NAVER_SECRET_KEY", "")
                
                results = []
                progress_bar = st.progress(0)
                
                for i, row in enumerate(target_df.itertuples()):
                    kw = getattr(row, '키워드')
                    time.sleep(0.3) # 봇 차단 방지 및 API 속도 조절
                    
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
    # 클립 노출(6위 이내)되고 검색량이 높은 순으로 정렬 표시
    res_df = st.session_state["bulk_results"]
    st.dataframe(res_df, width="stretch")

# -------------------------------------------------------------------
# STEP 2: 대본 입력 및 캡컷/Hailuo 자동화
# -------------------------------------------------------------------

st.markdown("---")
st.subheader("STEP 2: 캡컷 연동 및 자동 생성")

default_script = st.session_state.get("parsed_script", "")
script_text = st.text_area("📝 영상 자막(대본) 전문 (STEP 1에서 생성 시 자동 입력됨 / 직접 붙여넣기 가능)", value=default_script, height=200)

# 로컬 미디어 폴더 입력창 추가
local_media_folder = st.text_input("📁 로컬 미디어 소스 폴더 경로 (선택)", placeholder="예: C:\\Users\\User\\Videos\\Product")

media_mapping = {}
if local_media_folder and os.path.isdir(local_media_folder):
    try:
        valid_exts = ['.mp4', '.mov', '.jpg', '.jpeg', '.png']
        local_files = [f for f in os.listdir(local_media_folder) if os.path.splitext(f)[1].lower() in valid_exts]
        local_files.sort()
        
        if local_files:
            with st.expander("🎬 로컬 미디어 수동 매핑 (선택)", expanded=True):
                st.info("각 문장 재생 시 배경으로 표시될 로컬 미디어(영상/사진)를 선택하세요.")
                
                # 파싱해서 문장 목록 가져오기
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


# 🔀 자막 줄바꿈 자동 정리
def auto_format_subtitle(text: str, max_chars: int = 20) -> str:
    """한국어 자막 텍스트를 어절 단위로 자동 줄바꿈 (단어 끊김 방지)"""
    import re
    
    # 빈 줄 기준으로 단락 분리
    paragraphs = re.split(r'\n{2,}', text.strip())
    result_lines = []
    
    for para in paragraphs:
        # 단락 내 줄바꿈을 공백으로 합쳐서 하나의 텍스트로 만들기
        flat = re.sub(r'\n', ' ', para).strip()
        flat = re.sub(r' {2,}', ' ', flat)  # 중복 공백 제거
        
        if not flat:
            continue
        
        # 문장부호(. ! ?)로 먼저 분리
        sentences = re.split(r'(?<=[.!?])\s*', flat)
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            
            # 긴 문장: 공백 기준으로 어절 분리 후 max_chars 한도 내에서 묶기
            words = sentence.split(' ')
            current_line = ""
            
            for word in words:
                if not current_line:
                    current_line = word
                elif len(current_line) + 1 + len(word) <= max_chars:
                    current_line += " " + word
                else:
                    result_lines.append(current_line)
                    current_line = word
            
            if current_line:
                result_lines.append(current_line)
        
        result_lines.append("")  # 단락 사이 빈 줄
    
    return "\n".join(result_lines).strip()

col_fmt1, col_fmt2 = st.columns([1, 3])
with col_fmt1:
    fmt_chars = st.number_input("줄당 최대 글자 수", min_value=4, max_value=40, value=20, step=1)
with col_fmt2:
    if st.button("🔀 자막 줄바꿈 자동 정리 (붙여넣은 대본 → 자막 포맷)", width="stretch"):
        if not script_text.strip():
            st.error("대본이 비어있습니다!")
        else:
            formatted = auto_format_subtitle(script_text, max_chars=fmt_chars)
            st.session_state["parsed_script"] = formatted
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

from naver_clip_adforge import build_capcut_project_for_naver_clip

# -------------------------------------------------------------------
# 📹 레퍼런스 영상 학습 (스타일 프로필 생성)
# -------------------------------------------------------------------
st.markdown("---")
with st.expander("📹 레퍼런스 영상 학습 (스타일 프로필 생성)", expanded=False):
    st.markdown(
        "잘 만들어진 숏폼 영상들을 분석하여 자막 스타일·컷 리듬을 학습합니다. "
        "학습된 프로필은 이후 캡컷 프로젝트 생성 시 자동 적용됩니다."
    )

    ref_col1, ref_col2 = st.columns([2, 1])
    with ref_col1:
        ref_folder = st.text_input(
            "📁 레퍼런스 영상 폴더 경로",
            placeholder=r"예: C:\Users\임준모\Videos\references",
            help="분석할 .mp4 파일들이 있는 폴더 경로를 입력하세요."
        )
    with ref_col2:
        ref_profile_name = st.text_input(
            "💾 프로필 이름",
            value="default",
            help="분석 결과를 저장할 프로필 이름"
        )

    intensity_label = st.select_slider(
        "🎛️ 애니메이션 강도 제한",
        options=["subtle (절제)", "medium (보통)", "bold (강조)"],
        value="medium (보통)",
        help="subtle: 페이드인/슬라이드 등 자연스러운 효과만 허용 | medium: 팝/확대 추가 | bold: 글리치/폭발 효과 허용"
    )
    max_intensity = intensity_label.split(" ")[0]  # "subtle" | "medium" | "bold"
    st.session_state["max_intensity"] = max_intensity

    if ref_folder and os.path.isdir(ref_folder):
        mp4_files = [
            os.path.join(ref_folder, f)
            for f in os.listdir(ref_folder)
            if f.lower().endswith(".mp4")
        ]
        if mp4_files:
            st.info(f"📂 {len(mp4_files)}개 영상 감지: {', '.join([os.path.basename(f) for f in mp4_files[:5]])}" +
                    (f" 외 {len(mp4_files)-5}개" if len(mp4_files) > 5 else ""))

            if st.button("▶️ 레퍼런스 영상 분석 시작", type="primary"):
                from reference_analyzer import ReferenceAnalyzer
                analyzer = ReferenceAnalyzer(
                    openrouter_api_key=os.environ.get("OPENROUTER_API_KEY", nvidia_api_key),
                    nvidia_api_key=nvidia_api_key
                )

                progress_bar = st.progress(0.0)
                status_text = st.empty()

                def on_progress(frac, msg):
                    progress_bar.progress(min(frac, 1.0))
                    status_text.text(f"🔄 {msg}")

                try:
                    profile = analyzer.analyze_batch(
                        mp4_files,
                        profile_name=ref_profile_name,
                        progress_callback=on_progress
                    )
                    st.session_state["active_style_profile"] = profile
                    st.session_state["active_profile_name"] = ref_profile_name
                    progress_bar.progress(1.0)
                    status_text.text("✅ 분석 완료!")

                    st.success(f"✅ {len(mp4_files)}개 영상 분석 완료 — 프로필 '{ref_profile_name}' 저장됨")
                    cut = profile.get("cut_rhythm", {})
                    st.metric("평균 컷 간격", f"{cut.get('avg_cut_interval_sec', 0):.1f}초")

                except Exception as e:
                    st.error(f"분석 오류: {e}")
        else:
            st.warning("해당 폴더에 .mp4 파일이 없습니다.")
    elif ref_folder:
        st.error("폴더 경로를 찾을 수 없습니다.")

    # 저장된 프로필 로딩
    from reference_analyzer import ReferenceAnalyzer
    saved_profiles = ReferenceAnalyzer.list_profiles()
    if saved_profiles:
        st.markdown("**💾 저장된 프로필 불러오기**")
        profile_options = {p["name"]: p for p in saved_profiles}
        selected_prof = st.selectbox(
            "프로필 선택",
            options=["(사용 안 함)"] + list(profile_options.keys()),
            key="profile_selector"
        )
        if selected_prof != "(사용 안 함)":
            loaded = ReferenceAnalyzer.load_profile(selected_prof)
            if loaded:
                st.session_state["active_style_profile"] = loaded
                st.session_state["active_profile_name"] = selected_prof
                p = profile_options[selected_prof]
                st.caption(
                    f"📊 {p['source_count']}개 영상 기반 | "
                    f"평균 컷 {p['avg_cut_interval']:.1f}초 | "
                    f"총 {p['total_cuts']}컷 학습"
                )
        elif selected_prof == "(사용 안 함)":
            st.session_state.pop("active_style_profile", None)
            st.session_state.pop("active_profile_name", None)

# -------------------------------------------------------------------
# 🎨 AI 크리에이티브 연출 (옵시디언 마케팅 지식 기반)
# -------------------------------------------------------------------
st.markdown("---")
use_ai_direction = st.checkbox(
    "🎨 AI 크리에이티브 연출 (옵시디언 마케팅 지식 기반)",
    value=False,
    help="옵시디언 볼트의 마케팅 교육 매뉴얼을 기반으로 "
         "자막 스타일, 애니메이션, 강조 효과를 AI가 자동 결정합니다."
)

if use_ai_direction and script_text.strip():
    col_preview, col_mode = st.columns([3, 1])
    
    with col_mode:
        direction_mode = st.radio(
            "분석 모드",
            ["🤖 AI 분석 (LLM)", "⚡ 규칙 기반 (즉시)"],
            index=1,
            help="AI 분석은 LLM API를 호출하여 더 정교하게 분석합니다. 규칙 기반은 즉시 결과를 제공합니다."
        )
    
    with col_preview:
        if st.button("🔍 연출 미리보기", use_container_width=True):
            from creative_director import CreativeDirector
            active_profile = st.session_state.get("active_style_profile")
            active_intensity = st.session_state.get("max_intensity", "medium")
            cd = CreativeDirector(
                max_intensity=active_intensity,
                style_profile=active_profile
            )
            if active_profile:
                st.caption(f"📊 프로필 '{st.session_state.get('active_profile_name', '')}' 적용 중 | 강도: {active_intensity}")
            
            if direction_mode.startswith("🤖"):
                with st.spinner("🎬 옵시디언 마케팅 지식 로딩 + AI 대본 분석 중..."):
                    or_api_key = os.environ.get("OPENROUTER_API_KEY", nvidia_api_key)
                    direction = cd.analyze_script(script_text, api_key=or_api_key, model=model_choice)
            else:
                direction = cd._fallback_analysis(script_text)
                
            st.session_state["creative_direction"] = direction

    if "creative_direction" in st.session_state:
        direction = st.session_state["creative_direction"]
        role_emoji = {
            "hook": "🔥", "empathy": "💭", "agitate": "⚡",
            "evidence": "📊", "solution": "💡", "usp": "🏆",
            "cta": "🎯", "transition": "🔄", "normal": "📝"
        }
        
        with st.expander("📋 AI 연출 지시서 미리보기", expanded=True):
            for item in direction.get("sentences", []):
                role = item.get("role", "normal")
                emoji = role_emoji.get(role, "📝")
                text_preview = item.get("text", "")[:45]
                intro = item.get("text_intro", "없음") or "없음"
                loop = item.get("text_loop_anim", "없음") or "없음"
                reasoning = item.get("reasoning", "")
                psychology = item.get("psychology", "")
                
                st.markdown(
                    f"**{emoji} [{role.upper()}]** {text_preview}  \n"
                    f"　└ 입장: `{intro}` | 루프: `{loop}`"
                    + (f" | 💡 _{reasoning}_" if reasoning and "폴백" not in reasoning else "")
                    + (f" | 🧠 _{psychology}_" if psychology else "")
                )

if st.button("🎬 캡컷 프로젝트 1초 자동 생성", width="stretch"):
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
                    
                    # AI 연출 지시서 준비 (체크 시에만)
                    cd_data = None
                    if use_ai_direction:
                        active_profile = st.session_state.get("active_style_profile")
                        active_intensity = st.session_state.get("max_intensity", "medium")
                        
                        if "creative_direction" in st.session_state:
                            # 이미 미리보기를 한 경우 재사용
                            cd_data = st.session_state["creative_direction"]
                        else:
                            # 미리보기 없이 생성하는 경우 즉석 분석
                            from creative_director import CreativeDirector
                            cd = CreativeDirector(
                                max_intensity=active_intensity,
                                style_profile=active_profile
                            )
                            cd_data = cd._fallback_analysis(script_text)
                    
                    project_name = build_capcut_project_for_naver_clip(
                        script_text=script_text,
                        keyword=selected_keyword,
                        pexels_api_key=pexels_api_key,
                        pixabay_api_key=pixabay_api_key,
                        voice=actual_voice_choice,
                        el_api_key=el_api_key,
                        local_media_folder=local_media_folder,
                        media_mapping=media_mapping,
                        creative_direction=cd_data
                    )
                    st.success(f"성공적으로 캡컷 프로젝트 '{project_name}' 초안을 생성했습니다!")
                    if cd_data:
                        st.info("🎨 AI 크리에이티브 연출이 적용되었습니다. 캡컷에서 자막 애니메이션을 확인하세요!")
                    else:
                        st.info("PC의 캡컷(CapCut) 프로그램을 열면 임시 보관함에서 확인하실 수 있습니다.")
            except Exception as e:
                st.error(f"오류 발생: {e}")

