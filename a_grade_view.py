"""
🏆 A급 소재 탐색 & 브랜드 연결 계정 추적 화면 (app.py 탭)

A급 = ① 최근 1년 안에 브랜드·제품 월간 검색량 1만+ ② 메타 60일+ 게재 중 ③ 우리 제품 연관
A급 브랜드는 같은 자사몰로 광고하는 아랍어·외국어·위장·숨은 계정까지 추적합니다.
브랜드별 네이버 검색량·연령·성별층을 보여주고, A급 소재를 노션에 기록합니다.
"""

import json
import os
from dataclasses import asdict

import altair as alt
import pandas as pd
import streamlit as st

from notion_reference_panel import check_recorded, notion_ready, render_notion_saver
from a_grade_finder import (
    ACCOUNT_ARABIC,
    ACCOUNT_DISGUISED,
    ACCOUNT_FOREIGN,
    ACCOUNT_HIDDEN,
    ACCOUNT_OFFICIAL,
    ACCOUNT_ORDER,
    DEFAULT_EXCLUDE_TERMS,
    DEFAULT_RELEVANCE_TERMS,
    DEFAULT_SCAN_KEYWORDS,
    MIN_PEAK_VOLUME,
    MIN_RUNNING_DAYS,
    RISE_ROCKET,
    RISE_UP,
    SPIKE_MIN_JUMP,
    SPIKE_MIN_RATIO,
    ScanSettings,
    audience_keyword,
    fetch_brand_audience,
    find_a_grade_ads,
    parse_terms,
    recheck_brand_volume,
    rise_summary,
    save_report,
    sort_brands,
    track_brand,
    volume_summary,
)

_STATE_KEY = "a_grade_report"

TYPE_BADGE = {
    ACCOUNT_ARABIC: "🟥 아랍어",
    ACCOUNT_FOREIGN: "🟧 외국어",
    ACCOUNT_DISGUISED: "🟨 위장",
    ACCOUNT_HIDDEN: "🟦 숨은",
    ACCOUNT_OFFICIAL: "🟩 공식",
}


def _naver_creds() -> tuple:
    return tuple(os.environ.get(k, "") for k in ("NAVER_CUSTOMER_ID", "NAVER_ACCESS_LICENSE", "NAVER_SECRET_KEY"))


def _mark(value) -> str:
    return "✅" if value else ("⚠️" if value is None else "❌")


def _progress_bar(bar):
    def _update(fraction: float, message: str):
        bar.progress(min(max(float(fraction), 0.0), 1.0), text=message)
    return _update


def _persist(report) -> None:
    if report.saved_path:
        try:
            save_report(report, report.saved_path)
        except OSError:
            pass


def _max_days(brand) -> int:
    return max((a.running_days for a in brand.ads), default=0)


def _type_counts(accounts) -> str:
    counts = {t: sum(1 for a in accounts if a.account_type == t) for t in ACCOUNT_ORDER}
    return " · ".join(f"{TYPE_BADGE[t]} {n}" for t, n in counts.items() if n) or "없음"


def _rise_badge(volume) -> str:
    level = getattr(volume, "rise_level", "") if volume else ""
    return level or "추이 없음"


def _rise_jump_text(volume) -> str:
    if not volume or not getattr(volume, "rise_end", ""):
        return "-"
    ratio = volume.rise_ratio
    ratio_text = "신규" if ratio is None else f"{ratio:.1f}배"
    return f"{volume.rise_jump:+,} ({ratio_text})"


def _trend_chart(volume, settings):
    """30일 롤링 검색량 선 + 급상승 구간(음영) + ① 기준선"""
    data = pd.DataFrame(volume.windows)
    data["end"] = pd.to_datetime(data["end"])
    line = alt.Chart(data).mark_line(color="#00C73C").encode(
        x=alt.X("end:T", title="30일 구간 끝나는 날"),
        y=alt.Y("volume:Q", title="30일 검색량"),
        tooltip=[alt.Tooltip("end:T", title="끝나는 날"), alt.Tooltip("volume:Q", title="30일 검색량", format=",")],
    )
    layers = [line]
    if volume.rise_end:
        band = pd.DataFrame([{"start": pd.to_datetime(volume.rise_start), "end": pd.to_datetime(volume.rise_end)}])
        layers.insert(0, alt.Chart(band).mark_rect(color="#FF6D00", opacity=0.15).encode(x="start:T", x2="end:T"))
    rule = pd.DataFrame([{"y": settings.min_peak_volume}])
    layers.append(alt.Chart(rule).mark_rule(color="#9E9E9E", strokeDash=[4, 4]).encode(y="y:Q"))
    return alt.layer(*layers).properties(height=190)


