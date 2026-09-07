"""
AssetMatcher — CreativePlan의 SceneBeat와 미디어 에셋의 8차원 다차원 점수 매칭 엔진

핵심 특징:
1. 8차원 점수 모델 (의미, 행동, 마케팅 역할, 감정, 구도/종횡비, 길이 적합도, 시각 품질, 반복 감점)
2. 하이라이트 구간 지능형 선택 (동일 영상 재사용 시 서로 다른 구간 슬라이싱)
3. 완전 결정론적 점수 산출 및 디버깅용 Breakdown/Reasoning 제공
4. 기존 naver_clip_adforge와의 하위 호환 브릿지 지원
"""

import os
import re
from typing import List, Dict, Tuple, Optional
from models.creative_plan import SceneBeat, CreativePlan
from models.asset import AssetMetadata, MatchResult
from pipeline.asset_indexer import AssetIndexer


# 점수 가중치 (합계 1.00)
WEIGHT_SEMANTIC = 0.30       # visual_intent + script 키워드 매칭
WEIGHT_ACTION = 0.15         # visual_action 매칭
WEIGHT_MARKETING_ROLE = 0.15 # 광고 역할 적합도 (hook/empathy/solution/usp/cta)
WEIGHT_EMOTION = 0.10        # 감정 톤 일치도
WEIGHT_COMPOSITION = 0.10    # 세로 비율(9:16) 및 preferred_shot 일치도
WEIGHT_DURATION = 0.10       # 필요 재생 시간 충족도
WEIGHT_QUALITY = 0.10        # 에셋 기본 품질 점수

# 반복 사용 패널티 (이미 쓰인 횟수당 감점)
REPETITION_PENALTY_PER_USE = 0.35


