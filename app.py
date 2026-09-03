import os
import re
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from naver_clip_adforge import build_capcut_project_for_naver_clip, split_script_by_sentences_and_phrases, split_sentence_naturally

# .env 파일에서 환경 변수 로드 (최신 값 강제 로드)
load_dotenv(override=True)

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
# 📸 인스타그램 광고 레퍼런스 (Meta Ad Library)
# -------------------------------------------------------------------

def _generate_related_keywords(keyword: str) -> list:
    """키워드에서 관련 검색어를 생성합니다."""
    # 키워드 기반 변형 생성
    suffixes = ["추천", "효과", "후기"]
    suggestions = []
    for suffix in suffixes:
        suggestions.append(f"{keyword} {suffix}")
    return suggestions[:4]  # 최대 4개

st.markdown("---")
st.subheader("📸 인스타그램 광고 레퍼런스 (Meta Ad Library)")
st.caption("키워드를 입력하면 Meta Ad Library에서 **장기 집행 중인 광고**(성과가 검증된 레퍼런스)를 조회합니다.")

from dotenv import load_dotenv
load_dotenv()

meta_token = os.environ.get("META_ACCESS_TOKEN", "")

@st.cache_data(show_spinner=False, ttl=60)
def get_naver_autocomplete(keyword: str):
    if not keyword.strip(): return []
    try:
        import requests
        url = f"https://ac.search.naver.com/nx/ac?q={keyword}&con=0&dict=0&a_gb=0&spq=0&recover=0&fq=0&mod=0&r_format=json&r_enc=UTF-8&r_unicode=0&t_koreng=1&ans=2&run=2&rev=4&q_enc=UTF-8&st=100"
        r = requests.get(url, timeout=3)
        data = r.json()
        items = data.get('items', [[]])[0]
        return [item[0] for item in items][:10]
    except:
        return []

col_ig1, col_ig2, col_ig3 = st.columns([3, 1, 1])
with col_ig1:
    ig_keyword = st.text_input(
        "🔍 광고 검색 키워드",
        value=selected_keyword if selected_keyword else "",
        placeholder="예: 허리찜질기, 무릎보호대, 다이어트",
        key="ig_ad_keyword"
    )
    
    if ig_keyword:
        related = get_naver_autocomplete(ig_keyword)
        if related:
            def update_keyword_from_pill():
                if st.session_state.related_pills:
                    st.session_state.ig_ad_keyword = st.session_state.related_pills

            # st.pills의 on_change 콜백을 사용하여 오류 방지
            pill_selection = st.pills(
                "💡 네이버 연관 검색어 (클릭 시 키워드 변경)", 
                related, 
                key="related_pills",
                on_change=update_keyword_from_pill
            )
with col_ig2:
    ig_min_days = st.selectbox(
        "📅 최소 집행 기간",
        options=[50, 90, 120, 180, 365],
        format_func=lambda d: f"{d}일 ({d // 30}개월+)",
        index=0,
        key="ig_min_days"
    )
with col_ig3:
    ig_country = st.selectbox(
        "🌍 검색 국가",
        options=["KR", "US", "JP", "GB", "ALL"],
        format_func=lambda c: {"KR": "🇰🇷 한국", "US": "🇺🇸 미국", "JP": "🇯🇵 일본", "GB": "🇬🇧 영국", "ALL": "🌐 전체"}.get(c, c),
        index=0,
        key="ig_country"
    )

if st.button("🔍 인스타 광고 레퍼런스 검색", use_container_width=True, type="primary"):
    if not ig_keyword.strip():
        st.error("검색 키워드를 입력해주세요.")
    else:
        with st.spinner(f"Meta Ad Library에서 '{ig_keyword}' 관련 {ig_min_days}일+ 집행 광고 검색 중..."):
            from meta_ad_library import search_meta_ads
            result = search_meta_ads(
                keyword=ig_keyword.strip(),
                access_token=meta_token,
                country=ig_country,
                min_days_running=ig_min_days,
            )
            st.session_state["ig_ad_result"] = result
            st.session_state["ig_ad_keyword_used"] = ig_keyword.strip()

