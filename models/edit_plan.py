"""
EditPlan 데이터 모델 (STEP 3 구현)

CreativePlan + AssetMatch + TTS Timing을 결합하여
Renderer가 그대로 실행할 수 있는 최종 광고 타임라인 계약.

핵심 원칙:
1. SceneBeat != SceneEdit (1 Beat -> 1~N SceneEdit 지원)
2. TTS Timing = Master Timeline (음성에 맞춘 영상 설계)
3. Source Range (source_start/end)와 Timeline Range (timeline_start/end) 엄격 분리
"""

import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any


@dataclass
class SceneEdit:
    """타임라인 위의 하나의 편집 단위 (하나의 Shot)"""

    scene_id: str = ""
    beat_id: str = ""
    script: str = ""
    role: str = "normal"
    emotion: str = "neutral"

    # 에셋 정보 (STEP 2 AssetMatcher에서 전달)
    asset_id: str = ""
    asset_path: str = ""

    # 원본 영상 내 사용 구간 (Source Range)
    source_start: float = 0.0
    source_end: float = 0.0

    # 최종 광고 영상 내 재생 구간 (Timeline Range)
    timeline_start: float = 0.0
    timeline_end: float = 0.0
    duration: float = 0.0

    # 오디오 (TTS) 정보
    audio_path: str = ""

    # 편집 메타데이터
    importance: float = 0.5
    pacing: str = "medium"

    # 자막 정보 (STEP 4 CaptionEngine용 예약)
    caption_text: str = ""
    caption_style: str = "default"
    caption_position: str = "center_bottom"
    emphasis_words: List[str] = field(default_factory=list)

    # 카메라 모션 및 화면 전환 (기본: static + hard_cut)
    camera_motion: str = "static"
    transition: str = "hard_cut"

    # 상태 및 신뢰도
    status: str = "matched"  # "matched" | "no_match" | "fallback"
    confidence: float = 1.0
    reasoning: str = ""

    # ── 하위 호환성 프로퍼티 및 필드 매핑 ──────────────────────────
    @property
    def start_sec(self) -> float:
        return self.timeline_start

    @property
    def end_sec(self) -> float:
        return self.timeline_end

    @property
    def duration_sec(self) -> float:
        return self.duration

    @property
    def asset_start_sec(self) -> float:
        return self.source_start

    @property
    def asset_end_sec(self) -> float:
        return self.source_end

    def validate(self) -> 'SceneEdit':
        """타임라인 및 소스 레인지 유효성 검증 및 보정"""
        if self.duration <= 0.0 and self.timeline_end > self.timeline_start:
            self.duration = round(self.timeline_end - self.timeline_start, 3)
        elif self.timeline_end <= self.timeline_start and self.duration > 0.0:
            self.timeline_end = round(self.timeline_start + self.duration, 3)

        self.duration = max(0.0, round(self.duration, 3))
        self.source_start = max(0.0, round(self.source_start, 3))
        self.source_end = max(self.source_start, round(self.source_end, 3))
        self.importance = max(0.0, min(1.0, float(self.importance)))

        if not self.caption_text and self.script:
            self.caption_text = self.script

        return self

    def to_dict(self) -> dict:
        d = asdict(self)
        # 프로퍼티 및 가독성을 위한 필드 보완
        d["duration"] = round(self.duration, 3)
        d["source_start"] = round(self.source_start, 3)
        d["source_end"] = round(self.source_end, 3)
        d["timeline_start"] = round(self.timeline_start, 3)
        d["timeline_end"] = round(self.timeline_end, 3)
        return d


@dataclass
class EditPlanMetadata:
    """EditPlan 전체 메타데이터"""
    total_scenes: int = 0
    total_beats: int = 0
    total_duration_sec: float = 0.0
    style_profile_id: Optional[str] = None
    render_width: int = 1080
    render_height: int = 1920
    render_fps: int = 30
    avg_shot_duration_sec: float = 0.0
    hook_shot_duration_sec: float = 0.0
    body_shot_duration_sec: float = 0.0
    cta_shot_duration_sec: float = 0.0


