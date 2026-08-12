"""
AdForge V2 — Stock Scoring 시스템

점수 기준:
  해상도        25점
  세로 비율     25점
  검색어 적합도 20점
  피사체 위치   10점  (크기 비율로 추정)
  영상 길이     10점
  화질          10점
  ────────────────
  총점          100점
"""
from __future__ import annotations
from typing import List
from stock_engine.base import StockVideoResult

# 제외 기준
MIN_DURATION = 2.5   # seconds
MAX_SCORE_DURATION = 20.0  # 너무 길면 감점


def _resolution_score(result: StockVideoResult) -> int:
    """해상도 점수 (0~25)"""
    h = result.height
    if h >= 2160:
        return 25   # 4K
    elif h >= 1080:
        return 18   # 1080p
    elif h >= 720:
        return 10   # 720p
    return 3        # 저해상도


def _ratio_score(result: StockVideoResult) -> int:
    """세로 비율 점수 (0~25)
    9:16 세로 영상 → 만점
    16:9 (크롭 가능, 4K) → 15점
    16:9 (1080p, 크롭) → 10점
    기타 → 0점
    """
    r = result.aspect_ratio
    # 9:16 = 0.5625
    if result.is_vertical and abs(r - 9 / 16) < 0.08:
        return 25
    # 16:9 = 1.777..
    if not result.is_vertical and abs(r - 16 / 9) < 0.08:
        if result.height >= 2160:
            return 15   # 4K 16:9 — 크롭 가능
        elif result.height >= 1080:
            return 10   # 1080p 16:9
        return 5
    return 0


def _duration_score(result: StockVideoResult) -> int:
    """영상 길이 점수 (0~10)"""
    d = result.duration
    if d < MIN_DURATION:
        return 0   # 너무 짧아 사용 불가
    if 4.0 <= d <= 12.0:
        return 10  # 이상적인 길이
    if 3.0 <= d < 4.0:
        return 7
    if 12.0 < d <= 20.0:
        return 6
    return 3   # 너무 길거나 경계값


def _quality_score(result: StockVideoResult) -> int:
    """화질 추정 점수 (0~10): 해상도 + provider 기반 추정"""
    # Pexels/Pixabay는 일반적으로 무압축 원본 제공
    h = result.height
    if h >= 2160:
        return 10
    elif h >= 1080:
        return 7
    elif h >= 720:
        return 4
    return 1


def _keyword_relevance_score(result: StockVideoResult, keywords: List[str]) -> int:
    """검색어 적합도 (0~20) — 태그 매칭으로 추정"""
    if not keywords or not result.tags:
        return 10  # 태그 없으면 중간값
    kw_lower = {k.lower() for k in keywords}
    tag_lower = {t.lower() for t in result.tags}
    matches = len(kw_lower & tag_lower)
    if matches >= 3:
        return 20
    elif matches == 2:
        return 15
    elif matches == 1:
        return 10
    return 5


def _subject_position_score(result: StockVideoResult) -> int:
    """피사체 위치 점수 (0~10)
    실제로는 영상을 분석해야 하지만 현재는 비율로 추정:
    9:16이면 피사체가 중앙일 가능성이 높음
    """
    if result.is_vertical:
        return 10
    # 16:9는 크롭 시 피사체가 잘릴 수 있으므로 부분 점수
    return 5


def score_result(result: StockVideoResult, keywords: List[str]) -> int:
    """총 점수 계산 (0~100)"""
    total = (
        _resolution_score(result)
        + _ratio_score(result)
        + _keyword_relevance_score(result, keywords)
        + _subject_position_score(result)
        + _duration_score(result)
        + _quality_score(result)
    )
    return min(total, 100)


def is_usable(result: StockVideoResult) -> bool:
    """최소 사용 가능 기준"""
    if result.duration < MIN_DURATION:
        return False
    if result.height < 480:
        return False
    # 16:9 1080p 미만이고 세로도 아니면 제외
    if not result.is_vertical and result.height < 1080:
        return False
    return True


def rank_results(
    results: List[StockVideoResult],
    keywords: List[str],
    top_k: int = 5,
) -> List[StockVideoResult]:
    """결과를 Score 순으로 정렬해 상위 k개 반환"""
    usable = [r for r in results if is_usable(r)]
    for r in usable:
        r.score = score_result(r, keywords)
    ranked = sorted(usable, key=lambda r: r.score, reverse=True)
    return ranked[:top_k]