if "ig_ad_result" in st.session_state:
    result = st.session_state["ig_ad_result"]
    kw_used = st.session_state.get("ig_ad_keyword_used", "")

    # 항상 웹 링크 표시
    col_link1, col_link2 = st.columns(2)
    with col_link1:
        st.markdown(
            f"🔗 [Meta Ad Library에서 **'{kw_used}'** 직접 검색하기 →]({result['url']})",
        )
    with col_link2:
        # 장기 집행 광고 전용 URL (있으면)
        from meta_ad_library import _build_search_url_sorted
        sorted_url = _build_search_url_sorted(kw_used, ig_country)
        st.markdown(
            f"📊 [장기 집행 광고 보기 (시작일 정렬) →]({sorted_url})",
        )

    if result.get("error"):
        st.warning(f"⚠️ API 조회 중 오류: {result['error']}")
        st.info("위 링크를 클릭하여 Meta Ad Library에서 직접 확인해보세요.")
    elif result.get("permission_note") or (result["mode"] == "link"):
        # 권한 부족이거나 토큰 없음 → 링크 모드 안내 + 사용 가이드
        if result.get("permission_note"):
            st.info("📋 Meta Ad Library API 상업 광고 접근 권한이 제한되어 **웹 링크 모드**로 동작합니다.")

        with st.container(border=True):
            st.markdown("### 💡 3개월 이상 집행 광고 레퍼런스 찾는 법")
            st.markdown(f"""
1. **위 링크를 클릭**하여 Meta Ad Library 페이지로 이동합니다
2. 검색 결과에서 **시작 날짜**를 확인합니다 — 오래 전 시작된 광고일수록 성과가 검증된 광고입니다
3. **3개월 이상** (약 90일+) 집행 중인 광고는 ROAS가 양호하여 계속 예산을 투입하는 **"위닝 광고"**일 가능성이 높습니다
4. 해당 광고의 **카피, 영상 구성, 썸네일 스타일**을 레퍼런스로 활용하세요

> 🎯 **Tip**: 검색어 `{kw_used}`와 관련된 경쟁사 브랜드명이나 제품 카테고리명도 함께 검색해보세요!
            """)

            # 추천 검색어 제안
            st.markdown("**🔍 추가 추천 검색어:**")
            suggestions = _generate_related_keywords(kw_used)
            cols = st.columns(len(suggestions))
            for i, sug in enumerate(suggestions):
                from meta_ad_library import _build_search_url
                sug_url = _build_search_url(sug, ig_country)
                with cols[i]:
                    st.markdown(f"[`{sug}`]({sug_url})")

    elif result["mode"] in ("api", "scrape"):
        df = result["df"]
        mode_label = "🕷️ 스크래핑" if result["mode"] == "scrape" else "🔌 API"
        if df.empty:
            st.info(f"'{kw_used}' 키워드로 {ig_min_days}일 이상 집행 중인 활성 광고를 찾지 못했습니다. 키워드를 변경하거나 최소 집행 기간을 줄여보세요.")
        else:
            st.success(f"✅ {mode_label} 방식으로 {len(df)}개의 광고 레퍼런스를 찾았습니다!")

            # ── 카드 형태로 광고 표시 ──
            for i, row in df.iterrows():
                with st.container(border=True):
                    card_col1, card_col2 = st.columns([3, 1])
                    with card_col1:
                        st.markdown(f"**🏪 {row['페이지명']}**")
                        if row.get('광고 카피'):
                            st.caption(row['광고 카피'])
                        if row.get('CTA'):
                            st.markdown(f"🔘 *{row['CTA']}*")
                    with card_col2:
                        st.metric("집행 기간", row.get('집행 기간', '-'))
                        st.caption(f"시작: {row.get('집행 시작일', '-')}")
                        if row.get('게시 플랫폼'):
                            st.caption(f"📱 {row['게시 플랫폼']}")
                        if row.get('광고 보기'):
                            st.markdown(f"[👁️ 광고 보기 →]({row['광고 보기']})")

            st.markdown("---")

            # ── 📋 기획 테이블 + 노션 저장 ──
            st.markdown("#### 📋 기획 테이블 — 노션 저장용")
            st.caption("아래 표를 확인하고 브랜드/진행 여부를 입력한 뒤 노션에 저장하세요.")

            import pandas as pd
            from datetime import date as date_type

            # 기획 테이블 데이터 준비
            notion_rows = []
            for i, row in df.iterrows():
                notion_rows.append({
                    "선택": True,
                    "광고 카피": row.get("광고 카피", ""),
                    "레퍼런스 링크": row.get("광고 보기", ""),
                    "브랜드": row.get("페이지명", ""),
                    "진행 여부": "검토중",
                    "날짜": date_type.today(),
                })

            notion_df = pd.DataFrame(notion_rows)

            # 편집 가능한 데이터 편집기
            edited_df = st.data_editor(
                notion_df,
                column_config={
                    "선택": st.column_config.CheckboxColumn("☑️ 선택", help="저장할 항목을 선택하세요", default=True, width="small"),
                    "광고 카피": st.column_config.TextColumn("📝 광고 카피", width="large"),
                    "레퍼런스 링크": st.column_config.LinkColumn("🔗 레퍼런스 링크", width="medium"),
                    "브랜드": st.column_config.TextColumn("🏷️ 브랜드", width="small"),
                    "진행 여부": st.column_config.SelectboxColumn(
                        "📌 진행 여부",
                        options=["검토중", "진행", "보류", "완료"],
                        width="small",
                    ),
                    "날짜": st.column_config.DateColumn("📅 날짜", width="small", format="YYYY-MM-DD"),
                },
                width="stretch",
                hide_index=True,
                num_rows="fixed",
                key="notion_table",
            )

            st.markdown("")

            # ── 노션 저장 버튼 ──
            notion_token = os.environ.get("NOTION_TOKEN", "")
            notion_db_id = os.environ.get("NOTION_DATABASE_ID", "")

            if not notion_token or not notion_db_id:
                with st.expander("⚙️ 노션 연동 설정 필요", expanded=True):
                    st.warning("노션에 저장하려면 아래 정보를 입력하세요.")
                    n_col1, n_col2 = st.columns(2)
                    with n_col1:
                        input_token = st.text_input(
                            "Notion Integration Token",
                            placeholder="ntn_...",
                            type="password",
                            key="input_notion_token",
                        )
                    with n_col2:
                        input_db_id = st.text_input(
                            "Notion Database ID",
                            placeholder="32자리 ID",
                            key="input_notion_db_id",
                        )
                    if st.button("💾 설정 저장", key="save_notion_settings"):
                        if input_token and input_db_id:
                            import re
                            # .env 파일에 저장
                            env_path = os.path.join(os.path.dirname(__file__), ".env")
                            with open(env_path, "r", encoding="utf-8") as f:
                                env_content = f.read()
                            
                            env_content = re.sub(r"^NOTION_TOKEN=.*$", f"NOTION_TOKEN={input_token}", env_content, flags=re.MULTILINE)
                            env_content = re.sub(r"^NOTION_DATABASE_ID=.*$", f"NOTION_DATABASE_ID={input_db_id}", env_content, flags=re.MULTILINE)
                            
                            with open(env_path, "w", encoding="utf-8") as f:
                                f.write(env_content)
                            load_dotenv(override=True)
                            st.success("✅ 설정이 저장되었습니다! 페이지를 새로고침하세요.")
                        else:
                            st.error("토큰과 DB ID를 모두 입력해주세요.")
            else:
                # 연결 상태 표시
                from notion_sync import test_notion_connection, save_ad_reference_to_notion
                with st.expander("✅ 노션 연결됨", expanded=False):
                    conn_test = test_notion_connection(notion_token, notion_db_id)
                    if conn_test["ok"]:
                        st.success(f"데이터베이스: **{conn_test['title']}**")
                    else:
                        st.error(f"연결 오류: {conn_test['error']}")

                st.markdown("")
                n_save_col1, n_save_col2 = st.columns([2, 1])
                
                selected_rows = edited_df[edited_df["선택"] == True]
                
                with n_save_col1:
                    n_rows_label = f"☑️ 선택된 {len(selected_rows)}개 항목을 노션에 저장합니다"
                    st.caption(n_rows_label)
                with n_save_col2:
                    save_btn = st.button(
                        "📤 노션에 저장하기",
                        type="primary",
                        use_container_width=True,
                        key="save_to_notion",
                    )

                if save_btn:
                    with st.spinner("노션에 저장 중..."):
                        saved_count = 0
                        failed_count = 0
                        last_error = ""
                        
                        if len(selected_rows) == 0:
                            st.warning("선택된 항목이 없습니다.")
                        else:
                            for _, row in selected_rows.iterrows():
                                res = save_ad_reference_to_notion(
                                    token=notion_token,
                                    database_id=notion_db_id,
                                    ad_copy=str(row.get("광고 카피", "")),
                                    reference_url=str(row.get("레퍼런스 링크", "")),
                                    brand=str(row.get("브랜드", "")),
                                    status=str(row.get("진행 여부", "검토중")),
                                    date=str(row.get("날짜", str(date_type.today()))),
                                    keyword=kw_used,
                                )
                                if res["ok"]:
                                    saved_count += 1
                                else:
                                    failed_count += 1
                                    last_error = res.get("error", "알 수 없는 에러")

                    if failed_count == 0:
                        st.success(f"✅ {saved_count}개 항목이 노션에 저장되었습니다!")
                        st.balloons()
                    else:
                        st.warning(f"저장 완료: {saved_count}개 성공, {failed_count}개 실패")
                        st.error(f"실패 원인 (마지막 에러): {last_error}")

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
            st.session_state["script_text_area"] = script_text
            
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

