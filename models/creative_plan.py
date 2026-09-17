"""
CreativePlan 데이터 모델

대본을 "광고 연출 지시서"로 변환한 결과.
각 SceneBeat는 하나의 편집 지시 단위이며,
후속 AssetMatcher / EditPlanner / Renderer가 직접 소비한다.

핵심 철학: Scene = Semantic Beat (≠ Sentence)
- 하나의 문장이 2~3개 beat로 분할될 수 있음
- 짧은 문장 여러 개가 하나의 beat로 묶일 수 있음
"""

import json
import hashlib
from dataclasses import dataclass, field, asdict
from typing import List, Optional


# -------------------------------------------------------------------
# 허용 값 정의 (LLM 출력 검증 + fallback 복구용)
# -------------------------------------------------------------------

VALID_ROLES = frozenset({
    "hook", "empathy", "agitate", "evidence",
    "solution", "usp", "cta", "transition", "normal"
})

VALID_EMOTIONS = frozenset({
    "frustration", "shock", "curiosity", "fear", "anxiety",
    "relief", "confidence", "urgency", "empathy", "neutral",
    "excitement", "trust", "surprise", "pain", "hope", "satisfaction"
})

VALID_PACING = frozenset({"very_fast", "fast", "medium", "slow"})

VALID_SHOTS = frozenset({
    "closeup", "extreme_closeup", "medium", "wide",
    "detail", "product", "text_overlay", "over_shoulder", "any"
})

VALID_CAMERA_MOTION = frozenset({
    "static", "subtle_zoom_in", "subtle_zoom_out",
    "punch_zoom", "pan_left", "pan_right", "pan_up", "pan_down",
    "track", "reframing"
})

VALID_TRANSITIONS = frozenset({
    "hard_cut", "fade", "flash", "zoom_transition", "whip"
})


# -------------------------------------------------------------------
# SceneBeat — 하나의 광고 연출 지시 단위
# -------------------------------------------------------------------

@dataclass
class SceneBeat:
    """하나의 semantic beat = 하나의 편집 지시 단위

    후속 파이프라인 참조:
    - AssetMatcher: visual_intent, visual_action, preferred_shot, emotion
    - EditPlanner:  importance, pacing, camera_motion, transition, duration 결정
    - CaptionEngine: emphasis_words, role → 자막 스타일 결정
    - Renderer:     camera_motion, transition → FFmpeg filterchain 생성
    """

    id: str = ""
    script: str = ""

    # 광고 역할
    role: str = "normal"

    # 감정 톤
    emotion: str = "neutral"

    # 이 beat에서 무엇을 보여줘야 하는가 (AssetMatcher 검색 키)
    visual_intent: str = ""

    # 화면에서 무슨 동작이 일어나야 하는가
    visual_action: str = ""

    # 광고 전체에서 이 beat의 중요도 (0.0~1.0)
    importance: float = 0.5

    # 편집 속도감 (very_fast / fast / medium / slow)
    pacing: str = "medium"

    # 선호 샷 타입 (closeup / medium / wide / detail / product / ...)
    preferred_shot: str = "any"

    # 강조해야 할 핵심 단어 (자막에서 하이라이트)
    emphasis_words: list = field(default_factory=list)

    # 카메라 모션 (static / subtle_zoom_in / punch_zoom / ...)
    camera_motion: str = "static"

    # 다음 beat로의 전환 (hard_cut / fade / flash / ...)
    transition: str = "hard_cut"

    # 오디오 매핑: 이 beat가 속하는 원본 문장 인덱스(들)
    # - [0]: 첫 번째 문장에서 나온 beat
    # - [2, 3]: 두 문장이 합쳐져 하나의 beat가 된 경우
    # - [1]: 한 문장에서 여러 beat가 생긴 경우 모두 같은 값
    sentence_indices: list = field(default_factory=list)

    def validate(self) -> 'SceneBeat':
        """허용되지 않은 값을 안전한 기본값으로 복구한다.
        pipeline이 잘못된 LLM 출력으로 죽지 않도록 보장."""
        if self.role not in VALID_ROLES:
            self.role = "normal"
        if self.emotion not in VALID_EMOTIONS:
            self.emotion = "neutral"
        if self.pacing not in VALID_PACING:
            self.pacing = "medium"
        if self.preferred_shot not in VALID_SHOTS:
            self.preferred_shot = "any"
        if self.camera_motion not in VALID_CAMERA_MOTION:
            self.camera_motion = "static"
        if self.transition not in VALID_TRANSITIONS:
            self.transition = "hard_cut"
        try:
            self.importance = max(0.0, min(1.0, float(self.importance)))
        except (TypeError, ValueError):
            self.importance = 0.5
        if not isinstance(self.emphasis_words, list):
            self.emphasis_words = []
        if not isinstance(self.sentence_indices, list):
            self.sentence_indices = []
        if not self.id:
            self.id = f"b{self.sentence_indices[0]:02d}" if self.sentence_indices else "b00"
        return self


# -------------------------------------------------------------------
# CreativePlanMetadata — Creative Plan 전체 메타데이터
# -------------------------------------------------------------------

@dataclass
class CreativePlanMetadata:
    """Creative Plan의 메타데이터.

    reference_style_id: 향후 ReferenceAnalyzer의 StyleProfile 연결용.
                        STEP 6에서 실제 연결, STEP 1에서는 None 허용.
    """
    total_beats: int = 0
    total_sentences: int = 0
    estimated_duration_sec: float = 0.0
    reference_style_id: Optional[str] = None
    generation_method: str = "fallback"   # "llm" | "fallback"
    script_hash: str = ""


