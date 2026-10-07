"""
A급 소재 탐색 & 브랜드 연결 계정 추적
======================================

A급 소재 = 아래 3가지를 모두 충족하는 메타 광고
  ① 최근 1년 안에 브랜드(또는 제품) 키워드의 30일 검색량 1만 건 이상인 이력과 직전 60일 대비 60일 증가폭 7천 건 이상인 이력이 있다
     - 아이템스카우트와 같은 산출 방식: 네이버 검색광고 최근 30일 검색수 × 네이버 데이터랩 일간 추이
  ② 메타 광고 라이브러리에서 60일(2개월) 이상 게재 중이다
  ③ 우리 제품과 연관된다 (광고 문구·페이지명·랜딩 주소에 연관 키워드 포함, 제외 키워드 없음)

A급 브랜드를 찾으면 같은 랜딩(자사몰 도메인·스마트스토어 등)으로 광고를 보내는 다른 페이지를 모두 찾아
공식 / 숨은 / 위장(외국 문자 섞기) / 아랍어·외국어 계정으로 분류합니다.

사용하는 공개 데이터
  - 메타 광고 라이브러리 공개 GraphQL (meta_ad_library.AdLibraryClient)
  - 네이버 검색광고 키워드도구 API (NAVER_CUSTOMER_ID / NAVER_ACCESS_LICENSE / NAVER_SECRET_KEY)
  - 네이버 데이터랩 웹 (키 불필요)
"""

from __future__ import annotations

import base64
import binascii
import html
import json
import os
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime, timedelta
from typing import Callable, Optional
from urllib.parse import parse_qs, unquote, urlparse

from meta_ad_library import (
    AdLibraryBlocked,
    AdLibraryClient,
    clean_ad_copy,
    detect_media_type,
    _clean_landing_url,
    _extract_video_download_url,
)
from naver_datalab import _get_session as _datalab_session
from naver_datalab import (
    RISE_FLAT,
    RISE_LEVELS,
    RISE_ROCKET,
    RISE_UP,
    estimate_monthly_volumes,
    find_steepest_rise,
    format_rise,
    get_daily_search_trend,
    get_shopping_audience,
    rolling_30d_volumes,
)
from naver_scraper import get_naver_search_volumes

try:
    from curl_cffi import requests as _cf_requests
except ImportError:  # pragma: no cover - requirements.txt에 포함
    _cf_requests = None


# ─────────────────────────────────────────────────────────────────
# 기본값
# ─────────────────────────────────────────────────────────────────

DEFAULT_SCAN_KEYWORDS = [
    "여드름 영양제",
    "먹는 여드름",
    "트러블 영양제",
    "피지 영양제",
    "여드름 유산균",
    "피부 영양제",
    "이너뷰티",
    "여드름관리",
    "남자피부관리",
    "화농성여드름",
]
DEFAULT_RELEVANCE_TERMS = ["여드름", "트러블", "피지", "좁쌀", "뾰루지", "영양제", "이너뷰티", "유산균", "건강기능식품"]
DEFAULT_EXCLUDE_TERMS = ["강아지", "반려", "애완", "고양이", "펫", "애견", "댕댕"]

MIN_RUNNING_DAYS = 60          # ② 최소 게재 일수 (2개월)
MIN_PEAK_VOLUME = 10_000       # ① 연속 30일 검색량 기준
SEARCH_WINDOW_DAYS = 30
RISE_WINDOW_DAYS = 60
LOOKBACK_DAYS = 365            # ① 확인 기간 (최근 1년)
MAX_TREND_KEYWORDS = 2         # 브랜드당 데이터랩 추이를 확인할 최대 키워드 수
MAX_VERIFY_PAGES = 30          # 브랜드당 광고를 직접 열어 확인할 최대 페이지 수
MAX_TRACK_ROUNDS = 2           # 찾은 숨은 계정의 이름·광고 문구로 다시 검색하는 단계 수
MAX_EXPAND_QUERIES = 24        # 브랜드당 추가 검색(숨은 계정 이름·문구) 최대 횟수
SPIKE_MIN_JUMP = 7_000         # 🚀 급상승: 60일 증가폭
SPIKE_MIN_RATIO = 3.0          # 🚀 급상승: 직전 60일 대비 배수
TREND_EXTRA_DAYS = 120         # 1년 전 60일 구간과 직전 60일도 비교하도록 추가 조회

ACCOUNT_ARABIC = "아랍어 계정"
ACCOUNT_FOREIGN = "외국어 계정"
ACCOUNT_DISGUISED = "위장 계정"
ACCOUNT_HIDDEN = "숨은 계정"
ACCOUNT_OFFICIAL = "공식 계정"
ACCOUNT_ORDER = [ACCOUNT_ARABIC, ACCOUNT_FOREIGN, ACCOUNT_DISGUISED, ACCOUNT_HIDDEN, ACCOUNT_OFFICIAL]

CONFIRMED = "확정"   # 같은 랜딩으로 광고를 보냄
LIKELY = "유력"      # 광고 문구가 같지만 랜딩을 확인하지 못함

ProgressFn = Callable[[float, str], None]


def _no_progress(_fraction: float, _message: str) -> None:
    return None


# ─────────────────────────────────────────────────────────────────
# 결과 구조
# ─────────────────────────────────────────────────────────────────

@dataclass
class ScanSettings:
    scan_keywords: list = field(default_factory=lambda: list(DEFAULT_SCAN_KEYWORDS))
    relevance_terms: list = field(default_factory=lambda: list(DEFAULT_RELEVANCE_TERMS))
    exclude_terms: list = field(default_factory=lambda: list(DEFAULT_EXCLUDE_TERMS))
    min_running_days: int = MIN_RUNNING_DAYS
    min_peak_volume: int = MIN_PEAK_VOLUME
    lookback_days: int = LOOKBACK_DAYS
    pages_per_keyword: int = 3
    account_pages: int = 20
    country: str = "KR"
    track_accounts: bool = True
    spike_min_jump: int = SPIKE_MIN_JUMP       # 🚀 60일 증가폭 기준
    spike_min_ratio: float = SPIKE_MIN_RATIO   # 🚀 직전 60일 대비 배수 기준

    @classmethod
    def from_dict(cls, data: dict) -> "ScanSettings":
        return cls(**{k: v for k, v in (data or {}).items() if k in cls.__dataclass_fields__})


@dataclass
class AdSummary:
    ad_id: str
    page_id: str
    page_name: str
    start_date: str
    running_days: int
    media_type: str
    copy: str
    hook: str
    caption: str
    landing_url: str
    store_key: str
    video_url: str
    thumbnail_url: str
    library_url: str
    search_keyword: str = ""
    relevance: list = field(default_factory=list)
    collation_id: str = ""        # 메타 묶음 ID (같은 소재의 변형 광고끼리 같음)
    video_asset_id: str = ""      # 영상 자산 ID (같은 영상이면 같음)
    fingerprint: str = ""         # 첫 문장 지문
    variants: int = 1             # 스캔에서 합친 변형 광고 수
    recorded: str = ""            # 노션에 이미 기록된 소재면 그 이유
    variant_ids: list = field(default_factory=list)


@dataclass
class VolumeCheck:
    passed: Optional[bool] = None      # ① True 충족 / False 미달 / None 확인 불가
    keyword: str = ""                  # 대표 키워드 (① 통과 키워드 중 가장 가파르게 오른 것)
    peak_month: str = ""               # 최고 판정 구간 표시 (새 결과: 60일)
    peak_volume: int = 0               # search_window_days 기준 검색량 최고값
    prev_month_volume: int = 0         # (예전 저장 결과 호환용)
    recent_30d: int = 0
    recent_pc: int = 0
    recent_mobile: int = 0
    months: list = field(default_factory=list)    # 대표 키워드의 달력 월별 추정 검색량 (참고용)
    windows: list = field(default_factory=list)   # rise_window_days 기준 롤링 검색량
    search_window_days: int = 30    # 검색량 판정은 30일
    grade_windows: list = field(default_factory=list)
    peak_is_lower_bound: bool = False
    checked: list = field(default_factory=list)   # 확인한 키워드별 결과
    note: str = ""
    # 급상승 (검색량과 증가폭을 함께 A급 판정에 사용)
    rise_window_days: int = 30    # 기존 결과 호환; 새 계산은 60일
    rise_level: str = ""               # RISE_ROCKET / RISE_UP / RISE_FLAT, 추이가 없으면 ""
    rise_start: str = ""
    rise_end: str = ""
    rise_volume: int = 0               # 급상승 구간 검색량
    rise_prev: int = 0                 # 직전 구간 검색량
    rise_jump: int = 0                 # 증가폭
    rise_ratio: Optional[float] = None  # 증가 배수 (직전이 0이면 None)
    rise_baseline: int = 0             # 급상승 전 평소 검색량 (중앙값)

    @property
    def rise(self) -> dict:
        """naver_datalab.format_rise에 넘길 형태"""
        if not self.rise_end:
            return {}
        return {"start": self.rise_start, "end": self.rise_end, "volume": self.rise_volume,
                "prev_volume": self.rise_prev, "jump": self.rise_jump, "ratio": self.rise_ratio,
                "baseline": self.rise_baseline, "level": self.rise_level}


@dataclass
class LinkedAccount:
    page_id: str
    page_name: str
    account_type: str
    type_reason: str
    foreign_scripts: list = field(default_factory=list)
    confidence: str = CONFIRMED
    evidence: list = field(default_factory=list)
    brand_ads: int = 0             # 이 브랜드 랜딩으로 가는 광고 수 (확인한 범위)
    checked_ads: int = 0           # 확인한 게재 중 광고 수
    max_running_days: int = 0
    other_landings: list = field(default_factory=list)
    library_url: str = ""
    profile_url: str = ""
    sample_ads: list = field(default_factory=list)
    found_via: str = ""            # 처음 찾은 검색 (예: "도메인 're4day.co.kr'", "위장 계정 'OO' 이름")
    depth: int = 0                 # 0 = 브랜드 검색으로 찾음, 1 이상 = 찾은 숨은 계정을 다시 검색해서 찾음


@dataclass
class BrandCandidate:
    key: str                       # 브랜드 식별 키 (자사몰 도메인, smartstore.naver.com/상점 등)
    name: str = ""
    site_name: str = ""
    product_hint: str = ""
    landing_title: str = ""
    landing_url: str = ""
    keywords: list = field(default_factory=list)   # ① 검색량 확인 키워드
    ads: list = field(default_factory=list)        # ②·③을 충족한 광고 (AdSummary)
    relevance_terms: list = field(default_factory=list)
    volume: Optional[VolumeCheck] = None
    criteria: dict = field(default_factory=dict)
    is_a_grade: bool = False
    reasons: list = field(default_factory=list)
    accounts: list = field(default_factory=list)   # LinkedAccount
    tracked: bool = False
    tracking_note: str = ""
    tracking_failed: int = 0                       # 마지막 추적에서 실패한 메타 검색 수
    tracking_incomplete: bool = False
    tracking_limits: list = field(default_factory=list)
    audience: dict = field(default_factory=dict)   # 성별·연령 비중 (naver_datalab.get_shopping_audience)