# ─────────────────────────────────────────────────────────────────
# 네이버 검색량 · 연령·성별층 (예전 레퍼런스 검증 탭에서 옮김)
# ─────────────────────────────────────────────────────────────────

def _render_search_panel(brand, report, wkey: str) -> None:
    volume = brand.volume
    audience = getattr(brand, "audience", None) or {}
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            if volume and volume.keyword:
                st.metric(
                    f"🔎 네이버 검색량 · {volume.keyword}",
                    f"{volume.recent_30d:,}",
                    delta=f"PC {getattr(volume, 'recent_pc', 0):,} | 모바일 {getattr(volume, 'recent_mobile', 0):,}",
                    delta_color="off",
                )
                st.caption("최근 30일 검색수 (네이버 검색광고)")
            else:
                st.metric("🔎 네이버 검색량", "-")
                st.caption((volume.note if volume and volume.note else "") or "확인한 키워드가 없습니다")
    with right:
        with st.container(border=True):
            st.markdown("##### 👥 연령 및 성별층 분석")
            if audience.get("ok"):
                gender = audience.get("gender") or {}
                g1, g2 = st.columns(2)
                g1.metric("👨 남성", f"{gender.get('남성', 0.0)}%")
                g2.metric("👩 여성", f"{gender.get('여성', 0.0)}%")
                target = audience.get("target_4050", 0.0)
                color = "#00C853" if target >= 40 else "#FFB300"
                st.markdown(
                    f"""<div style="background:{color}18; border: 1px solid {color}; border-radius: 6px;
                    padding: 6px 12px; margin: 8px 0; text-align: center;">
                    <span style="font-weight: 700; color: {color}; font-size: 0.95rem;">🎯 4050 핵심 타겟 비중: {target}%</span>
                    </div>""",
                    unsafe_allow_html=True,
                )
                ages = pd.DataFrame([{"연령대": k, "비중(%)": v} for k, v in (audience.get("age") or {}).items()])
                if not ages.empty:
                    st.bar_chart(ages.set_index("연령대")["비중(%)"], height=160, color="#3B82F6")
                st.caption(
                    f"'{audience.get('keyword')}' 네이버 쇼핑인사이트 클릭 비중 · {audience.get('category')} 분류 · "
                    f"{audience.get('period')}"
                )
            else:
                st.caption(audience.get("error") or "아직 확인하지 않았습니다.")
            label = "🔄 다시 확인" if audience else "👥 연령·성별 확인"
            if st.button(label, key=f"ag_aud_{wkey}"):
                with st.spinner("연령·성별 비중을 확인하는 중…"):
                    fetch_brand_audience(brand)
                _persist(report)
                st.rerun()


# ─────────────────────────────────────────────────────────────────
# 표 데이터
# ─────────────────────────────────────────────────────────────────

def _visible_ads(brand, show_recorded: bool) -> list:
    return [a for a in brand.ads if show_recorded or not a.recorded]


def _new_ads_text(brand, report) -> str:
    if not report.recorded_checked:
        return f"{len(brand.ads)}"
    new = sum(1 for a in brand.ads if not a.recorded)
    return f"새 소재 {new}" + (f" (노션 {len(brand.ads) - new})" if new < len(brand.ads) else "")


def _summary_rows(report) -> list:
    rows = []
    for b in report.brands:
        rows.append({
            "등급": "🏆 A급" if b.is_a_grade else "—",
            "급상승": _rise_badge(b.volume),
            "30일 증가": _rise_jump_text(b.volume),
            "브랜드": b.name,
            "식별(랜딩)": b.key,
            "① 검색량 (최근 1년 최고)": volume_summary(b.volume),
            "② 최장 게재": f"{_max_days(b)}일",
            "③ 연관 키워드": ", ".join(b.relevance_terms),
            "광고 수": _new_ads_text(b, report),
            "연결 계정": len(b.accounts) if b.tracked else None,
            "미달 사유": " / ".join(b.reasons),
            "랜딩": b.landing_url or None,
        })
    return rows