# 🔀 자막 줄바꿈 자동 정리 함수 (스마트 문맥 규칙 기반)
def auto_format_subtitle(text: str, max_chars: int = 16) -> str:
    """한국어 대본을 문맥 및 호흡 단위(수식어 보존, 연결어미 분리)에 맞게 자동 줄바꿈"""
    if not text or not text.strip():
        return ""
    # 줄바꿈 정규화 (\r\n -> \n)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    
    # 누락된 구어체 종결 뒤 분리 보정 (예: '풀어줘요 차기만 하면' -> '풀어줘요. 차기만 하면')
    text = re.sub(r'([요죠다네함음임])\s+(?=(?:차기만|왜냐하면|그래서|하지만|그러니|지금|당장|30일|특허|대기))', r'\1. ', text)
    
    paragraphs = re.split(r'\n{2,}', text.strip())
    result_lines = []
    
    for para in paragraphs:
        flat = re.sub(r'\s+', ' ', para).strip()
        if not flat:
            continue
        
        # 문장 단위로 분할 (.!?…~ 기준)
        sentences = [s.strip() for s in re.split(r'(?<=[.!?…~])\s+', flat) if s.strip()]
        
        for sent in sentences:
            lines = split_sentence_naturally(sent, max_chars=max_chars)
            result_lines.extend(lines)
            
        result_lines.append("")  # 단락 구분용 빈 줄
    
    return "\n".join(result_lines).strip()