@dataclass
class AGradeReport:
    generated_at: str
    settings: dict
    scanned_ads: int = 0
    long_running_ads: int = 0
    relevant_ads: int = 0
    excluded_ads: int = 0
    brands: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    meta_requests: int = 0
    meta_diagnostics: dict = field(default_factory=dict)
    saved_path: str = ""
    recorded_checked: bool = False   # 노션 소재 표와 비교했는지
    recorded_error: str = ""
    scan_incomplete: bool = False

    @property
    def a_grade_brands(self) -> list:
        return [b for b in self.brands if b.is_a_grade]


# ─────────────────────────────────────────────────────────────────
# 텍스트 유틸
# ─────────────────────────────────────────────────────────────────

def parse_terms(text) -> list:
    """쉼표·줄바꿈으로 구분된 입력을 중복 없는 목록으로 바꿉니다."""
    if isinstance(text, (list, tuple)):
        items = text
    else:
        items = re.split(r"[,\n]", str(text or ""))
    out = []
    for item in items:
        item = str(item).strip()
        if item and item not in out:
            out.append(item)
    return out


def _compact(text) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def _norm_name(text) -> str:
    """이름 비교용: 한글 음절·영문·숫자만 남기고 소문자로."""
    return re.sub(r"[^0-9a-z가-힣]", "", str(text or "").lower())


def match_terms(text: str, terms: list) -> list:
    """text에 포함된 terms (공백·대소문자 무시)."""
    haystack = _compact(text)
    found = []
    for term in terms:
        needle = _compact(term)
        if needle and needle in haystack and term not in found:
            found.append(term)
    return found


def _shorten(text: str, limit: int = 14) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[:limit] + "…"


# ─────────────────────────────────────────────────────────────────
# 랜딩 주소 → 브랜드(상점) 식별
# ─────────────────────────────────────────────────────────────────

SHORTENER_HOSTS = {
    "bit.ly", "bitly.com", "bitly.ws", "j.mp", "abit.ly", "tinyurl.com", "naver.me", "me2.do", "han.gl",
    "url.kr", "vo.la", "t.ly", "buly.kr", "lrl.kr", "zrr.kr", "c11.kr", "goo.gl", "is.gd", "rb.gy",
    "cutt.ly", "shorturl.at", "s.id", "ow.ly", "rebrand.ly", "tiny.cc", "gg.gg", "kko.to", "abr.ge",
    "link.coupang.com", "coupa.ng", "oy.run", "amzn.to", "surl.li", "t.co", "lnkd.in",
}
FACEBOOK_HOSTS = {
    "facebook.com", "m.facebook.com", "web.facebook.com", "business.facebook.com", "fb.com", "fb.me",
    "fb.watch", "m.me", "messenger.com", "l.facebook.com", "lm.facebook.com", "wa.me", "whatsapp.com",
}
# 주소 경로의 첫 단계가 상점(계정)을 구분하는 호스트
PATH_STORE_HOSTS = {
    "smartstore.naver.com": "smartstore.naver.com",
    "m.smartstore.naver.com": "smartstore.naver.com",
    "brand.naver.com": "brand.naver.com",
    "m.brand.naver.com": "brand.naver.com",
    "m.site.naver.com": "m.site.naver.com",
    "blog.naver.com": "blog.naver.com",
    "m.blog.naver.com": "blog.naver.com",
    "instagram.com": "instagram.com",
    "m.instagram.com": "instagram.com",
    "linktr.ee": "linktr.ee",
    "link.inpock.co.kr": "link.inpock.co.kr",
    "litt.ly": "litt.ly",
    "pf.kakao.com": "pf.kakao.com",
    "store.kakao.com": "store.kakao.com",
}
_GENERIC_PATH_SEGMENTS = {
    "p", "products", "product", "shop", "reel", "reels", "stories", "explore", "accounts", "s", "home",
    "main", "search", "tv", "share", "profile", "i",
}
# 여러 브랜드가 함께 쓰는 쇼핑몰·플랫폼: 도메인만으로는 브랜드를 구분할 수 없어 상품 번호까지 봅니다
SHARED_MARKET_DOMAINS = {
    "coupang.com", "oliveyoung.co.kr", "11st.co.kr", "gmarket.co.kr", "auction.co.kr", "ssg.com",
    "lotteon.com", "kurly.com", "musinsa.com", "29cm.co.kr", "a-bly.com", "zigzag.kr", "tmon.co.kr",
    "wemakeprice.com", "interpark.com", "gsshop.com", "cjonstyle.com", "hmall.com", "iherb.com",
    "amazon.com", "aliexpress.com", "temu.com", "qoo10.com", "ohou.se", "10x10.co.kr", "lotteimall.com",
    "naver.com", "kakao.com", "daum.net", "google.com", "youtube.com", "youtu.be", "apple.com",
    "tiktok.com", "threads.net", "x.com", "twitter.com", "notion.so",
}
# 서브도메인이 곧 상점인 쇼핑몰 호스팅
HOSTED_SHOP_DOMAINS = {
    "cafe24.com", "imweb.me", "sixshop.com", "godomall.com", "shopby.co.kr", "myshopify.com",
    "wixsite.com", "modoo.at", "notion.site", "tistory.com", "blogspot.com", "creatorlink.net", "oopy.io",
}
_MULTI_LEVEL_SUFFIXES = {
    "co.kr", "or.kr", "ne.kr", "re.kr", "pe.kr", "go.kr", "ac.kr", "ms.kr", "kg.kr", "hs.kr", "es.kr",
    "sc.kr", "seoul.kr", "co.jp", "ne.jp", "or.jp", "ac.jp", "co.uk", "org.uk", "com.au", "net.au",
    "com.cn", "com.tw", "com.hk", "com.sg", "com.my", "co.id", "co.th", "com.vn", "co.nz", "com.br",
}
_PRODUCT_QUERY_KEYS = (
    "goodsNo", "goodsno", "goods_no", "product_no", "productNo", "productId", "prdNo", "itemId", "itemid",
    "item_id", "branduid", "pid",
)
_PRODUCT_PATH_RE = re.compile(r"/(?:vp/)?(?:products?|goods|items?|catalog)/([A-Za-z0-9_-]*\d[A-Za-z0-9_-]*)", re.I)
_DOMAIN_CAPTION_RE = re.compile(
    r"^(?:https?://)?([a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9-]+)*\.[a-z]{2,})(?::\d+)?(/\S*)?$", re.I
)


