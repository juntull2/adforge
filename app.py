import os
import re
import pandas as pd
import streamlit as st
from naver_clip_adforge import (
    build_capcut_project_for_naver_clip,
    generate_hailuo_prompts_stream,
    generate_image_prompts_stream,
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

PEXELS_API_KEY_FILE = "pexels_api_key.txt"
cached_pexels_api_key = ""
if os.path.exists(PEXELS_API_KEY_FILE):
    with open(PEXELS_API_KEY_FILE, "r", encoding="utf-8-sig") as f:
        cached_pexels_api_key = f.read().strip()

col_key, col_pexels, col_model = st.columns([2, 2, 2])
with col_key:
    nvidia_api_key = st.text_input("🔑 NVIDIA API Key (대본 & 프롬프트 생성용)", type="password", value=cached_api_key, placeholder="nvapi-...")
    if nvidia_api_key and nvidia_api_key != cached_api_key:
        with open(API_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(nvidia_api_key)
with col_pexels:
    pexels_api_key = st.text_input("📷 Pexels API Key (세로 스톡 영상 다운로드)", type="password", value=cached_pexels_api_key, placeholder="없으면 Mixkit 자동 fallback")
    if pexels_api_key and pexels_api_key != cached_pexels_api_key:
        with open(PEXELS_API_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(pexels_api_key)
with col_model:
    model_choice = st.selectbox(
        "🧠 NVIDIA 모델 선택",
        options=[
            "nvidia/nemotron-3-ultra-550b-a55b",        # 🥇 숏폼 및 전략 기획 최고 성능 (기본값)
            "meta/llama-3.3-70b-instruct",
            "nvidia/llama-3.1-nemotron-70b-instruct",
            "meta/llama-3.1-70b-instruct",
        ]
    )

st.markdown("---")

# -------------------------------------------------------------------
# 구글 시트 연동 (키워드 추천)
# -------------------------------------------------------------------
st.subheader("📊 타겟 키워드 분석 데이터 (Google Sheet 연동)")

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
        st.caption("아래 링크를 우클릭해서 시크릿 창으로 엽니다.")
        with st.container(height=400):
            for _, row in df_keywords.iterrows():
                kw = row['키워드']
                url = f"https://m.search.naver.com/search.naver?query={kw}"
                st.markdown(f"👉 **[{kw}]({url})**")
            
    # 호환성을 위해 선택된 키워드를 전역 변수처럼 처리
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

with st.expander("⚙️ 고급 대본 기획 설정 (프롬프트 & 벤치마킹)", expanded=False):
    st.markdown("AI에게 역할을 부여하는 프롬프트와, 따라 하고 싶은 대박 숏폼 대본(벤치마킹)을 직접 입력하여 생성 퀄리티를 비약적으로 높여보세요.")
    
    # 포맷별 자동 프롬프트
    if "포맷 A" in video_format:
        default_system_prompt = """당신은 100만 바이럴을 만드는 숏폼 건강 정보 크리에이터입니다.
[포맷 A: 순수 정보형] — 제품명은 절대 언급하지 마세요. 오직 유익한 건강 꿀팁만 제공합니다.

핵심 규칙 (1M Viral & Twist Formula):
1. 초반 3초 후킹: 뻔한 질문("뻐근하시죠?") 절대 금지. 감각적 비유("바위가 누르는 느낌")나 역설/배제("어설프게 아픈 분 시청 금지")를 반드시 사용하세요.
2. 미드롤 CTA: 비법을 공개하기 직전에 "좋아요 먼저 누르고 따라하세요!"를 삽입하세요.
3. 구체적 넘버링: "1단계", "2단계" 형식으로 따라하기 쉽게 분해하세요.
4. 강력한 효과 시각화: "시원합니다" 대신 "혈류가 심장으로 솟구치고" 등 감각적으로 묘사하세요.
5. 지정 댓글 유도: "좋아요 부탁드려요" 금지. "댓글에 '시원해요'라고 남겨주세요"처럼 구체적 키워드를 제시하세요."""
    elif "포맷 B" in video_format:
        default_system_prompt = """당신은 100만 바이럴을 만드는 숏폼 마케터이자 일반인 크리에이터입니다.
[포맷 B: 간접 홍보형] — 영상의 80%는 순수 꿀팁, 마지막 20%에서 "제가 쓰는 기구는 댓글에 남길게요!"라고 자연스럽게 유도합니다. 영상 안에서 제품명은 절대 말하지 마세요.

핵심 규칙 (1M Viral & Twist Formula):
1. 초반 3초 후킹: 뻔한 질문 금지. 감각적 비유나 역설/배제("웬만한 마사지기 써봤는데 다 실망한 분들만 보세요")를 사용하세요.
2. 미드롤 CTA: 꿀팁 공개 직전 "좋아요 먼저 누르고 따라하세요!" 삽입.
3. 매몰비용 자극: "안 그래도 돈 쓴 것도 억울한데" 등으로 공감 극대화.
4. 간접 제품 유도: 꿀팁 제공 후 "그냥 손으로 하긴 힘들어서 저는 기구 하나 쓰는데, 댓글에 올릴게요!"처럼 자연스럽게 연결.
5. 지정 댓글 유도: "댓글에 '기구 궁금'이라고 남겨주세요!"처럼 제품 수요를 댓글로 모으세요."""
    else:  # 포맷 C
        default_system_prompt = """당신은 100만 바이럴을 만드는 제품 리뷰어이자 숏폼 마케터입니다.
[포맷 C: 직접 홍보형] — 제품명을 당당하게 언급하며 대안재(비싼 안마의자, 비싼 도수치료 등)와 비교하여 압도적인 가성비를 어필합니다.

핵심 규칙 (1M Viral & Twist Formula):
1. 초반 3초 후킹: 역설/배제 기법 사용 (예: "어설프게 아픈 분들은 사지 마세요 — 진짜 심한 분들만 보세요").
2. 대안재 비교: "거대하고 비싼 안마의자 대신", "도수치료비 쏟아붓다가" 등으로 기존 대체재의 단점을 먼저 부각시키세요.
3. 미드롤 CTA: 제품 공개 직전 "좋아요 먼저 누르세요!" 삽입.
4. 매몰비용 자극 + 가성비 앵커링: "올해 또 예쁜 쓰레기 사실 건가요?" → "월 만원대로 평생 뽕뽑는다"처럼 손실 회피와 가성비를 동시에 찌르세요.
5. 지정 댓글 + 한정성 마감: "댓글에 '할인 링크'라고 남겨주세요!"처럼 구매 의향자를 댓글로 집결시키세요."""

    custom_system_prompt = st.text_area("🔧 시스템 프롬프트 (포맷별 자동 변경)", value=default_system_prompt, height=250)
    benchmark_script = st.text_area("📈 벤치마킹 대본 (참고할 타사 대박 숏폼 대본 원문)", value="", placeholder="예: 이거 모르면 평생 후회합니다! 매일 아침 얼굴 붓기 1분만에 빼는 비법...", height=150)

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
                    benchmark_script
                ):
                    yield chunk
                    
            raw_output = st.write_stream(script_stream_generator())
            st.session_state["raw_script_output"] = raw_output
            
            # Parsing the output robustly with regex
            script_part = raw_output
            comment_part = ""
            desc_part = ""
            
            script_matches = list(re.finditer(r'={2,}\s*SCRIPT\s*={2,}', raw_output, re.IGNORECASE))
            comment_matches = list(re.finditer(r'={2,}\s*COMMENT\s*={2,}', raw_output, re.IGNORECASE))
            desc_matches = list(re.finditer(r'={2,}\s*DESCRIPTION\s*={2,}', raw_output, re.IGNORECASE))
            
            # Find the indices of each delimiter
            s_idx = script_matches[-1].end() if script_matches else 0
            c_idx = comment_matches[-1].start() if comment_matches else -1
            c_end = comment_matches[-1].end() if comment_matches else -1
            d_idx = desc_matches[-1].start() if desc_matches else -1
            d_end = desc_matches[-1].end() if desc_matches else -1
            
            if script_matches and comment_matches and desc_matches:
                script_part = raw_output[s_idx:c_idx].strip()
                comment_part = raw_output[c_end:d_idx].strip()
                desc_part = raw_output[d_end:].strip()
            elif script_matches and comment_matches:
                script_part = raw_output[s_idx:c_idx].strip()
                comment_part = raw_output[c_end:].strip()
            elif comment_matches and desc_matches:
                script_part = raw_output[:c_idx].strip()
                comment_part = raw_output[c_end:d_idx].strip()
                desc_part = raw_output[d_end:].strip()
            else:
                # Fallback if delimiters are missing
                script_part = raw_output.strip()
                
            # 한 문장마다 강제 줄바꿈 처리 (마침표, 물음표, 느낌표 뒤)
            script_part = re.sub(r'([.?!])\s+', r'\1\n', script_part)
                
            # If AI left conversational text like "Here is the script:", we can try to strip it,
            # but using ====SCRIPT==== delimiter usually prevents this.
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