def format_subtitle_with_ai(text: str, api_key: str, model: str = "", max_chars: int = 16) -> str:
    """LLM을 이용해 광고 카피 자막을 최적의 호흡 단위로 줄바꿈"""
    if not text or not text.strip() or not api_key:
        return text
    import requests
    
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
    st.button("🤖 AI 문맥 줄바꿈 (LLM 카피)", on_click=apply_ai_format, use_container_width=True, help="AI가 문맥을 분석하여 시청자 호흡과 카피라이팅에 최적화된 1줄 자막으로 정리합니다.")

script_text = st.text_area("📝 영상 자막(대본) 전문 (STEP 1에서 생성 시 자동 입력됨 / 직접 붙여넣기 가능)", key="script_text_area", height=220)

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
            ("🐟 [Fish Audio] 신규 보이스", "fish_ed763b05d90b470284150bbc49a8d9e1"),
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

from naver_clip_adforge import build_capcut_project_for_naver_clip, build_final_video_with_caption_os, build_capcut_project_with_caption_os_overlay

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

# -------------------------------------------------------------------
# ✍️ 수동 자막 스타일 설정
# -------------------------------------------------------------------
st.markdown("---")

from anim_labels import make_selectbox_options
import json

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "style_templates")
os.makedirs(TEMPLATES_DIR, exist_ok=True)

@st.cache_data
def get_anim_options():
    from pycapcut.metadata.text_intro import TextIntro
    from pycapcut.metadata.text_outro import TextOutro
    from pycapcut.metadata.text_loop import TextLoopAnim
    intro_opts = make_selectbox_options([e.name for e in TextIntro], "intro")
    loop_opts  = make_selectbox_options([e.name for e in TextLoopAnim], "loop")
    outro_opts = make_selectbox_options([e.name for e in TextOutro], "outro")
    return intro_opts, loop_opts, outro_opts