def registrable_domain(host: str) -> str:
    """shop.brand.co.kr → brand.co.kr"""
    host = (host or "").lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in _MULTI_LEVEL_SUFFIXES:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _host(url: str) -> str:
    try:
        parsed = urlparse(url if "://" in url else "https://" + url)
        host = (parsed.hostname or "").lower().strip(".")
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def is_short_link(url: str) -> bool:
    """단축 주소(해석이 필요한 주소)인지."""
    if not url:
        return False
    try:
        parsed = urlparse(url if "://" in url else "https://" + url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    path = parsed.path.strip("/")
    if host in SHORTENER_HOSTS or registrable_domain(host) in SHORTENER_HOSTS:
        return bool(path)
    return False


def _market_product_id(parsed) -> str:
    m = _PRODUCT_PATH_RE.search(parsed.path or "")
    if m:
        return m.group(1)[:40]
    qs = parse_qs(parsed.query)
    for key in _PRODUCT_QUERY_KEYS:
        if qs.get(key):
            return qs[key][0][:40]
    return ""


def store_key(url: str) -> str:
    """랜딩 주소를 브랜드(상점) 식별 키로 바꿉니다. 브랜드를 구분할 수 없는 주소면 ""."""
    if not url:
        return ""
    try:
        parsed = urlparse(url if "://" in url else "https://" + url)
        host = (parsed.hostname or "").lower().strip(".")
    except ValueError:
        return ""
    if not host or "." not in host:
        return ""
    if host.startswith("www."):
        host = host[4:]
    if host in FACEBOOK_HOSTS or host.endswith(".facebook.com"):
        return ""
    segments = [s for s in (parsed.path or "").split("/") if s]
    if host in PATH_STORE_HOSTS:
        if not segments or segments[0].lower() in _GENERIC_PATH_SEGMENTS:
            return ""
        return f"{PATH_STORE_HOSTS[host]}/{segments[0].lower()}"
    reg = registrable_domain(host)
    if host in SHORTENER_HOSTS or reg in SHORTENER_HOSTS:
        return ""
    if reg in HOSTED_SHOP_DOMAINS:
        sub = host[: -len(reg)].rstrip(".")
        if sub.startswith("m."):
            sub = sub[2:]
        return f"{sub}.{reg}" if sub and sub not in ("m", "www") else ""
    if reg in SHARED_MARKET_DOMAINS:
        product_id = _market_product_id(parsed)
        return f"{reg}/p/{product_id}" if product_id else ""
    return reg


def is_own_site_key(key: str) -> bool:
    """자사몰(독립 도메인·쇼핑몰 호스팅) 키인지. 도메인 검색과 랜딩 페이지 확인에 씁니다."""
    return bool(key) and "/" not in key and not key.startswith("page:")


def _key_label(key: str) -> str:
    """키에서 브랜드 영문명 후보: re4day.co.kr → re4day, smartstore.naver.com/abc → abc"""
    if not key or key.startswith("page:"):
        return ""
    if "/" in key:
        host, _, rest = key.partition("/")
        if host in PATH_STORE_HOSTS.values():
            return rest.split("/")[0].lower()
        return ""  # 쿠팡·올리브영 상품 번호 키에는 브랜드명이 없음
    reg = registrable_domain(key)
    if reg in HOSTED_SHOP_DOMAINS:
        return key.split(".")[0].lower()
    return reg.split(".")[0].lower()


def _unwrap_redirect(url: str) -> str:
    url = _clean_landing_url(url)
    if "l.instagram.com" in url:
        try:
            qs = parse_qs(urlparse(url).query)
            if qs.get("u"):
                url = unquote(qs["u"][0])
        except ValueError:
            pass
    return url


def _caption_url(caption) -> str:
    caption = str(caption or "").strip()
    if not caption or " " in caption:
        return ""
    if not _DOMAIN_CAPTION_RE.match(caption):
        return ""
    return caption if caption.lower().startswith("http") else "https://" + caption


# ─────────────────────────────────────────────────────────────────
# 광고 필드
# ─────────────────────────────────────────────────────────────────

def _snapshot(ad: dict) -> dict:
    snap = ad.get("snapshot")
    return snap if isinstance(snap, dict) else {}


def _text(value) -> str:
    if isinstance(value, dict):
        value = value.get("text")
    return str(value) if value not in (None, "") else ""


def _body_text(ad: dict) -> str:
    return _text(_snapshot(ad).get("body"))


def ad_page(ad: dict) -> tuple:
    snap = _snapshot(ad)
    page_id = str(ad.get("page_id") or snap.get("page_id") or "").strip()
    page_name = str(ad.get("page_name") or snap.get("page_name") or "").strip()
    return page_id, page_name


def ad_start_date(ad: dict) -> Optional[date]:
    value = ad.get("start_date") or _snapshot(ad).get("creation_time")
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            return datetime.fromtimestamp(int(value)).date()
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (ValueError, OSError, OverflowError):
        return None


def ad_running_days(ad: dict, today: date) -> int:
    start = ad_start_date(ad)
    return max(0, (today - start).days) if start else 0


def ad_link_urls(ad: dict) -> list:
    """광고가 보내는 주소 후보 (클릭 주소 → 카드 → 표시 주소 → 본문 링크 순)."""
    snap = _snapshot(ad)
    candidates = [snap.get("link_url"), snap.get("cta_url")]
    for card in snap.get("cards") or []:
        if isinstance(card, dict):
            candidates.extend([card.get("link_url"), card.get("cta_url")])
    for link in snap.get("extra_links") or []:
        candidates.append(link.get("link_url") if isinstance(link, dict) else link)
    candidates.append(_caption_url(snap.get("caption")))
    candidates.extend(re.findall(r"https?://[^\s<>\"'()]+", _body_text(ad)))

    urls = []
    for url in candidates:
        if not url or not isinstance(url, str) or not url.startswith("http"):
            continue
        url = _unwrap_redirect(url.strip())
        host = _host(url)
        if not host:
            continue
        if (host in SHORTENER_HOSTS or registrable_domain(host) in SHORTENER_HOSTS) and not is_short_link(url):
            continue  # "https://bit.ly" 처럼 경로 없는 단축 주소는 쓸모 없음
        if url not in urls:
            urls.append(url)
    return urls


def ad_text(ad: dict) -> str:
    """③ 연관성 판정에 쓰는 광고의 모든 글자 (페이지명·문구·제목·표시 주소·랜딩 주소)."""
    snap = _snapshot(ad)
    parts = [ad.get("page_name"), snap.get("page_name"), _body_text(ad), snap.get("title"),
             snap.get("link_description"), snap.get("caption")]
    for card in snap.get("cards") or []:
        if isinstance(card, dict):
            parts.extend([_text(card.get("body")), card.get("title"), card.get("link_description")])
    for extra in snap.get("extra_texts") or []:
        parts.append(_text(extra))
    parts.extend(unquote(u) for u in ad_link_urls(ad))
    return " ".join(str(p) for p in parts if p)


def ad_thumbnail(ad: dict) -> str:
    snap = _snapshot(ad)
    for video in snap.get("videos") or []:
        if isinstance(video, dict) and video.get("video_preview_image_url"):
            return video["video_preview_image_url"]
    for image in snap.get("images") or []:
        if isinstance(image, dict):
            url = image.get("original_image_url") or image.get("resized_image_url")
            if url:
                return url
    for card in snap.get("cards") or []:
        if isinstance(card, dict):
            url = card.get("video_preview_image_url") or card.get("original_image_url") or card.get("resized_image_url")
            if url:
                return url
    return ""


def _hook_line(raw_body: str) -> str:
    """광고 문구에서 정확 문구 검색에 쓸 한 줄 (이모지·기호 없이 이어진 가장 긴 구간)."""
    for line in re.split(r"[\r\n]+", raw_body or ""):
        line = re.sub(r"\{\{[^}]*\}\}", " ", line)
        line = re.sub(r"https?://\S+|[#@][^\s#@]+", " ", line)
        segments = re.split(r"[^0-9A-Za-z가-힣\s,.?!~%'\"-]", line)
        best = max((re.sub(r"\s+", " ", s).strip(" ,.-~") for s in segments),
                   key=lambda s: len(re.sub(r"[^가-힣A-Za-z0-9]", "", s)), default="")
        if len(re.sub(r"[^가-힣A-Za-z0-9]", "", best)) >= 10:
            if len(best) > 40:
                cut = best[:40].rfind(" ")
                best = best[: cut if cut >= 20 else 40]
            return best.strip()
    return ""


def page_library_url(page_id: str, country: str = "KR") -> str:
    if not page_id:
        return ""
    return (
        "https://www.facebook.com/ads/library/?active_status=active&ad_type=all"
        f"&country={country}&view_all_page_id={page_id}&search_type=page&media_type=all"
    )


# ─────────────────────────────────────────────────────────────────
# 단축 주소 해석 · 랜딩 페이지 읽기
# ─────────────────────────────────────────────────────────────────

def _meta_tags(text: str) -> dict:
    tags = {}
    for tag in re.findall(r"<meta\b[^>]*>", text[:300_000], re.I):
        attrs = {}
        for name, _, dq, sq, bare in re.findall(r'([\w:-]+)\s*=\s*("([^"]*)"|\'([^\']*)\'|([^\s>]+))', tag):
            attrs[name.lower()] = dq or sq or bare
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        if key and "content" in attrs and key not in tags:
            tags[key] = html.unescape(attrs["content"]).strip()
    return tags


def parse_landing_html(text: str) -> dict:
    tags = _meta_tags(text or "")
    title = re.search(r"<title[^>]*>(.*?)</title>", text or "", re.I | re.S)
    return {
        "site_name": tags.get("og:site_name", ""),
        "og_title": tags.get("og:title", ""),
        "title": re.sub(r"\s+", " ", html.unescape(title.group(1))).strip() if title else "",
        "description": tags.get("og:description") or tags.get("description", ""),
    }


def _decode_html(response) -> str:
    raw = (response.content or b"")[:400_000]
    enc = ""
    m = re.search(r"charset=([\w-]+)", response.headers.get("content-type", "") or "", re.I)
    if m:
        enc = m.group(1)
    else:
        m = re.search(rb'charset=["\']?([\w-]+)', raw[:4096], re.I)
        if m:
            enc = m.group(1).decode("ascii", "ignore")
    enc = (enc or "utf-8").lower()
    if enc in ("euc-kr", "ks_c_5601-1987", "ksc5601", "x-windows-949"):
        enc = "cp949"
    try:
        return raw.decode(enc, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


class LinkResolver:
    """단축 주소를 최종 주소로 풀고, 자사몰 랜딩 페이지에서 브랜드명·제품명을 읽습니다 (결과 캐시)."""

    def __init__(self, timeout: float = 10.0, workers: int = 6):
        self.timeout = timeout
        self.workers = workers
        self._final: dict = {}
        self._landing_cache: dict = {}

    def _get(self, url: str):
        if _cf_requests is None:
            return None
        try:
            return _cf_requests.get(
                url, impersonate="chrome124", timeout=self.timeout, allow_redirects=True, max_redirects=8,
                headers={"Accept-Language": "ko-KR,ko;q=0.9"},
            )
        except Exception:
            return None

    def _fetch(self, url: str) -> tuple:
        """(최종 주소, HTML). 실패하면 (None, "")."""
        response = self._get(url)
        if response is None:
            return None, ""
        final = str(response.url or url)
        text = _decode_html(response)
        if is_short_link(final):
            # 일부 단축 주소는 HTML·자바스크립트로 이동시킴
            m = (re.search(r'http-equiv=["\']?refresh["\']?[^>]*url=([^"\'>\s]+)', text, re.I)
                 or re.search(r'location\.(?:href|replace)\s*(?:=|\()\s*["\'](https?://[^"\']+)', text))
            if m and m.group(1).startswith("http"):
                second = self._get(html.unescape(m.group(1)))
                if second is not None:
                    return str(second.url or m.group(1)), _decode_html(second)
        return final, text

    def resolve(self, url: str) -> str:
        if not is_short_link(url):
            return url
        if url not in self._final:
            final, _ = self._fetch(url)
            self._final[url] = _unwrap_redirect(final) if final else url
        return self._final[url]

    def resolve_many(self, urls) -> None:
        todo = [u for u in dict.fromkeys(urls) if is_short_link(u) and u not in self._final]
        if not todo:
            return
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            for url, (final, _) in zip(todo, pool.map(self._fetch, todo)):
                self._final[url] = _unwrap_redirect(final) if final else url

    def _read_landing(self, url: str) -> dict:
        final, text = self._fetch(url)
        info = parse_landing_html(text) if text else {"site_name": "", "og_title": "", "title": "", "description": ""}
        info["final_url"] = final or ""
        return info

    def landing_infos(self, urls_by_key: dict) -> dict:
        """{브랜드 키: 랜딩 주소} → {브랜드 키: 랜딩 정보}"""
        todo = {k: u for k, u in urls_by_key.items() if u and k not in self._landing_cache}
        if todo:
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                for key, info in zip(todo, pool.map(self._read_landing, todo.values())):
                    self._landing_cache[key] = info
        return {k: self._landing_cache.get(k, {}) for k in urls_by_key}


def ad_store_keys(ad: dict, resolver: Optional[LinkResolver]) -> list:
    """광고가 보내는 브랜드(상점) 키 목록. 첫 번째가 대표 랜딩."""
    keys = []
    for url in ad_link_urls(ad):
        final = resolver.resolve(url) if (resolver and is_short_link(url)) else url
        key = store_key(final)
        if key and key not in keys:
            keys.append(key)
    return keys


def summarize_ad(ad: dict, today: date, resolver: Optional[LinkResolver], keys: Optional[list] = None) -> AdSummary:
    snap = _snapshot(ad)
    page_id, page_name = ad_page(ad)
    keys = ad_store_keys(ad, resolver) if keys is None else keys
    urls = ad_link_urls(ad)
    landing = ""
    if urls:
        landing = resolver.resolve(urls[0]) if (resolver and is_short_link(urls[0])) else urls[0]
    start = ad_start_date(ad)
    ad_id = str(ad.get("ad_archive_id") or ad.get("id") or "")
    raw_body = _body_text(ad)
    return AdSummary(
        ad_id=ad_id,
        page_id=page_id,
        page_name=page_name,
        start_date=start.isoformat() if start else "",
        running_days=ad_running_days(ad, today),
        media_type=detect_media_type(ad, snap),
        copy=clean_ad_copy(raw_body, brand=page_name),
        hook=_hook_line(raw_body),
        caption=str(snap.get("caption") or ""),
        landing_url=landing,
        store_key=keys[0] if keys else "",
        video_url=_extract_video_download_url(ad, snap),
        thumbnail_url=ad_thumbnail(ad),
        library_url=f"https://www.facebook.com/ads/library/?id={ad_id}" if ad_id else "",
        search_keyword=str(ad.get("_search_keyword") or ""),
        relevance=list(ad.get("_relevance") or []),
        collation_id=str(ad.get("collation_id") or ""),
        video_asset_id=video_asset_id(ad),
        fingerprint=creative_fingerprint(raw_body),
        variants=int(ad.get("_variants") or 1),
        variant_ids=list(ad.get("_variant_ids") or [ad_id]),
    )


# ─────────────────────────────────────────────────────────────────
# 같은 소재 알아보기 (노션에 이미 기록된 소재 제외용)
# ─────────────────────────────────────────────────────────────────

def _decode_efg(value: str) -> dict:
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            raw = decoder(value + "=" * (-len(value) % 4))
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, binascii.Error):
            continue
    return {}


def video_asset_id(ad: dict) -> str:
    """영상 주소의 efg 값(base64 JSON)에 들어 있는 xpv_asset_id. 같은 영상을 여러 광고·페이지가 쓰면 같은 값입니다."""
    snap = _snapshot(ad)
    sources = [snap] + [v for v in (snap.get("videos") or []) if isinstance(v, dict)]
    sources += [c for c in (snap.get("cards") or []) if isinstance(c, dict)]
    sources += [v for v in (snap.get("extra_videos") or []) if isinstance(v, dict)]
    for src in sources:
        for key in ("video_hd_url", "video_sd_url"):
            url = src.get(key)
            if not url or not isinstance(url, str):
                continue
            try:
                efg = parse_qs(urlparse(url).query).get("efg", [""])[0]
            except ValueError:
                continue
            asset = _decode_efg(efg).get("xpv_asset_id") if efg else None
            if asset:
                return str(asset)
    return ""


def creative_fingerprint(raw_body: str) -> str:
    """광고 문구 첫 문장을 글자·숫자만 남겨 소문자로. 너무 짧으면(8자 미만) 쓰지 않습니다."""
    hook = _hook_line(raw_body or "")
    fp = _norm_name(hook)[:60]
    return fp if len(fp) >= 8 else ""


@dataclass
class RecordedKeys:
    """노션 소재 표에 이미 기록된 소재의 식별값"""
    ad_ids: set = field(default_factory=set)
    collation_ids: set = field(default_factory=set)
    asset_ids: set = field(default_factory=set)
    fingerprints: set = field(default_factory=set)   # (브랜드 키, 소재 지문)
    loaded: bool = False
    error: str = ""

    def match(self, ad: "AdSummary", brand_key: str) -> str:
        """이미 기록된 소재면 이유를, 아니면 ""를 돌려줍니다."""
        if ad.ad_id and ad.ad_id in self.ad_ids:
            return "광고 ID 같음"
        if ad.collation_id and ad.collation_id in self.collation_ids:
            return "묶음 ID 같음"
        if ad.video_asset_id and ad.video_asset_id in self.asset_ids:
            return "같은 영상"
        if ad.fingerprint and brand_key and (brand_key, ad.fingerprint) in self.fingerprints:
            return "같은 브랜드·같은 첫 문장"
        return ""

    def add(self, ad: "AdSummary", brand_key: str) -> None:
        if ad.ad_id:
            self.ad_ids.add(ad.ad_id)
        if ad.collation_id:
            self.collation_ids.add(ad.collation_id)
        if ad.video_asset_id:
            self.asset_ids.add(ad.video_asset_id)
        if ad.fingerprint and brand_key:
            self.fingerprints.add((brand_key, ad.fingerprint))


def mark_recorded(report: "AGradeReport", keys: RecordedKeys) -> int:
    """광고마다 노션 기록 여부를 표시합니다. 판정·순위는 바꾸지 않습니다. 새로 표시된 광고 수를 돌려줍니다."""
    count = 0
    for brand in report.brands:
        for ad in brand.ads:
            ad.recorded = keys.match(ad, brand.key)
            count += bool(ad.recorded)
    report.recorded_checked = keys.loaded
    report.recorded_error = keys.error
    return count


def merge_collations(ads: list) -> list:
    """같은 묶음 ID(한 소재의 변형 광고)는 가장 오래 게재된 광고 하나로 합치고 변형 수를 _variants에 남깁니다."""
    groups: dict = {}
    order = []
    for ad in ads:
        cid = str(ad.get("collation_id") or "") or f"ad:{ad.get('ad_archive_id')}"
        if cid not in groups:
            groups[cid] = []
            order.append(cid)
        groups[cid].append(ad)
    merged = []
    for cid in order:
        members = groups[cid]
        keep = min(members, key=lambda a: ad_start_date(a) or date.max)
        keep["_variants"] = len(members)
        keep["_variant_ids"] = [str(a.get("ad_archive_id") or "") for a in members]
        merged.append(keep)
    return merged


# ─────────────────────────────────────────────────────────────────
# 페이지 이름 분류 (아랍어 · 외국어 · 위장 · 숨은 · 공식)
# ─────────────────────────────────────────────────────────────────

_SCRIPT_RANGES = [
    ("아랍 문자", ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))),
    ("히브리 문자", ((0x0590, 0x05FF),)),
    ("태국 문자", ((0x0E00, 0x0E7F),)),
    ("라오 문자", ((0x0E80, 0x0EFF),)),
    ("데바나가리 문자", ((0x0900, 0x097F),)),
    ("벵골 문자", ((0x0980, 0x09FF),)),
    ("구르무키 문자", ((0x0A00, 0x0A7F),)),
    ("구자라트 문자", ((0x0A80, 0x0AFF),)),
    ("인도계 문자", ((0x0B00, 0x0DFF),)),
    ("미얀마 문자", ((0x1000, 0x109F),)),
    ("조지아 문자", ((0x10A0, 0x10FF),)),
    ("에티오피아 문자", ((0x1200, 0x139F),)),
    ("크메르 문자", ((0x1780, 0x17FF),)),
    ("키릴 문자", ((0x0400, 0x052F),)),
    ("그리스 문자", ((0x0370, 0x03FF), (0x1F00, 0x1FFF))),
    ("아르메니아 문자", ((0x0530, 0x058F),)),
    ("일본 가나", ((0x3040, 0x30FF), (0x31F0, 0x31FF), (0xFF66, 0xFF9F))),
    ("한자", ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF))),
    ("특수 서체", ((0x1D400, 0x1D7FF), (0x2460, 0x24FF), (0x1F130, 0x1F189), (0x1D00, 0x1DBF),
                (0x02B0, 0x02FF), (0xFF21, 0xFF3A), (0xFF41, 0xFF5A))),
    ("확장 라틴", ((0x0100, 0x024F), (0x1E00, 0x1EFF))),
    ("한글 자모", ((0x1100, 0x11FF), (0x3131, 0x318E), (0xA960, 0xA97F), (0xD7B0, 0xD7FF))),
    ("한글", ((0xAC00, 0xD7A3),)),
]
_NATIVE_SCRIPTS = {"한글", "한글 자모", "라틴"}