class AssetMatcher:
    """다차원 점수 기반 에셋 매칭 엔진"""

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or {
            "semantic": WEIGHT_SEMANTIC,
            "action": WEIGHT_ACTION,
            "marketing_role": WEIGHT_MARKETING_ROLE,
            "emotion": WEIGHT_EMOTION,
            "composition": WEIGHT_COMPOSITION,
            "duration": WEIGHT_DURATION,
            "quality": WEIGHT_QUALITY,
        }

    def match(
        self,
        beat: SceneBeat,
        assets: List[AssetMetadata],
        used_counts: Optional[Dict[str, int]] = None,
        needed_duration_sec: float = 3.0,
    ) -> MatchResult:
        """단일 SceneBeat에 대해 후보 에셋들 중 최적의 에셋을 점수화하여 선택한다."""
        if not assets:
            return MatchResult(
                beat_id=beat.id,
                total_score=0.0,
                reasoning="후보 에셋이 비어있음"
            )

        used_counts = used_counts or {}
        scored_candidates = []

        for asset in assets:
            score, breakdown = self._score_asset(beat, asset, used_counts.get(asset.id, 0), needed_duration_sec)
            scored_candidates.append((score, breakdown, asset))

        # 점수 내림차순 정렬
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_breakdown, best_asset = scored_candidates[0]

        # 최적 하이라이트 구간 계산 (재사용 횟수에 따라 오프셋 적용)
        usage_count = used_counts.get(best_asset.id, 0)
        highlight = self._calculate_highlight_range(best_asset, needed_duration_sec, usage_count)

        reasoning = (
            f"선택: '{best_asset.file_name}' (점수: {best_score:.3f}, "
            f"의미:{best_breakdown.get('semantic', 0):.2f}, "
            f"역할:{best_breakdown.get('marketing_role', 0):.2f}, "
            f"반복감점:{best_breakdown.get('repetition_penalty', 0):.2f})"
        )

        return MatchResult(
            beat_id=beat.id,
            asset_id=best_asset.id,
            asset_path=best_asset.file_path,
            total_score=round(best_score, 3),
            breakdown=best_breakdown,
            highlight_range=[round(highlight[0], 2), round(highlight[1], 2)],
            reasoning=reasoning,
        )

    def match_all(
        self,
        creative_plan: CreativePlan,
        assets: List[AssetMetadata],
        default_beat_duration: float = 3.0,
    ) -> List[MatchResult]:
        """CreativePlan의 모든 beat에 대해 순차적으로 에셋을 매칭하고,
        반복 사용 횟수를 누적 추적하여 시각적 다양성을 극대화한다."""
        results = []
        used_counts: Dict[str, int] = {}

        for beat in creative_plan.beats:
            # pacing에 따른 추천 길이 계산
            pacing_durations = {
                "very_fast": 1.5,
                "fast": 2.2,
                "medium": 3.2,
                "slow": 4.5,
            }
            needed_dur = pacing_durations.get(beat.pacing, default_beat_duration)

            match_res = self.match(beat, assets, used_counts, needed_duration_sec=needed_dur)
            results.append(match_res)

            if match_res.asset_id:
                used_counts[match_res.asset_id] = used_counts.get(match_res.asset_id, 0) + 1

        return results

    # ================================================================
    # 8차원 점수 계산 세부 로직
    # ================================================================

    def _score_asset(
        self,
        beat: SceneBeat,
        asset: AssetMetadata,
        usage_count: int,
        needed_duration_sec: float,
    ) -> Tuple[float, Dict[str, float]]:
        """단일 에셋과 SceneBeat 간의 8개 항목 점수 산출"""
        breakdown = {}

        # 1. Semantic Score (시각적 의도 + 대본 텍스트 매칭)
        semantic_score = self._compute_semantic_score(beat, asset)
        breakdown["semantic"] = round(semantic_score, 3)

        # 2. Action Score (시각적 동작 일치도)
        action_score = self._compute_action_score(beat, asset)
        breakdown["action"] = round(action_score, 3)

        # 3. Marketing Role Fit (광고 역할 적합도)
        role_score = self._compute_role_score(beat, asset)
        breakdown["marketing_role"] = round(role_score, 3)

        # 4. Emotion Relevance (감정 일치도)
        emotion_score = self._compute_emotion_score(beat, asset)
        breakdown["emotion"] = round(emotion_score, 3)

        # 5. Composition Score (구도 & 9:16 세로 가산점)
        composition_score = self._compute_composition_score(beat, asset)
        breakdown["composition"] = round(composition_score, 3)

        # 6. Duration Suitability (길이 적합도)
        duration_score = self._compute_duration_score(needed_duration_sec, asset)
        breakdown["duration"] = round(duration_score, 3)

        # 7. Quality Score (품질 점수)
        quality_score = max(0.0, min(1.0, asset.visual_quality))
        breakdown["quality"] = round(quality_score, 3)

        # 가중치 합계 계산
        weighted_total = (
            self.weights["semantic"] * semantic_score +
            self.weights["action"] * action_score +
            self.weights["marketing_role"] * role_score +
            self.weights["emotion"] * emotion_score +
            self.weights["composition"] * composition_score +
            self.weights["duration"] * duration_score +
            self.weights["quality"] * quality_score
        )

        # 8. Repetition Penalty (반복 사용 감점)
        penalty = usage_count * REPETITION_PENALTY_PER_USE
        breakdown["repetition_penalty"] = round(penalty, 3)

        final_score = max(0.0, weighted_total - penalty)
        return final_score, breakdown

    def _compute_semantic_score(self, beat: SceneBeat, asset: AssetMetadata) -> float:
        """visual_intent 및 script 단어와 asset tags 간의 일치도 계산"""
        score = 0.1  # 기본 탐색 점수

        # 1) visual_intent 매칭 (가장 중요)
        intent_tokens = [t.lower() for t in beat.visual_intent.split("_") if t]
        asset_tags_lower = [t.lower() for t in asset.tags]
        asset_subjects_lower = [s.lower() for s in asset.subject]

        matched_tokens = 0
        for token in intent_tokens:
            if token in asset_tags_lower or token in asset_subjects_lower:
                matched_tokens += 1
            elif any(token in t for t in asset_tags_lower):
                matched_tokens += 0.6

        if intent_tokens:
            intent_ratio = matched_tokens / len(intent_tokens)
            score += 0.6 * intent_ratio

        # 2) 대본 원문 한국어 단어와 asset tags 간의 매칭
        script_words = re.findall(r'[가-힣]{2,}', beat.script)
        matched_kr = 0
        for kw in script_words:
            if any(kw in t for t in asset_tags_lower):
                matched_kr += 1

        if script_words:
            kr_ratio = min(1.0, matched_kr / 2.0)
            score += 0.3 * kr_ratio

        return min(1.0, score)

    def _compute_action_score(self, beat: SceneBeat, asset: AssetMetadata) -> float:
        """visual_action과 asset.action 일치도 계산"""
        if not beat.visual_action or not asset.action:
            return 0.3

        action_tokens = [t.lower() for t in beat.visual_action.split("_") if t]
        asset_actions = [a.lower() for a in asset.action]

        matched = 0
        for token in action_tokens:
            if token in asset_actions:
                matched += 1
            elif any(token in a for a in asset_actions):
                matched += 0.5

        return min(1.0, matched / max(1, len(action_tokens)))

    def _compute_role_score(self, beat: SceneBeat, asset: AssetMetadata) -> float:
        """광고 역할 적합도"""
        if not asset.marketing_roles:
            return 0.4

        if beat.role in asset.marketing_roles:
            return 1.0
        # 유사 역할 매핑
        compat_map = {
            "hook": ["agitate", "empathy"],
            "empathy": ["hook", "agitate"],
            "solution": ["usp", "evidence"],
            "usp": ["solution", "evidence"],
            "cta": ["solution"],
        }
        compatibles = compat_map.get(beat.role, [])
        if any(c in asset.marketing_roles for c in compatibles):
            return 0.7

        return 0.2

    def _compute_emotion_score(self, beat: SceneBeat, asset: AssetMetadata) -> float:
        """감정 일치도"""
        if not asset.emotion or beat.emotion == "neutral":
            return 0.5

        if beat.emotion in asset.emotion:
            return 1.0

        # 유사 감정군
        pain_group = {"pain", "frustration", "anxiety", "fear"}
        relief_group = {"relief", "confidence", "hope", "satisfaction"}
        active_group = {"active", "excitement", "confidence"}

        beat_em = beat.emotion
        for group in (pain_group, relief_group, active_group):
            if beat_em in group and any(e in group for e in asset.emotion):
                return 0.75

        return 0.3

    def _compute_composition_score(self, beat: SceneBeat, asset: AssetMetadata) -> float:
        """세로 쇼츠(9:16) 적합도 및 샷 타입 매칭"""
        score = 0.5

        # 9:16 세로 영상 우대 (크롭 손실 없음)
        if asset.orientation == "vertical_9_16":
            score += 0.35
        elif asset.orientation == "square_1_1":
            score += 0.15
        elif asset.orientation == "horizontal_16_9":
            score += 0.0  # 가로 영상은 세로 크롭 시 품질 저하 가능성

        # 선호 샷 타입 일치
        if beat.preferred_shot != "any" and asset.shot_type != "any":
            if beat.preferred_shot == asset.shot_type:
                score += 0.15
            else:
                score -= 0.05

        return max(0.0, min(1.0, score))

    def _compute_duration_score(self, needed_duration_sec: float, asset: AssetMetadata) -> float:
        """길이 적합도 (영상 길이가 필요한 씬 길이보다 넉넉해야 안정적 트림 가능)"""
        if asset.media_type == "image":
            return 0.8  # 이미지는 임의 길이 확장 가능

        if asset.duration_sec <= 0:
            return 0.5

        if asset.duration_sec >= needed_duration_sec + 1.0:
            return 1.0
        elif asset.duration_sec >= needed_duration_sec:
            return 0.8
        else:
            # 길이가 부족한 경우 감점
            ratio = asset.duration_sec / max(0.1, needed_duration_sec)
            return max(0.1, ratio * 0.7)

    # ================================================================
    # 하이라이트 구간 선택
    # ================================================================

    def _calculate_highlight_range(
        self,
        asset: AssetMetadata,
        needed_duration_sec: float,
        usage_count: int,
    ) -> Tuple[float, float]:
        """에셋의 최적 하이라이트 구간 [start, end]을 결정한다.
        
        원칙:
        - 0초 시작 금지: 첫 0.5~1.0초의 정적 프레임 건너뜀
        - 동일 영상 재사용 시 사용 횟수(usage_count)에 따라 구간을 슬라이싱하여 중복 시각 방지
        """
        dur = asset.duration_sec
        if dur <= 0:
            return (0.0, needed_duration_sec)

        # 에셋이 필요한 길이보다 짧은 경우 전체 사용
        if dur <= needed_duration_sec:
            return (0.0, dur)

        # 기본 시작점 (초반 안정화 0.5초 후)
        base_start = 0.5 if dur >= 3.0 else 0.0
        available_window = dur - needed_duration_sec - base_start

        if available_window <= 0:
            return (base_start, min(dur, base_start + needed_duration_sec))

        # 동일 에셋이 여러 번 사용될 경우 오프셋 점프
        step = available_window / max(1, usage_count + 1)
        offset_start = base_start + (usage_count * step) % available_window
        offset_end = min(dur, offset_start + needed_duration_sec)

        return (offset_start, offset_end)