intro_opts, loop_opts, outro_opts = get_anim_options()
intro_labels = [ko for ko, _ in intro_opts]
loop_labels  = [ko for ko, _ in loop_opts]
outro_labels = [ko for ko, _ in outro_opts]

import os as _os
_lad = _os.environ.get("LOCALAPPDATA", "").replace("\\", "/")
AVAILABLE_FONTS = {
    "Pretendard": f"{_lad}/Microsoft/Windows/Fonts/Pretendard-Bold.otf",
    "Black Han Sans": f"{_lad}/Microsoft/Windows/Fonts/BlackHanSans-Regular.ttf",
}
AVAILABLE_FONTS = {k: v for k, v in AVAILABLE_FONTS.items() if _os.path.exists(v)}
FONT_NAMES = list(AVAILABLE_FONTS.keys()) or ["Pretendard"]

def _find_default(opts_labels, ko_name):
    try: return opts_labels.index(ko_name)
    except ValueError: return 0

def _make_role_ui(role_key, tab_label, defaults):
    """역할 하나의 탭 UI를 렌더링하고 설정 dict 반환."""
    # session_state에 아직 값이 없을 때만 기본값을 미리 주입
    # → index= 파라미터와 session_state가 동시에 존재하는 충돌 방지
    if f"{role_key}_font" not in st.session_state:
        st.session_state[f"{role_key}_font"] = (
            defaults["font"] if defaults["font"] in FONT_NAMES else FONT_NAMES[0]
        )
    if f"{role_key}_size" not in st.session_state:
        st.session_state[f"{role_key}_size"] = defaults["size"]
    if f"{role_key}_intro" not in st.session_state:
        st.session_state[f"{role_key}_intro"] = _find_default(intro_labels, defaults["intro_ko"])
    if f"{role_key}_loop" not in st.session_state:
        st.session_state[f"{role_key}_loop"] = _find_default(loop_labels, defaults["loop_ko"])
    if f"{role_key}_outro" not in st.session_state:
        st.session_state[f"{role_key}_outro"] = _find_default(outro_labels, defaults.get("outro_ko", "(없음)"))

    c1, c2 = st.columns(2)
    with c1:
        font = st.selectbox("폰트", FONT_NAMES, key=f"{role_key}_font")
        size = st.slider("글자 크기", 10.0, 30.0, step=0.5, key=f"{role_key}_size")
    with c2:
        intro_i = st.selectbox("등장 애니메이션", range(len(intro_labels)), key=f"{role_key}_intro",
                               format_func=lambda i: intro_labels[i])
        loop_i  = st.selectbox("반복 애니메이션", range(len(loop_labels)), key=f"{role_key}_loop",
                               format_func=lambda i: loop_labels[i])
        outro_i = st.selectbox("퇴장 애니메이션", range(len(outro_labels)), key=f"{role_key}_outro",
                               format_func=lambda i: outro_labels[i])
    return {
        "font_name": font,
        "font_path": AVAILABLE_FONTS.get(font, ""),
        "size": size,
        "intro": intro_opts[intro_i][1],
        "loop":  loop_opts[loop_i][1],
        "outro": outro_opts[outro_i][1],
    }


# 역할별 기본값
ROLE_DEFAULTS = {
    "hook":     {"font": "Black Han Sans", "size": 18.0, "intro_ko": "⭐ 팝업 (튀어나오기)",   "loop_ko": "⭐ 떨림 II",           "outro_ko": "(없음)"},
    "empathy":  {"font": "Pretendard",     "size": 14.5, "intro_ko": "⭐ 페이드인",             "loop_ko": "(없음)",               "outro_ko": "(없음)"},
    "evidence": {"font": "Pretendard",     "size": 14.0, "intro_ko": "⭐ 타자기",               "loop_ko": "(없음)",               "outro_ko": "(없음)"},
    "solution": {"font": "Pretendard",     "size": 14.5, "intro_ko": "위로 슬라이드",           "loop_ko": "(없음)",               "outro_ko": "(없음)"},
    "cta":      {"font": "Black Han Sans", "size": 17.0, "intro_ko": "⭐ 확대 등장",            "loop_ko": "⭐ 심장박동",          "outro_ko": "(없음)"},
}

