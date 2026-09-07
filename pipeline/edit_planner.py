"""
EditPlanner — 광고 타임라인 설계 엔진 (STEP 3)

책임:
1. CreativePlan + AssetMatch + TTS Timing을 결합하여 실제 광고 타임라인(EditPlan) 설계
2. SceneBeat != SceneEdit (1 Beat -> 1~N SceneEdits/Shots 지능형 분할)
3. TTS Timing을 마스터 시간축으로 고정 (음성과 화면의 완벽한 싱크)
4. Source Range (원본 영상 내 구간)와 Timeline Range (광고 내 재생 구간) 엄격 분리 및 보존
5. 절제된 연출 규칙: 기본 static + hard_cut, 필요한 지점(Hook/USP/CTA)에만 motion/transition 부여
6. 100% 결정론적(Deterministic) 알고리즘 — random 배제
"""

import os
import re
from typing import List, Dict, Tuple, Optional, Any
from models.creative_plan import CreativePlan, SceneBeat
from models.edit_plan import EditPlan, SceneEdit, EditPlanMetadata
from models.asset import AssetMetadata, MatchResult


def calculate_korean_speech_weight(text: str) -> float:
    """한국어 발화 길이 가중치 계산 (문장 내 Beat 비율 배분용)"""
    letters_count = len(re.sub(r'[\s.,!?…]', '', text))
    punct_count = len(re.findall(r'[,!?…]', text))
    return max(1.0, letters_count + (punct_count * 1.5))


