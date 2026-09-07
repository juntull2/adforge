"""
Asset 데이터 모델

로컬 영상/이미지 에셋의 기술적 속성(해상도, fps, 길이, orientation)과
의미론적 속성(subject, action, environment, emotion, tags, marketing_roles),
그리고 매칭 결과(MatchResult)를 정의한다.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Tuple, Optional
import json
import os
import hashlib


@dataclass
class AssetMetadata:
    """단일 미디어 에셋(영상/이미지)의 기술적 및 의미론적 메타데이터"""

    id: str = ""
    file_path: str = ""
    file_name: str = ""
    media_type: str = "video"  # "video" | "image"

    # 기술적 속성 (FFprobe 기반)
    width: int = 0
    height: int = 0
    duration_sec: float = 0.0
    fps: float = 30.0
    orientation: str = "vertical_9_16"  # "vertical_9_16" | "horizontal_16_9" | "square_1_1" | "other"

    # 의미론적 속성 (파일명/디렉토리 파싱, VLM 또는 태그 기반)
    subject: List[str] = field(default_factory=list)          # 예: ["senior", "woman", "spine", "back"]
    action: List[str] = field(default_factory=list)           # 예: ["stretching", "yoga", "exercise", "pain"]
    environment: List[str] = field(default_factory=list)      # 예: ["indoor", "clinic", "living_room"]
    emotion: List[str] = field(default_factory=list)          # 예: ["pain", "relief", "active", "frustration"]
    shot_type: str = "any"                                   # "closeup", "medium", "wide", "detail", "any"
    marketing_roles: List[str] = field(default_factory=list)  # ["hook", "empathy", "solution", "usp", "cta"]
    tags: List[str] = field(default_factory=list)             # 검색 키워드 (영문 + 한글)

    # 하이라이트 구간 (시작초, 종료초) 목록
    highlight_ranges: List[List[float]] = field(default_factory=list)

    # 시각적 품질 점수 (0.0 ~ 1.0)
    visual_quality: float = 0.8

    def validate(self) -> 'AssetMetadata':
        """종횡비 및 기본 하이라이트 구간 보정"""
        if not self.id and self.file_path:
            self.id = hashlib.md5(self.file_path.encode("utf-8")).hexdigest()[:12]

        if not self.file_name and self.file_path:
            self.file_name = os.path.basename(self.file_path)

        if self.width > 0 and self.height > 0:
            ratio = self.width / self.height
            if 0.5 <= ratio <= 0.65:
                self.orientation = "vertical_9_16"
            elif 1.6 <= ratio <= 1.9:
                self.orientation = "horizontal_16_9"
            elif 0.9 <= ratio <= 1.1:
                self.orientation = "square_1_1"
            else:
                self.orientation = "other"

        if not self.highlight_ranges and self.duration_sec > 0:
            # 기본 하이라이트: 시작 0.5초(안정화 후) ~ min(duration, 4.5초)
            start = 0.5 if self.duration_sec >= 3.0 else 0.0
            end = min(self.duration_sec, start + 4.0)
            self.highlight_ranges = [[round(start, 2), round(end, 2)]]

        return self

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'AssetMetadata':
        known = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known}
        obj = cls(**filtered)
        obj.validate()
        return obj


@dataclass
class MatchResult:
    """SceneBeat에 매칭된 에셋 결과 및 8차원 평가 점수"""

    beat_id: str = ""
    asset_id: str = ""
    asset_path: str = ""
    total_score: float = 0.0

    # 8차원 점수 상세 내역
    breakdown: Dict[str, float] = field(default_factory=dict)

    # 추천 하이라이트 구간 [시작초, 종료초]
    highlight_range: List[float] = field(default_factory=lambda: [0.0, 0.0])

    # 매칭 사유 설명 (디버깅 / 시각화용)
    reasoning: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
