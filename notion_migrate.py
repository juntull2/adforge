"""
기존 노션 레퍼런스 → 새 🏢 브랜드 · 🎬 소재 표로 옮기기
=======================================================

    python notion_migrate.py plan                     ← 읽기만 해서 보고서를 만듭니다 (노션·메타에 쓰지 않음)
    python notion_migrate.py apply <보고서.json>        ← 보고서에서 '옮김'으로 나온 것만 새 표에 넣습니다
    python notion_migrate.py tidy                     ← 기존 DB 보관 표시·템플릿 잔여물 정리 미리보기
    python notion_migrate.py tidy --rename --apply    ← 기존 DB 이름 앞에 "(보관)"
    python notion_migrate.py tidy --trash-template --apply  ← 부모 페이지의 템플릿 잔여물을 휴지통으로 (30일 복구 가능)

옮기는 기준 (지금 A급 기준으로 다시 판정)
- 기존 행에서 메타 광고 ID를 찾고, 그 광고가 지금도 게재 중이며 60일 이상인지 메타에서 확인합니다.
- 광고 문구에 제품 연관 키워드가 있어야 합니다.
- 브랜드의 최근 1년 30일 검색량 최고값이 1만 이상이어야 합니다 (제품명도 함께 확인).
- 확인할 수 없는 광고·브랜드는 옮기지 않습니다.
- 소재링크 · 편집일 · 대표님 피드백은 읽지도 옮기지도 않습니다. 진행 여부는 '검토중'으로 시작합니다.
- 기존 표의 행은 고치거나 지우지 않습니다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime, timedelta
from typing import Optional

import a_grade_finder as g
import notion_references as nr
from meta_ad_library import AdLibraryBlocked, AdLibraryClient, _get_page, _make_session
from notion_sync import NotionClient, NotionError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE_DIR, "outputs", "notion_migration")

MOVE = "옮김"
SKIP = "제외"

_PLANNING_WORDS = ("대본", "기획", "촬영가이드", "촬영 가이드", "벤치마킹", "가이드")
_NOTICE_WORDS = ("판별 기준", "필독", "기준 안내")
_EXCLUDED_WORDS = ("[제외]", "탈락")
_TITLE_RE = re.compile(
    r"^\s*(?:\[(?P<appeal>[^\]]*)\]\s*)?\[(?P<media>영상|이미지|캐러셀)\]\s*(?P<rest>.*)$"
)
_DAYS_SUFFIX_RE = re.compile(r"\s*\(\s*\d+\s*일\s*(?:롱런|차)?[^)]*\)\s*$")
_URL_ID_RE = re.compile(r"facebook\.com/ads/library/?\?[^\s\"']*?\bid=(\d{10,20})")
_AD_ID_TEXT_RE = re.compile(r"Ad\s*ID\s*[:：]\s*([\d,\s]+)", re.I)
_DRIVE_RE = re.compile(r"https://drive\.google\.com/file/d/[\w-]+[^\s\"')]*")
_EMOJI_RE = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200d]")


# ─────────────────────────────────────────────────────────────────
# 기존 행 읽기
# ─────────────────────────────────────────────────────────────────

@dataclass
class LegacyRow:
    source: str
    row_id: str
    title: str
    props: dict = field(default_factory=dict)      # 사람 전용 칸을 뺀 칸 값(글자)
    body: str = ""
    ad_ids: list = field(default_factory=list)
    landing: str = ""
    drive_link: str = ""
    appeals: list = field(default_factory=list)
    media_type: str = ""
    product_names: list = field(default_factory=list)   # 제목의 브랜드명 + 자사몰 판매 제품명 (검색량 확인용)
    brand_names: list = field(default_factory=list)     # 제목의 브랜드명
    decision: str = ""
    reason: str = ""


def _plain_value(prop: dict):
    kind = prop.get("type")
    value = prop.get(kind)
    if kind in ("title", "rich_text"):
        return "".join(r.get("plain_text", "") for r in value or [])
    if kind in ("select", "status"):
        return (value or {}).get("name", "")
    if kind == "multi_select":
        return ", ".join(o.get("name", "") for o in value or [])
    if kind == "url":
        return value or ""
    if kind == "date":
        return (value or {}).get("start", "") if value else ""
    return ""


def parse_title(title: str) -> dict:
    """'[🩺 진피재생 / 시술대체] [영상] 셀라이징 - 프락셀 … (200일 롱런)' → 소구 포인트·소재 유형·브랜드·제목"""
    out = {"appeals": [], "media_type": "", "brand": "", "headline": (title or "").strip()}
    m = _TITLE_RE.match(title or "")
    if not m:
        return out
    appeal = _EMOJI_RE.sub("", m.group("appeal") or "").strip()
    if appeal and appeal not in ("-", "—"):
        out["appeals"] = [a.strip() for a in re.split(r"[/·,]", appeal) if a.strip()]
    out["media_type"] = m.group("media")
    rest = _DAYS_SUFFIX_RE.sub("", m.group("rest")).strip()
    brand, sep, headline = rest.partition(" - ")
    out["brand"] = brand.strip() if sep else ""
    out["headline"] = (headline if sep else rest).strip()
    return out


def legacy_brand_names(title_brand: str) -> list:
    """제목의 브랜드 부분('Cèlisîng (셀라이징)', '닥터지')에서 검색량을 확인할 브랜드명 후보.
    띄어쓰기 없는 2~12자 이름만 씁니다 ('피부 과학의 모든 것' 같은 계정 이름은 제외)."""
    out = []
    for part in re.split(r"[()\[\]/]", title_brand or ""):
        name = part.strip()
        if 2 <= len(name) <= 12 and " " not in name and "서브" not in name and name not in out:
            if g.classify_page_name(name, [])[0] not in (g.ACCOUNT_ARABIC, g.ACCOUNT_FOREIGN, g.ACCOUNT_DISGUISED):
                out.append(name)
    return out


def extract_ad_ids(texts: list) -> list:
    ids = []
    for text in texts:
        for m in _URL_ID_RE.finditer(text or ""):
            ids.append(m.group(1))
        for m in _AD_ID_TEXT_RE.finditer(text or ""):
            ids.extend(re.findall(r"\d{12,20}", m.group(1)))
    return list(dict.fromkeys(ids))


def _first_landing(props: dict) -> str:
    for name in ("연결링크", "연결 링크", "자사몰", "랜딩"):
        value = props.get(name, "")
        if value.startswith("http") and "datalab.naver.com" not in value:
            return value
    return ""


def build_row(source: str, page: dict, body: str) -> LegacyRow:
    props = {k: _plain_value(p) for k, p in (page.get("properties") or {}).items() if k not in nr.HUMAN_ONLY}
    title = next((_plain_value(p) for p in (page.get("properties") or {}).values() if p.get("type") == "title"), "")
    parsed = parse_title(title)
    texts = [v for v in props.values() if isinstance(v, str)] + [body]
    drive = next((m.group(0) for t in texts for m in [_DRIVE_RE.search(t or "")] if m), "")
    brand_names = legacy_brand_names(parsed["brand"])
    products = list(brand_names)
    for name in ("자사몰 판매 제품명",):
        cleaned = g.clean_brand_name(props.get(name, ""))
        if cleaned and cleaned not in products:
            products.append(cleaned)
    return LegacyRow(
        source=source, row_id=page["id"], title=title, props=props, body=body[:3000],
        ad_ids=extract_ad_ids(texts), landing=_first_landing(props), drive_link=drive,
        appeals=parsed["appeals"], media_type=parsed["media_type"], product_names=products,
        brand_names=brand_names,
    )


_RELEVANCE_FIELDS = ("키워드", "자사몰 판매 제품명", "광고 카피", "Name")


def legacy_relevance_text(row: LegacyRow) -> str:
    """③ 연관성 판단에 쓰는 기존 행 글자: 제목과 키워드·제품명 칸 (본문의 긴 분석 글은 쓰지 않음)"""
    return " ".join([row.title] + [row.props.get(name, "") for name in _RELEVANCE_FIELDS])


def classify_row(row: LegacyRow) -> tuple:
    """(계속 확인할지, 이유)"""
    title = row.title or ""
    keyword = row.props.get("키워드", "")
    if any(w in title for w in _EXCLUDED_WORDS):
        return False, "제외로 표시된 행"
    if title.strip().startswith("📌") or any(w in title for w in _NOTICE_WORDS):
        return False, "안내 행"
    if any(w in title for w in _PLANNING_WORDS) or "벤치마킹 대본" in keyword:
        return False, "우리 기획물 (새 구조에 넣지 않음)"
    if not row.ad_ids:
        if not row.landing and not title.strip():
            return False, "빈 행"
        return False, "메타 광고 ID가 없어 지금 게재 중인지 확인할 수 없음"
    return True, ""


def read_legacy(client: NotionClient, legacy_db_id: str, progress=None) -> list:
    """기존 DB의 모든 데이터 소스 행을 읽습니다 (읽기만)."""
    db = client.get(f"databases/{legacy_db_id}")
    rows = []
    for ds in db.get("data_sources") or []:
        pages = client.query_data_source(ds["id"])
        for i, page in enumerate(pages):
            if progress:
                progress(f"노션 읽기: {ds.get('name')} {i + 1}/{len(pages)}")
            texts = []
            for block in client.block_children(page["id"])[:40]:
                inner = block.get(block.get("type"), {}) or {}
                texts.append("".join(r.get("plain_text", "") for r in inner.get("rich_text", []) or []))
            rows.append(build_row(ds.get("name", ds["id"]), page, "\n".join(t for t in texts if t)))
    return rows


# ─────────────────────────────────────────────────────────────────
# 메타에서 광고 확인
# ─────────────────────────────────────────────────────────────────

class AdLookup:
    """광고 ID로 지금 게재 중인 광고를 찾습니다: ID 검색 → 없으면 광고 상세 페이지에서 페이지 ID → 그 페이지의 게재 중 광고."""

    def __init__(self, client: AdLibraryClient):
        self.client = client
        self._page_ads: dict = {}
        self._html = None

    def _page_id_from_html(self, ad_id: str) -> str:
        if self._html is None:
            self._html = _make_session()
            _get_page(self._html, "https://www.facebook.com/")
        resp = _get_page(self._html, f"https://www.facebook.com/ads/library/?id={ad_id}")
        text = getattr(resp, "text", "") or ""
        m = re.search(r'"ad_archive_id":"' + ad_id + r'".{0,200}?"page_id":"(\d+)"', text)
        if m:
            return m.group(1)
        ids = set(re.findall(r'"page_id":"(\d+)"', text)) | set(re.findall(r"view_all_page_id=(\d+)", text))
        return next(iter(ids)) if len(ids) == 1 else ""

    def find(self, ad_id: str) -> tuple:
        """(원본 광고 dict 또는 None, 설명)"""
        for ad in self.client.search(ad_id, active_status="active", max_pages=1):
            if str(ad.get("ad_archive_id")) == ad_id:
                return ad, "ID 검색"
        page_id = self._page_id_from_html(ad_id)
        if not page_id:
            return None, "지금 게재 중인 광고에서 찾지 못함 (게재 종료 또는 확인 불가)"
        if page_id not in self._page_ads:
            self._page_ads[page_id] = self.client.page_ads(page_id, active_status="active", max_pages=5)
        for ad in self._page_ads[page_id]:
            if str(ad.get("ad_archive_id")) == ad_id:
                return ad, "페이지 광고 목록"
        return None, "지금 게재 중인 광고에서 찾지 못함 (게재 종료 또는 확인 불가)"


# ─────────────────────────────────────────────────────────────────
# 계획 만들기
# ─────────────────────────────────────────────────────────────────

@dataclass
class MigrationPlan:
    generated_at: str
    settings: dict
    rows: list = field(default_factory=list)       # LegacyRow
    ads: list = field(default_factory=list)        # {"ad_id", "brand_key", "decision", "reason", "row_id", "appeals", "drive_link"}
    brands: list = field(default_factory=list)     # BrandCandidate
    brand_decisions: dict = field(default_factory=dict)   # 브랜드 키 → {"decision", "reason"}
    warnings: list = field(default_factory=list)

    def moving_brands(self) -> list:
        return [b for b in self.brands if self.brand_decisions.get(b.key, {}).get("decision") == MOVE]


def plan_migration(notion: NotionClient, legacy_db_id: str, naver_creds: tuple, settings: g.ScanSettings = None,
                   meta: AdLibraryClient = None, lookup: AdLookup = None, resolver: g.LinkResolver = None,
                   today: date = None, progress=print, fetch_audience: bool = True) -> MigrationPlan:
    settings = settings or g.ScanSettings()
    today = today or date.today()
    plan = MigrationPlan(generated_at=datetime.now().isoformat(timespec="seconds"), settings=asdict(settings))
    plan.rows = read_legacy(notion, legacy_db_id, progress=None)
    progress(f"기존 행 {len(plan.rows)}개 읽음")

    # 1) 행 분류
    ad_rows: dict = {}   # 광고 ID → 처음 나온 행
    for row in plan.rows:
        keep, reason = classify_row(row)
        row.decision, row.reason = ("확인", "") if keep else (SKIP, reason)
        for ad_id in row.ad_ids if keep else []:
            ad_rows.setdefault(ad_id, row)

    # 2) 광고가 지금도 60일 이상 게재 중인지
    meta = meta or AdLibraryClient()
    lookup = lookup or AdLookup(meta)
    resolver = resolver or g.LinkResolver()
    raw_ads, ad_info = [], {}
    for i, (ad_id, row) in enumerate(ad_rows.items()):
        progress(f"메타 확인 {i + 1}/{len(ad_rows)}: {ad_id}")
        try:
            raw, how = lookup.find(ad_id)
        except AdLibraryBlocked as exc:
            plan.warnings.append(f"메타 접속 실패: {exc}")
            raw, how = None, "메타 접속 실패"
        info = {"ad_id": ad_id, "row_id": row.row_id, "appeals": row.appeals, "drive_link": row.drive_link,
                "brand_key": "", "decision": SKIP, "reason": how}
        ad_info[ad_id] = info
        if raw is None:
            continue
        days = g.ad_running_days(raw, today)
        text = g.ad_text(raw)
        # 영상만 있고 문구가 없는 광고가 많아서, 팀이 기존 행에 적어 둔 제목·키워드·제품명도 연관성 판단에 씁니다
        relevance_text = f"{text} {legacy_relevance_text(row)}"
        if days < settings.min_running_days:
            info["reason"] = f"② 게재 {days}일 (< {settings.min_running_days}일)"
        elif g.match_terms(text, settings.exclude_terms):
            info["reason"] = "제외 키워드 포함"
        elif not g.match_terms(relevance_text, settings.relevance_terms):
            info["reason"] = "③ 제품 연관 키워드 없음 (광고 문구·기존 행 제목·키워드 모두)"
        else:
            raw["_relevance"] = g.match_terms(relevance_text, settings.relevance_terms)
            raw["_search_keyword"] = "기존 노션"
            raw_ads.append(raw)
            info["reason"] = f"게재 {days}일 · {how}"
            info["decision"] = "브랜드 확인"
    plan.ads = list(ad_info.values())

    # 3) 브랜드 묶기 → ① 검색량 (브랜드명 + 기존 행의 제품명)
    resolver.resolve_many(u for ad in raw_ads for u in g.ad_link_urls(ad))
    brands = g.group_brands(raw_ads, resolver, today)
    infos = resolver.landing_infos({b.key: b.landing_url for b in brands if g.is_own_site_key(b.key)})
    datalab = g.DataLabTrends()
    for brand in brands:
        g._apply_landing_info(brand, infos.get(brand.key, {}), settings.relevance_terms)
        products, legacy_names = [], []
        for ad in brand.ads:
            row = ad_rows.get(ad.ad_id)
            products += row.product_names if row else []
            legacy_names += row.brand_names if row else []
            ad_info[ad.ad_id]["brand_key"] = brand.key
        if legacy_names and not g.is_own_site_key(brand.key):
            brand.name = legacy_names[0]   # 올리브영 등 자사몰이 아니면 페이지 이름 대신 팀이 적어 둔 브랜드명
        brand.keywords = list(dict.fromkeys(brand.keywords + products))[:6]
        progress(f"검색량 확인: {brand.name} ({', '.join(brand.keywords)})")
        brand.volume = g.check_search_spike(brand.keywords, naver_creds, settings.min_peak_volume, settings.lookback_days,
                                            today=today, datalab=datalab, min_jump=settings.spike_min_jump,
                                            min_ratio=settings.spike_min_ratio)
        g.grade_brand(brand, settings)
        decision = MOVE if brand.is_a_grade else SKIP
        plan.brand_decisions[brand.key] = {"decision": decision, "reason": " / ".join(brand.reasons) or "A급"}
        if brand.is_a_grade and fetch_audience:
            g.fetch_brand_audience(brand)
        for ad in brand.ads:
            ad_info[ad.ad_id]["decision"] = decision
            if decision == SKIP:
                ad_info[ad.ad_id]["reason"] = f"브랜드 미달: {plan.brand_decisions[brand.key]['reason']}"
    plan.brands = g.sort_brands(brands)

    # 4) 행 결과 정리
    for row in plan.rows:
        if row.decision != "확인":
            continue
        results = [ad_info[a] for a in row.ad_ids if a in ad_info]
        moved = [r for r in results if r["decision"] == MOVE]
        row.decision = MOVE if moved else SKIP
        row.reason = (f"광고 {len(moved)}개 옮김" if moved else
                      " / ".join(dict.fromkeys(r["reason"] for r in results)) or "확인 불가")
    return plan


# ─────────────────────────────────────────────────────────────────
# 보고서
# ─────────────────────────────────────────────────────────────────

def plan_to_dict(plan: MigrationPlan) -> dict:
    return {
        "generated_at": plan.generated_at,
        "settings": plan.settings,
        "rows": [asdict(r) for r in plan.rows],
        "ads": plan.ads,
        "brands": [asdict(b) for b in plan.brands],
        "brand_decisions": plan.brand_decisions,
        "warnings": plan.warnings,
    }


def _dc_from_dict(cls, data: dict):
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in (data or {}).items() if k in names})


def brand_from_dict(data: dict) -> g.BrandCandidate:
    brand = _dc_from_dict(g.BrandCandidate, data)
    brand.ads = [_dc_from_dict(g.AdSummary, a) for a in data.get("ads") or []]
    brand.volume = _dc_from_dict(g.VolumeCheck, data["volume"]) if data.get("volume") else None
    accounts = []
    for a in data.get("accounts") or []:
        acc = _dc_from_dict(g.LinkedAccount, a)
        acc.sample_ads = [_dc_from_dict(g.AdSummary, s) for s in a.get("sample_ads") or []]
        accounts.append(acc)
    brand.accounts = accounts
    return brand


def plan_from_dict(data: dict) -> MigrationPlan:
    plan = MigrationPlan(generated_at=data["generated_at"], settings=data.get("settings") or {})
    plan.rows = [_dc_from_dict(LegacyRow, r) for r in data.get("rows") or []]
    plan.ads = data.get("ads") or []
    plan.brands = [brand_from_dict(b) for b in data.get("brands") or []]
    plan.brand_decisions = data.get("brand_decisions") or {}
    plan.warnings = data.get("warnings") or []
    return plan


def format_report(plan: MigrationPlan) -> str:
    moving = plan.moving_brands()
    moving_ads = [a for a in plan.ads if a["decision"] == MOVE]
    lines = [
        "# 기존 노션 레퍼런스 옮기기 보고서 (미리보기)", "",
        f"- 만든 시각: {plan.generated_at}",
        f"- 기존 행 {len(plan.rows)}개 → 옮길 브랜드 {len(moving)}곳 · 소재 {len(moving_ads)}개",
        "- 노션·메타에는 아무것도 쓰지 않았습니다. 소재링크·편집일·대표님 피드백은 옮기지 않습니다.",
    ]
    for w in plan.warnings:
        lines.append(f"- ⚠️ {w}")
    lines += ["", "## 옮길 브랜드", "", "| 브랜드 | 자사몰 | ① 최고 30일 | 급상승 | 소재 |", "|---|---|---|---|---|"]
    for b in moving:
        n = sum(1 for a in moving_ads if a["brand_key"] == b.key)
        lines.append(f"| {b.name} | {b.key} | {g.volume_summary(b.volume)} | {g.rise_summary(b.volume)} | {n} |")
    if not moving:
        lines.append("| (없음) | | | | |")
    skipped = [b for b in plan.brands if b not in moving]
    if skipped:
        lines += ["", "## 게재 중이지만 A급 미달인 브랜드", "", "| 브랜드 | 자사몰 | 이유 |", "|---|---|---|"]
        for b in skipped:
            lines.append(f"| {b.name} | {b.key} | {plan.brand_decisions.get(b.key, {}).get('reason', '')} |")
    lines += ["", "## 행별 결과", "", "| 표 | 제목 | 결과 | 이유 |", "|---|---|---|---|"]
    for r in plan.rows:
        title = (r.title or "(제목 없음)").replace("|", "/")[:60]
        lines.append(f"| {r.source[:10]} | {title} | {r.decision} | {r.reason.replace('|', '/')[:120]} |")
    return "\n".join(lines)


def save_plan(plan: MigrationPlan) -> tuple:
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(OUT_DIR, f"migration_plan_{stamp}.json")
    md_path = os.path.join(OUT_DIR, f"migration_plan_{stamp}.md")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(plan_to_dict(plan), f, ensure_ascii=False, indent=2, default=str)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(format_report(plan))
    return json_path, md_path


# ─────────────────────────────────────────────────────────────────
# 실행 (확인 후)
# ─────────────────────────────────────────────────────────────────

def apply_migration(plan: MigrationPlan, store: nr.ReferenceStore, track: bool = True, progress=print,
                    today: date = None) -> dict:
    """보고서에서 '옮김'인 브랜드·소재만 새 표에 저장합니다. 여러 번 실행해도 중복되지 않습니다."""
    today = today or date.today()
    settings = g.ScanSettings.from_dict(plan.settings)
    ad_extra = {a["ad_id"]: a for a in plan.ads if a["decision"] == MOVE}
    result = {"brands": 0, "ads_created": 0, "ads_updated": 0, "errors": []}
    for brand in plan.moving_brands():
        try:
            if track and not brand.tracked:
                progress(f"연결 계정 추적: {brand.name}")
                g.track_brand(brand, settings)
            page_id, _ = store.upsert_brand(brand, today)
            result["brands"] += 1
            for ad in brand.ads:
                extra = ad_extra.get(ad.ad_id)
                if not extra:
                    continue
                _, created = store.upsert_ad(ad, brand, page_id, account_type=g.ad_account_type(brand, ad),
                                             status=nr.STATUS_DEFAULT, appeals=extra.get("appeals") or [],
                                             video_link=extra.get("drive_link") or "")
                result["ads_created" if created else "ads_updated"] += 1
                progress(f"소재 저장: {brand.name} · {ad.page_name} ({'새로' if created else '갱신'})")
        except (NotionError, RuntimeError) as exc:
            result["errors"].append(f"{brand.name}: {exc}")
    return result


# ─────────────────────────────────────────────────────────────────
# 기존 DB 정리 (선택)
# ─────────────────────────────────────────────────────────────────

TEMPLATE_TEXTS = (
    "아래 표에 레퍼런스를 계속 추가해두면",
    "레퍼런스 모음",
    "태그/분류 가이드",
    "카테고리(목적) 예시",
    "크리에이티브 유형 예시",
    "포맷: 피드",
    "링크: Meta Ad Library",
    "사용 팁",
    "같은 캠페인의 소재가 여러 개면",
    "\"크리에이티브 포인트\"에는",
)
ARCHIVE_PREFIX = "(보관) "


def plan_tidy(client: NotionClient, legacy_db_id: str) -> dict:
    db = client.get(f"databases/{legacy_db_id}")
    title = "".join(t.get("plain_text", "") for t in db.get("title") or [])
    parent = (db.get("parent") or {}).get("page_id", "")
    blocks = []
    for b in client.block_children(parent) if parent else []:
        kind = b.get("type")
        if kind in ("child_database", "child_page"):
            continue
        inner = b.get(kind, {}) or {}
        text = "".join(r.get("plain_text", "") for r in inner.get("rich_text", []) or [])
        if kind == "table" or any(text.startswith(t) for t in TEMPLATE_TEXTS):
            blocks.append({"id": b["id"], "type": kind, "text": text[:60]})
    return {"db_title": title, "new_title": title if title.startswith(ARCHIVE_PREFIX) else ARCHIVE_PREFIX + title,
            "parent": parent, "template_blocks": blocks}


def apply_tidy(client: NotionClient, legacy_db_id: str, tidy: dict, rename: bool, trash_template: bool) -> list:
    log = []
    if rename and tidy["db_title"] != tidy["new_title"]:
        client.patch(f"databases/{legacy_db_id}", json={"title": [{"type": "text", "text": {"content": tidy["new_title"]}}]})
        log.append(f"기존 DB 이름: {tidy['db_title']} → {tidy['new_title']}")
    if trash_template:
        for b in tidy["template_blocks"]:
            client.delete(f"blocks/{b['id']}")
            log.append(f"휴지통으로: [{b['type']}] {b['text']}")
    return log


# ─────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────

def _main(argv=None) -> int:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(BASE_DIR, ".env"))
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="기존 노션 레퍼런스 옮기기")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan", help="읽기만 해서 보고서 만들기")
    ap = sub.add_parser("apply", help="보고서대로 새 표에 저장")
    ap.add_argument("report", help="plan이 만든 migration_plan_*.json")
    ap.add_argument("--no-track", action="store_true", help="연결 계정 추적을 건너뜀")
    td = sub.add_parser("tidy", help="기존 DB 보관 표시·템플릿 잔여물 정리 (기본은 미리보기)")
    td.add_argument("--rename", action="store_true")
    td.add_argument("--trash-template", action="store_true")
    td.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    token = os.environ.get("NOTION_TOKEN", "").strip()
    legacy = os.environ.get("NOTION_DATABASE_ID", "").strip()
    if not token or not legacy:
        print("NOTION_TOKEN과 NOTION_DATABASE_ID가 필요합니다.")
        return 2
    client = NotionClient(token)

    if args.cmd == "plan":
        creds = tuple(os.environ.get(k, "") for k in ("NAVER_CUSTOMER_ID", "NAVER_ACCESS_LICENSE", "NAVER_SECRET_KEY"))
        started = time.time()
        plan = plan_migration(client, legacy, creds, progress=lambda m: print(m, flush=True))
        json_path, md_path = save_plan(plan)
        print(f"\n보고서: {md_path}\n실행용: {json_path}\n({time.time() - started:.0f}초, 노션·메타에 쓰지 않음)")
        return 0

    if args.cmd == "apply":
        with open(args.report, encoding="utf-8") as f:
            plan = plan_from_dict(json.load(f))
        store = nr.ReferenceStore.from_env(client).load()
        result = apply_migration(plan, store, track=not args.no_track, progress=lambda m: print(m, flush=True))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["errors"] else 0

    tidy = plan_tidy(client, legacy)
    print(f"기존 DB 이름: {tidy['db_title']} → {tidy['new_title']}" + ("" if args.rename else " (--rename 시)"))
    print(f"템플릿 잔여물 {len(tidy['template_blocks'])}개" + ("" if args.trash_template else " (--trash-template 시 휴지통으로)"))
    for b in tidy["template_blocks"]:
        print(f"  - [{b['type']}] {b['text']}")
    if args.apply:
        for line in apply_tidy(client, legacy, tidy, args.rename, args.trash_template):
            print(line)
    else:
        print("(미리보기입니다. 실제로 하려면 --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
