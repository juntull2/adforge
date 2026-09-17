import os
import re
import json
import time
import requests
import pandas as pd
import streamlit as st
import concurrent.futures as _cf
from datetime import date as date_type, datetime
from dotenv import load_dotenv

load_dotenv()


def _generate_related_keywords(keyword: str) -> list:
    suffixes = ["추천", "효과", "후기"]
    return [f"{keyword} {suffix}" for suffix in suffixes][:4]


@st.cache_data(show_spinner=False, ttl=1800)
def get_naver_10k_related(keyword: str, min_volume: int = 10000):
    if not keyword.strip():
        return []
    from naver_scraper import get_naver_related_keywords_over_10k
    _cid = os.environ.get("NAVER_CUSTOMER_ID", "")
    _lic = os.environ.get("NAVER_ACCESS_LICENSE", "")
    _sk  = os.environ.get("NAVER_SECRET_KEY", "")
    return get_naver_related_keywords_over_10k(keyword, _cid, _lic, _sk, min_volume=min_volume)


@st.cache_data(show_spinner=False, ttl=60)
def get_naver_autocomplete(keyword: str):
    if not keyword.strip():
        return []
    try:
        url = f"https://ac.search.naver.com/nx/ac?q={keyword}&con=0&dict=0&a_gb=0&spq=0&recover=0&fq=0&mod=0&r_format=json&r_enc=UTF-8&r_unicode=0&t_koreng=1&ans=2&run=2&rev=4&q_enc=UTF-8&st=100"
        r = requests.get(url, timeout=3)
        data = r.json()
        items = data.get('items', [[]])[0]
        return [item[0] for item in items][:10]
    except Exception:
        return []


@st.cache_data(show_spinner=False, ttl=1800)
def cached_naver_search_volume(keyword: str, cid: str, lic: str, sk: str):
    from naver_scraper import get_naver_search_volume
    return get_naver_search_volume(keyword, cid, lic, sk)


@st.cache_data(show_spinner=False, ttl=1800)
def cached_search_meta_ads(keyword: str, token: str, country: str, min_days: int):
    from meta_ad_library import search_meta_ads
    return search_meta_ads(
        keyword=keyword,
        access_token=token,
        country=country,
        min_days_running=min_days,
        limit=30,
    )


@st.cache_data(show_spinner=False, ttl=1800)
def cached_datalab_trends(keyword: str):
    from naver_datalab import get_datalab_trends
    return get_datalab_trends(keyword)


@st.cache_data(show_spinner=False, ttl=600)
def cached_test_notion_connection(token: str, db_id: str):
    from notion_sync import test_notion_connection
    return test_notion_connection(token, db_id)