def _ad_rows(ads) -> list:
    return [{
        "노션": f"✔ 기록됨 ({a.recorded})" if a.recorded else "",
        "페이지": a.page_name,
        "시작일": a.start_date,
        "게재일수": a.running_days,
        "유형": a.media_type,
        "변형": a.variants if a.variants > 1 else None,
        "연관 키워드": ", ".join(a.relevance),
        "광고 문구": (a.copy[:90] + "…") if len(a.copy) > 90 else a.copy,
        "광고 보기": a.library_url or None,
        "영상": a.video_url or None,
        "랜딩": a.landing_url or None,
    } for a in ads]


def _account_rows(brand) -> list:
    return [{
        "유형": TYPE_BADGE.get(a.account_type, a.account_type),
        "페이지명": a.page_name,
        "판단 이유": a.type_reason,
        "신뢰도": a.confidence,
        "이 브랜드 광고": a.brand_ads,
        "확인한 게재 광고": a.checked_ads,
        "최장 게재": a.max_running_days,
        "찾은 경로": _found_via_text(a),
        "근거": " / ".join(a.evidence),
        "다른 랜딩": ", ".join(a.other_landings),
        "광고 라이브러리": a.library_url or None,
        "페이지": a.profile_url or None,
    } for a in brand.accounts]


def _found_via_text(account) -> str:
    via = getattr(account, "found_via", "") or ""
    depth = getattr(account, "depth", 0) or 0
    return f"🔁 {depth}단계 · {via}" if depth else via


def _export_ads(report) -> pd.DataFrame:
    rows = []
    for b in report.a_grade_brands:
        for a in b.ads:
            rows.append({
                "브랜드": b.name, "식별(랜딩)": b.key, "① 검색량": volume_summary(b.volume),
                "급상승": rise_summary(b.volume),
                "페이지": a.page_name, "page_id": a.page_id, "시작일": a.start_date, "게재일수": a.running_days,
                "유형": a.media_type, "연관 키워드": ", ".join(a.relevance), "광고 문구": a.copy,
                "광고 보기": a.library_url, "영상": a.video_url, "랜딩": a.landing_url,
            })
    return pd.DataFrame(rows)


def _export_accounts(report) -> pd.DataFrame:
    rows = []
    for b in report.brands:
        for a in b.accounts:
            rows.append({
                "브랜드": b.name, "식별(랜딩)": b.key, "유형": a.account_type, "페이지명": a.page_name,
                "page_id": a.page_id, "판단 이유": a.type_reason, "섞인 문자": ", ".join(a.foreign_scripts),
                "신뢰도": a.confidence, "이 브랜드 광고": a.brand_ads, "확인한 게재 광고": a.checked_ads,
                "최장 게재일": a.max_running_days, "찾은 경로": _found_via_text(a), "근거": " / ".join(a.evidence),
                "다른 랜딩": ", ".join(a.other_landings), "광고 라이브러리": a.library_url, "페이지": a.profile_url,
            })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────
# 화면
# ─────────────────────────────────────────────────────────────────