def _load_template_to_state(tmpl: dict):
    """템플릿 dict를 st.session_state에 주입."""
    for role, cfg in tmpl.items():
        if role not in ROLE_DEFAULTS:
            continue
        if "font_name" in cfg and cfg["font_name"] in FONT_NAMES:
            st.session_state[f"{role}_font"] = cfg["font_name"]
        if "size" in cfg:
            st.session_state[f"{role}_size"] = float(cfg["size"])
        for anim_key, opts, labels in [
            ("intro", intro_opts, intro_labels),
            ("loop",  loop_opts,  loop_labels),
            ("outro", outro_opts, outro_labels),
        ]:
            cn = cfg.get(anim_key)
            if cn:
                for i, (_, v) in enumerate(opts):
                    if v == cn:
                        st.session_state[f"{role}_{anim_key}"] = i
                        break
            else:
                st.session_state[f"{role}_{anim_key}"] = 0

manual_style = None
with st.expander("✍️ 자막 스타일 직접 설정 (역할별 폰트·애니메이션)", expanded=False):
    # ── 템플릿 불러오기 ────────────────────────────────────────────
    tmpl_files = [f for f in os.listdir(TEMPLATES_DIR) if f.endswith(".json")]
    top_col1, top_col2, top_col3 = st.columns([2, 1, 1])
    with top_col1:
        selected_tmpl = st.selectbox("📂 저장된 템플릿 불러오기",
                                     ["(선택 안 함)"] + [f.replace(".json", "") for f in tmpl_files],
                                     key="tmpl_select")
    with top_col2:
        st.markdown(" ")
        st.markdown(" ")
        if st.button("📂 불러오기", key="tmpl_load", use_container_width=True):
            if selected_tmpl != "(선택 안 함)":
                path = os.path.join(TEMPLATES_DIR, f"{selected_tmpl}.json")
                try:
                    with open(path, encoding="utf-8") as f:
                        _load_template_to_state(json.load(f))
                    st.success(f"'{selected_tmpl}' 템플릿을 불러왔습니다!")
                    st.rerun()
                except Exception as e:
                    st.error(f"불러오기 실패: {e}")
    with top_col3:
        st.markdown(" ")
        st.markdown(" ")
        if selected_tmpl != "(선택 안 함)" and st.button("🗑️ 삭제", key="tmpl_delete", use_container_width=True):
            try:
                os.remove(os.path.join(TEMPLATES_DIR, f"{selected_tmpl}.json"))
                st.success("삭제했습니다.")
                st.rerun()
            except Exception as e:
                st.error(f"삭제 실패: {e}")

    st.caption("💡 AI가 각 문장의 역할(훅/공감/증거/솔루션/CTA)을 분류하고, 해당 역할에 맞는 폰트·애니메이션을 템플릿에서 자동 적용합니다.")

    # ── 역할 탭 5개 ────────────────────────────────────────────────
    tabs = st.tabs(["🔥 훅", "💭 공감", "📊 증거/데이터", "💡 솔루션", "🎯 CTA"])
    role_keys = ["hook", "empathy", "evidence", "solution", "cta"]
    role_configs = {}
    for tab, role_key in zip(tabs, role_keys):
        with tab:
            role_configs[role_key] = _make_role_ui(role_key, role_key, ROLE_DEFAULTS[role_key])

    # ── 적용 체크 ──────────────────────────────────────────────────
    st.markdown("---")
    use_manual = st.checkbox("✅ 템플릿 스타일 사용 (AI가 역할 분류 → 템플릿 스타일 적용)", value=False, key="use_manual_style")

    # ── 템플릿 저장 ────────────────────────────────────────────────
    save_col1, save_col2 = st.columns([3, 1])
    with save_col1:
        tmpl_name = st.text_input("💾 템플릿 이름", placeholder="예: 허리찜질기_스타일", key="tmpl_name")
    with save_col2:
        st.markdown(" ")
        st.markdown(" ")
        if st.button("💾 저장", key="tmpl_save", use_container_width=True):
            if not tmpl_name.strip():
                st.warning("템플릿 이름을 입력해주세요.")
            else:
                save_path = os.path.join(TEMPLATES_DIR, f"{tmpl_name.strip()}.json")
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(role_configs, f, ensure_ascii=False, indent=2)
                st.success(f"✅ '{tmpl_name}' 저장 완료!")

    if use_manual:
        manual_style = role_configs
        manual_style["normal"] = role_configs.get("empathy", role_configs.get("hook", {}))
        st.success("✅ 템플릿 스타일 적용 준비 완료! AI가 역할을 분류하고 템플릿 스타일을 적용합니다.")

