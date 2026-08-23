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
    sheet_url = "https://docs.google.com/spreadsheets/d/1-xfToD-ns9nBwj7Eh0URGOKc_YWcxxt5a3vJXgRqz9Q/export?format=csv"
    try:
        df = pd.read_csv(sheet_url)
        # 컬럼명의 개행문자 제거 및 공백 정리
        df.columns = df.columns.str.replace(r'\n', ' ', regex=True).str.strip()
        
        if '키워드' in df.columns:
            df = df.dropna(subset=['키워드'])
            # 첫 번째 데이터 행이 고유번호 안내인 경우 제외
            if len(df) > 0 and df.iloc[0]['키워드'] == '고유번호':
                df = df.iloc[1:]
                
        # --- 네이버 클립 6탭 이내 노출 조건 필터링 ---
        tab_cols = ['1탭', '2탭', '3탭', '4탭', '5탭', '6탭']
        mask = pd.Series([False] * len(df), index=df.index)
        for col in tab_cols:
            if col in df.columns:
                mask = mask | df[col].astype(str).str.contains('네이버 클립', na=False)
        df = df[mask]
        # ---------------------------------------------
        
        # 필터링할 주요 컬럼만 추출 (정규화된 이름에 맞춰서)
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
            
    # 호환성을 위해 선택된 키워드를 전역 변수처럼 처리
    if len(event.selection.rows) > 0:
        selected_idx = event.selection.rows[0]
        selected_keyword = df_keywords.iloc[selected_idx]['키워드']



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
def auto_format_subtitle(text: str, max_chars: int = 8) -> str:
    """한국어 자막 텍스트를 6~8자 단위로 자동 줄바꿈"""
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
            
            # 이미 짧으면 그대로
            if len(sentence) <= max_chars:
                result_lines.append(sentence)
                continue
            
            # 긴 문장: 공백 기준으로 토큰 분리 후 max_chars씩 묶기
            tokens = sentence.split(' ')
            current_line = ""
            
            for token in tokens:
                test = (current_line + token).strip()
                if len(test) <= max_chars:
                    current_line = test + " "
                else:
                    if current_line.strip():
                        result_lines.append(current_line.strip())
                    # 토큰 자체가 max_chars보다 길면 글자수로 쪼개기
                    if len(token) > max_chars:
                        for i in range(0, len(token), max_chars):
                            result_lines.append(token[i:i+max_chars])
                        current_line = ""
                    else:
                        current_line = token + " "
            
            if current_line.strip():
                result_lines.append(current_line.strip())
        
        result_lines.append("")  # 단락 사이 빈 줄
    
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
                        keyword=selected_keyword,
                        pexels_api_key=pexels_api_key,
                        pixabay_api_key=pixabay_api_key,
                        voice=actual_voice_choice,
                        el_api_key=el_api_key,
                        local_media_folder=local_media_folder,
                        media_mapping=media_mapping
                    )
                    st.success(f"성공적으로 캡컷 프로젝트 '{project_name}' 초안을 생성했습니다!")
                    st.info("PC의 캡컷(CapCut) 프로그램을 열면 임시 보관함에서 확인하실 수 있습니다.")
            except Exception as e:
                st.error(f"오류 발생: {e}")