# -------------------------------------------------------------------
# CreativePlan — 광고 연출 지시서 전체
# -------------------------------------------------------------------

@dataclass
class CreativePlan:
    """광고 연출 지시서 전체.

    beats:    semantic beat 목록 (시간 순서)
    metadata: 생성 메타데이터
    """

    beats: List[SceneBeat] = field(default_factory=list)
    metadata: CreativePlanMetadata = field(default_factory=CreativePlanMetadata)

    # ── 직렬화 ───────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, path: str = None, indent: int = 2) -> str:
        """JSON 문자열로 변환. path가 주어지면 파일에도 저장."""
        text = json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)
        if path:
            import os
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        return text

    @classmethod
    def from_dict(cls, data: dict) -> 'CreativePlan':
        """dict에서 CreativePlan 복원. 잘못된 값은 자동 보정."""
        beats_data = data.get("beats", [])
        beats = []
        known_fields = {f for f in SceneBeat.__dataclass_fields__}
        for b in beats_data:
            filtered = {k: v for k, v in b.items() if k in known_fields}
            beat = SceneBeat(**filtered)
            beat.validate()
            beats.append(beat)

        meta_data = data.get("metadata", {})
        known_meta = {f for f in CreativePlanMetadata.__dataclass_fields__}
        filtered_meta = {k: v for k, v in meta_data.items() if k in known_meta}
        meta = CreativePlanMetadata(**filtered_meta)
        return cls(beats=beats, metadata=meta)

    @classmethod
    def from_json(cls, path: str) -> 'CreativePlan':
        """JSON 파일에서 CreativePlan 로딩."""
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    # ── 디버그 마크다운 ──────────────────────────────────────────────

    def to_debug_markdown(self, path: str = None) -> str:
        """사람이 읽을 수 있는 디버그 보고서 생성."""
        lines = [
            "# Creative Plan Debug Report\n",
            f"**Total Beats**: {len(self.beats)}",
            f"**Total Sentences**: {self.metadata.total_sentences}",
            f"**Generation Method**: {self.metadata.generation_method}",
            f"**Reference Style**: {self.metadata.reference_style_id or 'none'}",
            "",
            "---",
            "",
        ]

        for beat in self.beats:
            lines.append(f"## Beat `{beat.id}` — [{beat.role.upper()}]")
            lines.append("")
            lines.append(f"> **대본**: \"{beat.script}\"")
            lines.append("")
            lines.append("| 항목 | 값 |")
            lines.append("|---|---|")
            lines.append(f"| role | `{beat.role}` |")
            lines.append(f"| emotion | `{beat.emotion}` |")
            lines.append(f"| visual_intent | `{beat.visual_intent}` |")
            lines.append(f"| visual_action | `{beat.visual_action}` |")
            lines.append(f"| importance | `{beat.importance}` |")
            lines.append(f"| pacing | `{beat.pacing}` |")
            lines.append(f"| preferred_shot | `{beat.preferred_shot}` |")
            lines.append(f"| emphasis_words | `{beat.emphasis_words}` |")
            lines.append(f"| camera_motion | `{beat.camera_motion}` |")
            lines.append(f"| transition | `{beat.transition}` |")
            lines.append(f"| sentence_indices | `{beat.sentence_indices}` |")
            lines.append("")

        text = "\n".join(lines)
        if path:
            import os
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        return text

    # ── 기존 pipeline 호환 어댑터 ────────────────────────────────────

    def to_legacy_creative_direction(self) -> dict:
        """기존 build_capcut_project_for_naver_clip()의 creative_direction 형식으로 변환.

        기존 형식: {"sentences": [{"index": 0, "text": "...", "role": "hook", ...}]}
        이 어댑터를 통해 새 CreativePlan → 기존 CapCut 파이프라인으로 전달 가능.
        """
        ROLE_PRESETS = {
            "hook": {"size": 18.0, "color": [1.0, 0.9, 0.0], "bold": True, "border_color": [0.0, 0.0, 0.0], "border_width": 55.0},
            "normal": {"size": 14.5, "color": [1.0, 1.0, 1.0], "bold": True, "border_color": [0.0, 0.0, 0.0], "border_width": 25.0},
        }

        sentences = []
        for beat in self.beats:
            idx = beat.sentence_indices[0] if beat.sentence_indices else 0
            role = beat.role if beat.role in ROLE_PRESETS else "normal"
            preset = ROLE_PRESETS.get(role, ROLE_PRESETS["normal"])

            sentences.append({
                "index": idx,
                "text": beat.script,
                "role": role,
                "reasoning": f"CreativePlan beat {beat.id}: {beat.visual_intent}",
                "psychology": beat.emotion if beat.emotion != "neutral" else None,
                "subtitle_style": {
                    "size": preset["size"],
                    "color": preset["color"],
                    "bold": preset["bold"],
                    "border_color": preset["border_color"],
                    "border_width": preset["border_width"],
                },
                "text_intro": preset.get("text_intro"),
                "text_outro": preset.get("text_outro"),
                "text_loop_anim": preset.get("text_loop_anim"),
            })
        return {"sentences": sentences}

    # ── 유틸리티 ─────────────────────────────────────────────────────

    @staticmethod
    def hash_script(script_text: str) -> str:
        return hashlib.md5(script_text.encode("utf-8")).hexdigest()[:12]

    def get_beats_by_role(self, role: str) -> List[SceneBeat]:
        return [b for b in self.beats if b.role == role]

    def get_beats_by_sentence(self, sentence_index: int) -> List[SceneBeat]:
        return [b for b in self.beats if sentence_index in b.sentence_indices]