def _char_script(ch: str) -> str:
    if ("a" <= ch <= "z") or ("A" <= ch <= "Z"):
        return "라틴"
    code = ord(ch)
    if 0xC0 <= code <= 0xFF and code not in (0xD7, 0xF7):
        return "라틴"  # é, ü 같은 서유럽 문자는 일반 영문 표기로 봄
    for name, ranges in _SCRIPT_RANGES:
        if any(lo <= code <= hi for lo, hi in ranges):
            return name
    return ""


def detect_scripts(name: str) -> list:
    scripts = []
    for ch in str(name or ""):
        script = _char_script(ch)
        if script and script not in scripts:
            scripts.append(script)
    return scripts


def _name_has_brand(name: str, brand_terms: list) -> bool:
    normalized = _norm_name(name)
    return any(len(_norm_name(t)) >= 2 and _norm_name(t) in normalized for t in brand_terms)


def classify_page_name(name: str, brand_terms: list) -> tuple:
    """(계정 유형, 섞인 외국 문자 목록, 판단 이유)"""
    scripts = detect_scripts(name)
    foreign = [s for s in scripts if s not in _NATIVE_SCRIPTS]
    has_korean = "한글" in scripts or "한글 자모" in scripts
    if "아랍 문자" in scripts:
        return ACCOUNT_ARABIC, foreign, "아랍 문자 이름"
    if foreign:
        if has_korean or "라틴" in scripts:
            return ACCOUNT_DISGUISED, foreign, f"한글·영문에 섞은 문자: {', '.join(foreign)}"
        if len(foreign) >= 2:
            # 실제 외국어 이름은 한 문자 체계만 씀. 여러 체계를 섞으면 영문처럼 보이게 만든 위장 이름
            return ACCOUNT_DISGUISED, foreign, f"여러 외국 문자를 섞은 이름: {', '.join(foreign)}"
        return ACCOUNT_FOREIGN, foreign, f"외국 문자 이름: {', '.join(foreign)}"
    if "한글 자모" in scripts and "한글" in scripts:
        return ACCOUNT_DISGUISED, [], "자음·모음을 떼어 섞은 이름"
    if re.search(r"[가-힣][lI|][가-힣]", str(name or "")):
        return ACCOUNT_DISGUISED, [], "한글 사이에 영문 l·I를 끼워 넣은 이름"
    if _name_has_brand(name, brand_terms):
        return ACCOUNT_OFFICIAL, [], "이름에 브랜드명 있음"
    return ACCOUNT_HIDDEN, [], "이름에 브랜드명 없음"


# ─────────────────────────────────────────────────────────────────
# 브랜드명 · 검색량 확인 키워드
# ─────────────────────────────────────────────────────────────────

_BRAND_SUFFIX_RE = re.compile(
    r"\s*(공식\s*(온라인\s*)?(몰|스토어|쇼핑몰|사이트|홈페이지|판매처)?|온라인\s*(몰|스토어)|쇼핑몰"
    r"|official\s*(store|mall|site|shop)?|online\s*(store|shop|mall))\s*$",
    re.I,
)
_TITLE_NOISE_RE = re.compile(
    r"비밀\s*링크|이벤트|특가|한정\s*수량|완판|증정|할인|무료\s*배송|리뉴얼|기념|단독|최저가|공식|정품|신제품"
    r"|런칭|출시|오픈|세일|쿠폰|\d+\s*\+\s*\d+",
    re.I,
)
_SIZE_RE = re.compile(r"\d+(\.\d+)?\s*(ml|g|kg|mg|정|포|개입|개|캡슐|박스|box|일분|주분|개월분|개월|병|매|ea)\b", re.I)
_GENERIC_NAME_WORDS = {
    "공식", "공식몰", "스토어", "store", "shop", "mall", "official", "kr", "korea", "코리아", "뷰티", "beauty",
    "코스메틱", "cosmetic", "cosmetics", "건강", "헬스", "health", "샵", "몰", "랩", "lab", "꿀팁", "정보",
    "연구소", "클리닉", "매거진", "추천", "리뷰", "후기", "모음", "저장소", "노트", "비밀", "피부", "일상",
    "생활", "라이프", "life", "daily", "care", "케어",
}
_GENERIC_DOMAIN_LABELS = {
    "shop", "store", "mall", "official", "brand", "health", "beauty", "app", "link", "event", "promo",
    "landing", "page", "site", "home", "buy", "www", "the", "pro", "top", "one", "all", "get", "kor", "diet",
}
# 페이지 이름에서 떼어 낸 영문 단어 중 브랜드명으로 쓰면 안 되는 흔한 단어
_GENERIC_ENGLISH = {
    "for", "the", "and", "with", "your", "best", "good", "love", "happy", "daily", "care", "life", "info",
    "tips", "news", "blog", "story", "world", "plus", "pure", "real", "true", "well", "wellness", "healthy",
    "diet", "club", "korea", "official", "beauty", "health", "shop", "store", "mall", "team", "home",
}