def _render_brand(brand, report, settings, expanded: bool, show_recorded: bool = False) -> None:
    token = report.generated_at.replace(":", "")
    wkey = f"{token}_{brand.key}"
    rise_badge = _rise_badge(brand.volume)
    title = (f"{'🏆' if brand.is_a_grade else '▫️'} {brand.name}  ·  {rise_badge}  ·  {brand.key}  ·  "
             f"{volume_summary(brand.volume)}")
    with st.expander(title, expanded=expanded):
        if brand.volume and brand.volume.rise_end:
            color = {RISE_ROCKET: "#FF6D00", RISE_UP: "#2E7D32"}.get(brand.volume.rise_level, "#757575")
            st.markdown(
                f"<div style='border-left:4px solid {color};padding:4px 10px;margin-bottom:6px;'>"
                f"<b>{brand.volume.rise_level}</b> · {rise_summary(brand.volume).split(' · ', 1)[1]}</div>",
                unsafe_allow_html=True,
            )
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f"**① 검색량 1만+** {_mark(brand.criteria.get('search_spike'))}")
            st.caption(volume_summary(brand.volume))
        with c2:
            st.markdown(f"**② {settings.min_running_days}일+ 게재** {_mark(brand.criteria.get('long_running'))}")
            st.caption(f"최장 {_max_days(brand)}일 · 연관 광고 {len(brand.ads)}개")
        with c3:
            st.markdown(f"**③ 제품 연관** {_mark(brand.criteria.get('relevant'))}")
            st.caption(", ".join(brand.relevance_terms) or "-")
        if brand.reasons:
            st.caption("미달: " + " / ".join(brand.reasons))

        _render_search_panel(brand, report, wkey)

        volume = brand.volume
        windows = getattr(volume, "windows", None) if volume else None
        if volume and (windows or volume.months):
            tab_trend, tab_month = st.tabs(["📈 30일 검색량 추이", "📊 달력 월별 (참고)"])
            with tab_trend:
                if windows:
                    st.altair_chart(_trend_chart(volume, settings), width="stretch")
                    st.caption(
                        f"'{volume.keyword}' 끝나는 날마다 직전 30일 검색량 (네이버 검색광고 최근 30일 {volume.recent_30d:,}건 × "
                        f"데이터랩 일간 추이) · 주황 음영 = 가장 가파른 30일 · 점선 = ① 기준 {settings.min_peak_volume:,}건"
                    )
                else:
                    st.caption("30일 추이가 없습니다.")
            with tab_month:
                if volume.months:
                    chart = pd.DataFrame([
                        {"월": m["month"] + ("*" if m.get("partial") else ""), "검색량": m["volume"]} for m in volume.months
                    ]).set_index("월")["검색량"]
                    st.bar_chart(chart, height=170, color="#00C73C")
                    st.caption("*는 일부 날짜만 포함된 달입니다. 달 경계에 걸친 급상승은 두 달로 나뉘어 보입니다.")
                else:
                    st.caption("월별 추이가 없습니다.")
        if volume and volume.checked:
            st.caption("확인한 키워드: " + " · ".join(
                f"{c['keyword']} 최근 30일 {c['recent_30d']:,}건"
                + (f" / 최고 {c['peak_volume']:,}건" if c.get("peak_volume") else "")
                + (f" / {c['rise_level']} {c['rise_jump']:+,}" if c.get("rise_level") else "")
                + (f" ({c['note']})" if c.get("note") else "")
                for c in volume.checked
            ))

        kc1, kc2 = st.columns([4, 1])
        with kc1:
            new_keywords = st.text_input(
                "① 검색량 확인 키워드 (쉼표 구분 · 브랜드명·제품명, 검색수 상위 2개는 30일 추이까지 확인)",
                value=", ".join(brand.keywords),
                key=f"ag_kw_{wkey}",
                help="자사몰 이름·영문 도메인·페이지 이름에서 자동으로 골랐습니다. 제품명으로도 확인하려면 추가하세요.",
            )
        with kc2:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            recheck = st.button("🔄 다시 확인", key=f"ag_recheck_{wkey}", width="stretch")
        hints = []
        if brand.product_hint:
            hints.append(f"💡 제품명 후보: **{brand.product_hint}**")
        if brand.landing_title:
            hints.append(f"랜딩 제목: {brand.landing_title}")
        if hints:
            st.caption(" · ".join(hints))
        if recheck:
            with st.spinner("검색량을 다시 확인하는 중…"):
                recheck_brand_volume(brand, parse_terms(new_keywords), settings, _naver_creds())
                audience = getattr(brand, "audience", None) or {}
                if brand.is_a_grade and audience.get("keyword") != audience_keyword(brand):
                    fetch_brand_audience(brand)
            if brand.is_a_grade and settings.track_accounts and not brand.tracked:
                bar = st.progress(0.0, text="연결 계정 추적 준비 중…")
                track_brand(brand, settings, progress=_progress_bar(bar))
            report.brands = sort_brands(report.brands)
            _persist(report)
            st.rerun()

        ads = _visible_ads(brand, show_recorded)
        hidden = len(brand.ads) - len(ads)
        st.markdown(f"**📌 {settings.min_running_days}일 이상 게재 중인 연관 광고 {len(ads)}개**"
                    + (f" · 노션에 있는 소재 {hidden}개 제외" if hidden else ""))
        st.dataframe(
            pd.DataFrame(_ad_rows(ads)),
            column_config={
                "게재일수": st.column_config.NumberColumn("게재일수", format="%d일"),
                "변형": st.column_config.NumberColumn("변형", format="%d개", help="같은 소재의 변형 광고를 하나로 합친 수"),
                "광고 보기": st.column_config.LinkColumn("광고 보기", display_text="메타"),
                "영상": st.column_config.LinkColumn("영상", display_text="mp4"),
                "랜딩": st.column_config.LinkColumn("랜딩", display_text="열기"),
            },
            hide_index=True,
            width="stretch",
        )

        if brand.tracked:
            extra = sum(1 for a in brand.accounts if getattr(a, "depth", 0))
            st.markdown(f"**🕵️ 연결 계정 {len(brand.accounts)}개** — {_type_counts(brand.accounts)}"
                        + (f" · 🔁 숨은 계정 재검색으로 {extra}개 추가" if extra else ""))
            if getattr(brand, "tracking_failed", 0):
                st.warning(f"추적이 일부만 끝났습니다: {brand.tracking_note}")
            if brand.accounts:
                st.dataframe(
                    pd.DataFrame(_account_rows(brand)),
                    column_config={
                        "최장 게재": st.column_config.NumberColumn("최장 게재", format="%d일"),
                        "광고 라이브러리": st.column_config.LinkColumn("광고 라이브러리", display_text="광고 보기"),
                        "페이지": st.column_config.LinkColumn("페이지", display_text="페이지"),
                    },
                    hide_index=True,
                    width="stretch",
                )
        elif brand.tracking_note:
            st.warning(brand.tracking_note)

        if brand.is_a_grade:
            label = "🔁 연결 계정 다시 추적" if brand.tracked else "🕵️ 연결 계정(아랍어·위장·숨은) 추적"
            if st.button(label, key=f"ag_track_{wkey}"):
                bar = st.progress(0.0, text="연결 계정 추적 준비 중…")
                track_brand(brand, settings, progress=_progress_bar(bar))
                _persist(report)
                st.rerun()