# ================================================================
# 기존 naver_clip_adforge와의 하위 호환 브릿지 함수
# ================================================================

_GLOBAL_INDEXER: Optional[AssetIndexer] = None
_GLOBAL_ASSETS: Optional[List[AssetMetadata]] = None
_GLOBAL_MATCHER: Optional[AssetMatcher] = None


def intelligent_find_best_video(
    sentence: str,
    stock_videos: List[str],
    last_used_video: str = "",
    role: str = "normal",
) -> str:
    """기존 find_best_video_for_sentence()의 시그니처를 유지하면서,
    새로운 8차원 AssetMatcher를 내부에서 구동하는 브릿지 함수."""
    global _GLOBAL_INDEXER, _GLOBAL_ASSETS, _GLOBAL_MATCHER

    if not stock_videos:
        return ""

    if _GLOBAL_INDEXER is None:
        _GLOBAL_INDEXER = AssetIndexer(cache_dir="outputs")
        _GLOBAL_MATCHER = AssetMatcher()

    # stock_videos 목록 기반 AssetMetadata 변환 (캐시 활용)
    first_dir = os.path.dirname(stock_videos[0])
    if _GLOBAL_ASSETS is None or len(_GLOBAL_ASSETS) != len(stock_videos):
        _GLOBAL_ASSETS = _GLOBAL_INDEXER.scan_directory(first_dir, recursive=True, use_cache=True)

    # 임시 SceneBeat 생성
    temp_beat = SceneBeat(
        script=sentence,
        role=role,
        visual_intent=sentence[:30],
    )

    used_counts = {last_used_video: 1} if last_used_video else {}
    match_res = _GLOBAL_MATCHER.match(temp_beat, _GLOBAL_ASSETS, used_counts=used_counts)

    if match_res.asset_path and os.path.exists(match_res.asset_path):
        return match_res.asset_path

    # 폴백
    candidates = [v for v in stock_videos if v != last_used_video]
    return candidates[0] if candidates else stock_videos[0]
