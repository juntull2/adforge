"""
노션 A급 소재 기록 패널 (A급 탭 아래 '📝 노션에 기록')

- 🏢 브랜드 표 + 🎬 소재 표(notion_references)에 저장합니다. 같은 브랜드·광고는 새로 만들지 않고 갱신합니다.
- 사람 전용 칸(제작 영상 링크 · 제작 날짜 · 대표님 피드백)은 쓰지 않습니다. 제목·진행 여부는 처음 저장할 때만 씁니다.
- 구글 드라이브 폴더가 연결돼 있으면 원본 영상을 드라이브에 올리고 '영상 원본' 칸에 링크를 남깁니다.
"""

import os
import re
import time
from copy import deepcopy
from datetime import date

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

import notion_references as nr
from a_grade_finder import ad_account_type, mark_recorded, ScanSettings, grade_brand, match_terms, _merge_brand_ad
from notion_sync import NotionClient, NotionError

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATUS_OPTIONS = [name for name, _, _ in nr.STATUS_OPTIONS]
_STORE_KEY = "_notion_reference_store"


@st.cache_data(show_spinner=False, ttl=600)
def cached_test_gdrive(folder: str, credentials_path: str) -> dict:
    from gdrive_sync import test_gdrive_folder_access
    return test_gdrive_folder_access(folder, credentials_path)


def _write_env(values: dict) -> None:
    nr.write_env(values)
    load_dotenv(nr.ENV_PATH, override=True)


def open_store() -> nr.ReferenceStore:
    """노션 표를 읽어 둔 저장소 (세션에 보관). 테스트에서 이 함수를 바꿔 끼웁니다."""
    token = os.environ.get("NOTION_TOKEN", "").strip()
    ids = nr.configured_ids()
    signature = (token, ids[nr.ENV_BRAND_DS], ids[nr.ENV_AD_DS], nr.B_PEAK, nr.B_JUMP)
    cached = st.session_state.get(_STORE_KEY)
    if cached and cached[0] == signature:
        return cached[1]
    store = nr.ReferenceStore(NotionClient(token), ids[nr.ENV_BRAND_DS], ids[nr.ENV_AD_DS]).load()
    st.session_state[_STORE_KEY] = (signature, store)
    return store


def reset_store() -> None:
    st.session_state.pop(_STORE_KEY, None)


def notion_ready() -> tuple:
    """(준비됐는지, 안내 문구)"""
    if not os.environ.get("NOTION_TOKEN", "").strip():
        return False, "NOTION_TOKEN이 없습니다."
    if not nr.is_configured():
        return False, "노션 브랜드·소재 표가 아직 없습니다."
    return True, ""


def check_recorded(report) -> None:
    """탐색 결과의 광고마다 노션 소재 표에 이미 있는지 표시합니다 (결과마다 한 번)."""
    if getattr(report, "_recorded_done", False):
        return
    ready, why = notion_ready()
    if not ready:
        report.recorded_checked, report.recorded_error = False, why
    else:
        try:
            mark_recorded(report, open_store().recorded_keys())
        except (NotionError, RuntimeError) as exc:
            report.recorded_checked, report.recorded_error = False, f"노션 소재 표를 읽지 못했습니다: {exc}"
    report._recorded_done = True


def _token_form(key: str) -> None:
    with st.expander("⚙️ 노션 연동 설정 필요", expanded=True):
        st.warning("노션에 저장하려면 Notion Integration Token을 입력하세요.")
        token = st.text_input("Notion Integration Token", placeholder="ntn_...", type="password", key=f"{key}_token")
        if st.button("💾 토큰 저장", key=f"{key}_save_token"):
            if token.strip():
                _write_env({"NOTION_TOKEN": token.strip()})
                reset_store()
                st.rerun()
            else:
                st.error("토큰을 입력해주세요.")


def _setup_guide() -> None:
    with st.container(border=True):
        st.markdown("##### 🧱 노션 브랜드·소재 표 만들기")
        st.markdown(
            "처음 한 번만 실행합니다. 먼저 미리보기로 무엇을 만들지 확인한 뒤 `--apply`로 만듭니다.\n\n"
            "```powershell\n"
            ".\\.venv\\Scripts\\python.exe notion_references.py setup\n"
            ".\\.venv\\Scripts\\python.exe notion_references.py setup --apply\n"
            "```\n"
            f"'메타 광고 레퍼런스 모음' 페이지 안에 '{nr.PAGE_TITLE}' 페이지와 🏢 브랜드 · 🎬 소재 표가 생기고, "
            "ID가 `.env`에 저장됩니다. 만든 뒤 앱을 새로고침하세요."
        )