def _render_report(report) -> None:
    settings = ScanSettings.from_dict(report.settings)
    check_recorded(report)
    for warning in report.warnings:
        st.warning(warning)
    ready, _ = notion_ready()
    if report.recorded_error and ready:
        st.warning(f"{report.recorded_error} — 노션에 있는 소재를 제외하지 않고 보여줍니다.")

    a_brands = report.a_grade_brands
    m = st.columns(6)
    m[0].metric("검색된 광고", f"{report.scanned_ads:,}")
    m[1].metric(f"② {settings.min_running_days}일+ 게재", f"{report.long_running_ads:,}")
    m[2].metric("③ 제품 연관", f"{report.relevant_ads:,}", delta=f"제외 {report.excluded_ads}" if report.excluded_ads else None,
                delta_color="off")
    m[3].metric("연관 브랜드", f"{len(report.brands):,}")
    m[4].metric("🏆 A급 브랜드", f"{len(a_brands):,}")
    m[5].metric("🕵️ 찾은 연결 계정", f"{sum(len(b.accounts) for b in report.brands):,}")
    saved = f" · 저장: `{report.saved_path}`" if report.saved_path else ""
    st.caption(f"{report.generated_at} 기준 · 메타 요청 {report.meta_requests}회{saved}")

    if not report.brands:
        if report.scanned_ads == 0:
            st.info(
                f"검색어에 걸린 광고 중 {settings.min_running_days}일 이상 게재 중인 광고가 없습니다. "
                "최근에 시작한 광고만 있거나 검색 결과가 없는 경우입니다. 다른 검색어를 더해 보세요."
            )
        else:
            st.info(
                f"{settings.min_running_days}일+ 게재 광고 {report.long_running_ads}개 중 제품 연관 키워드가 들어간 광고가 없습니다"
                + (f" (제외 키워드로 {report.excluded_ads}개 제외)" if report.excluded_ads else "")
                + ". 연관 키워드를 늘려 보세요."
            )
        return

    st.markdown("#### 📋 브랜드별 판정")
    st.dataframe(
        pd.DataFrame(_summary_rows(report)),
        column_config={
            "연결 계정": st.column_config.NumberColumn("연결 계정", format="%d개"),
            "랜딩": st.column_config.LinkColumn("랜딩", display_text="열기"),
        },
        hide_index=True,
        width="stretch",
    )

    recorded_total = sum(1 for b in report.brands for a in b.ads if a.recorded)
    show_recorded = False
    if report.recorded_checked:
        st.caption(f"🗂️ 노션 🎬 소재 표와 비교: 이미 기록된 소재 {recorded_total}개는 브랜드 카드와 저장 표에서 뺍니다 "
                   "(A급 판정·순위는 전체 광고 기준).")
        show_recorded = st.checkbox("노션에 있는 소재도 보기 (브랜드 카드)", value=False, key="ag_show_recorded_cards")

    others = [b for b in report.brands if not b.is_a_grade]
    tab_a, tab_rest = st.tabs([f"🏆 A급 브랜드 ({len(a_brands)})", f"① 미달·확인 불가 ({len(others)})"])
    with tab_a:
        if not a_brands:
            st.info("세 가지 기준을 모두 충족한 브랜드가 없습니다. 옆 탭에서 제품명 키워드로 ① 검색량을 다시 확인해 보세요.")
        else:
            st.caption(
                "연결 계정 유형 — 🟥 아랍어: 아랍 문자 이름 · 🟧 외국어: 외국 문자만 쓴 이름 · "
                "🟨 위장: 한글·영문에 외국 문자나 자음·모음을 섞은 이름 · 🟦 숨은: 브랜드명이 없는 이름 · 🟩 공식. "
                "신뢰도 '확정'은 같은 자사몰로 광고를 보내는 계정, '유력'은 광고 문구만 같은 계정입니다. "
                "확정된 숨은·위장·아랍어·외국어 계정은 그 계정 이름과 광고 문구로 메타 광고 라이브러리를 다시 검색해 "
                "연결 계정을 더 찾습니다 (🔁 표시)."
            )
        for i, brand in enumerate(a_brands):
            _render_brand(brand, report, settings, expanded=(i == 0), show_recorded=show_recorded)
    with tab_rest:
        st.caption("브랜드명 검색량이 낮아도 제품명 검색량이 1만을 넘었을 수 있습니다. 키워드를 고쳐 '다시 확인'을 누르세요.")
        for brand in others:
            _render_brand(brand, report, settings, expanded=False, show_recorded=show_recorded)

    st.markdown("#### 📝 노션에 기록")
    if a_brands:
        st.caption("A급 브랜드의 60일+ 게재 광고입니다. 저장할 광고를 고르고 처음 저장할 제목·진행 여부를 정하세요.")
        render_notion_saver(report, key=f"ag_notion_{report.generated_at.replace(':', '')}")
    else:
        st.caption("A급 브랜드가 생기면 해당 광고를 노션에 기록할 수 있습니다.")

    st.markdown("#### 📥 내려받기")
    d1, d2, d3 = st.columns(3)
    token = report.generated_at.replace(":", "").replace("-", "")
    with d1:
        ads_df = _export_ads(report)
        st.download_button("A급 소재 CSV", data=ads_df.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"a_grade_ads_{token}.csv", mime="text/csv",
                           disabled=ads_df.empty, width="stretch", key="ag_dl_ads")
    with d2:
        acc_df = _export_accounts(report)
        st.download_button("연결 계정 CSV", data=acc_df.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"a_grade_accounts_{token}.csv", mime="text/csv",
                           disabled=acc_df.empty, width="stretch", key="ag_dl_accounts")
    with d3:
        st.download_button("전체 결과 JSON",
                           data=json.dumps(asdict(report), ensure_ascii=False, indent=2, default=str).encode("utf-8"),
                           file_name=f"a_grade_{token}.json", mime="application/json", width="stretch",
                           key="ag_dl_json")


