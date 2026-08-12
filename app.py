import os
import re
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

mode = st.radio("작업 모드 선택", ["📌 단일 기획 및 제작", "🚀 대량 기획 및 제작 (10편)"], horizontal=True)
st.markdown("---")

if mode == "🚀 대량 기획 및 제작 (10편)":
    st.subheader("🚀 대량 자동 제작 (10편)")
    st.info("메인 주제를 입력하면 관련 세부 주제 10개를 자동 추천하고, 대본부터 캡컷 영상까지 한 번에 생성합니다.")
    
    col_cat, col_sub = st.columns(2)
    with col_cat:
        topic_category = st.selectbox(
            "📌 타겟 카테고리 (순위별) ",
            ["1순위: 건강 (관여도 높은 질병, 허리 보호 등)", "2순위: 골프 (시니어 스포츠)", "3순위: 미용 (주름, 머리 등)"]
        )
    with col_sub:
        main_topic = st.text_input("✏️ 메인 주제", placeholder="예) 허리 통증")
        
    col_fmt, col_prod = st.columns(2)
    with col_fmt:
        video_format = st.selectbox(
            "🎬 영상 포맷(전략) 선택 ",
            [
                "포맷 A (순수 정보성): 제품 노출 0%, 꿀팁만 제공",
                "포맷 B (간접 홍보): 꿀팁 + '제가 쓰는 기구는 댓글에~' (영상 내 브랜드 금지)",
                "포맷 C (직접 홍보): 대놓고 리뷰 및 제품 장점 어필",
                "포맷 D (Q&A/고민해결): 시청자의 사연을 읽어주고 속 시원한 해결책 제시",
                "포맷 E (팩트체크): 사람들이 잘못 알고 있는 흔한 오해를 반박하며 올바른 정보 제공",
                "포맷 F (스토리텔링): 본인이나 지인의 생생한 경험담(고생담)을 바탕으로 공감 유도 및 팁 제공"
            ]
        )
    with col_prod:
        product_name = st.text_input("📦 연결할 제품명 ", value="다피다 허리찜질기")
        
    st.markdown("##### 🎙️ 음성 및 API 설정")
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        selected_voice = st.selectbox(
            "AI 성우 보이스 선택",
            options=[
                ("🌟 [프리미엄] 매력적인 여성 - Rachel", "el_21m00Tcm4TlvDq8ikWAM"),
                ("🌟 [프리미엄] 다이내믹 남성 - Drew", "el_29vD33N1CtxCmqQRPOHJ"),
                ("🌟 [프리미엄] 발랄한 여성 - Bella", "el_EXAVITQu4vr4xnSDxMaL"),
                ("🌟 [프리미엄] 묵직한 중년 남성 - Antoni", "el_ErXwobaYiN019PkySvjV"),
                ("---", ""),
                ("🐟 [Fish Audio] 건강한 여성 목소리", "fish_0340360282524779a06c68b76d80f773"),
                ("🐟 [Fish Audio] 3040 건강정보 단호한 아내", "fish_d93d9edfdc7649ce9fa573cfa7be504f"),
                ("🐟 [Fish Audio] 활기찬 건강 보이스", "fish_88790aeef3ab48c0a88f9c5676362ed3"),
                ("---", ""),
                ("👩‍💼 [무료] 마케팅 여성 - 선희", "ko-KR-SunHiNeural"),
                ("👩‍🏫 [무료] 아나운서 여성 - 지민", "ko-KR-JiMinNeural"),
                ("👵 [무료] 다정한 아주머니 - 순복", "ko-KR-SoonBokNeural"),
                ("👨‍💼 [무료] 마케팅 남성 - 인준", "ko-KR-InJoonNeural"),
                ("👨‍🏫 [무료] 신뢰감 남성 - 봉진", "ko-KR-BongJinNeural"),
                ("🎧 [무료] 유튜버 청년 - 현수", "ko-KR-HyunsuNeural")
            ],
            format_func=lambda x: x[0],
            key="bulk_voice"
        )[1]
    with col_v2:
        EL_API_KEY_FILE = "el_api_key.txt"
        cached_el_api_key = os.environ.get("ELEVENLABS_API_KEY", "")
        if os.path.exists(EL_API_KEY_FILE):
            with open(EL_API_KEY_FILE, "r", encoding="utf-8-sig") as f:
                cached_el_api_key = f.read().strip()
                
        FISH_API_KEY_FILE = "fish_api_key.txt"
        cached_fish_api_key = os.environ.get("FISH_API_KEY", "")
        if os.path.exists(FISH_API_KEY_FILE):
            with open(FISH_API_KEY_FILE, "r", encoding="utf-8-sig") as f:
                cached_fish_api_key = f.read().strip()

        el_api_key = st.text_input("🔑 ElevenLabs API Key", type="password", value=cached_el_api_key, key="bulk_el")
        fish_api_key = st.text_input("🔑 Fish Audio API Key", type="password", value=cached_fish_api_key, key="bulk_fish")

    st.markdown("---")
    
    if st.button("1️⃣ 세부 주제 10개 자동 추출", use_container_width=True, type="primary"):
        if not nvidia_api_key:
            st.error("NVIDIA API Key를 상단에 입력해주세요.")
        elif not main_topic:
            st.error("메인 주제를 입력해주세요.")
        else:
            with st.spinner("주제 추출 중..."):
                from openai import OpenAI
                _base_url = "https://openrouter.ai/api/v1" if nvidia_api_key.startswith("sk-or-") else "https://integrate.api.nvidia.com/v1"
                client = OpenAI(base_url=_base_url, api_key=nvidia_api_key)
                prompt = f"'{main_topic}'과(와) 관련된 숏폼 영상 세부 주제로 쓰기 좋은 짧고 명확한 한글 키워드 딱 10개를 콤마(,)로 구분해서 적어주세요.\n[CRITICAL RULE]: 영어(English) 알파벳은 단 한 글자도 출력하지 마세요! 사고 과정(Thinking process)이나 부연 설명도 절대 출력하지 마세요. 오직 콤마로 구분된 '한글' 단어 10개만 출력해야 합니다.\n예시: 허리 통증 원인, 집에서 하는 허리 운동, 코어 강화 루틴"
                completion = client.chat.completions.create(
                    model=model_choice,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=200
                )
                import re
                raw_content = completion.choices[0].message.content.strip()
                raw_kws = re.split(r'[,\n]+', raw_content)
                clean_kws = []
                for k in raw_kws:
                    k = re.sub(r'^\d+[\.\)]\s*', '', k.strip())
                    k = k.strip('-* \t\n')
                    # 특수문자 제거
                    k = re.sub(r'[^\w\s가-힣]', '', k).strip()
                    # 영어 알파벳이 포함되어 있거나 길이가 너무 짧은 경우 무시 (AI 영어 답변 필터링)
                    if k and not re.search(r'[a-zA-Z]', k) and len(k) > 1:
                        clean_kws.append(k)
                st.session_state["bulk_keywords"] = clean_kws[:10]
                st.success("세부 주제 추출 완료!")

    if "bulk_keywords" in st.session_state and st.session_state["bulk_keywords"]:
        st.write("📌 **추출된 세부 주제 10개:**")
        for i, k in enumerate(st.session_state["bulk_keywords"]):
            st.write(f"{i+1}. {k}")
            
        if st.button("2️⃣ 10편 대본 일괄 생성", use_container_width=True, type="primary"):
            scripts = []
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            from concurrent.futures import ThreadPoolExecutor, as_completed
            from naver_clip_adforge import generate_strategic_script_stream
            import random

            # 채널 방향성 문서 17항: 반드시 Hook/각도/감정을 분산해야 함
            # 10개 모두 다른 Hook을 쓰도록 사전에 1:1 배정 (random.choice는 겹침 위험)
            ALL_HOOK_TYPES = ["경고형", "금지형", "숫자형", "연령형", "공감형", "궁금증형", "반전형", "비교형", "체크리스트형", "행동유도형"]
            ALL_VISUAL_HOOKS = ["BODY", "MOVEMENT", "BEFORE_AFTER", "PROBLEM_SITUATION", "EXPERT", "EXERCISE_RESULT",
                                "BODY", "MOVEMENT", "BEFORE_AFTER", "PROBLEM_SITUATION"]  # 6개 유형 순환
            ALL_FORMATS = ["포맷 A (순수 정보형): 제품 언급 0%. 꿀팁만. 마지막은 댓글 CTA.",
                           "포맷 D (Q&A): 시청자 사연을 읽어주고 속 시원한 해결책 제시.",
                           "포맷 E (팩트체크): 흔한 오해를 반박하며 올바른 정보 제공.",
                           "포맷 F (스토리텔링): 본인/지인의 생생한 경험담(고생담)으로 공감 유도 후 팁 제공.",
                           "포맷 A (순수 정보형): 제품 언급 0%. 꿀팁만. 마지막은 댓글 CTA.",
                           "포맷 D (Q&A): 시청자 사연을 읽어주고 속 시원한 해결책 제시.",
                           "포맷 E (팩트체크): 흔한 오해를 반박하며 올바른 정보 제공.",
                           "포맷 F (스토리텔링): 본인/지인의 생생한 경험담(고생담)으로 공감 유도 후 팁 제공.",
                           "포맷 A (순수 정보형): 제품 언급 0%. 꿀팁만. 마지막은 댓글 CTA.",
                           "포맷 D (Q&A): 시청자 사연을 읽어주고 속 시원한 해결책 제시."]

            # shuffle하여 순서 무작위화 후 zip으로 1:1 배정
            random.shuffle(ALL_HOOK_TYPES)
            random.shuffle(ALL_VISUAL_HOOKS)
            random.shuffle(ALL_FORMATS)

            keywords = st.session_state["bulk_keywords"]
            assignments = {
                kw: {
                    "hook": ALL_HOOK_TYPES[i % len(ALL_HOOK_TYPES)],
                    "visual": ALL_VISUAL_HOOKS[i % len(ALL_VISUAL_HOOKS)],
                    "fmt": ALL_FORMATS[i % len(ALL_FORMATS)],
                    "expert": (i % 2 == 0)  # 홀/짝 번갈아
                }
                for i, kw in enumerate(keywords)
            }

            def _gen_script(kw):
                raw_out = ""
                assign = assignments[kw]
                
                for chunk in generate_strategic_script_stream(
                    topic_category, kw, assign["fmt"], product_name, nvidia_api_key, model_choice,
                    hook_type=assign["hook"], visual_hook=assign["visual"], expert_present=assign["expert"]
                ):
                    raw_out += chunk
                if "EngineCore" in raw_out or "오류 발생" in raw_out:
                    raise Exception("AI 모델(API) 응답 오류가 발생했습니다. (EngineCore 또는 시간 초과)")
                
                pattern = r'={2,}\s*(VISUAL_HOOK|SCRIPT|COMMENT|DM[_\s]*MESSAGE|DESCRIPTION)\s*={2,}'
                matches = list(re.finditer(pattern, raw_out, re.IGNORECASE))
                script_part = ""
                if matches:
                    for j, match in enumerate(matches):
                        key = match.group(1).upper()
                        if "SCRIPT" in key:
                            start_idx = match.end()
                            end_idx = matches[j+1].start() if j + 1 < len(matches) else len(raw_out)
                            script_part = raw_out[start_idx:end_idx].strip()
                            break
                if not script_part:
                    script_part = raw_out
                script_part = re.sub(r'([.?!])\s+', r'\1\n', script_part)
                return {"keyword": kw, "script": script_part, "hook": assign["hook"], "format": assign["fmt"][:5]}

            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {executor.submit(_gen_script, kw): kw for kw in keywords}
                completed = 0
                for future in as_completed(futures):
                    try:
                        scripts.append(future.result())
                    except Exception as e:
                        st.error(f"대본 생성 실패: {e}")
                    completed += 1
                    status_text.text(f"({completed}/{len(futures)}) 대본 병렬 생성 중...")
                    progress_bar.progress(completed / len(futures))
                
            st.session_state["bulk_scripts"] = scripts
            status_text.text("대본 병렬 생성 완료!")
            
    if "bulk_scripts" in st.session_state and st.session_state["bulk_scripts"]:
        st.write("📝 **생성된 대본 10편 (미리보기 및 직접 수정 가능):**")
        st.info("비디오 생성 전 대본을 자유롭게 수정할 수 있습니다. 수정 후 바로 아래 생성 버튼을 누르면 수정된 대본이 반영됩니다.")
        for i, s in enumerate(st.session_state["bulk_scripts"]):
            hook_label = s.get("hook", "")
            fmt_label = s.get("format", "")
            expander_title = f"{i+1}. {s['keyword']}   [{hook_label}] [{fmt_label}]"
            with st.expander(expander_title, expanded=False):
                st.text_area("대본 수정", value=s["script"], height=200, key=f"bulk_script_text_{i}", label_visibility="collapsed")
                
        if st.button("3️⃣ 캡컷 프로젝트 10편 일괄 생성 (스톡 영상 자동 삽입)", use_container_width=True, type="primary"):
            progress_bar2 = st.progress(0)
            status_text2 = st.empty()
            
            # API 키 저장
            if el_api_key:
                with open(EL_API_KEY_FILE, "w", encoding="utf-8") as f:
                    f.write(el_api_key)
            if fish_api_key:
                with open(FISH_API_KEY_FILE, "w", encoding="utf-8") as f:
                    f.write(fish_api_key)
                    
            if selected_voice.startswith("fish_"):
                os.environ["FISH_API_KEY"] = fish_api_key
            
            from concurrent.futures import ThreadPoolExecutor, as_completed
            from naver_clip_adforge import build_capcut_project_for_naver_clip
            
            def _build_capcut(idx, s):
                kw = s["keyword"]
                script = st.session_state.get(f"bulk_script_text_{idx}", s["script"])
                build_capcut_project_for_naver_clip(
                    script_text=script,
                    keyword=kw,
                    pexels_api_key=pexels_api_key,
                    pixabay_api_key=pixabay_api_key,
                    voice=selected_voice,
                    el_api_key=el_api_key
                )
                return kw

            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {executor.submit(_build_capcut, i, s): s for i, s in enumerate(st.session_state["bulk_scripts"])}
                completed = 0
                for future in as_completed(futures):
                    try:
                        kw = future.result()
                    except Exception as e:
                        st.error(f"캡컷 생성 실패: {e}")
                    completed += 1
                    status_text2.text(f"({completed}/{len(futures)}) 캡컷 프로젝트 병렬 생성 중...")
                    progress_bar2.progress(completed / len(futures))
                
            status_text2.text("🎬 캡컷 프로젝트 병렬 생성 완료! 캡컷 임시 보관함을 확인하세요.")

    st.stop()


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
    # 괄호 앞의 영문자만 추출
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
    
    # 포맷별 자동 프롬프트
    if "포맷 A" in video_format:
        default_system_prompt = """당신은 100만 바이럴을 만드는 숏폼 건강 정보 크리에이터입니다.
[포맷 A: 순수 정보형] — 제품명은 절대 언급하지 마세요. 오직 유익한 건강 꿀팁만 제공합니다.

핵심 규칙 (1M Viral & Twist Formula):
1. 미드롤 CTA: 비법을 공개하기 직전에 "좋아요 먼저 누르고 따라하세요!"를 삽입하세요.
2. 구체적 넘버링: "1단계", "2단계" 형식으로 따라하기 쉽게 분해하세요.
3. 강력한 효과 시각화: "시원합니다" 대신 "혈류가 심장으로 솟구치고" 등 감각적으로 묘사하세요.
4. 지정 댓글 유도: "좋아요 부탁드려요" 금지. "댓글에 '시원해요'라고 남겨주세요"처럼 구체적 키워드를 제시하세요."""
    elif "포맷 B" in video_format:
        default_system_prompt = """당신은 100만 바이럴을 만드는 숏폼 마케터이자 일반인 크리에이터입니다.
[포맷 B: 간접 홍보형] — 영상의 80%는 순수 꿀팁, 마지막 20%에서 "제가 쓰는 기구는 댓글에 남길게요!"라고 자연스럽게 유도합니다. 영상 안에서 제품명은 절대 말하지 마세요.

핵심 규칙 (1M Viral & Twist Formula):
1. 미드롤 CTA: 꿀팁 공개 직전 "좋아요 먼저 누르고 따라하세요!" 삽입.
2. 매몰비용 자극: "안 그래도 돈 쓴 것도 억울한데" 등으로 공감 극대화.
3. 간접 제품 유도: 꿀팁 제공 후 "그냥 손으로 하긴 힘들어서 저는 기구 하나 쓰는데, 댓글에 올릴게요!"처럼 자연스럽게 연결.
4. 지정 댓글 유도: "댓글에 '기구 궁금'라고 남겨주세요!"처럼 제품 수요를 댓글로 모으세요."""
    else:  # 포맷 C
        default_system_prompt = """당신은 100만 바이럴을 만드는 제품 리뷰어이자 숏폼 마케터입니다.
[포맷 C: 직접 홍보형] — 제품명을 당당하게 언급하며 대안재(비싼 안마의자, 비싼 도수치료 등)와 비교하여 압도적인 가성비를 어필합니다.

핵심 규칙 (1M Viral & Twist Formula):
1. 대안재 비교: "거대하고 비싼 안마의자 대신", "도수치료비 쏟아붓다가" 등으로 기존 대체재의 단점을 먼저 부각시키세요.
2. 미드롤 CTA: 제품 공개 직전 "좋아요 먼저 누르세요!" 삽입.
3. 매몰비용 자극 + 가성비 앵커링: "올해 또 예쁜 쓰레기 사실 건가요?" → "월 만원대로 평생 뽕뽑는다"처럼 손실 회피와 가성비를 동시에 찌르세요.
4. 지정 댓글 + 한정성 마감: "댓글에 '할인 링크'라고 남겨주세요!"처럼 구매 의향자를 댓글로 집결시키세요."""

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
                
            # 한 문장마다 강제 줄바꿈 처리 (마침표, 물음표, 느낌표 뒤)
            script_part = re.sub(r'([.?!])\s+', r'\1\n', script_part)
                
            # If AI left conversational text like "Here is the script:", we can try to strip it,
            # but using ====SCRIPT==== delimiter usually prevents this.
            st.session_state["parsed_visual"] = visual_part
            st.session_state["parsed_script"] = script_part
            st.session_state["parsed_comment"] = comment_part
            st.session_state["parsed_dm"] = dm_part
            st.session_state["parsed_description"] = desc_part
            
            # Log performance metrics placeholder (with new hook params)
            try:
                from performance_logger import log_performance
                log_performance({
                    "content_id": "temp_" + pd.Timestamp.now().strftime("%Y%m%d%H%M%S"),
                    "topic": topic_category,
                    "hook_type": hook_type_val,
                    "visual_hook": visual_hook_val,
                    "expert_present": expert_present,
                    "title": sub_topic,
                    "duration": 45, # estimated
                    "upload_datetime": pd.Timestamp.now().isoformat()
                })
            except Exception as e:
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

st.markdown("---")

# -------------------------------------------------------------------
# STEP 2: 대본 입력 및 캡컷/Hailuo 자동화
# -------------------------------------------------------------------

st.markdown("---")
st.subheader("STEP 2: 캡컷 연동 & Hailuo 프롬프트 추출")

default_script = st.session_state.get("parsed_script", "")
script_text = st.text_area("📝 영상 자막(대본) 전문 (STEP 1에서 생성 시 자동 입력됨 / 직접 붙여넣기 가능)", value=default_script, height=200)

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

# ✨ 대본 → CTA/DM/설명 자동 생성 (Step 1 없이도 독립 사용)
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

            # 파싱
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
                            keyword=sub_topic,
                            pexels_api_key=pexels_api_key,
                            pixabay_api_key=pixabay_api_key,
                            voice=actual_voice_choice,
                            el_api_key=el_api_key
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