def _drive_status(folder: str, drive: dict, key: str) -> None:
    with st.expander("⚙️ 구글 드라이브 연동 상태", expanded=False):
        if drive.get("ok"):
            st.success(f"폴더 연결 성공: **{drive.get('folder_name', '확인됨')}** — 원본 영상을 올려 '영상 원본' 칸에 링크합니다.")
        elif drive.get("api_disabled"):
            st.error("❌ Google Drive API 활성화 필요")
            st.markdown(f"👉 [Google Cloud Console에서 Drive API 사용 설정하기]({drive.get('enable_url')})")
        else:
            st.warning(f"⚠️ 구글 드라이브 상태: {drive.get('error', '설정 필요')} — '영상 원본' 칸은 비워 둡니다.")
        with st.popover("⚙️ 구글 드라이브 폴더 변경"):
            new_folder = st.text_input("구글 드라이브 폴더 링크", value=folder, key=f"{key}_re_gdrive")
            if st.button("💾 폴더 링크 저장", key=f"{key}_re_gdrive_save"):
                if new_folder.strip():
                    _write_env({"GOOGLE_DRIVE_FOLDER_URL": new_folder.strip()})
                    cached_test_gdrive.clear()
                    st.rerun()


def saver_rows(report, show_recorded: bool) -> list:
    """저장 표에 보여줄 (브랜드, 광고) 목록. 노션에 이미 있는 소재는 show_recorded일 때만."""
    rows = []
    for brand in report.a_grade_brands:
        for ad in brand.ads:
            if ad.recorded and not show_recorded:
                continue
            rows.append((brand, ad))
    return rows


def retained_candidates(current, history):
    """현재 판정을 우선하며, 재수집되지 않은 이전 소재를 출처와 함께 보존합니다."""
    result = deepcopy(current)
    settings = ScanSettings.from_dict(current.settings)
    brands = {b.key: b for b in result.brands}
    sources = {(b.key, a.ad_id): current.generated_at for b in result.brands for a in b.ads}
    for old in sorted(history, key=lambda r: r.generated_at, reverse=True):
        if old.generated_at >= current.generated_at or old.settings.get("country", "KR") != settings.country:
            continue
        for previous in old.brands:
            if previous.key in brands and not brands[previous.key].is_a_grade:
                continue  # 최신 결과에서 명시적으로 미달이면 예전 합격으로 덮지 않습니다.
            if not previous.is_a_grade:
                if previous.key not in brands:
                    brands[previous.key] = deepcopy(previous)
                continue
            candidate = deepcopy(previous)
            candidate.ads = [a for a in candidate.ads
                             if a.running_days >= settings.min_running_days
                             and match_terms(a.copy + " " + a.caption + " " + " ".join(a.relevance), settings.relevance_terms)
                             and not match_terms(a.copy + " " + a.caption, settings.exclude_terms)]
            grade_brand(candidate, settings)
            if not candidate.is_a_grade:
                continue
            target = brands.setdefault(candidate.key, candidate)
            for ad in candidate.ads:
                sources.setdefault((candidate.key, ad.ad_id), old.generated_at)
                if target is not candidate:
                    _merge_brand_ad(target, ad)
    result.brands = list(brands.values())
    result._candidate_sources = sources
    result._recorded_done = False
    return result


def _upload_video(ad, brand, folder: str, credentials_path: str, idx: int) -> tuple:
    """(드라이브 링크, 오류)"""
    from gdrive_sync import download_video_file, upload_video_to_gdrive

    safe = re.sub(r"[^\w\s-]", "", brand.name or "광고").strip().replace(" ", "_")[:20] or "광고"
    file_name = f"[{safe}]_{ad.start_date}_{ad.ad_id or int(time.time())}_{idx + 1}.mp4"
    local_path = os.path.join(_BASE_DIR, "outputs", "references", file_name)
    if not download_video_file(ad.video_url, local_path):
        return "", "영상 내려받기 실패"
    up = upload_video_to_gdrive(local_path=local_path, file_name=file_name, folder_id_or_url=folder,
                                credentials_path=credentials_path)
    return (up["web_view_link"], "") if up.get("ok") else ("", str(up.get("error")))