def render_a_grade_view() -> None:
    st.subheader("🏆 A급 소재 탐색 & 브랜드 계정 추적")
    st.caption(
        "A급 = ① 최근 1년 안에 브랜드·제품 30일 검색량 1만 이상 (아이템스카우트와 같은 방식: 네이버 검색광고 최근 30일 검색수 × 데이터랩 추이) "
        "② 메타 광고 라이브러리 60일 이상 게재 중 ③ 우리 제품 연관. "
        "결과는 30일 만에 가파르게 오른 브랜드(🚀)부터 보여주고, A급 브랜드는 같은 자사몰로 광고하는 아랍어·위장·숨은 계정까지 찾아냅니다."
    )

    report = st.session_state.get(_STATE_KEY)
    with st.expander("⚙️ 탐색 조건", expanded=report is None):
        c1, c2 = st.columns(2)
        with c1:
            keywords_text = st.text_area(
                "🔍 메타 광고 라이브러리 검색어 (한 줄에 하나)",
                value="\n".join(DEFAULT_SCAN_KEYWORDS), height=200, key="ag_scan_keywords",
            )
            pages = st.slider("검색어당 조회 페이지 (1페이지 = 60일+ 광고 10개)", 1, 10, 3, key="ag_pages")
        with c2:
            relevance_text = st.text_input(
                "③ 제품 연관 키워드 (쉼표 구분 · 하나라도 있으면 연관)",
                value=", ".join(DEFAULT_RELEVANCE_TERMS), key="ag_relevance",
            )
            exclude_text = st.text_input(
                "제외 키워드 (하나라도 있으면 제외)", value=", ".join(DEFAULT_EXCLUDE_TERMS), key="ag_exclude",
            )
            n1, n2 = st.columns(2)
            with n1:
                min_volume = st.number_input("① 30일 검색량 기준", min_value=1000, max_value=500000,
                                             value=MIN_PEAK_VOLUME, step=1000, key="ag_min_volume")
            with n2:
                min_days = st.number_input("② 최소 게재 일수", min_value=7, max_value=365,
                                           value=MIN_RUNNING_DAYS, step=1, key="ag_min_days")
            r1, r2 = st.columns(2)
            with r1:
                spike_jump = st.number_input("🚀 급상승: 30일 증가폭", min_value=500, max_value=500000,
                                             value=SPIKE_MIN_JUMP, step=500, key="ag_spike_jump")
            with r2:
                spike_ratio = st.number_input("🚀 급상승: 직전 30일 대비 배수", min_value=1.1, max_value=20.0,
                                              value=SPIKE_MIN_RATIO, step=0.5, key="ag_spike_ratio")
            st.caption("급상승은 A급 조건이 아니라 순위·표시에만 씁니다. 📈 상승 = 증가폭이 기준의 절반 이상이거나 1.5배 이상.")
            track = st.checkbox("A급 브랜드를 찾으면 연결 계정(아랍어·위장·숨은 계정)까지 자동 추적",
                                value=True, key="ag_track")
        if not all(_naver_creds()):
            st.warning("네이버 검색광고 API 키(NAVER_CUSTOMER_ID · NAVER_ACCESS_LICENSE · NAVER_SECRET_KEY)가 없으면 ① 검색량을 확인할 수 없습니다.")
        st.caption("기본 설정(검색어 7개 · 3페이지)으로 4분 안팎 걸립니다. 진행 중에 다른 버튼을 누르면 탐색이 멈춥니다.")

    if st.button("🏆 A급 소재 찾기", type="primary", key="ag_run"):
        settings = ScanSettings(
            scan_keywords=parse_terms(keywords_text),
            relevance_terms=parse_terms(relevance_text),
            exclude_terms=parse_terms(exclude_text),
            min_running_days=int(min_days),
            min_peak_volume=int(min_volume),
            pages_per_keyword=int(pages),
            track_accounts=bool(track),
            spike_min_jump=int(spike_jump),
            spike_min_ratio=float(spike_ratio),
        )
        if not settings.scan_keywords or not settings.relevance_terms:
            st.error("검색어와 제품 연관 키워드를 한 개 이상 입력하세요.")
        else:
            bar = st.progress(0.0, text="준비 중…")
            report = find_a_grade_ads(settings, _naver_creds(), progress=_progress_bar(bar))
            bar.empty()
            st.session_state[_STATE_KEY] = report

    if report is not None:
        _render_report(report)