class EditPlanner:
    """광고 편집 타임라인 설계 엔진"""

    def __init__(self):
        pass

    def plan(
        self,
        creative_plan: CreativePlan,
        asset_matches: List[MatchResult],
        tts_timing: Optional[Any] = None,
        reference_style: Optional[dict] = None,
        assets_map: Optional[Dict[str, AssetMetadata]] = None,
    ) -> EditPlan:
        """CreativePlan, AssetMatches, TTS Timing을 바탕으로 완전한 EditPlan을 생성한다.
        
        Args:
            creative_plan: STEP 1에서 생성된 CreativePlan
            asset_matches: STEP 2에서 생성된 MatchResult 목록 (각 beat에 대응)
            tts_timing: 문장별/Beat별 TTS 재생 시간 및 오디오 파일 정보
            reference_style: ReferenceAnalyzer의 StyleProfile (선택)
            assets_map: asset_id -> AssetMetadata 맵 (선택)
        """
        if not creative_plan or not creative_plan.beats:
            return EditPlan(metadata=EditPlanMetadata())

        # 1. MatchResult 매핑 테이블 구축 (beat_id -> MatchResult)
        match_by_beat: Dict[str, MatchResult] = {m.beat_id: m for m in asset_matches if m.beat_id}

        # 2. TTS Timing 정규화 (각 Beat별 timeline duration 및 audio_path 배분)
        beat_timings = self._resolve_beat_timings(creative_plan, tts_timing)

        # 3. Reference Style 파라미터 추출
        ref_cut_rhythm = self._extract_reference_cut_rhythm(reference_style)

        # 4. Beat별 SceneEdit(들) 생성 (1 Beat -> 1~N Shots)
        scenes: List[SceneEdit] = []
        current_timeline_time = 0.0
        scene_counter = 0

        # 동일 에셋 재사용 추적기 (asset_id -> 사용 횟수)
        asset_usage_tracker: Dict[str, int] = {}

        prev_role = ""

        for beat_idx, beat in enumerate(creative_plan.beats):
            timing = beat_timings.get(beat.id, {"duration": 2.5, "audio_path": ""})
            beat_duration = max(0.6, timing["duration"])
            audio_path = timing.get("audio_path", "")

            # 해당 beat의 매칭 결과
            match_res = match_by_beat.get(beat.id)
            if not match_res and asset_matches:
                # 인덱스 기준 매칭 폴백
                if beat_idx < len(asset_matches):
                    match_res = asset_matches[beat_idx]

            # 에셋 메타데이터 조회
            asset_meta = None
            if assets_map and match_res and match_res.asset_id:
                asset_meta = assets_map.get(match_res.asset_id)

            # 4-1. Beat 분할 여부 결정 (Shot Count 결정)
            shot_durations = self._determine_shot_splits(beat, beat_duration, ref_cut_rhythm)

            # 4-2. 각 Shot에 대한 SceneEdit 생성
            for shot_idx, shot_dur in enumerate(shot_durations):
                scene_id = f"s{scene_counter:02d}"
                scene_counter += 1

                t_start = round(current_timeline_time, 3)
                t_end = round(t_start + shot_dur, 3)
                current_timeline_time = t_end

                # 에셋 사용 구간(source_start, source_end) 결정
                source_range, chosen_asset_id, chosen_asset_path, match_status, confidence, reasoning = (
                    self._resolve_source_range(
                        beat=beat,
                        match_res=match_res,
                        asset_meta=asset_meta,
                        shot_duration=shot_dur,
                        shot_idx=shot_idx,
                        total_shots_in_beat=len(shot_durations),
                        usage_count=asset_usage_tracker.get(match_res.asset_id, 0) if match_res else 0,
                    )
                )

                if chosen_asset_id:
                    asset_usage_tracker[chosen_asset_id] = asset_usage_tracker.get(chosen_asset_id, 0) + 1

                # 카메라 모션 결정
                camera_motion = self._determine_camera_motion(beat, shot_idx, len(shot_durations))

                # 트랜지션 결정
                transition = self._determine_transition(beat, prev_role, shot_idx)

                # 자막 및 강조 단어
                caption_style, caption_position = self._determine_caption_styling(beat)

                scene = SceneEdit(
                    scene_id=scene_id,
                    beat_id=beat.id,
                    script=beat.script,
                    role=beat.role,
                    emotion=beat.emotion,
                    asset_id=chosen_asset_id,
                    asset_path=chosen_asset_path,
                    source_start=round(source_range[0], 3),
                    source_end=round(source_range[1], 3),
                    timeline_start=t_start,
                    timeline_end=t_end,
                    duration=round(shot_dur, 3),
                    audio_path=audio_path,
                    importance=beat.importance,
                    pacing=beat.pacing,
                    caption_text=beat.script,
                    caption_style=caption_style,
                    caption_position=caption_position,
                    emphasis_words=list(beat.emphasis_words),
                    camera_motion=camera_motion,
                    transition=transition,
                    status=match_status,
                    confidence=confidence,
                    reasoning=reasoning,
                )
                scene.validate()
                scenes.append(scene)

            prev_role = beat.role

        # 5. 전체 메타데이터 계산
        metadata = self._compute_metadata(scenes, creative_plan, reference_style)

        return EditPlan(scenes=scenes, metadata=metadata)

    # ================================================================
    # 1. TTS Timing 정규화 및 Beat 타임라인 배분
    # ================================================================

    def _resolve_beat_timings(
        self, creative_plan: CreativePlan, tts_timing: Optional[Any]
    ) -> Dict[str, Dict[str, Any]]:
        """TTS timing 정보(문장 단위 또는 Beat 단위)를 각 Beat에 정확히 배분한다.
        
        원칙:
        - 음성(TTS)이 마스터 타임라인이다.
        - 한 문장이 여러 Beat로 나뉜 경우(예: b04a, b04b), 한국어 발화 가중치로 비례 분할한다.
        - 누적 오차 0.0s를 보장한다.
        """
        beat_timings: Dict[str, Dict[str, Any]] = {}

        # 1) tts_timing이 dict로 각 beat_id를 직접 제공하는 경우
        if isinstance(tts_timing, dict) and any(b.id in tts_timing for b in creative_plan.beats):
            for beat in creative_plan.beats:
                val = tts_timing.get(beat.id)
                if isinstance(val, (int, float)):
                    beat_timings[beat.id] = {"duration": float(val), "audio_path": ""}
                elif isinstance(val, dict):
                    beat_timings[beat.id] = {
                        "duration": float(val.get("duration", val.get("duration_sec", 2.5))),
                        "audio_path": val.get("audio_path", ""),
                    }
            return beat_timings

        # 2) 문장 인덱스별 TTS timing 구조 파싱
        sentence_timing_map: Dict[int, Dict[str, Any]] = {}

        if isinstance(tts_timing, list):
            for idx, item in enumerate(tts_timing):
                if isinstance(item, dict):
                    s_idx = item.get("sentence_idx", item.get("index", idx))
                    dur = float(item.get("duration_sec", item.get("duration", 0.0)))
                    path = item.get("audio_path", "")
                    sentence_timing_map[s_idx] = {"duration": dur, "audio_path": path}
                elif isinstance(item, (int, float)):
                    sentence_timing_map[idx] = {"duration": float(item), "audio_path": ""}
        elif isinstance(tts_timing, dict):
            for k, v in tts_timing.items():
                try:
                    s_idx = int(k)
                    if isinstance(v, dict):
                        dur = float(v.get("duration_sec", v.get("duration", 0.0)))
                        path = v.get("audio_path", "")
                        sentence_timing_map[s_idx] = {"duration": dur, "audio_path": path}
                    elif isinstance(v, (int, float)):
                        sentence_timing_map[s_idx] = {"duration": float(v), "audio_path": ""}
                except ValueError:
                    pass

        # 3) 문장별로 속한 Beat들을 그룹화
        sentence_to_beats: Dict[int, List[SceneBeat]] = {}
        for beat in creative_plan.beats:
            s_indices = beat.sentence_indices if beat.sentence_indices else [0]
            primary_s_idx = s_indices[0]
            sentence_to_beats.setdefault(primary_s_idx, []).append(beat)

        # 4) 문장 오디오 길이를 Beat들에게 비례 배분
        for s_idx, beats_in_sentence in sentence_to_beats.items():
            s_info = sentence_timing_map.get(s_idx)

            if s_info and s_info["duration"] > 0:
                total_sentence_dur = s_info["duration"]
                audio_path = s_info.get("audio_path", "")
            else:
                # 폴백: 한국어 평균 발화 속도 (초당 5글자 기준)
                combined_script = "".join(b.script for b in beats_in_sentence)
                total_sentence_dur = round(calculate_korean_speech_weight(combined_script) / 5.0, 2)
                audio_path = ""

            if len(beats_in_sentence) == 1:
                beat_timings[beats_in_sentence[0].id] = {
                    "duration": total_sentence_dur,
                    "audio_path": audio_path,
                }
            else:
                # 여러 Beat로 분할된 문장: 한국어 발화 가중치 기준 비례 배분
                weights = [calculate_korean_speech_weight(b.script) for b in beats_in_sentence]
                total_weight = sum(weights) or 1.0

                allocated_sum = 0.0
                for i, beat in enumerate(beats_in_sentence):
                    if i == len(beats_in_sentence) - 1:
                        # 마지막 beat에 남은 시간 전액 할당 (오차 0.0s 보장)
                        beat_dur = round(total_sentence_dur - allocated_sum, 3)
                    else:
                        beat_dur = round(total_sentence_dur * (weights[i] / total_weight), 3)
                        allocated_sum += beat_dur

                    beat_timings[beat.id] = {
                        "duration": max(0.5, beat_dur),
                        "audio_path": audio_path,
                    }

        return beat_timings

    # ================================================================
    # 2. Shot 분할 로직 (SceneBeat -> 1~N Shots)
    # ================================================================

    def _determine_shot_splits(
        self,
        beat: SceneBeat,
        beat_duration: float,
        reference_cut_rhythm: Optional[dict] = None,
    ) -> List[float]:
        """하나의 Beat를 몇 개의 Shot으로 나눌지와 각 Shot의 길이를 결정한다.
        
        규칙:
        1. Hook Beat:
           - 첫 1~3초가 매우 중요.
           - duration >= 1.6s이고 중요도가 높으면 2개의 빠른 컷으로 분할 (예: 0.9s + 1.3s)
        2. Problem / Agitation / 복합 문장 Beat:
           - duration >= 3.0s이고 pacing이 빠르면 2개 컷으로 분할
        3. CTA Beat:
           - 정보 전달 및 행동 유도를 위해 단일 Shot으로 유지 (체류 시간 확보)
        4. 짧은 Beat (< 1.8s):
           - 불필요하게 쪼개지 않고 단일 Shot 유지
        5. 각 분할된 Shot의 합은 beat_duration과 정확히 일치.
        """
        # A. 무조건 단일 Shot으로 유지해야 하는 경우
        if beat.role == "cta":
            return [round(beat_duration, 3)]

        if beat_duration < 1.7:
            return [round(beat_duration, 3)]

        # B. Hook 분할 판단
        if beat.role == "hook":
            # Hook은 빠른 템포가 핵심 (0.8s ~ 1.2s의 첫 충격 샷)
            if beat_duration >= 1.8:
                first_shot = 0.95
                second_shot = round(beat_duration - first_shot, 3)
                if second_shot >= 0.8:
                    return [first_shot, second_shot]

        # C. 긴 문장 / 빠른 페이싱 분할 판단
        if beat_duration >= 3.2 and beat.pacing in ("fast", "very_fast"):
            half = round(beat_duration / 2.0, 3)
            return [half, round(beat_duration - half, 3)]

        # D. 복합 조건절 또는 쉼표가 포함된 긴 Beat
        if beat_duration >= 2.8 and ("," in beat.script or "는데" in beat.script or "다면" in beat.script):
            shot1 = round(beat_duration * 0.45, 3)
            shot2 = round(beat_duration - shot1, 3)
            if shot1 >= 1.0 and shot2 >= 1.0:
                return [shot1, shot2]

        # 기본: 단일 Shot 유지
        return [round(beat_duration, 3)]

    # ================================================================
    # 3. Source Range 및 에셋 할당 (AssetMatcher 결과 보존)
    # ================================================================

    def _resolve_source_range(
        self,
        beat: SceneBeat,
        match_res: Optional[MatchResult],
        asset_meta: Optional[AssetMetadata],
        shot_duration: float,
        shot_idx: int,
        total_shots_in_beat: int,
        usage_count: int,
    ) -> Tuple[Tuple[float, float], str, str, str, float, str]:
        """에셋의 source_start, source_end를 계산한다.
        
        원칙:
        - AssetMatcher가 선택한 highlight_range[0]을 시작점으로 존중 (절대 0으로 초기화 금지)
        - 하나의 Beat가 2개 Shot으로 쪼개진 경우, 2번째 Shot은 연속된 뒷구간을 사용하여
          동일 영상의 앞부분이 반복 재생되는 현상 방지
        - 동일 에셋이 이전 Beat에서 이미 쓰인 경우 usage_count에 따른 오프셋 슬라이싱
        """
        if not match_res or not match_res.asset_path or not os.path.exists(match_res.asset_path):
            # No match / 에셋 부재 fallback
            return (
                (0.0, shot_duration),
                match_res.asset_id if match_res else "unresolved",
                match_res.asset_path if match_res else "",
                "no_match",
                0.0,
                "적합한 에셋을 찾지 못함 (unresolved)",
            )

        asset_id = match_res.asset_id
        asset_path = match_res.asset_path

        # 기본 하이라이트 시작점 가져오기
        hl_start = 0.5
        if match_res.highlight_range and len(match_res.highlight_range) >= 2:
            hl_start = float(match_res.highlight_range[0])

        # 에셋 전체 길이 (알 수 없는 경우 60.0초 가정)
        asset_duration = asset_meta.duration_sec if (asset_meta and asset_meta.duration_sec > 0) else 60.0

        # 다중 샷인 경우: 2번째 샷은 1번째 샷의 뒷부분 사용
        if total_shots_in_beat > 1 and shot_idx > 0:
            hl_start += (shot_duration * shot_idx)

        # 에셋 길이 초과 방지
        if hl_start + shot_duration > asset_duration:
            hl_start = max(0.0, asset_duration - shot_duration)

        source_start = round(hl_start, 3)
        source_end = round(min(asset_duration, source_start + shot_duration), 3)

        # 길이가 여전히 부족한 경우 (에셋 자체가 shot_duration보다 짧음)
        status = "matched"
        confidence = match_res.total_score if match_res.total_score > 0 else 0.8
        reasoning = (
            f"AssetMatcher 매칭 보존: '{os.path.basename(asset_path)}' "
            f"구간 [{source_start:.2f}s~{source_end:.2f}s]"
        )

        if (source_end - source_start) < (shot_duration - 0.05):
            status = "loop_required"
            reasoning += f" (에셋 길이 부족: {asset_duration:.1f}s < 필요 {shot_duration:.1f}s)"

        return (source_start, source_end), asset_id, asset_path, status, round(confidence, 2), reasoning

    # ================================================================
    # 4. 카메라 모션 및 전환 결정 (절제된 규칙)
    # ================================================================

    def _determine_camera_motion(
        self, beat: SceneBeat, shot_idx: int, total_shots: int
    ) -> str:
        """기본 static 원칙하에 필요한 장면에만 모션 적용"""
        # Hook의 첫 1초: 시선 강탈을 위한 펀치/푸시인
        if beat.role == "hook" and shot_idx == 0:
            if beat.importance >= 0.8:
                return "push_in"

        # USP / 핵심 차별점: 제품 디테일 강조
        if beat.role in ("usp", "solution") and beat.importance >= 0.75:
            return "subtle_zoom_in"

        # CTA: 행동 유도 집중
        if beat.role == "cta":
            return "subtle_zoom_in"

        # 나머지 모든 장면은 static (기계적 줌인 절대 방지)
        return "static"

    def _determine_transition(
        self, beat: SceneBeat, prev_role: str, shot_idx: int
    ) -> str:
        """기본 hard_cut 원칙하에 파트 전환에만 절제된 효과 적용"""
        # 한 Beat 내에서 쪼개진 Shot 간 전환은 무조건 hard_cut
        if shot_idx > 0:
            return "hard_cut"

        # 문제(Agitate/Empathy) -> 해결책(Solution/USP)으로 넘어갈 때만 flash 전환
        if prev_role in ("agitate", "empathy", "hook") and beat.role in ("solution", "usp"):
            return "flash"

        # 기본은 빠른 템포의 hard_cut
        return "hard_cut"

    def _determine_caption_styling(self, beat: SceneBeat) -> Tuple[str, str]:
        """자막 스타일 및 위치 결정 (CaptionEngine 전달용)"""
        if beat.role == "hook":
            return "hook", "center"
        elif beat.role == "cta":
            return "cta", "center_bottom"
        elif beat.role in ("usp", "solution"):
            return "highlight", "center_bottom"
        return "normal", "center_bottom"

    # ================================================================
    # 5. Reference Style 및 메타데이터 계산
    # ================================================================

    def _extract_reference_cut_rhythm(self, reference_style: Optional[dict]) -> Optional[dict]:
        if not reference_style:
            return None
        return reference_style.get("cut_rhythm")

    def _compute_metadata(
        self,
        scenes: List[SceneEdit],
        creative_plan: CreativePlan,
        reference_style: Optional[dict],
    ) -> EditPlanMetadata:
        total_scenes = len(scenes)
        total_beats = len(creative_plan.beats)
        total_duration = round(scenes[-1].timeline_end, 3) if scenes else 0.0

        avg_shot = round(total_duration / total_scenes, 2) if total_scenes > 0 else 0.0

        hook_shots = [s.duration for s in scenes if s.role == "hook"]
        body_shots = [s.duration for s in scenes if s.role not in ("hook", "cta")]
        cta_shots = [s.duration for s in scenes if s.role == "cta"]

        hook_avg = round(sum(hook_shots) / len(hook_shots), 2) if hook_shots else avg_shot
        body_avg = round(sum(body_shots) / len(body_shots), 2) if body_shots else avg_shot
        cta_avg = round(sum(cta_shots) / len(cta_shots), 2) if cta_shots else avg_shot

        style_id = reference_style.get("style_id") if reference_style else None

        return EditPlanMetadata(
            total_scenes=total_scenes,
            total_beats=total_beats,
            total_duration_sec=total_duration,
            style_profile_id=style_id,
            render_width=1080,
            render_height=1920,
            render_fps=30,
            avg_shot_duration_sec=avg_shot,
            hook_shot_duration_sec=hook_avg,
            body_shot_duration_sec=body_avg,
            cta_shot_duration_sec=cta_avg,
        )


# ================================================================
# Renderer 연동용 호환성 어댑터 (STEP 5 준비)
# ================================================================

def render_edit_plan(edit_plan: EditPlan, output_path: str = "outputs/final_render.mp4") -> str:
    """EditPlan을 렌더링하기 위한 compatibility adapter 인터페이스.

    STEP 5에서 본격 Renderer가 구현될 예정이며, 현재는 EditPlan의 계약 스펙을
    검증하고 렌더링 인터페이스를 제공한다.
    """
    if not edit_plan or not edit_plan.scenes:
        raise ValueError("렌더링할 Scene이 EditPlan에 존재하지 않습니다.")

    for s in edit_plan.scenes:
        s.validate()

    return output_path