def save_rows(store: nr.ReferenceStore, rows: list, drive_ok: bool, folder: str, credentials_path: str,
              progress=None, today: date = None) -> dict:
    """선택한 (브랜드, 광고, 제목, 진행 여부) 목록을 노션에 저장합니다."""
    today = today or date.today()
    brand_pages, result = {}, {"created": 0, "updated": 0, "failed": 0, "uploaded": 0, "errors": []}
    keys = store.recorded_keys()
    for idx, (brand, ad, title, status) in enumerate(rows):
        if progress:
            progress(idx / max(len(rows), 1), f"📝 [{idx + 1}/{len(rows)}] {brand.name} · {ad.page_name}")
        try:
            if brand.key not in brand_pages:
                brand_pages[brand.key] = store.upsert_brand(brand, today)[0]
            video_link = ""
            if drive_ok and ad.video_url.startswith("http") and ad.ad_id not in store.ads:
                video_link, err = _upload_video(ad, brand, folder, credentials_path, idx)
                if video_link:
                    result["uploaded"] += 1
                elif err:
                    result["errors"].append(f"{brand.name} 드라이브 업로드 실패: {err}")
            _, created = store.upsert_ad(ad, brand, brand_pages[brand.key], account_type=ad_account_type(brand, ad),
                                         title=title, status=status, video_link=video_link)
            result["created" if created else "updated"] += 1
            keys.add(ad, brand.key)
            ad.recorded = ad.recorded or "방금 저장"
        except (NotionError, RuntimeError) as exc:
            result["failed"] += 1
            result["errors"].append(f"{brand.name} · {ad.page_name}: {exc}")
    return result


def _set_saver_selection(key: str, mode: str) -> None:
    st.session_state[f"{key}_default"] = mode
    st.session_state[f"{key}_ver"] += 1