@dataclass
class EditPlan:
    """완전한 광고 편집 계획 — Renderer가 실행하는 최종 계약"""

    scenes: List[SceneEdit] = field(default_factory=list)
    metadata: EditPlanMetadata = field(default_factory=EditPlanMetadata)

    @property
    def duration(self) -> float:
        return self.metadata.total_duration_sec

    def to_dict(self) -> dict:
        return {
            "duration": round(self.metadata.total_duration_sec, 3),
            "scenes": [s.to_dict() for s in self.scenes],
            "metadata": asdict(self.metadata),
        }

    def to_json(self, path: str = None, indent: int = 2) -> str:
        text = json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)
        if path:
            import os
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        return text

    @classmethod
    def from_dict(cls, data: dict) -> 'EditPlan':
        scenes_data = data.get("scenes", [])
        known_fields = {f for f in SceneEdit.__dataclass_fields__}
        scenes = []
        for s in scenes_data:
            # alias 호환
            if "start_sec" in s and "timeline_start" not in s:
                s["timeline_start"] = s["start_sec"]
            if "end_sec" in s and "timeline_end" not in s:
                s["timeline_end"] = s["end_sec"]
            if "duration_sec" in s and "duration" not in s:
                s["duration"] = s["duration_sec"]
            if "asset_start_sec" in s and "source_start" not in s:
                s["source_start"] = s["asset_start_sec"]
            if "asset_end_sec" in s and "source_end" not in s:
                s["source_end"] = s["asset_end_sec"]

            filtered = {k: v for k, v in s.items() if k in known_fields}
            scene = SceneEdit(**filtered)
            scene.validate()
            scenes.append(scene)

        meta_data = data.get("metadata", {})
        known_meta = {f for f in EditPlanMetadata.__dataclass_fields__}
        filtered_meta = {k: v for k, v in meta_data.items() if k in known_meta}
        if "duration" in data and "total_duration_sec" not in filtered_meta:
            filtered_meta["total_duration_sec"] = float(data["duration"])
        meta = EditPlanMetadata(**filtered_meta)

        return cls(scenes=scenes, metadata=meta)

    @classmethod
    def from_json(cls, path: str) -> 'EditPlan':
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def to_debug_markdown(self, path: str = None) -> str:
        """디버그 및 사람이 읽을 수 있는 타임라인 검토 보고서 생성"""
        lines = [
            "# Edit Plan Debug Report",
            "",
            f"**Total Duration**: {self.metadata.total_duration_sec:.2f}s",
            f"**Total Scenes (Shots)**: {self.metadata.total_scenes}",
            f"**Total Beats**: {self.metadata.total_beats}",
            f"**Average Shot Duration**: {self.metadata.avg_shot_duration_sec:.2f}s",
            f"**Hook Shot Avg**: {self.metadata.hook_shot_duration_sec:.2f}s | "
            f"**Body Shot Avg**: {self.metadata.body_shot_duration_sec:.2f}s | "
            f"**CTA Shot Avg**: {self.metadata.cta_shot_duration_sec:.2f}s",
            "",
            "---",
            "",
            "## Timeline Scenes Summary",
            "",
            "| Scene | Beat | Role | Timeline | Shot Dur | Asset | Source Range | Motion | Transition |",
            "|---|---|---|---|---|---|---|---|---|",
        ]

        import os
        for s in self.scenes:
            asset_name = os.path.basename(s.asset_path) if s.asset_path else "None"
            tl_str = f"{s.timeline_start:.2f}s ~ {s.timeline_end:.2f}s"
            src_str = f"{s.source_start:.2f}s ~ {s.source_end:.2f}s"
            lines.append(
                f"| `{s.scene_id}` | `{s.beat_id}` | `{s.role}` | `{tl_str}` | `{s.duration:.2f}s` | "
                f"`{asset_name}` | `{src_str}` | `{s.camera_motion}` | `{s.transition}` |"
            )

        lines.extend([
            "",
            "---",
            "",
            "## Detailed Beat-by-Beat Timeline",
            "",
        ])

        # Beat별로 그룹화
        beat_groups: Dict[str, List[SceneEdit]] = {}
        for s in self.scenes:
            beat_groups.setdefault(s.beat_id, []).append(s)

        for b_id, scenes in beat_groups.items():
            first = scenes[0]
            lines.append(f"### Beat `{b_id}` [{first.role.upper()}] — {len(scenes)} Shot(s)")
            lines.append(f"> **대본**: \"{first.script}\"")
            lines.append(f"> **타임라인**: {scenes[0].timeline_start:.2f}s ~ {scenes[-1].timeline_end:.2f}s (총 {sum(x.duration for x in scenes):.2f}s)")
            lines.append("")
            for idx, s in enumerate(scenes, 1):
                asset_name = os.path.basename(s.asset_path) if s.asset_path else "None"
                lines.append(f"**Shot {idx} (`{s.scene_id}`)**:")
                lines.append(f"- Timeline: `{s.timeline_start:.2f}s ~ {s.timeline_end:.2f}s` (길이: `{s.duration:.2f}s`)")
                lines.append(f"- Asset: `{asset_name}` (Source: `{s.source_start:.2f}s ~ {s.source_end:.2f}s`)")
                lines.append(f"- Camera Motion: `{s.camera_motion}` | Transition: `{s.transition}`")
                lines.append(f"- Importance: `{s.importance:.2f}` | Pacing: `{s.pacing}`")
                if s.emphasis_words:
                    lines.append(f"- Emphasis Words: {s.emphasis_words}")
                if s.reasoning:
                    lines.append(f"- Reasoning: {s.reasoning}")
                lines.append("")

        text = "\n".join(lines)
        if path:
            import os
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        return text
