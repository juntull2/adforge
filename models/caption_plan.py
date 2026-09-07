"""
CaptionPlan 데이터 모델 (STEP 4-1)

광고 영상의 자막 연출 계약(Contract)을 정의하는 내부 데이터 모델.
EditPlan의 SceneEdit 및 TTS Timing을 바탕으로 자막 이벤트, 단어 타이밍,
강조 키워드 및 스타일 계층(Hierarchy)을 표현한다.

파이프라인 아키텍처:
CreativePlan -> EditPlan -> CaptionPlan -> CaptionOSAdapter -> vendor/caption-os (plan.json)
"""

import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Union

VALID_CAPTION_STYLES = frozenset({
    "karaoke", "keyword", "minimal", "kinetic3d", "default"
})

VALID_ROLES = frozenset({
    "hook", "empathy", "agitate", "evidence",
    "solution", "usp", "cta", "transition", "normal"
})

VALID_POSITIONS = frozenset({
    "top", "upper_center", "center", "lower_center", "bottom", "center_bottom"
})


@dataclass
class CaptionWord:
    """단어 단위 자막 타이밍 및 텍스트 모델
    
    caption-os의 line.words 규격: { "w": str, "start": float, "end": float }
    """
    w: str = ""
    start: float = 0.0
    end: float = 0.0

    def to_dict(self) -> dict:
        return {
            "w": self.w,
            "start": round(float(self.start), 3),
            "end": round(float(self.end), 3),
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'CaptionWord':
        return cls(
            w=str(data.get("w", "")),
            start=float(data.get("start", 0.0)),
            end=float(data.get("end", 0.0)),
        )

    def validate(self, raise_error: bool = True) -> List[str]:
        errors = []
        if self.start < 0.0:
            errors.append(f"CaptionWord start ({self.start}) cannot be negative")
        if self.end < self.start:
            errors.append(f"CaptionWord end ({self.end}) cannot be less than start ({self.start})")
        if raise_error and errors:
            raise ValueError(f"CaptionWord validation error: {'; '.join(errors)}")
        return errors


@dataclass
class CaptionEvent:
    """하나의 자막 이벤트 단위 (Shot/Scene에 매핑되는 자막 연출 단위)"""
    scene_id: str = ""
    start: float = 0.0
    end: float = 0.0
    text: str = ""
    words: List[CaptionWord] = field(default_factory=list)
    keywords: List[int] = field(default_factory=list)
    style: str = "karaoke"
    anchor_top: Optional[str] = None
    size: Optional[Union[int, float]] = None
    font: Optional[str] = None
    position: Optional[str] = None
    role: str = "normal"
    emphasis_words: List[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max(0.0, round(self.end - self.start, 3))

    def to_dict(self) -> dict:
        return {
            "scene_id": self.scene_id,
            "start": round(float(self.start), 3),
            "end": round(float(self.end), 3),
            "text": self.text,
            "words": [w.to_dict() for w in self.words],
            "keywords": list(self.keywords),
            "style": self.style,
            "anchor_top": self.anchor_top,
            "size": self.size,
            "font": self.font,
            "position": self.position,
            "role": self.role,
            "emphasis_words": list(self.emphasis_words),
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'CaptionEvent':
        words_raw = data.get("words", [])
        words = []
        for w in words_raw:
            if isinstance(w, dict):
                words.append(CaptionWord.from_dict(w))
            elif isinstance(w, CaptionWord):
                words.append(w)

        return cls(
            scene_id=str(data.get("scene_id", "")),
            start=float(data.get("start", 0.0)),
            end=float(data.get("end", 0.0)),
            text=str(data.get("text", "")),
            words=words,
            keywords=[int(k) for k in data.get("keywords", [])],
            style=str(data.get("style", "karaoke")),
            anchor_top=data.get("anchor_top"),
            size=data.get("size"),
            font=data.get("font"),
            position=data.get("position"),
            role=str(data.get("role", "normal")),
            emphasis_words=list(data.get("emphasis_words", [])),
        )

    def validate(self, raise_error: bool = True) -> List[str]:
        errors = []
        if self.start < 0.0:
            errors.append(f"start ({self.start}) cannot be negative")
        if self.end < self.start:
            errors.append(f"end ({self.end}) cannot be less than start ({self.start})")
        if not self.text or not self.text.strip():
            errors.append("text cannot be empty")

        for idx, k in enumerate(self.keywords):
            if k < 0:
                errors.append(f"keyword index {k} cannot be negative")
            if self.words and k >= len(self.words):
                errors.append(f"keyword index {k} exceeds words length ({len(self.words)})")

        if not self.words and self.keywords:
            errors.append("keywords specified but words list is empty")

        for w_idx, w in enumerate(self.words):
            word_errs = w.validate(raise_error=False)
            for we in word_errs:
                errors.append(f"words[{w_idx}]: {we}")

        if raise_error and errors:
            raise ValueError(f"CaptionEvent validation error: {'; '.join(errors)}")
        return errors


@dataclass
class CaptionPlan:
    """전체 영상의 자막 계획 (AdForge 내부 계약 모델)"""
    lang: str = "ko"
    duration: float = 0.0
    events: List[CaptionEvent] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "lang": self.lang,
            "duration": round(float(self.duration), 3),
            "events": [e.to_dict() for e in self.events],
            "metadata": dict(self.metadata),
        }

    def to_json(self, path: Optional[str] = None, indent: int = 2) -> str:
        text = json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)
        if path:
            import os
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        return text

    @classmethod
    def from_dict(cls, data: dict) -> 'CaptionPlan':
        events_raw = data.get("events", [])
        events = []
        for e in events_raw:
            if isinstance(e, dict):
                events.append(CaptionEvent.from_dict(e))
            elif isinstance(e, CaptionEvent):
                events.append(e)

        return cls(
            lang=str(data.get("lang", "ko")),
            duration=float(data.get("duration", 0.0)),
            events=events,
            metadata=dict(data.get("metadata", {})),
        )

    @classmethod
    def from_json(cls, path: str) -> 'CaptionPlan':
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def validate(self, raise_error: bool = True) -> List[str]:
        errors = []
        if self.duration < 0.0:
            errors.append(f"duration ({self.duration}) cannot be negative")

        for idx, ev in enumerate(self.events):
            ev_errs = ev.validate(raise_error=False)
            for ee in ev_errs:
                errors.append(f"events[{idx}] ({ev.scene_id}): {ee}")
            if self.duration > 0.0 and ev.end > self.duration + 0.05:
                errors.append(f"events[{idx}] end ({ev.end}) exceeds plan duration ({self.duration})")

        if raise_error and errors:
            raise ValueError(f"CaptionPlan validation error: {'; '.join(errors)}")
        return errors

    def to_debug_markdown(self, path: Optional[str] = None) -> str:
        lines = [
            "# Caption Plan Debug Report",
            "",
            f"- **Language**: `{self.lang}`",
            f"- **Total Duration**: `{self.duration:.2f}s`",
            f"- **Total Events**: `{len(self.events)}`",
            "",
            "| # | Scene | Start | End | Dur | Role | Style | Position | Text | Keywords |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for idx, ev in enumerate(self.events):
            kw_tokens = []
            if ev.words and ev.keywords:
                for k in ev.keywords:
                    if 0 <= k < len(ev.words):
                        kw_tokens.append(ev.words[k].w)
            kw_str = ", ".join(kw_tokens) if kw_tokens else "-"
            pos_str = ev.anchor_top or ev.position or "-"
            lines.append(
                f"| {idx+1} | `{ev.scene_id}` | {ev.start:.2f}s | {ev.end:.2f}s | {ev.duration:.2f}s | `{ev.role}` | `{ev.style}` | `{pos_str}` | \"{ev.text}\" | `{kw_str}` |"
            )

        text = "\n".join(lines)
        if path:
            import os
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        return text