col_render1, col_render2, col_render3 = st.columns(3)

with col_render1:
    st.markdown("#### 1. 캡컷 프로젝트 생성 (수동 편집용)")
    
    # --- 템플릿 선택 기능 추가 ---
    from naver_clip_adforge import get_capcut_projects
    capcut_projects = get_capcut_projects()
    
    st.markdown("<div style='background-color: #F0F4F8; padding: 10px; border-radius: 5px; margin-bottom: 10px; border-left: 3px solid #00E676;'>"
                "<span style='font-size: 13px;'>✨ <b>SuperShorts 스타일 템플릿</b><br>미리 만들어둔 캡컷 프로젝트(카드형, 이미지 슬롯 등)의 레이아웃을 그대로 재활용합니다.</span></div>", unsafe_allow_html=True)
    
    template_options = {"none": "자동 생성 (기본 배치)"}
    for name, folder in capcut_projects:
        template_options[folder] = f"🖼️ {name}"
        
    selected_capcut_template = st.selectbox(
        "🎞️ 영상 레이아웃 템플릿 선택", 
        options=list(template_options.keys()), 
        format_func=lambda x: template_options[x],
        help="미리 만들어둔 캡컷 프로젝트를 선택하면 텍스트와 오디오만 새롭게 교체합니다."
    )

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
                        
                        # AI 연출 지시서 준비
                        cd_data = None
                        if use_ai_direction or manual_style:
                            # 템플릿 스타일 사용 시에도 AI 역할 분류는 필수
                            active_profile = st.session_state.get("active_style_profile")
                            active_intensity = st.session_state.get("max_intensity", "medium")

                            if "creative_direction" in st.session_state:
                                cd_data = st.session_state["creative_direction"]
                            else:
                                from creative_director import CreativeDirector
                                cd = CreativeDirector(
                                    max_intensity=active_intensity,
                                    style_profile=active_profile
                                )
                                if manual_style and not use_ai_direction:
                                    # 템플릿 모드: 규칙 기반으로 역할만 빠르게 분류
                                    with st.spinner("🔍 AI 역할 분류 중 (훅/공감/증거/솔루션/CTA)..."):
                                        cd_data = cd._fallback_analysis(script_text)
                                else:
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
                            creative_direction=cd_data,
                            manual_style=manual_style,
                            template_folder=selected_capcut_template if selected_capcut_template != "none" else None
                        )
                        st.success(f"성공적으로 캡컷 프로젝트 '{project_name}' 초안을 생성했습니다!")
                        if manual_style:
                            st.info("🎨 AI가 역할을 분류하고 템플릿 스타일을 적용했습니다. 캡컷에서 자막을 확인하세요!")
                        elif cd_data:
                            st.info("🎨 AI 크리에이티브 연출이 적용되었습니다. 캡컷에서 자막 애니메이션을 확인하세요!")
                        else:
                            st.info("PC의 캡컷(CapCut) 프로그램을 열면 임시 보관함에서 확인하실 수 있습니다.")
                except Exception as e:
                    st.error(f"오류 발생: {e}")