@st.fragment
def render_notion_saver(report, key: str, history=()) -> None:
    """A급 브랜드의 60일+ 게재 광고를 기획 표로 보여주고, 선택한 광고를 노션에 저장합니다."""
    ready, why = notion_ready()
    if not os.environ.get("NOTION_TOKEN", "").strip():
        _token_form(key)
        return
    if not ready:
        st.info(why)
        _setup_guide()
        return

    if history:
        include_previous = st.checkbox("이전에 확인한 A급 소재도 포함", value=True, key=f"{key}_include_previous")
        if include_previous:
            report = retained_candidates(report, history)
            check_recorded(report)
        st.caption("이전 소재는 확인 시각을 표시합니다. 이번 검색에서 다시 확인되지 않았으므로 현재 게재 여부·검색량은 재확인이 필요합니다. 이번에 미달 판정을 받은 브랜드는 이전 합격으로 되살리지 않습니다.")
    show_recorded = st.checkbox("노션에 있는 소재도 보기", value=False, key=f"{key}_show_recorded")
    pairs = saver_rows(report, show_recorded)
    hidden = sum(1 for b in report.a_grade_brands for a in b.ads if a.recorded) if not show_recorded else 0
    total = sum(len(b.ads) for b in report.a_grade_brands)
    st.caption(f"키워드 검색 수집 {report.scanned_ads:,}개 → 제품 연관 {report.relevant_ads:,}개 "
               f"→ A급 브랜드 {len(report.a_grade_brands)}곳의 소재 {total:,}개 "
               f"→ 현재 저장 표 {len(pairs):,}개 (노션에 이미 있는 소재 {hidden:,}개 숨김). "
               "동일 광고·소재 변형은 합치며, A급 미달·확인 불가 브랜드는 이 표에서 제외합니다.")
    if hidden:
        st.caption(f"노션에 있는 소재 {hidden}개 제외")
    if not pairs:
        st.info("노션에 새로 기록할 A급 소재가 없습니다.")
        return

    # 기본: 새 소재만 선택 · '전체 선택'을 누르면 노션에 있는 소재까지 · '전체 해제'면 모두 해제
    version_key, default_key = f"{key}_ver", f"{key}_default"
    st.session_state.setdefault(version_key, 0)
    st.session_state.setdefault(default_key, "new")
    mode = st.session_state[default_key]
    table = pd.DataFrame([{
        "선택": mode == "all" or (mode == "new" and not ad.recorded),
        "제목": nr.ad_title(ad, brand),
        "노션": "이미 있음 (갱신)" if ad.recorded else "새 소재",
        "브랜드": brand.name,
        "확인 시각": getattr(report, "_candidate_sources", {}).get((brand.key, ad.ad_id), report.generated_at),
        "검색 출처": "이번 검색" if getattr(report, "_candidate_sources", {}).get((brand.key, ad.ad_id), report.generated_at) == report.generated_at else "이전 검색에서 보존",
        "급상승": brand.volume.rise_level if brand.volume and brand.volume.rise_level else "-",
        "광고 계정": ad.page_name,
        "계정 유형": ad_account_type(brand, ad),
        "소재 유형": ad.media_type,
        "게재 시작일": ad.start_date,
        "게재일수": ad.running_days,
        "진행 여부": nr.STATUS_DEFAULT,
        "연관 키워드": ", ".join(ad.relevance),
        "메타 광고": ad.library_url or None,
        "랜딩": ad.landing_url or None,
    } for brand, ad in pairs])
    drafts = st.session_state.setdefault(f"{key}_drafts", {})
    for i, (brand, ad) in enumerate(pairs):
        for column, value in drafts.get((brand.key, ad.ad_id), {}).items():
            table.at[i, column] = value

    b1, b2, _ = st.columns([1, 1, 4])
    with b1:
        st.button("☑️ 전체 선택", key=f"{key}_all", width="stretch",
                  on_click=_set_saver_selection, args=(key, "all"))
    with b2:
        st.button("◻️ 전체 해제", key=f"{key}_none", width="stretch",
                  on_click=_set_saver_selection, args=(key, "none"))

    locked = [c for c in table.columns if c not in ("선택", "제목", "진행 여부")]
    edited = st.data_editor(
        table,
        column_config={
            "선택": st.column_config.CheckboxColumn("☑️ 선택", width="small"),
            "제목": st.column_config.TextColumn("🏷️ 제목", width="large", help="처음 저장할 때만 씁니다"),
            "진행 여부": st.column_config.SelectboxColumn("📌 진행 여부", options=STATUS_OPTIONS, width="small",
                                                     help="처음 저장할 때만 씁니다"),
            "게재일수": st.column_config.NumberColumn("게재일수", format="%d일"),
            "메타 광고": st.column_config.LinkColumn("메타 광고", display_text="보기"),
            "랜딩": st.column_config.LinkColumn("랜딩", display_text="열기"),
        },
        disabled=locked,
        width="stretch",
        hide_index=True,
        num_rows="fixed",
        key=f"{key}_table_{st.session_state[version_key]}",
    )
    for i, (brand, ad) in enumerate(pairs):
        drafts[(brand.key, ad.ad_id)] = {column: edited.iloc[i][column] for column in ("제목", "진행 여부")}
    st.caption(
        f"사람 전용 칸({' · '.join(nr.HUMAN_ONLY)})은 adforge가 쓰지 않습니다. "
        "이미 노션에 있는 소재는 제목·진행 여부·소구 포인트를 바꾸지 않고 나머지 칸만 갱신합니다."
    )

    folder = os.environ.get("GOOGLE_DRIVE_FOLDER_URL", "").strip()
    credentials_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json").strip()
    drive = cached_test_gdrive(folder, credentials_path) if folder else {"ok": False, "error": "폴더 미설정"}
    _drive_status(folder, drive, key)

    picked = [i for i, flag in enumerate(edited["선택"]) if bool(flag)]
    c1, c2 = st.columns([2, 1])
    with c1:
        badge = "☁️ 구글 드라이브 영상 백업 포함" if drive.get("ok") else "드라이브 미연동 (영상 원본 칸 비움)"
        st.caption(f"☑️ 선택된 {len(picked)}개를 🎬 소재 표에 저장하고 🏢 브랜드 행을 만들거나 갱신합니다. ({badge})")
    with c2:
        save = st.button("📤 노션에 저장하기", type="primary", width="stretch", key=f"{key}_save")
    if not save:
        return
    if not picked:
        st.warning("선택된 항목이 없습니다.")
        return

    rows = []
    for i in picked:
        brand, ad = pairs[i]
        rows.append((brand, ad, str(edited.iloc[i]["제목"] or ""), str(edited.iloc[i]["진행 여부"] or nr.STATUS_DEFAULT)))
    bar = st.progress(0.0, text="노션 저장 준비 중...")
    try:
        store = open_store()
    except (NotionError, RuntimeError) as exc:
        st.error(f"노션 표를 읽지 못했습니다: {exc}")
        return
    result = save_rows(store, rows, drive.get("ok", False), folder, credentials_path,
                       progress=lambda f, m: bar.progress(min(f, 1.0), text=m))
    bar.progress(1.0, text="저장 완료!")
    done = result["created"] + result["updated"]
    drive_note = f" · ☁️ 드라이브 업로드 {result['uploaded']}개" if result["uploaded"] else ""
    if result["failed"] == 0:
        st.success(f"✅ 노션에 {done}개 저장 (새로 {result['created']}개 · 갱신 {result['updated']}개){drive_note}")
    else:
        st.warning(f"저장 결과: {done}개 성공, {result['failed']}개 실패{drive_note}")
    for err in result["errors"][:5]:
        st.caption(f"⚠️ {err}")
    st.session_state[f"{key}_last_result"] = result