def clean_brand_name(raw: str) -> str:
    """'비피젠 | 균형 잡힌…' → '비피젠', '리포데이 공식몰' → '리포데이'"""
    if not raw:
        return ""
    text = html.unescape(str(raw))
    text = re.split(r"\s+[|·\-–—:]\s+|[|｜]", text)[0]
    text = re.sub(r"[\[\(【<].*?[\]\)】>]", " ", text)
    text = re.sub(r"[^\w\s&.+']|_", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .'")
    text = _BRAND_SUFFIX_RE.sub("", text).strip(" .'")
    return text if 2 <= len(text) <= 20 else ""


_HINT_STOPWORDS = {
    "new", "best", "hot", "sale", "event", "gift", "set", "special", "limited", "edition", "renewal", "premium",
    "네이버", "쿠팡", "카카오", "신상", "인기", "추천", "대용량", "리필", "기획", "세트", "특별", "한정", "무료",
    "정가", "본품", "선물", "구성", "단품", "최신", "프리미엄", "순한", "약산성", "저자극", "국내", "해외",
    "추석", "설날", "명절", "추석한정", "최대", "역대급", "파격", "오늘만", "마감", "품절", "재입고", "선착순",
    "팔로워", "케어", "어린이", "아이가",
}


def product_hint(og_title: str, title: str, brand: str, stop_terms: Optional[list] = None) -> str:
    """랜딩 제목에서 제품명 후보: '[증정 이벤트] 파이토업 플러스 (30포)' → '파이토업'"""
    stops = {_norm_name(t) for t in (stop_terms or [])} | _HINT_STOPWORDS
    for raw in (og_title, title):
        if not raw or "에러" in raw or "error" in raw.lower():
            continue
        text = re.sub(r"[\[\(【<].*?[\]\)】>]", " ", html.unescape(raw))
        parts = [p.strip() for p in re.split(r"\s+[|\-–—:]\s+|[|｜]|\s+-\s*$", text) if p.strip()]
        parts = [p for p in parts if _norm_name(p) and _norm_name(p) != _norm_name(brand)]
        if not parts:
            continue
        text = _SIZE_RE.sub(" ", _TITLE_NOISE_RE.sub(" ", parts[0]))
        text = re.sub(r"[^\w\s]|_", " ", text)
        tokens = [t for t in text.split()
                  if len(t) >= 2 and not re.search(r"\d", t)
                  and _norm_name(t) not in stops and _norm_name(t) != _norm_name(brand)]
        if tokens:
            return tokens[0]
    return ""


def _is_generic_token(token: str, relevance_terms: list, strict: bool = False) -> bool:
    """
    검색량 판정에 쓰면 안 되는 일반 단어인지.
    strict=True(페이지 이름을 쪼갠 단어)면 한글 3자·영문 4자 미만도 버립니다 ('아이', 'hi' 같은 일반어 방지).
    """
    normalized = _norm_name(token)
    if len(normalized) < 2 or normalized in _GENERIC_NAME_WORDS or normalized in _GENERIC_ENGLISH:
        return True
    if strict:
        min_len = 4 if re.fullmatch(r"[a-z0-9]+", normalized) else 3
        if len(normalized) < min_len:
            return True
    related = [_norm_name(t) for t in relevance_terms if len(_norm_name(t)) >= 2]
    return any(r in normalized for r in related)


def brand_keyword_candidates(site_name: str, page_names: list, key: str, landing_texts: list,
                             relevance_terms: list) -> list:
    """
    ① 검색량을 확인할 브랜드 키워드 후보.
    - 자사몰의 사이트 이름(og:site_name)을 가장 먼저 씁니다.
    - 영문 도메인 이름(noily.kr → noily)을 더합니다.
    - 페이지 이름은 위장 계정이 아니고 자사몰 랜딩 글자에도 나오는 단어만 씁니다.
      ('여드름 꿀팁모음' 같은 일반어 페이지 이름이 검색량 판정을 오염시키지 않도록)
    """
    out = []

    def add(word: str):
        word = re.sub(r"\s+", " ", word or "").strip()
        normalized = _norm_name(word)
        if 2 <= len(normalized) <= 20 and normalized not in {_norm_name(c) for c in out}:
            out.append(word)

    if site_name:
        add(site_name)
    label = _key_label(key)
    if label and re.fullmatch(r"[a-z][a-z0-9]{2,}", label) and label not in _GENERIC_DOMAIN_LABELS:
        add(label)
    anchor = _norm_name(" ".join(t for t in landing_texts if t))
    for name in page_names:
        account_type, _, _ = classify_page_name(name, [])
        if account_type in (ACCOUNT_ARABIC, ACCOUNT_FOREIGN, ACCOUNT_DISGUISED):
            continue
        cleaned = clean_brand_name(name)
        if not cleaned:
            continue
        if anchor:
            tokens = [(cleaned, False)] + [(t, True) for t in cleaned.split() if t != cleaned]
            for token, strict in tokens:
                if not _is_generic_token(token, relevance_terms, strict) and _norm_name(token) in anchor:
                    add(token)
        elif not _is_generic_token(cleaned, relevance_terms):
            add(cleaned)
    return out[:5]


# ─────────────────────────────────────────────────────────────────
# ① 검색량 급상승 이력 (아이템스카우트 방식)
# ─────────────────────────────────────────────────────────────────

class DataLabTrends:
    """데이터랩 일간 추이 조회. 너무 빠르게 부르면 응답을 끊으므로 간격을 두고, 실패하면 새 세션으로 한 번 재시도합니다."""

    def __init__(self, min_interval: float = 1.5, retry_wait: float = 4.0):
        self.min_interval = min_interval
        self.retry_wait = retry_wait
        self._session = None
        self._last = 0.0

    def daily(self, keyword: str, start: date, end: date) -> list:
        for attempt in range(2):
            gap = time.monotonic() - self._last
            if gap < self.min_interval:
                time.sleep(self.min_interval - gap)
            try:
                if self._session is None:
                    self._session = _datalab_session()
                points = get_daily_search_trend(keyword, start, end, session=self._session)
            except Exception:
                points = []
            self._last = time.monotonic()
            if points:
                return points
            if attempt == 0:
                time.sleep(self.retry_wait)
                self._session = None
        return []


def _rise_rank(level: str) -> int:
    return RISE_LEVELS.index(level) if level in RISE_LEVELS else len(RISE_LEVELS)


def check_search_spike(keywords: list, naver_creds: tuple, min_volume: int = MIN_PEAK_VOLUME,
                       lookback_days: int = LOOKBACK_DAYS, today: Optional[date] = None,
                       datalab: Optional[DataLabTrends] = None, min_jump: int = SPIKE_MIN_JUMP,
                       min_ratio: float = SPIKE_MIN_RATIO) -> VolumeCheck:
    """
    ① 판정과 60일 급상승 계산.
    - 키워드별 최근 30일 검색수(검색광고 API)를 받고, 검색수 상위 키워드 최대 2개는 데이터랩 일간 추이로
      최근 1년의 60일 롤링 검색량과 급상승 추이를 만듭니다.
    - ① 통과: 동일 키워드의 최근 1년 30일 검색량 ≥ min_volume 및 60일 증가폭 ≥ min_jump.
      추이가 없으면 급상승 이력을 확인할 수 없어 판정을 보류합니다.
    - 급상승: 각 60일 구간을 직전 60일과 비교해 🚀/📈/➖ 중 가장 좋은 구간 (순위·표시용)
    - 대표 키워드: ① 통과 키워드 중 가장 가파르게 오른 키워드 (없으면 최고값이 가장 큰 키워드)
    """
    keywords = [k for k in dict.fromkeys(str(k).strip() for k in (keywords or [])) if k]
    if not keywords:
        return VolumeCheck(passed=None, search_window_days=SEARCH_WINDOW_DAYS, note="검색량을 확인할 키워드가 없습니다")
    customer_id, access_license, secret_key = (naver_creds or ("", "", ""))[:3]
    if not (customer_id and access_license and secret_key):
        return VolumeCheck(passed=None, search_window_days=SEARCH_WINDOW_DAYS, note="네이버 검색광고 API 키가 없어 확인하지 못했습니다")

    today = today or date.today()
    volumes = get_naver_search_volumes(keywords, customer_id, access_license, secret_key)
    if all(volumes.get(k, {}).get("error") for k in keywords):
        return VolumeCheck(passed=None, search_window_days=SEARCH_WINDOW_DAYS, note="네이버 검색광고 API 호출에 실패했습니다")

    end = today - timedelta(days=1)
    since = today - timedelta(days=lookback_days)
    fetch_start = since - timedelta(days=TREND_EXTRA_DAYS)
    month_start = since.replace(day=1)
    ranked = sorted(keywords, key=lambda k: volumes.get(k, {}).get("total", 0), reverse=True)
    datalab = datalab or DataLabTrends()
    trend_budget = MAX_TREND_KEYWORDS
    checked, candidates = [], []

    for kw in ranked:
        info = volumes.get(kw, {})
        recent = int(info.get("total", 0))
        entry = {"keyword": kw, "recent_30d": recent, "peak_month": "", "peak_volume": 0,
                 "rise_level": "", "rise_jump": 0, "note": ""}
        rise, windows, grade_windows, months = None, [], [], []
        if info.get("error"):
            entry["note"] = "검색수 조회 실패"
        elif recent <= 0:
            entry["note"] = "검색수 데이터 없음"
        elif trend_budget > 0:
            trend_budget -= 1
            daily = datalab.daily(kw, fetch_start, end)
            windows = rolling_30d_volumes(daily, recent, start=fetch_start, end=end, window=RISE_WINDOW_DAYS)
            grade_windows = [w for w in rolling_30d_volumes(daily, recent, start=fetch_start, end=end,
                                                          window=SEARCH_WINDOW_DAYS) if w["end"] >= since]
            if windows:
                rise = find_steepest_rise(windows, min_jump=min_jump, min_ratio=min_ratio, since=since,
                                          window=RISE_WINDOW_DAYS)
                months = estimate_monthly_volumes(daily, recent, start=month_start, end=end)
            else:
                entry["note"] = "데이터랩 추이 없음 (30일 실측 검색량만 확인; 60일 증가폭 확인 불가)"
        else:
            entry["note"] = "추이 확인 생략 (30일 실측 검색량만 확인; 60일 증가폭 확인 불가)"

        if info.get("error"):
            checked.append(entry)
            continue
        if grade_windows:
            peak_window = max(grade_windows, key=lambda w: (w["volume"], w["end"]))
            peak = int(peak_window["volume"])
            label = "최근 30일" if peak_window["end"] >= end else f"~{peak_window['end'].isoformat()}"
        else:
            peak, label = recent, "최근 30일 실측"
        entry.update(peak_month=label, peak_volume=peak)
        if rise and rise.get("end"):
            entry.update(rise_level=rise["level"], rise_jump=int(rise["jump"]))
        checked.append(entry)
        if peak > 0:
            candidates.append({"keyword": kw, "peak": peak, "label": label, "recent": recent, "rise": rise,
                               "windows": windows, "grade_windows": grade_windows, "months": months, "info": info})

    if not candidates:
        return VolumeCheck(passed=None, checked=checked, search_window_days=SEARCH_WINDOW_DAYS,
                           note="확인한 키워드의 60일 검색량을 산출할 수 없습니다")

    passing = [c for c in candidates if c["rise"] and c["rise"].get("end")
               and c["peak"] >= min_volume and c["rise"]["jump"] >= min_jump]
    incomplete = any(not c["grade_windows"] for c in candidates) or any(volumes.get(k, {}).get("error") for k in keywords)
    if passing:
        def steepness(c):
            rise = c["rise"] or {}
            return (_rise_rank(rise.get("level", "") if rise.get("end") else ""), -int(rise.get("jump", 0)), -c["peak"])
        best = min(passing, key=steepness)
    else:
        best = max(candidates, key=lambda c: c["peak"])

    rise = best["rise"] or {}
    has_rise = bool(rise.get("end"))
    return VolumeCheck(
        passed=True if passing else (None if incomplete else False),
        search_window_days=SEARCH_WINDOW_DAYS,
        rise_window_days=RISE_WINDOW_DAYS,
        peak_is_lower_bound=False,
        grade_windows=[{"end": w["end"].isoformat(), "volume": w["volume"]} for w in best["grade_windows"]],
        note="일부 키워드의 60일 검색량 확인 불가" if not passing and incomplete else "",
        keyword=best["keyword"],
        peak_month=best["label"],
        peak_volume=int(best["peak"]),
        recent_30d=best["recent"],
        recent_pc=int(best["info"].get("pc", 0)),
        recent_mobile=int(best["info"].get("mobile", 0)),
        months=best["months"],
        windows=[{"end": w["end"].isoformat(), "volume": w["volume"]} for w in best["windows"]
                 if w["end"] >= since],
        checked=checked,
        rise_level=rise.get("level", "") if has_rise else "",
        rise_start=rise["start"].isoformat() if has_rise else "",
        rise_end=rise["end"].isoformat() if has_rise else "",
        rise_volume=int(rise.get("volume", 0)) if has_rise else 0,
        rise_prev=int(rise.get("prev_volume", 0)) if has_rise else 0,
        rise_jump=int(rise.get("jump", 0)) if has_rise else 0,
        rise_ratio=rise.get("ratio") if has_rise else None,
        rise_baseline=int(rise.get("baseline", 0)) if has_rise else 0,
    )


def rise_summary(volume: Optional[VolumeCheck]) -> str:
    """'🚀 급상승 · 3,100 → 10,200 (+7,100, 3.3배) · 6/3~7/2 · 평소 2,900'"""
    if volume is None or not getattr(volume, "rise_end", ""):
        return "추이 없음"
    r_days = getattr(volume, "rise_window_days", 30)
    level = getattr(volume, "rise_level", "")
    return f"{level} · {r_days}일 기준 · {format_rise(volume.rise)}"


def audience_keyword(brand: BrandCandidate) -> str:
    """성별·연령을 볼 키워드: ① 판정 근거 키워드, 없으면 첫 번째 확인 키워드."""
    if brand.volume and brand.volume.keyword:
        return brand.volume.keyword
    return brand.keywords[0] if brand.keywords else ""


def fetch_brand_audience(brand: BrandCandidate) -> None:
    """브랜드 키워드의 성별·연령 비중(네이버 쇼핑인사이트)을 brand.audience에 채웁니다."""
    keyword = audience_keyword(brand)
    if not keyword:
        brand.audience = {"ok": False, "keyword": "", "error": "성별·연령을 볼 키워드가 없습니다"}
        return
    try:
        brand.audience = get_shopping_audience(keyword)
    except Exception as exc:
        brand.audience = {"ok": False, "keyword": keyword, "error": f"조회 실패: {exc}"}


def volume_summary(volume: Optional[VolumeCheck]) -> str:
    """검색량 판정에 사용한 기간과 최고값을 표시합니다."""
    if volume is None:
        return "미확인"
    if volume.passed is None:
        return f"확인 불가 ({volume.note})" if volume.note else "확인 불가"
    if not volume.keyword:
        return volume.note or "검색수 없음"
    when = volume.peak_month or f"최근 {getattr(volume, 'search_window_days', 30)}일"
    label = f"{getattr(volume, 'search_window_days', 30)}일 검색량 최소" if getattr(volume, 'peak_is_lower_bound', False) else f"최고 {getattr(volume, 'search_window_days', 30)}일"
    return f"{label} {volume.peak_volume:,}건 ({when}) · {volume.keyword}"


# ─────────────────────────────────────────────────────────────────
# 판정
# ─────────────────────────────────────────────────────────────────

def grade_brand(brand: BrandCandidate, settings: ScanSettings) -> None:
    volume = brand.volume
    c1 = volume.passed if volume else None
    if volume and (getattr(volume, 'search_window_days', 30) != SEARCH_WINDOW_DAYS
                   or getattr(volume, 'rise_window_days', 30) != RISE_WINDOW_DAYS):
        c1 = None
    elif volume and c1 is not None:
        c1 = bool(c1 and volume.rise_end and volume.peak_volume >= settings.min_peak_volume
                  and volume.rise_jump >= settings.spike_min_jump)
    c2 = any(ad.running_days >= settings.min_running_days for ad in brand.ads)
    c3 = bool(brand.relevance_terms)
    reasons = []
    if c1 is None:
        reasons.append(f"① 검색량 확인 불가 — {volume.note if volume and volume.note else '확인 전'}")
    elif not c1:
        if volume.keyword:
            reasons.append(
                f"① 최근 1년 30일 검색량 {settings.min_peak_volume:,}건 이상 및 "
                f"직전 60일 대비 증가폭 {settings.spike_min_jump:,}건 이상인 이력 없음 ('{volume.keyword}')"
            )
        else:
            reasons.append(f"① {volume.note or '검색수 없음'}")
    if not c2:
        reasons.append(f"② {settings.min_running_days}일 이상 게재 중인 광고 없음")
    if not c3:
        reasons.append("③ 제품 연관 키워드 없음")
    brand.criteria = {"search_spike": c1, "long_running": c2, "relevant": c3}
    brand.is_a_grade = bool(c1) and c2 and c3
    brand.reasons = reasons


def sort_brands(brands: list) -> list:
    """A급 → 급상승 등급(🚀 > 📈 > ➖ > 추이 없음) → 60일 증가폭 → 최고 검색량 → 최장 게재일"""
    def key(b):
        v = b.volume
        has_current_rise = bool(v and getattr(v, 'rise_window_days', 30) == RISE_WINDOW_DAYS)
        return (
            not b.is_a_grade,
            _rise_rank(v.rise_level if has_current_rise else ""),
            -(v.rise_jump if has_current_rise else 0),
            -(v.peak_volume if v else 0),
            -max((a.running_days for a in b.ads), default=0),
        )
    return sorted(brands, key=key)


# ─────────────────────────────────────────────────────────────────
# 연결 계정 추적
# ─────────────────────────────────────────────────────────────────

def distinctive_phrases(ads: list, limit: int = 2) -> list:
    phrases = []
    for ad in sorted(ads, key=lambda a: -a.running_days):
        if ad.hook and _compact(ad.hook) not in {_compact(p) for p in phrases}:
            phrases.append(ad.hook)
        if len(phrases) >= limit:
            break
    return phrases


def _brand_terms(brand: BrandCandidate) -> list:
    """
    '공식 계정' 판단에 쓰는 브랜드명: 브랜드명 · 자사몰 이름 · 도메인 이름 · ① 대표 키워드.
    페이지 이름에서 뽑은 키워드 후보는 넣지 않습니다 (숨은 계정 이름이 브랜드명으로 오인되지 않도록).
    """
    representative = brand.volume.keyword if brand.volume and brand.volume.keyword else \
        (brand.keywords[0] if brand.keywords else "")
    terms = [brand.name, brand.site_name, _key_label(brand.key), representative]
    return [t for t in dict.fromkeys(terms) if t and len(_norm_name(t)) >= 2]


def ad_account_type(brand: BrandCandidate, ad: AdSummary) -> str:
    """광고를 올린 페이지의 계정 유형. 연결 계정 추적 결과가 있으면 그것을, 없으면 페이지 이름으로 판단합니다."""
    for account in brand.accounts or []:
        if account.page_id and account.page_id == ad.page_id:
            return account.account_type
    return classify_page_name(ad.page_name, _brand_terms(brand))[0]


def brand_mall_url(brand: BrandCandidate) -> str:
    """노션 '자사몰' 칸에 넣을 주소"""
    key = brand.key or ""
    if not key or key.startswith("page:"):
        return brand.landing_url or ""
    host = key.split("/")[0]
    if "/p/" in key:   # 쿠팡·올리브영 같은 상품 키는 실제 랜딩 주소를 씁니다
        return brand.landing_url or f"https://{host}"
    return f"https://{key}"


def _tracking_queries(brand: BrandCandidate) -> list:
    """(검색어, 검색 방식, 페이지 수, 설명)"""
    queries, seen = [], set()

    def add(query: str, search_type: str, pages: int, label: str):
        query = (query or "").strip()
        if len(query) < 2 or (query.lower(), search_type) in seen:
            return
        seen.add((query.lower(), search_type))
        queries.append((query, search_type, pages, label))

    if is_own_site_key(brand.key):
        # 숨은·외국어 계정도 광고 표시 주소(caption)에는 자사몰 도메인이 찍혀서 도메인 검색으로 잡힘
        add(brand.key, "keyword_unordered", 4, f"도메인 '{brand.key}'")
        for ad in brand.ads:
            caption_host = _host(_caption_url(ad.caption)) if ad.caption else ""
            if caption_host and caption_host != brand.key and caption_host.endswith(brand.key):
                add(caption_host, "keyword_unordered", 3, f"도메인 '{caption_host}'")
                break
    for kw in brand.keywords[:2]:
        add(kw, "keyword_unordered", 2, f"브랜드명 '{kw}'")
    if brand.product_hint:
        add(brand.product_hint, "keyword_unordered", 1, f"제품명 '{brand.product_hint}'")
    for phrase in distinctive_phrases(brand.ads):
        add(phrase, "keyword_exact_phrase", 1, f"같은 문구 '{_shorten(phrase)}'")
    return queries


def _account_label(account_type: str, name: str) -> str:
    return f"{account_type} '{_shorten(name)}'"


def _sort_accounts(accounts: list) -> list:
    return sorted(accounts, key=lambda a: (a.confidence != CONFIRMED, ACCOUNT_ORDER.index(a.account_type),
                                           -a.brand_ads, -a.max_running_days))


def _expansion_queries(candidates: dict, brand_terms: list) -> list:
    """
    같은 자사몰로 광고하는 게 확인된 연결 계정의 이름과 그 계정 광고 문구로 다시 검색할 목록.
    이름 검색을 먼저, 광고가 많은 계정부터. 한 계정은 한 번만 넓혀 봅니다.
    """
    pending = []
    for cand in candidates.values():
        if cand["expanded"] or not cand["landing"] or not cand["verified"]:
            continue
        cand["expanded"] = True
        account_type = classify_page_name(cand["name"], brand_terms)[0]
        pending.append((cand, account_type))
    pending.sort(key=lambda item: -len(item[0]["ads"]))
    names, phrases = [], []
    for cand, account_type in pending:
        who = _account_label(account_type, cand["name"])
        if len(_norm_name(cand["name"])) >= 2:
            names.append((cand["name"], "keyword_unordered", 2, f"{who} 이름"))
        for phrase in distinctive_phrases(list(cand["ads"].values())):
            phrases.append((phrase, "keyword_exact_phrase", 1, f"{who} 광고 문구 '{_shorten(phrase)}'"))
    return names + phrases


def _eligible_ad(ad: dict, settings: ScanSettings, today: date) -> bool:
    """최초 검색과 계정 추적에서 동일한 기간·제품 연관성 조건을 적용합니다."""
    text = ad_text(ad)
    if ad_running_days(ad, today) < settings.min_running_days or match_terms(text, settings.exclude_terms):
        return False
    hits = match_terms(text, settings.relevance_terms)
    if not hits:
        return False
    ad["_relevance"] = hits
    return True


def _merge_brand_ad(brand: BrandCandidate, ad: AdSummary) -> None:
    """동일 광고·묶음은 합치고 재추적해도 변형 수가 늘지 않게 합니다."""
    for i, existing in enumerate(brand.ads):
        if existing.ad_id == ad.ad_id or (ad.collation_id and existing.collation_id == ad.collation_id):
            ids = set(existing.variant_ids or [existing.ad_id]) | set(ad.variant_ids or [ad.ad_id])
            keep = ad if ad.running_days > existing.running_days else existing
            keep.variant_ids = sorted(ids)
            keep.variants = max(existing.variants, ad.variants, len(ids))
            keep.relevance = list(dict.fromkeys(existing.relevance + ad.relevance))
            brand.ads[i] = keep
            return
    brand.ads.append(ad)


def track_brand_accounts(client: AdLibraryClient, resolver: LinkResolver, brand: BrandCandidate,
                         settings: ScanSettings, progress: ProgressFn = _no_progress,
                         today: Optional[date] = None) -> list:
    """
    A급 브랜드와 같은 랜딩으로 광고하는 모든 페이지를 찾습니다.
      1) 도메인·브랜드명·제품명·같은 광고 문구로 검색
      2) 랜딩이 같으면 '확정', 문구만 같고 랜딩을 확인할 수 없으면 '유력' (다른 브랜드 랜딩이면 제외)
      3) 찾은 페이지의 게재 중 광고를 직접 열어 이 브랜드 광고 수와 다른 브랜드 광고를 확인
      4) 확정된 연결 계정은 공식 계정을 포함해 이름과 광고 문구로 다시 검색해 또 다른 계정을 찾습니다
         (최대 MAX_TRACK_ROUNDS 단계, 추가 검색 MAX_EXPAND_QUERIES회)
    """
    today = today or date.today()
    target = brand.key
    brand_terms = _brand_terms(brand)
    candidates: dict = {}
    searched: set = set()
    verified = [0]
    brand.tracking_incomplete = False
    brand.tracking_limits = []

    def collection_status(raw, label):
        if getattr(raw, "incomplete", False):
            reason = getattr(raw, "stop_reason", "failed")
            reasons = {"page_limit": "페이지 제한 도달", "failed": "검색 실패", "blocked": "접속 차단",
                       "rate_limit": "요청 한도 초과", "missing_cursor": "다음 페이지 주소 없음",
                       "pagination_stalled": "추가 화면에서 새 광고를 확인하지 못함",
                       "account_name_fallback": "직접 계정 조회가 0개여서 계정명 검색으로 보완 (전체 확인 미완료)",
                       "browser_error": "브라우저 수집 중단"}
            brand.tracking_limits.append(f"{label}: {reasons.get(reason, reason)}")
            brand.tracking_incomplete = True

    def summary_for(ad, keys):
        eligible = _eligible_ad(ad, settings, today)
        summary = summarize_ad(ad, today, resolver, keys)
        if eligible:
            _merge_brand_ad(brand, summary)
        return summary

    def note(page_id: str, page_name: str, evidence: str, landing_match: bool, summary: Optional[AdSummary],
             via: str, depth: int):
        if not page_id:
            return
        cand = candidates.setdefault(page_id, {
            "name": page_name, "evidence": [], "landing": False, "ads": {}, "profile": "", "via": via,
            "depth": depth, "checked": 0, "other": Counter(), "verified": False, "expanded": False,
        })
        if page_name and not cand["name"]:
            cand["name"] = page_name
        if evidence not in cand["evidence"]:
            cand["evidence"].append(evidence)
        cand["landing"] = cand["landing"] or landing_match
        if summary and landing_match:
            cand["ads"][summary.ad_id] = summary

    def run(queries: list, depth: int, base: float, span: float):
        for i, (query, search_type, pages, label) in enumerate(queries):
            key = (_compact(query), search_type)
            if key in searched:
                continue
            searched.add(key)
            progress(base + span * i / max(len(queries), 1), f"🔎 {brand.name}: {label} 검색 중")
            limit = settings.account_pages if label.endswith(" 이름") else settings.pages_per_keyword
            raw = client.search(query, search_type=search_type, active_status="active", max_pages=limit)
            collection_status(raw, label)
            resolver.resolve_many(u for ad in raw for u in ad_link_urls(ad))
            for ad in raw:
                page_id, page_name = ad_page(ad)
                keys = ad_store_keys(ad, resolver)
                if target in keys:
                    note(page_id, page_name, f"랜딩 동일 ({target}) · {label}", True,
                         summary_for(ad, keys), label, depth)
                elif search_type == "keyword_exact_phrase" and not keys and _compact(query) in _compact(_body_text(ad)):
                    note(page_id, page_name, f"광고 문구 동일 · {label} (랜딩 확인 불가)", False, None, label, depth)
                if page_id in candidates and not candidates[page_id]["profile"]:
                    candidates[page_id]["profile"] = str(_snapshot(ad).get("page_profile_uri") or "")

    def verify(base: float, span: float):
        todo = sorted((pid for pid, c in candidates.items() if not c["verified"]),
                      key=lambda pid: (not candidates[pid]["landing"], -len(candidates[pid]["ads"])))
        for i, page_id in enumerate(todo):
            if verified[0] >= MAX_VERIFY_PAGES:
                brand.tracking_incomplete = True
                limit = f"계정 확인 {MAX_VERIFY_PAGES}개 제한 도달"
                if limit not in brand.tracking_limits:
                    brand.tracking_limits.append(limit)
                return
            cand = candidates[page_id]
            progress(base + span * i / max(len(todo), 1), f"🕵️ {brand.name}: '{cand['name']}' 광고 확인 중")
            if hasattr(client, "remember_page"):
                client.remember_page(page_id, cand["name"])
            page_raw = client.page_ads(page_id, active_status="active", max_pages=settings.account_pages)
            collection_status(page_raw, cand["name"])
            resolver.resolve_many(u for ad in page_raw for u in ad_link_urls(ad))
            cand["checked"], cand["verified"] = len(page_raw), True
            verified[0] += 1
            for ad in page_raw:
                keys = ad_store_keys(ad, resolver)
                if target in keys:
                    cand["ads"].setdefault(str(ad.get("ad_archive_id") or ""), summary_for(ad, keys))
                    cand["landing"] = True
                elif keys:
                    cand["other"][keys[0]] += 1
                if not cand["profile"]:
                    cand["profile"] = str(_snapshot(ad).get("page_profile_uri") or "")
                _, fresh_name = ad_page(ad)
                if fresh_name:
                    cand["name"] = fresh_name

    for ad in brand.ads:
        note(ad.page_id, ad.page_name, "A급 스캔에서 같은 랜딩 광고 발견", True, ad, "A급 스캔", 0)

    rounds = MAX_TRACK_ROUNDS + 1
    budget = MAX_EXPAND_QUERIES
    queries, depth = _tracking_queries(brand), 0
    try:
        while True:
            base, span = depth / rounds, 1 / rounds
            run(queries, depth, base, span * 0.5)
            verify(base + span * 0.5, span * 0.5)
            if depth >= MAX_TRACK_ROUNDS or budget <= 0:
                break
            queries = [q for q in _expansion_queries(candidates, brand_terms)
                       if (_compact(q[0]), q[1]) not in searched][:budget]
            if not queries:
                break
            budget -= len(queries)
            depth += 1
            progress(depth / rounds, f"🔁 {brand.name}: 찾은 숨은 계정 {len(queries)}건으로 다시 검색 ({depth}단계)")
    except AdLibraryBlocked as exc:
        brand.tracking_incomplete = True
        brand.tracking_limits.append(f"추적 중단: {exc}")
        brand.tracking_failed = max(brand.tracking_failed, 1)
    brand.ads.sort(key=lambda a: -a.running_days)
    brand.relevance_terms = list(dict.fromkeys(t for a in brand.ads for t in a.relevance))

    accounts = []
    for page_id, cand in candidates.items():
        brand_ads = sorted(cand["ads"].values(), key=lambda a: -a.running_days)
        account_type, scripts, reason = classify_page_name(cand["name"], brand_terms)
        evidence = list(cand["evidence"])
        # 쿠팡·올리브영 상품 링크는 같은 브랜드 제품일 수 있으니, 다른 자사몰·스토어 광고만 센다
        other_stores = sum(n for k, n in cand["other"].items() if "/p/" not in k)
        if other_stores > len(brand_ads):
            evidence.append("다른 브랜드 자사몰 광고가 더 많음 → 대행·바이럴 계정일 수 있음")
        accounts.append(LinkedAccount(
            page_id=page_id,
            page_name=cand["name"],
            account_type=account_type,
            type_reason=reason,
            foreign_scripts=scripts,
            confidence=CONFIRMED if cand["landing"] else LIKELY,
            evidence=evidence,
            brand_ads=len(brand_ads),
            checked_ads=cand["checked"],
            max_running_days=max((a.running_days for a in brand_ads), default=0),
            other_landings=[f"{k} ({n})" for k, n in cand["other"].most_common(3)],
            library_url=page_library_url(page_id, settings.country),
            profile_url=cand["profile"],
            sample_ads=brand_ads[:5],
            found_via=cand["via"],
            depth=cand["depth"],
        ))
    accounts = _sort_accounts(accounts)
    extra = sum(1 for a in accounts if a.depth > 0)
    progress(1.0, f"✅ {brand.name}: 연결 계정 {len(accounts)}개" + (f" (숨은 계정 재검색으로 {extra}개 추가)" if extra else ""))
    return accounts


def _track_brand(brand: BrandCandidate, settings: ScanSettings, progress: ProgressFn = _no_progress,
                client: Optional[AdLibraryClient] = None, resolver: Optional[LinkResolver] = None) -> None:
    """
    한 브랜드의 연결 계정을 추적해 brand.accounts에 채웁니다.
    메타 검색이 일부 실패하면 새 결과만으로 바꾸지 않고 이전에 찾은 계정과 합칩니다 (차단 때문에 계정이 줄어 보이지 않도록).
    """
    try:
        client = client or AdLibraryClient(country=settings.country)
        resolver = resolver or LinkResolver()
        failed_before = len(client.failed_queries)
        brand.tracking_failed = 0
        accounts = track_brand_accounts(client, resolver, brand, settings, progress)
        failed = client.failed_queries[failed_before:]
        if (failed or brand.tracking_incomplete) and brand.accounts:
            merged = {a.page_id: a for a in brand.accounts}
            for account in accounts:
                old = merged.get(account.page_id)
                if old:
                    account.brand_ads = max(old.brand_ads, account.brand_ads)
                    account.checked_ads = max(old.checked_ads, account.checked_ads)
                    account.max_running_days = max(old.max_running_days, account.max_running_days)
                    if old.confidence == CONFIRMED:
                        account.confidence = CONFIRMED
                    account.evidence = list(dict.fromkeys(old.evidence + account.evidence))
                    samples = {a.ad_id: a for a in old.sample_ads}
                    samples.update({a.ad_id: a for a in account.sample_ads})
                    account.sample_ads = sorted(samples.values(), key=lambda a: -a.running_days)[:5]
                merged[account.page_id] = account
            accounts = _sort_accounts(list(merged.values()))
        brand.accounts = accounts
        brand.tracked = True
        brand.tracking_failed = max(brand.tracking_failed, len(failed))
        brand.tracking_incomplete = brand.tracking_incomplete or bool(failed)
        counts = Counter(a.account_type for a in brand.accounts)
        brand.tracking_note = " · ".join(f"{t} {counts[t]}" for t in ACCOUNT_ORDER if counts.get(t))
        if failed:
            brand.tracking_note += f" · ⚠️ 메타 검색 {len(failed)}건 실패 (이전에 찾은 계정 유지)"
        if brand.tracking_limits:
            brand.tracking_note += " · 부분 수집: " + " / ".join(dict.fromkeys(brand.tracking_limits))
    except AdLibraryBlocked as exc:
        brand.tracking_failed = max(getattr(brand, "tracking_failed", 0), 1)
        brand.tracking_incomplete = True
        brand.tracking_note = f"추적 중단: {exc}" + (" (이전에 찾은 계정 유지)" if brand.accounts else "")
        brand.tracked = bool(brand.accounts)


# ─────────────────────────────────────────────────────────────────
# 전체 흐름
# ─────────────────────────────────────────────────────────────────

def track_brand(brand: BrandCandidate, settings: ScanSettings, progress: ProgressFn = _no_progress,
                client=None, resolver=None) -> None:
    if client is not None:
        return _track_brand(brand, settings, progress, client, resolver)
    from meta_browser_client import BrowserAdLibraryClient
    with BrowserAdLibraryClient(country=settings.country) as browser_client:
        return _track_brand(brand, settings, progress, browser_client, resolver)


def _page_names_by_frequency(ads: list) -> list:
    counts = Counter(a.page_name for a in ads if a.page_name)
    return [name for name, _ in counts.most_common()]


def _apply_landing_info(brand: BrandCandidate, info: dict, relevance_terms: list) -> None:
    info = info or {}
    final_key = store_key(info.get("final_url", "")) if info.get("final_url") else ""
    if final_key and final_key != brand.key and not is_own_site_key(final_key):
        info = {}  # 자사몰이 스마트스토어 등으로 넘어가면 그 페이지 제목은 브랜드명이 아님
    brand.site_name = clean_brand_name(info.get("site_name", ""))
    texts = [info.get(k, "") for k in ("site_name", "og_title", "title", "description")]
    brand.landing_title = info.get("og_title") or info.get("title") or ""
    brand.product_hint = product_hint(info.get("og_title", ""), info.get("title", ""), brand.site_name,
                                      stop_terms=relevance_terms)
    page_names = _page_names_by_frequency(brand.ads)
    brand.keywords = brand_keyword_candidates(brand.site_name, page_names, brand.key, texts, relevance_terms)
    if brand.site_name:
        brand.name = brand.site_name
    elif is_own_site_key(brand.key):
        brand.name = brand.key  # 자사몰 이름을 못 읽었으면 도메인이 가장 정확함
    else:
        readable = [n for n in page_names if classify_page_name(n, [])[0] in (ACCOUNT_HIDDEN, ACCOUNT_OFFICIAL)]
        brand.name = (readable[0] if readable else "") or (brand.keywords[0] if brand.keywords else "") or brand.key


def group_brands(ads: list, resolver: LinkResolver, today: date) -> list:
    groups: dict = {}
    for ad in ads:
        keys = ad_store_keys(ad, resolver)
        summary = summarize_ad(ad, today, resolver, keys)
        key = keys[0] if keys else f"page:{summary.page_id or summary.page_name}"
        brand = groups.setdefault(key, BrandCandidate(key=key))
        brand.ads.append(summary)
        for term in summary.relevance:
            if term not in brand.relevance_terms:
                brand.relevance_terms.append(term)
        if not brand.landing_url and summary.landing_url and keys:
            brand.landing_url = summary.landing_url
    for brand in groups.values():
        brand.ads.sort(key=lambda a: -a.running_days)
    return list(groups.values())


def _find_a_grade_ads(settings: ScanSettings, naver_creds: tuple, progress: ProgressFn = _no_progress,
                     client: Optional[AdLibraryClient] = None, resolver: Optional[LinkResolver] = None,
                     save: bool = True) -> AGradeReport:
    """메타 광고 라이브러리를 검색해 A급 소재를 찾고, 설정에 따라 A급 브랜드의 연결 계정까지 추적합니다."""
    today = date.today()
    report = AGradeReport(generated_at=datetime.now().isoformat(timespec="seconds"), settings=asdict(settings))
    keywords = parse_terms(settings.scan_keywords)
    if not keywords:
        report.warnings.append("검색어를 한 개 이상 입력하세요.")
        return report

    try:
        client = client or AdLibraryClient(country=settings.country)
    except AdLibraryBlocked as exc:
        report.scan_incomplete = True
        report.warnings.append(str(exc))
        return report
    resolver = resolver or LinkResolver()

    # ② 60일 이상 게재 중인 광고 수집. 실패한 키워드 때문에 나머지를 건너뛰지 않습니다.
    started_before = today - timedelta(days=settings.min_running_days)
    collected: dict = {}
    query_results = []
    for i, kw in enumerate(keywords):
        try:
            progress(0.40 * i / len(keywords), f"📡 메타 광고 라이브러리 검색: '{kw}' ({i + 1}/{len(keywords)})")
            found = client.search(kw, started_before=started_before, max_pages=settings.pages_per_keyword)
            query_results.append({"keyword": kw, "ads": len(found),
                                  "screens": getattr(found, "pages_collected", None),
                                  "limit": settings.pages_per_keyword,
                                  "stop_reason": getattr(found, "stop_reason", "")})
            if getattr(found, "incomplete", False):
                if found.stop_reason != "page_limit":
                    report.scan_incomplete = True
                reason = {"page_limit": "설정한 수집 화면 수에 도달",
                          "pagination_stalled": "추가 화면에서 새 광고를 확인하지 못함"}.get(found.stop_reason, "검색 중단")
                report.warnings.append(f"'{kw}' 부분 수집: {reason} (수집한 광고는 유지)")
            for ad in found:
                ad_id = str(ad.get("ad_archive_id") or "")
                if ad_id and ad_id not in collected:
                    ad["_search_keyword"] = kw
                    collected[ad_id] = ad
        except AdLibraryBlocked as exc:
            report.scan_incomplete = True
            report.warnings.append(f"'{kw}' 검색 실패: {exc}")
            query_results.append({"keyword": kw, "ads": 0, "limit": settings.pages_per_keyword,
                                  "stop_reason": "failed"})
    raw_ads = list(collected.values())
    report.scanned_ads = len(raw_ads)
    long_ads = [ad for ad in raw_ads if ad_running_days(ad, today) >= settings.min_running_days]
    report.long_running_ads = len(long_ads)

    # ③ 제품 연관성
    relevant = []
    for ad in long_ads:
        text = ad_text(ad)
        if match_terms(text, settings.exclude_terms):
            report.excluded_ads += 1
            continue
        if _eligible_ad(ad, settings, today):
            relevant.append(ad)
    report.relevant_ads = len(relevant)
    relevant = merge_collations(relevant)   # 같은 소재의 변형 광고는 하나로

    # 랜딩 식별 → 브랜드 묶기
    progress(0.42, f"🔗 광고 {len(relevant)}개의 랜딩 주소 확인 중 (단축 주소 해석)")
    resolver.resolve_many(u for ad in relevant for u in ad_link_urls(ad))
    brands = group_brands(relevant, resolver, today)

    progress(0.48, f"🏷️ 브랜드 {len(brands)}곳의 자사몰에서 브랜드명 확인 중")
    infos = resolver.landing_infos({b.key: b.landing_url for b in brands if is_own_site_key(b.key)})
    for brand in brands:
        _apply_landing_info(brand, infos.get(brand.key, {}), settings.relevance_terms)

    # ① 검색량 급상승 이력
    datalab = DataLabTrends()
    for i, brand in enumerate(brands):
        progress(0.52 + 0.18 * i / max(len(brands), 1), f"📊 검색량 확인: {brand.name} ({i + 1}/{len(brands)})")
        brand.volume = check_search_spike(brand.keywords, naver_creds, settings.min_peak_volume,
                                          settings.lookback_days, today=today, datalab=datalab,
                                          min_jump=settings.spike_min_jump, min_ratio=settings.spike_min_ratio)
        grade_brand(brand, settings)
    if brands and all(b.volume and b.volume.passed is None for b in brands):
        report.warnings.append(f"① 검색량을 확인하지 못했습니다: {brands[0].volume.note}")

    # A급 브랜드 성별·연령 비중
    a_grade = [b for b in brands if b.is_a_grade]
    for i, brand in enumerate(a_grade):
        progress(0.70, f"👥 성별·연령 확인: {brand.name} ({i + 1}/{len(a_grade)})")
        fetch_brand_audience(brand)

    # A급 브랜드 연결 계정 추적
    if settings.track_accounts and a_grade:
        for i, brand in enumerate(a_grade):
            base, span = 0.70 + 0.28 * i / len(a_grade), 0.28 / len(a_grade)
            track_brand(brand, settings, lambda f, m, b=base, s=span: progress(b + s * f, m), client, resolver)

    report.brands = sort_brands(brands)
    report.meta_requests = client.request_count
    report.meta_diagnostics = {"source": getattr(client, "collection_mode", "web_graphql"),
                               "keywords": query_results,
                               **(getattr(client, "last_error", {}) or {})}
    if client.failed_queries:
        failed = ", ".join(client.failed_queries[:5]) + (" …" if len(client.failed_queries) > 5 else "")
        report.warnings.append(f"메타 검색 {len(client.failed_queries)}건이 실패했습니다: {failed}")
    if save:
        try:
            report.saved_path = save_report(report)
        except OSError as exc:
            report.warnings.append(f"결과 저장 실패: {exc}")
    progress(1.0, "✅ 완료")
    return report


def find_a_grade_ads(settings: ScanSettings, naver_creds: tuple, progress: ProgressFn = _no_progress,
                     client=None, resolver=None, save: bool = True) -> AGradeReport:
    if client is not None:
        return _find_a_grade_ads(settings, naver_creds, progress, client, resolver, save)
    from meta_browser_client import BrowserAdLibraryClient
    with BrowserAdLibraryClient(country=settings.country) as browser_client:
        return _find_a_grade_ads(settings, naver_creds, progress, browser_client, resolver, save)


def recheck_brand_volume(brand: BrandCandidate, keywords: list, settings: ScanSettings, naver_creds: tuple) -> None:
    """사용자가 고친 키워드로 ① 검색량을 다시 확인하고 등급을 갱신합니다."""
    brand.keywords = parse_terms(keywords)
    brand.volume = check_search_spike(brand.keywords, naver_creds, settings.min_peak_volume, settings.lookback_days,
                                      min_jump=settings.spike_min_jump, min_ratio=settings.spike_min_ratio)
    grade_brand(brand, settings)


def save_report(report: AGradeReport, path: str = "") -> str:
    if not path:
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs", "a_grade")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"a_grade_{datetime.now():%Y%m%d_%H%M%S}.json")
    data = asdict(report)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    return path


def load_report(path: str) -> AGradeReport:
    """저장한 결과를 중첩된 광고·계정·검색량 객체까지 복원합니다."""
    with open(path, encoding="utf-8") as source:
        data = json.load(source)

    def restore(cls, values):
        allowed = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in values.items() if k in allowed})

    report = restore(AGradeReport, data)
    report.brands = []
    for values in data.get("brands", []):
        brand = restore(BrandCandidate, values)
        brand.ads = [restore(AdSummary, ad) for ad in values.get("ads", [])]
        brand.volume = restore(VolumeCheck, values["volume"]) if values.get("volume") else None
        brand.accounts = []
        for account_data in values.get("accounts", []):
            account = restore(LinkedAccount, account_data)
            account.sample_ads = [restore(AdSummary, ad) for ad in account_data.get("sample_ads", [])]
            brand.accounts.append(account)
        report.brands.append(brand)
    report.saved_path = os.path.abspath(path)
    return report