with col_render2:
    st.markdown("#### 2. 완제품 영상 직접 렌더링 (caption-os 자동화)")
    
    col_opt1, col_opt2 = st.columns(2)
    with col_opt1:
        mood_opts = {
            "professional": "💼 전문적/정보성 (신뢰감)",
            "old_money": "☕ 올드머니 (고급스러움)",
            "girly": "🎀 걸리쉬 (러블리)",
            "y2k_deco": "✨ 다꾸/Y2K (화려함)",
            "street_hype": "🛹 스트릿 (하이텐션)",
            "soft_natural": "🌿 소프트/내추럴 (잔잔함)",
            "classic_editorial": "📰 잡지/클래식",
            "retro_70s": "📻 레트로 70s"
        }
        caption_mood = st.selectbox("🎨 화면 무드 (색상/분위기)", options=list(mood_opts.keys()), format_func=lambda x: mood_opts[x])
        
    with col_opt2:
        caption_style_raw = st.selectbox("✨ 자막 애니메이션", ["karaoke (단어별 팝업)", "kinetic3d (3D 모션)", "keyword (키워드 강조)", "minimal (심플 페이드업)"])
        caption_style = caption_style_raw.split(" ")[0]
    
    if st.button("🚀 완제품 영상 1초 자동 생성", use_container_width=True):
        if not script_text.strip():
            st.error("대본이 비어있습니다!")
        else:
            with st.spinner(f"FFmpeg 합성 및 {caption_style} 무드로 자막 렌더링 중... (최대 1~2분 소요)"):
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
                        final_mp4 = build_final_video_with_caption_os(
                            script_text=script_text,
                            keyword=selected_keyword,
                            pexels_api_key=pexels_api_key,
                            pixabay_api_key=pixabay_api_key,
                            voice=actual_voice_choice,
                            el_api_key=el_api_key,
                            local_media_folder=local_media_folder,
                            media_mapping=media_mapping,
                            mood=caption_mood,
                            style=caption_style
                        )
                        st.success("🎉 완제품 렌더링 성공!")
                        st.video(final_mp4)
                        
                        with open(final_mp4, "rb") as f:
                            st.download_button("💾 완성된 영상 다운로드", f, file_name=os.path.basename(final_mp4), mime="video/mp4", type="primary")
                except Exception as e:
                    st.error(f"렌더링 실패: {e}")

with col_render3:
    st.markdown("#### 3. 캡컷 프로젝트 내보내기 (투명 자막 오버레이)")
    
    col_opt3, col_opt4 = st.columns(2)
    with col_opt3:
        mood_opts_draft = {
            "professional": "💼 전문적/정보성 (신뢰감)",
            "old_money": "☕ 올드머니 (고급스러움)",
            "girly": "🎀 걸리쉬 (러블리)",
            "y2k_deco": "✨ 다꾸/Y2K (화려함)",
            "street_hype": "🛹 스트릿 (하이텐션)",
            "soft_natural": "🌿 소프트/내추럴 (잔잔함)",
            "classic_editorial": "📰 잡지/클래식",
            "retro_70s": "📻 레트로 70s"
        }
        caption_mood_draft = st.selectbox("🎨 자막 무드", options=list(mood_opts_draft.keys()), format_func=lambda x: mood_opts_draft[x], key="draft_mood")
        
    with col_opt4:
        caption_style_raw_draft = st.selectbox("✨ 애니메이션", ["karaoke (단어별 팝업)", "kinetic3d (3D 모션)", "keyword (키워드 강조)", "minimal (심플 페이드업)"], key="draft_style")
        caption_style_draft = caption_style_raw_draft.split(" ")[0]
    
    if st.button("🚀 캡컷 초안 1초 생성 (투명 자막 포함)", use_container_width=True):
        if not script_text.strip():
            st.error("대본이 비어있습니다!")
        else:
            with st.spinner("투명 자막 오버레이(.mov) 렌더링 및 캡컷 프로젝트 구성 중... (최대 1~2분 소요)"):
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
                        project_name = build_capcut_project_with_caption_os_overlay(
                            script_text=script_text,
                            keyword=selected_keyword,
                            pexels_api_key=pexels_api_key,
                            pixabay_api_key=pixabay_api_key,
                            voice=actual_voice_choice,
                            el_api_key=el_api_key,
                            local_media_folder=local_media_folder,
                            media_mapping=media_mapping,
                            mood=caption_mood_draft,
                            style=caption_style_draft
                        )
                        st.success(f"🎉 캡컷 프로젝트 '{project_name}' 초안 생성 완료!")
                        st.info("PC의 캡컷(CapCut) 프로그램을 열면 임시 보관함에서 확인하실 수 있습니다.")
                        st.info("메인 트랙의 배경 영상들을 원하시는 대로 편집하시면 됩니다. 최상단 트랙의 자막 비디오는 투명 배경이므로 글자들만 깔끔하게 얹어집니다.")
                except Exception as e:
                    st.error(f"오류 발생: {e}")