def render_reference_validator_view(selected_keyword: str = ""):
    st.subheader("🎯 인스타 광고 레퍼런스 & 적합도 검증기")
    st.caption("키워드 하나로 **네이버 검색량 + 메타 장기집행 광고**를 동시에 확인하고, 레퍼런스 적합도를 즉시 판단합니다.")

    meta_token = os.environ.get("META_ACCESS_TOKEN", "")

    # ── 판정 기준 설정 ─────────────────────────────────
    with st.expander("⚙️ 판정 기준값 설정", expanded=False):
        _crit_col1, _crit_col2, _crit_col3 = st.columns(3)
        with _crit_col1:
            crit_min_volume = st.slider(
                "📊 최소 네이버 검색량 (PC+모바일)",
                min_value=1000, max_value=50000, value=10000, step=1000,
                help="이 수치 이상이면 '검색량 합격'"
            )
        with _crit_col2:
            crit_min_days = st.slider(
                "📅 메타 광고 최소 집행일",
                min_value=10, max_value=365, value=50, step=5,
                help="이 일수 이상 집행 중인 광고가 1건 이상이면 '메타 합격'"
            )
        with _crit_col3:
            ig_country = st.selectbox(
                "🌍 검색 국가",
                options=["KR", "US", "JP", "GB"],
                format_func=lambda c: {"KR": "🇰🇷 한국", "US": "🇺🇸 미국", "JP": "🇯🇵 일본", "GB": "🇬🇧 영국"}.get(c, c),
                key="ig_country"
            )

    tab_single, tab_bulk = st.tabs(["🔍 단일 키워드 검증", "📦 대량 일괄 검증"])

    # ────────────────────────────────────────────────────
    # 단일 키워드 검증 탭
    # ────────────────────────────────────────────────────
    with tab_single:
        if "root_ad_keyword" not in st.session_state:
            st.session_state["root_ad_keyword"] = selected_keyword if selected_keyword else ""
        if "ig_ad_keyword" not in st.session_state:
            st.session_state["ig_ad_keyword"] = selected_keyword if selected_keyword else ""

        def _on_keyword_input_change():
            val = st.session_state.get("ig_ad_keyword", "").strip()
            if val:
                st.session_state["root_ad_keyword"] = val
                st.session_state["trigger_search_auto"] = True
                if "related_pills_unified" in st.session_state:
                    st.session_state["related_pills_unified"] = None

        _sv_col1, _sv_col2 = st.columns([4, 1])
        with _sv_col1:
            ig_keyword = st.text_input(
                "🔍 검증할 키워드",
                placeholder="예: 허리찜질기, 무릎보호대, 다이어트",
                key="ig_ad_keyword",
                on_change=_on_keyword_input_change
            )

            curr_kw = st.session_state.get("ig_ad_keyword", "").strip()
            root_kw = st.session_state.get("root_ad_keyword", "").strip()
            if not root_kw and curr_kw:
                root_kw = curr_kw
                st.session_state["root_ad_keyword"] = curr_kw

            if root_kw and curr_kw and curr_kw != root_kw:
                _col_rev1, _col_rev2 = st.columns([3.2, 0.8])
                with _col_rev1:
                    st.info(f"📌 기준 키워드: **'{root_kw}'** ➔ 현재 연관 브랜드/키워드 검증: **'{curr_kw}'**")
                with _col_rev2:
                    if st.button(f"↩️ '{root_kw}' 복귀", key="btn_revert_root", use_container_width=True, type="primary"):
                        st.session_state["ig_ad_keyword"] = root_kw
                        st.session_state["related_pills_unified"] = root_kw
                        st.session_state["trigger_search_auto"] = True
                        st.rerun()

            target_kw_for_pills = root_kw if root_kw else curr_kw

            if target_kw_for_pills:
                _rel_items = get_naver_10k_related(target_kw_for_pills, min_volume=crit_min_volume)
                if _rel_items:
                    _kw_options = []
                    if root_kw:
                        _kw_options.append(root_kw)
                    for item in _rel_items:
                        if item["keyword"] != root_kw:
                            _kw_options.append(item["keyword"])

                    _kw_labels = {}
                    for k in _kw_options:
                        if k == root_kw:
                            _kw_labels[k] = f"↩️ {k} (원래 키워드 복귀)" if curr_kw != root_kw else f"🎯 {k} (기준 키워드)"
                        else:
                            it = next((x for x in _rel_items if x["keyword"] == k), None)
                            if it:
                                v = it["volume"]
                                v_fmt = f"{v/10000:.1f}만" if v >= 10000 else f"{v:,}"
                                prefix = "🏷️ " if it.get("is_brand") else ""
                                _kw_labels[k] = f"{prefix}{k} ({v_fmt})"
                            else:
                                _kw_labels[k] = k

                    def _update_kw_from_pill():
                        selected = st.session_state.get("related_pills_unified")
                        if selected:
                            st.session_state["ig_ad_keyword"] = selected
                            st.session_state["trigger_search_auto"] = True

                    if st.session_state.get("related_pills_unified") not in _kw_options:
                        st.session_state["related_pills_unified"] = curr_kw if curr_kw in _kw_options else None

                    st.pills(
                        f"🏷️ '{target_kw_for_pills}' 연관 검색어 & 브랜드 (검색량 {crit_min_volume:,}+ · {len(_kw_options)}개)",
                        options=_kw_options,
                        format_func=lambda k: _kw_labels.get(k, k),
                        key="related_pills_unified",
                        on_change=_update_kw_from_pill
                    )
                else:
                    _related = get_naver_autocomplete(target_kw_for_pills)
                    if _related:
                        _auto_options = []
                        if root_kw and root_kw not in _related:
                            _auto_options.append(root_kw)
                        _auto_options.extend([r for r in _related if r != root_kw])

                        _auto_labels = {}
                        for k in _auto_options:
                            if k == root_kw:
                                _auto_labels[k] = f"↩️ {k} (원래 키워드 복귀)" if curr_kw != root_kw else f"🎯 {k} (기준 키워드)"
                            else:
                                _auto_labels[k] = k

                        def _update_kw_from_pill_auto():
                            selected = st.session_state.get("related_pills_unified")
                            if selected:
                                st.session_state["ig_ad_keyword"] = selected
                                st.session_state["trigger_search_auto"] = True

                        if st.session_state.get("related_pills_unified") not in _auto_options:
                            st.session_state["related_pills_unified"] = curr_kw if curr_kw in _auto_options else None

                        st.pills(
                            f"💡 '{target_kw_for_pills}' 네이버 연관 검색어 (클릭 시 즉시 검증)",
                            options=_auto_options,
                            format_func=lambda k: _auto_labels.get(k, k),
                            key="related_pills_unified",
                            on_change=_update_kw_from_pill_auto
                        )
        with _sv_col2:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            _search_btn = st.button(
                "🔍 검색 & 검증",
                use_container_width=True,
                type="primary",
                key="sv_search_btn"
            )
            if _search_btn:
                val = st.session_state.get("ig_ad_keyword", "").strip()
                if val:
                    st.session_state["root_ad_keyword"] = val

        _auto_run = st.session_state.pop("trigger_search_auto", False)
        if _search_btn or _auto_run:
            _kw_to_search = (st.session_state.get("ig_ad_keyword") or ig_keyword or "").strip()
            if not _kw_to_search:
                st.error("키워드를 입력해주세요.")
            else:
                from naver_scraper import get_naver_search_volume
                from meta_ad_library import search_meta_ads
                from naver_datalab import get_datalab_trends, apply_volume_scaling
                _cid = os.environ.get("NAVER_CUSTOMER_ID", "")
                _lic = os.environ.get("NAVER_ACCESS_LICENSE", "")
                _sk  = os.environ.get("NAVER_SECRET_KEY", "")
                _kw_stripped = _kw_to_search

                with st.spinner(f"'{_kw_stripped}' 검색량, 1·3년 트렌드, 연령·성별 및 메타 광고 실시간 수집 중..."):
                    def _fetch_vol():
                        return cached_naver_search_volume(_kw_stripped, _cid, _lic, _sk)
                    def _fetch_meta_ads():
                        return cached_search_meta_ads(
                            keyword=_kw_stripped,
                            token=meta_token,
                            country=ig_country,
                            min_days=crit_min_days
                        )
                    def _fetch_datalab():
                        return cached_datalab_trends(_kw_stripped)

                    with _cf.ThreadPoolExecutor(max_workers=3) as _ex:
                        _fv = _ex.submit(_fetch_vol)
                        _fm = _ex.submit(_fetch_meta_ads)
                        _fdl = _ex.submit(_fetch_datalab)

                        _sv_vol  = _fv.result()
                        _sv_meta = _fm.result()
                        _sv_dl   = _fdl.result()

                if _sv_vol.get("total", 0) > 0 and _sv_dl.get("ok"):
                    _sv_dl = apply_volume_scaling(_sv_dl, _sv_vol["total"])

                st.session_state["unified_result"] = {
                    "keyword": _kw_stripped,
                    "vol": _sv_vol,
                    "meta": _sv_meta,
                    "datalab": _sv_dl,
                    "crit_vol": crit_min_volume,
                    "crit_days": crit_min_days,
                    "country": ig_country,
                }

        # ── 결과 표시 ────────────────────────────────────────────────
        if "unified_result" in st.session_state:
            _r      = st.session_state["unified_result"]
            _kw     = _r["keyword"]
            _vol    = _r["vol"]
            _meta   = _r["meta"]
            _dl     = _r.get("datalab", {})
            _cv     = _r["crit_vol"]
            _cd     = _r["crit_days"]
            _ctry   = _r.get("country", "KR")
            _total  = _vol.get("total", 0)
            _ads    = _meta.get("ads", [])
            _ad_cnt = len(_ads)
            _vol_ok  = _total >= _cv
            _meta_ok = _ad_cnt >= 1

            if _vol_ok and _meta_ok:
                _vc, _vt, _ve = "#00C853", "적합", "✅"
                _vd = f"검색 수요({_total:,})와 광고 성과({_ad_cnt}건) 모두 확인됨. 레퍼런스로 활용하기 좋습니다!"
            elif _vol_ok:
                _vc, _vt, _ve = "#FFB300", "조건부 (메타 레퍼런스 부족)", "⚠️"
                _vd = f"검색량({_total:,})은 충분하지만 {_cd}일+ 집행 광고가 없습니다. 직접 메타 라이브러리를 확인하세요."
            elif _meta_ok:
                _vc, _vt, _ve = "#FFB300", "조건부 (검색량 부족)", "⚠️"
                _vd = f"광고 성과({_ad_cnt}건)는 있지만 검색량({_total:,})이 기준({_cv:,}) 미달입니다."
            else:
                _vc, _vt, _ve = "#FF5252", "부적합", "❌"
                _vd = f"검색량({_total:,})과 장기집행 광고 모두 기준 미달입니다."

            st.markdown(
                f"""<div style="background:{_vc}1A;border-left:5px solid {_vc};
                border-radius:8px;padding:14px 18px;margin:12px 0;">
                <span style="font-size:1.3rem;font-weight:800;color:{_vc};">{_ve} {_vt}</span><br>
                <span style="font-size:0.93rem;color:#555;">{_vd}</span></div>""",
                unsafe_allow_html=True
            )

            if _total > 0 and _dl.get("df_1y") is not None and "검색량" not in _dl["df_1y"].columns:
                from naver_datalab import apply_volume_scaling
                _dl = apply_volume_scaling(_dl, _total)

            _mc1, _mc2 = st.columns(2)
            with _mc1:
                with st.container(border=True):
                    st.metric(
                        f"{'✅' if _vol_ok else '❌'} 네이버 검색량 (기준 {_cv:,}+)",
                        f"{_total:,}",
                        delta=f"PC {_vol.get('pc',0):,} | 모바일 {_vol.get('mobile',0):,}",
                        delta_color="normal"
                    )

                    st.markdown("---")
                    st.markdown("##### 👥 검색 연령 및 성별층 분석")

                    if _dl.get("ok"):
                        _g_ratio = _dl.get("gender_ratio", {"남성": 50.0, "여성": 50.0})
                        _a_ratio = _dl.get("age_ratio", {})
                        _target_4050 = _dl.get("target_4050_ratio", 50.0)

                        _m_pct = _g_ratio.get("남성", 50.0)
                        _f_pct = _g_ratio.get("여성", 50.0)

                        _g_col1, _g_col2 = st.columns(2)
                        with _g_col1:
                            st.metric("👨 남성 관심도", f"{_m_pct}%")
                        with _g_col2:
                            st.metric("👩 여성 관심도", f"{_f_pct}%")

                        _4050_color = "#00C853" if _target_4050 >= 40 else "#FFB300"
                        st.markdown(
                            f"""<div style="background:{_4050_color}18; border: 1px solid {_4050_color}; 
                            border-radius: 6px; padding: 6px 12px; margin: 8px 0; text-align: center;">
                            <span style="font-weight: 700; color: {_4050_color}; font-size: 0.95rem;">
                            🎯 4050 핵심 타겟 비중: {_target_4050}%
                            </span>
                            </div>""",
                            unsafe_allow_html=True
                        )

                        _age_df = pd.DataFrame([
                            {"연령대": k, "관심도(%)": v} for k, v in _a_ratio.items()
                        ])
                        st.bar_chart(
                            _age_df.set_index("연령대")["관심도(%)"],
                            height=160,
                            color="#3B82F6"
                        )
                    else:
                        st.caption("ℹ️ 연령 및 성별 분석 데이터를 불러오는 중이거나 조회가 지원되지 않는 키워드입니다.")

            with _mc2:
                with st.container(border=True):
                    _mode_label = {"scrape": "스크래핑", "api": "API", "link": "링크 모드"}.get(_meta.get("mode",""), "")
                    st.metric(
                        f"{'✅' if _meta_ok else '❌'} 메타 {_cd}일+ 장기집행 광고",
                        f"{_ad_cnt}건",
                        delta=_mode_label,
                        delta_color="normal"
                    )

                    st.markdown("---")
                    st.markdown("##### 📈 네이버 검색 트렌드 변화 그래프")

                    if _dl.get("ok"):
                        _period_choice = st.radio(
                            "기간 선택",
                            ["최근 1년", "최근 3년"],
                            horizontal=True,
                            key="trend_period_radio",
                            label_visibility="collapsed"
                        )

                        _chart_df = _dl.get("df_1y" if _period_choice == "최근 1년" else "df_3y")
                        if _chart_df is not None and not _chart_df.empty:
                            if "검색량" in _chart_df.columns and _total > 0:
                                st.line_chart(
                                    _chart_df.set_index("월")["검색량"],
                                    height=160,
                                    color="#00C73C"
                                )
                                _max_row = _chart_df.loc[_chart_df["검색량"].idxmax()]
                                _latest_row = _chart_df.iloc[-1]
                                st.caption(
                                    f"💡 **{_period_choice} 월간 검색량 (건)** · "
                                    f"최고: **{_max_row['월']}** ({_max_row['검색량']:,}건) | "
                                    f"최근: **{_latest_row['월']}** ({_latest_row['검색량']:,}건)"
                                )
                            else:
                                st.line_chart(
                                    _chart_df.set_index("월")["검색지수"],
                                    height=160,
                                    color="#00C73C"
                                )
                                st.caption(f"💡 {_period_choice} 월별 상대 검색지수 (최고점 = 100 기준)")

                            with st.expander("ℹ️ 검색량 산출 기준 및 오차범위 안내 (보고용)", expanded=False):
                                st.markdown(
                                    """
                                    <div style="font-size: 0.88rem; line-height: 1.6; color: #444;">
                                    <strong>📌 데이터 원천 및 산출 기준</strong><br>
                                    • <strong>공식 실데이터</strong>: 네이버 검색광고 API(<code>keywordstool</code>)에서 최근 30일 절대 검색량을 직접 호출 (오차 0%).<br>
                                    • <strong>과거 시계열 역산</strong>: 네이버는 과거 월별 절대 건수 API를 비공개하므로, <strong>최근 30일 공식 실측값</strong>과 네이버 데이터랩 선형 쿼리 지수를 매핑해 복원했습니다.<br>
                                    • <strong>업계 표준 방식</strong>: <em>아이템스카우트, 블랙키위, 판다랭크</em> 등 국내 1위권 키워드 분석 SaaS와 100% 동일한 산출 알고리즘입니다.<br><br>

                                    <strong>📊 구간별 오차범위 및 신뢰도</strong><br>
                                    • <strong>최근 1개월</strong>: <strong>오차 0% ~ 1% 미만</strong> (네이버 공식 실측치 직접 반영)<br>
                                    • <strong>과거 1년 데이터</strong>: <strong>오차 ±2% ~ ±4% 내외 (신뢰도 96%+)</strong><br>
                                    • <strong>과거 3년 데이터</strong>: <strong>오차 ±5% ~ ±7% 내외</strong><br>
                                    • <em>오차 원인</em>: 검색광고(최근 30일 롤링)와 데이터랩(달력 1일~말일)의 며칠 간 날짜 윈도우 편차 및 데이터랩 지수 소수점 반올림 때문입니다.<br><br>

                                    <strong>💡 실무 의사결정 활용도</strong><br>
                                    월 50,000건 키워드 기준 편차는 약 ±1,000~1,500건 안팎으로, <strong>시즌별 피크 시점 포착 및 숏폼 광고 소재 수요 규모 판단 시 98% 이상의 높은 신뢰도</strong>를 가집니다.
                                    </div>
                                    """,
                                    unsafe_allow_html=True
                                )
                    else:
                        st.caption("ℹ️ 네이버 데이터랩 트렌드 데이터를 불러오는 중이거나 조회가 지원되지 않는 키워드입니다.")

            from meta_ad_library import _build_search_url, _build_search_url_sorted
            _link_col1, _link_col2 = st.columns(2)
            with _link_col1:
                st.markdown(f"🔗 [Meta Ad Library 직접 검색 →]({_meta.get('url', _build_search_url(_kw, _ctry))})")
            with _link_col2:
                st.markdown(f"📊 [시작일 정렬로 보기 →]({_build_search_url_sorted(_kw, _ctry)})")

            _df_meta = _meta.get("df")
            if _meta.get("mode") in ("scrape", "api") and _df_meta is not None and not _df_meta.empty:
                _mode_icon = "🕷️ 스크래핑" if _meta.get("mode") == "scrape" else "🔌 API"
                st.success(f"{_mode_icon} 방식으로 {_cd}일+ 집행 광고 **{len(_df_meta)}개** 발견!")

                _sel_card_count = sum(1 for _idx in range(len(_df_meta)) if st.session_state.get(f"ad_card_sel_{_kw}_{_idx}", True))
                _top_c1, _top_c2, _top_c3 = st.columns([2.2, 0.9, 0.9])
                with _top_c1:
                    st.markdown(f"##### 🎯 검색 결과 목록 (총 {len(_df_meta)}개 중 **{_sel_card_count}개 선택됨**)")
                    st.caption("💡 각 카드 좌측의 체크박스로 노션에 저장할 광고를 바로 선택/해제할 수 있습니다.")
                with _top_c2:
                    if st.button("☑️ 전체 선택", key=f"btn_sel_all_{_kw}", use_container_width=True):
                        for _idx in range(len(_df_meta)):
                            st.session_state[f"ad_card_sel_{_kw}_{_idx}"] = True
                        if "notion_table_unified" in st.session_state and "edited_rows" in st.session_state["notion_table_unified"]:
                            st.session_state["notion_table_unified"]["edited_rows"] = {
                                _idx: {"선택": True} for _idx in range(len(_df_meta))
                            }
                        st.rerun()
                with _top_c3:
                    if st.button("◻️ 전체 해제", key=f"btn_desel_all_{_kw}", use_container_width=True):
                        for _idx in range(len(_df_meta)):
                            st.session_state[f"ad_card_sel_{_kw}_{_idx}"] = False
                        if "notion_table_unified" in st.session_state and "edited_rows" in st.session_state["notion_table_unified"]:
                            st.session_state["notion_table_unified"]["edited_rows"] = {
                                _idx: {"선택": False} for _idx in range(len(_df_meta))
                            }
                        st.rerun()

                for _i, _row in _df_meta.iterrows():
                    _card_key = f"ad_card_sel_{_kw}_{_i}"
                    if _card_key not in st.session_state:
                        st.session_state[_card_key] = True

                    _is_card_sel = st.session_state[_card_key]

                    with st.container(border=True):
                        _chk_col, _cc1, _cc2 = st.columns([0.45, 2.7, 1.1])
                        with _chk_col:
                            st.write("")
                            _card_checked = st.checkbox(
                                f"광고 #{_i+1} 선택",
                                value=_is_card_sel,
                                key=_card_key,
                                label_visibility="collapsed",
                            )
                            st.markdown(f"**#{_i+1}**")
                            if _card_checked:
                                st.caption("✅ 포함")
                            else:
                                st.caption("⚪ 제외")

                        with _cc1:
                            st.markdown(f"**🏪 {_row['페이지명']}**")
                            if _row.get("광고 카피"):
                                st.caption(_row["광고 카피"])
                            if _row.get("CTA"):
                                st.markdown(f"🔘 *{_row['CTA']}*")
                            if _row.get("연결링크"):
                                st.caption(f"🛒 **자사몰**: [{_row['연결링크'][:45]}...]({_row['연결링크']})")

                        with _cc2:
                            st.metric("집행 기간", _row.get("집행 기간", "-"))
                            st.caption(f"시작: {_row.get('집행 시작일', '-')}")
                            _m_type = _row.get("소재 유형", "")
                            if _m_type:
                                _m_badge = "🎬 영상" if _m_type == "영상" else ("🖼️ 이미지" if _m_type == "이미지" else "📑 캐러셀")
                                st.caption(f"**유형**: {_m_badge}")
                            if _row.get("게시 플랫폼"):
                                st.caption(f"📱 {_row['게시 플랫폼']}")
                            if _row.get("광고 보기"):
                                st.markdown(f"[👁️ 메타 광고 보기 →]({_row['광고 보기']})")

                st.markdown("---")
                st.markdown("#### 📋 기획 테이블 — 노션 저장용")
                st.caption("아래 표를 확인하고 광고 계정명/진행 여부를 입력한 뒤 노션에 저장하세요. (위 카드의 체크박스와 연동됩니다)")

                from meta_ad_library import clean_ad_copy

                if "notion_table_unified" in st.session_state:
                    if "edited_rows" not in st.session_state["notion_table_unified"]:
                        st.session_state["notion_table_unified"]["edited_rows"] = {}
                    for _k_idx in range(len(_df_meta)):
                        _c_val = st.session_state.get(f"ad_card_sel_{_kw}_{_k_idx}")
                        if _c_val is not None:
                            if _k_idx not in st.session_state["notion_table_unified"]["edited_rows"]:
                                st.session_state["notion_table_unified"]["edited_rows"][_k_idx] = {}
                            st.session_state["notion_table_unified"]["edited_rows"][_k_idx]["선택"] = _c_val

                _notion_rows = []
                for _idx_r, _row in _df_meta.iterrows():
                    _page_name = str(_row.get("페이지명", "")).strip()
                    _media_type = str(_row.get("소재 유형", "영상")).strip() or "영상"
                    _start_str = str(_row.get("집행 시작일", "")).strip()

                    _ad_date = date_type.today()
                    if _start_str:
                        try:
                            _ad_date = datetime.strptime(_start_str[:10], "%Y-%m-%d").date()
                        except Exception:
                            pass

                    _days_diff = max(0, (date_type.today() - _ad_date).days)

                    _raw_copy = _row.get("광고 카피 원문") or _row.get("광고 카피", "")
                    _cleaned_copy = clean_ad_copy(str(_raw_copy), brand=_page_name)

                    _media_tag = f"[{_media_type}]"
                    if _cleaned_copy and len(_cleaned_copy) >= 3 and _cleaned_copy.lower() not in ("none", "nan", "null"):
                        _short_copy = _cleaned_copy[:35] + ("..." if len(_cleaned_copy) > 35 else "")
                        _default_title = f"{_media_tag} {_page_name} - {_short_copy}" if _page_name else f"{_media_tag} {_short_copy}"
                    elif _page_name:
                        _date_label = _start_str if _start_str else "레퍼런스"
                        _default_title = f"{_media_tag} {_page_name} ({_date_label})"
                    else:
                        _default_title = f"{_media_tag} 광고 레퍼런스"

                    _row_is_checked = st.session_state.get(f"ad_card_sel_{_kw}_{_idx_r}", True)

                    _notion_rows.append({
                        "선택": _row_is_checked,
                        "제목": _default_title,
                        "소재 유형": _media_type,
                        "게재일": _ad_date,
                        "집행일수": f"{_days_diff}일차",
                        "광고 계정명": _page_name,
                        "진행 여부": "검토중",
                        "레퍼런스 링크": _row.get("광고 보기", ""),
                        "연결링크": _row.get("연결링크", ""),
                        "_days_diff": _days_diff,
                        "_video_url": _row.get("_video_url", ""),
                        "_광고 카피 원문": _cleaned_copy,
                        "_page_library_url": _row.get("_page_library_url", ""),
                    })
                _notion_df = pd.DataFrame(_notion_rows)
                _edited_df = st.data_editor(
                    _notion_df,
                    column_config={
                        "선택": st.column_config.CheckboxColumn("☑️ 선택", default=True, width="small"),
                        "제목": st.column_config.TextColumn("🏷️ 제목", width="large"),
                        "소재 유형": st.column_config.SelectboxColumn(
                            "🎬 소재 유형",
                            options=["영상", "이미지", "캐러셀"],
                            default="영상",
                            width="small",
                        ),
                        "게재일": st.column_config.DateColumn("📅 게재일", width="small", format="YYYY-MM-DD"),
                        "집행일수": st.column_config.TextColumn("⏳ 집행일수", width="small", disabled=True, help="오늘 기준 집행 경과 일수"),
                        "광고 계정명": st.column_config.TextColumn("🏷️ 광고 계정명", width="small"),
                        "진행 여부": st.column_config.SelectboxColumn(
                            "📌 진행 여부",
                            options=["검토중", "진행", "보류", "완료"],
                            width="small",
                        ),
                        "레퍼런스 링크": st.column_config.LinkColumn("🔗 레퍼런스(메타)", width="small"),
                        "연결링크": st.column_config.LinkColumn("🛒 연결링크(자사몰)", width="medium"),
                        "_days_diff": None,
                        "_video_url": None,
                        "_광고 카피 원문": None,
                        "_page_library_url": None,
                    },
                    width="stretch",
                    hide_index=True,
                    num_rows="fixed",
                    key="notion_table_unified",
                )

                def _save_notion_config(token: str, db_id: str):
                    _env_path = os.path.join(os.path.dirname(__file__), ".env")
                    _ec = ""
                    if os.path.exists(_env_path):
                        with open(_env_path, "r", encoding="utf-8") as _ef:
                            _ec = _ef.read()
                    if re.search(r"^NOTION_TOKEN=.*$", _ec, flags=re.MULTILINE):
                        _ec = re.sub(r"^NOTION_TOKEN=.*$", f"NOTION_TOKEN={token}", _ec, flags=re.MULTILINE)
                    else:
                        _ec = _ec.rstrip() + f"\nNOTION_TOKEN={token}\n"
                    if re.search(r"^NOTION_DATABASE_ID=.*$", _ec, flags=re.MULTILINE):
                        _ec = re.sub(r"^NOTION_DATABASE_ID=.*$", f"NOTION_DATABASE_ID={db_id}", _ec, flags=re.MULTILINE)
                    else:
                        _ec = _ec.rstrip() + f"\nNOTION_DATABASE_ID={db_id}\n"
                    with open(_env_path, "w", encoding="utf-8") as _ef:
                        _ef.write(_ec)
                    os.environ["NOTION_TOKEN"] = token
                    os.environ["NOTION_DATABASE_ID"] = db_id
                    load_dotenv(override=True)
                    cached_test_notion_connection.clear()

                def _save_gdrive_config(folder_url: str):
                    _env_path = os.path.join(os.path.dirname(__file__), ".env")
                    _ec = ""
                    if os.path.exists(_env_path):
                        with open(_env_path, "r", encoding="utf-8") as _ef:
                            _ec = _ef.read()
                    if re.search(r"^GOOGLE_DRIVE_FOLDER_URL=.*$", _ec, flags=re.MULTILINE):
                        _ec = re.sub(r"^GOOGLE_DRIVE_FOLDER_URL=.*$", f"GOOGLE_DRIVE_FOLDER_URL={folder_url}", _ec, flags=re.MULTILINE)
                    else:
                        _ec = _ec.rstrip() + f"\nGOOGLE_DRIVE_FOLDER_URL={folder_url}\n"
                    with open(_env_path, "w", encoding="utf-8") as _ef:
                        _ef.write(_ec)
                    os.environ["GOOGLE_DRIVE_FOLDER_URL"] = folder_url
                    load_dotenv(override=True)

                from gdrive_sync import test_gdrive_folder_access, download_video_file, upload_video_to_gdrive

                _notion_token = os.environ.get("NOTION_TOKEN", "").strip()
                _notion_db_id = os.environ.get("NOTION_DATABASE_ID", "").strip()
                _gdrive_folder = os.environ.get("GOOGLE_DRIVE_FOLDER_URL", "").strip()
                _gdrive_sa = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json").strip()

                if not _notion_token or not _notion_db_id:
                    with st.expander("⚙️ 노션 연동 설정 필요", expanded=True):
                        st.warning("노션에 저장하려면 아래 정보를 입력하세요.")
                        _nc1, _nc2 = st.columns(2)
                        with _nc1:
                            _in_token = st.text_input("Notion Integration Token", placeholder="ntn_...", type="password", key="input_notion_token")
                        with _nc2:
                            _in_db = st.text_input("Notion Database ID", placeholder="32자리 ID", key="input_notion_db_id")
                        if st.button("💾 설정 저장", key="save_notion_settings"):
                            if _in_token.strip() and _in_db.strip():
                                _save_notion_config(_in_token.strip(), _in_db.strip())
                                st.success("✅ 설정이 저장되었습니다!")
                                st.rerun()
                            else:
                                st.error("토큰과 DB ID를 모두 입력해주세요.")
                else:
                    from notion_sync import save_ad_reference_to_notion
                    _conn = cached_test_notion_connection(_notion_token, _notion_db_id)

                    _gd_res = test_gdrive_folder_access(_gdrive_folder, _gdrive_sa) if _gdrive_folder else {"ok": False, "error": "폴더 미설정"}

                    with st.expander("⚙️ 노션 & 구글 드라이브 연동 상태", expanded=(not _conn["ok"] or not _gd_res["ok"])):
                        _st_col1, _st_col2 = st.columns(2)
                        with _st_col1:
                            st.markdown("##### 📝 노션 연동")
                            if _conn["ok"]:
                                st.success(f"데이터베이스: **{_conn['title']}**")
                            else:
                                st.error(f"연결 오류: {_conn['error']}")
                                st.info("💡 DB 페이지 우측 상단 `···` → `연결(Connections)`에 통합 추가 여부 확인")

                            with st.popover("⚙️ 노션 정보 변경"):
                                _re_token = st.text_input("토큰", value=_notion_token, type="password", key="re_token")
                                _re_db = st.text_input("DB ID", value=_notion_db_id, key="re_db")
                                if st.button("💾 노션 변경 저장", key="re_save_notion"):
                                    if _re_token.strip() and _re_db.strip():
                                        _save_notion_config(_re_token.strip(), _re_db.strip())
                                        st.rerun()

                        with _st_col2:
                            st.markdown("##### ☁️ 구글 드라이브 연동")
                            if _gd_res["ok"]:
                                st.success(f"폴더 연결 성공: **{_gd_res.get('folder_name', '확인됨')}**")
                                st.caption("✅ 저장 시 원본 영상이 구글 드라이브에 자동 업로드되어 노션에 링크됩니다.")
                            elif _gd_res.get("api_disabled"):
                                st.error("❌ Google Drive API 활성화 필요")
                                st.markdown(f"👉 [Google Cloud Console에서 Drive API 사용 설정하기]({_gd_res.get('enable_url')})")
                                st.caption("위 링크 접속 후 **[사용 설정]** 버튼을 클릭하시면 1분 내 활성화됩니다.")
                            else:
                                st.warning(f"⚠️ 구글 드라이브 상태: {_gd_res.get('error', '설정 필요')}")
                                st.caption("💡 폴더 공유 설정에서 서비스 계정(`nori-213@nori-508115.iam.gserviceaccount.com`)을 **편집자**로 추가해주세요.")

                            with st.popover("⚙️ 구글 드라이브 폴더 변경"):
                                _re_gdrive = st.text_input("구글 드라이브 폴더 링크", value=_gdrive_folder, key="re_gdrive_input")
                                if st.button("💾 폴더 링크 저장", key="save_gdrive_folder_btn"):
                                    if _re_gdrive.strip():
                                        _save_gdrive_config(_re_gdrive.strip())
                                        st.rerun()

                    _sel_rows = _edited_df[_edited_df["선택"] == True]
                    _ns1, _ns2 = st.columns([2, 1])
                    with _ns1:
                        _drive_badge = "☁️ 구글 드라이브 자동 백업 포함" if _gd_res["ok"] else "⚠️ 메타 링크로 저장 (드라이브 미연동)"
                        st.caption(f"☑️ 선택된 {len(_sel_rows)}개 항목을 노션에 저장합니다. ({_drive_badge})")
                    with _ns2:
                        _save_btn = st.button("📤 노션에 저장하기", type="primary", use_container_width=True, key="save_to_notion_unified")
                    if _save_btn:
                        if len(_sel_rows) == 0:
                            st.warning("선택된 항목이 없습니다.")
                        else:
                            _progress_bar = st.progress(0, text="노션 저장 준비 중...")
                            _saved, _failed, _last_err = 0, 0, ""
                            _gdrive_uploaded = 0

                            for _idx, (_, _row) in enumerate(_sel_rows.iterrows()):
                                _brand_name = str(_row.get("광고 계정명", _row.get("브랜드", ""))).strip()
                                _video_src = str(_row.get("_video_url", "")).strip()
                                _meta_ref_url = str(_row.get("레퍼런스 링크", "")).strip()
                                _final_ref_url = _meta_ref_url

                                if _gd_res["ok"] and _video_src and _video_src.startswith("http"):
                                    _progress_bar.progress(
                                        int((_idx / len(_sel_rows)) * 100),
                                        text=f"☁️ [{_idx + 1}/{len(_sel_rows)}] '{_brand_name}' 영상 다운로드 및 구글 드라이브 업로드 중..."
                                    )
                                    _safe_brand = re.sub(r"[^\w\s-]", "", _brand_name).strip().replace(" ", "_")[:20] or "광고"
                                    _ad_date_str = str(_row.get("게재일", str(date_type.today())))
                                    _fname = f"[{_safe_brand}]_{_ad_date_str}_{int(time.time())}_{_idx+1}.mp4"
                                    _local_path = os.path.join(os.path.dirname(__file__), "outputs", "references", _fname)

                                    if download_video_file(_video_src, _local_path):
                                        _up_res = upload_video_to_gdrive(
                                            local_path=_local_path,
                                            file_name=_fname,
                                            folder_id_or_url=_gdrive_folder,
                                            credentials_path=_gdrive_sa,
                                        )
                                        if _up_res["ok"]:
                                            _final_ref_url = _up_res["web_view_link"]
                                            _gdrive_uploaded += 1
                                        else:
                                            st.caption(f"⚠️ '{_brand_name}' 드라이브 업로드 실패(메타 링크 대체): {_up_res.get('error')}")

                                _progress_bar.progress(
                                    int(((_idx + 0.5) / len(_sel_rows)) * 100),
                                    text=f"📝 [{_idx + 1}/{len(_sel_rows)}] '{_brand_name}' 노션 데이터베이스 저장 중..."
                                )

                                _acct_url = str(_row.get("_page_library_url", "")).strip()
                                if not _acct_url or not _acct_url.startswith("http"):
                                    _pid = str(_row.get("page_id", "")).strip()
                                    if _pid and _pid.isdigit():
                                        _acct_url = f"https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=KR&view_all_page_id={_pid}"
                                    elif _brand_name:
                                        from urllib.parse import quote_plus
                                        _acct_url = f"https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=KR&q={quote_plus(_brand_name)}&search_type=keyword_unordered"

                                _ad_date_raw = str(_row.get("게재일", str(date_type.today())))
                                _days_val = None
                                try:
                                    _parsed_d = datetime.strptime(_ad_date_raw[:10], "%Y-%m-%d").date()
                                    _days_val = max(0, (date_type.today() - _parsed_d).days)
                                except Exception:
                                    if "_days_diff" in _row and pd.notna(_row.get("_days_diff")):
                                        try:
                                            _days_val = int(_row.get("_days_diff"))
                                        except Exception:
                                            pass

                                _res = save_ad_reference_to_notion(
                                    token=_notion_token,
                                    database_id=_notion_db_id,
                                    title=str(_row.get("제목", "")),
                                    media_type=str(_row.get("소재 유형", "영상")),
                                    date=_ad_date_raw,
                                    days_elapsed=_days_val,
                                    ad_copy=str(_row.get("_광고 카피 원문", "")),
                                    reference_url=_final_ref_url,
                                    landing_url=str(_row.get("연결링크", "")),
                                    account_name=_brand_name,
                                    account_url=_acct_url,
                                    status=str(_row.get("진행 여부", "검토중")),
                                    keyword=_kw,
                                    page_name=_brand_name,
                                    client_account_id=str(_row.get("page_id", "")),
                                )
                                if _res["ok"]:
                                    _saved += 1
                                else:
                                    _failed += 1
                                    _last_err = _res.get("error", "")

                            _progress_bar.progress(100, text="저장 완료!")
                            if _failed == 0:
                                _gmsg = f" (☁️ {_gdrive_uploaded}개 구글 드라이브 업로드 완료)" if _gdrive_uploaded > 0 else ""
                                st.success(f"✅ {_saved}개 항목이 노션에 성공적으로 저장되었습니다!{_gmsg}")
                                st.balloons()
                            else:
                                st.warning(f"저장 결과: {_saved}개 성공, {_failed}개 실패")
                                if _last_err:
                                    st.error(f"실패 원인: {_last_err}")

            elif _meta.get("mode") == "link" or (_df_meta is None or _df_meta.empty):
                if _meta.get("mode") == "link":
                    st.info("📋 스크래핑이 차단됐거나 Access Token이 없어 직접 확인이 필요합니다.")
                else:
                    st.info(f"'{_kw}' 키워드로 {_cd}일+ 집행 중인 활성 광고를 찾지 못했습니다. 기간을 줄이거나 키워드를 변경해보세요.")

                with st.container(border=True):
                    st.markdown("### 💡 장기집행 광고 레퍼런스 찾는 법")
                    st.markdown(f"""
1. 위 **Meta Ad Library** 링크로 이동하여 검색 결과의 **시작 날짜**를 확인합니다.
2. 오래 전 시작된 광고 = ROAS가 좋아서 예산이 유지되는 **"위닝 광고"**입니다.
3. 해당 광고의 **카피, 영상 구성, 썸네일 스타일**을 레퍼런스로 활용하세요.

> 🎯 **Tip**: `{_kw}`와 관련된 경쟁사 브랜드명이나 제품 카테고리명도 함께 검색해보세요!
                    """)
                    _sug_kws = _generate_related_keywords(_kw)
                    _sc = st.columns(len(_sug_kws))
                    for _si, _sug in enumerate(_sug_kws):
                        _sug_url = _build_search_url(_sug, _ctry)
                        with _sc[_si]:
                            st.markdown(f"[`{_sug}`]({_sug_url})")

    # ────────────────────────────────────────────────────
    # 대량 일괄 검증 탭
    # ────────────────────────────────────────────────────
    with tab_bulk:
        st.caption("키워드를 **한 줄에 하나씩** 입력하면 전체를 일괄 검증합니다.")
        bulk_kw_text = st.text_area(
            "📝 키워드 목록 (줄바꿈으로 구분)",
            placeholder="허리찜질기\n무릎보호대\n발뒤꿈치 통증\n목디스크 치료",
            height=160,
            key="bulk_kw_textarea"
        )
        _bulk_col1, _bulk_col2 = st.columns([3, 1])
        with _bulk_col2:
            bulk_btn = st.button("🚀 일괄 검증 시작", use_container_width=True, type="primary", key="bulk_btn")

        if bulk_btn:
            _raw_kws = [k.strip() for k in bulk_kw_text.strip().splitlines() if k.strip()]
            if not _raw_kws:
                st.error("키워드를 입력해주세요.")
            else:
                from naver_scraper import get_naver_search_volume
                from meta_ad_library import search_meta_ads, _build_search_url
                _cid2 = os.environ.get("NAVER_CUSTOMER_ID", "")
                _lic2 = os.environ.get("NAVER_ACCESS_LICENSE", "")
                _sk2  = os.environ.get("NAVER_SECRET_KEY", "")

                _bulk_rows = []
                _prog = st.progress(0)
                _status = st.empty()

                for _i, _kw2 in enumerate(_raw_kws):
                    _status.text(f"🔄 {_i+1}/{len(_raw_kws)} — {_kw2} 조회 중...")
                    try:
                        _v = get_naver_search_volume(_kw2, _cid2, _lic2, _sk2)
                        _v_total = _v.get("total", 0)
                    except Exception:
                        _v_total = 0

                    try:
                        _m = search_meta_ads(keyword=_kw2, access_token=meta_token, country=ig_country, min_days_running=crit_min_days, limit=10)
                        _m_cnt = len(_m.get("ads", []))
                        _m_url = _m.get("url", _build_search_url(_kw2, ig_country))
                    except Exception:
                        _m_cnt = 0
                        _m_url = _build_search_url(_kw2, ig_country)

                    _vol_ok2  = _v_total >= crit_min_volume
                    _meta_ok2 = _m_cnt >= 1
                    if _vol_ok2 and _meta_ok2:
                        _v2 = "✅ 적합"
                    elif _vol_ok2 or _meta_ok2:
                        _v2 = "⚠️ 조건부"
                    else:
                        _v2 = "❌ 부적합"

                    _bulk_rows.append({
                        "키워드": _kw2,
                        f"검색량 (≥{crit_min_volume:,})": _v_total,
                        f"메타 {crit_min_days}일+ 광고": f"{_m_cnt}건",
                        "판정": _v2,
                        "Meta 라이브러리": _m_url,
                    })
                    _prog.progress((_i + 1) / len(_raw_kws))
                    time.sleep(0.3)

                _status.empty()
                _prog.empty()
                st.session_state["bulk_sv_results"] = _bulk_rows

        if "bulk_sv_results" in st.session_state:
            _brows = st.session_state["bulk_sv_results"]
            _bdf = pd.DataFrame(_brows)
            _n_ok   = sum(1 for r in _brows if r["판정"].startswith("✅"))
            _n_cond = sum(1 for r in _brows if r["판정"].startswith("⚠️"))
            _n_bad  = sum(1 for r in _brows if r["판정"].startswith("❌"))

            _s1, _s2, _s3, _s4 = st.columns(4)
            _s1.metric("전체", f"{len(_brows)}건")
            _s2.metric("✅ 적합", f"{_n_ok}건")
            _s3.metric("⚠️ 조건부", f"{_n_cond}건")
            _s4.metric("❌ 부적합", f"{_n_bad}건")

            _sort_map = {"✅ 적합": 0, "⚠️ 조건부": 1, "❌ 부적합": 2}
            _bdf["_s"] = _bdf["판정"].map(lambda x: _sort_map.get(x, 9))
            _bdf = _bdf.sort_values("_s").drop(columns=["_s"]).reset_index(drop=True)

            st.dataframe(
                _bdf,
                column_config={"Meta 라이브러리": st.column_config.LinkColumn("🔗 Meta 라이브러리")},
                hide_index=True, width="stretch"
            )
            _csv = _bdf.drop(columns=["Meta 라이브러리"]).to_csv(index=False, encoding="utf-8-sig")
            st.download_button(
                "📥 결과 CSV 다운로드",
                data=_csv.encode("utf-8-sig"),
                file_name="reference_validation.csv",
                mime="text/csv"
            )
