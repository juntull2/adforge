"""
AdForge V2 — Asset 데이터 모델
Stock 영상 메타데이터 (라이선스 포함)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
import uuid
from datetime import datetime


@dataclass
class Asset:
    local_path: str
    source: str                   # "pexels" | "pixabay" | "local" | "hailuo"
    source_url: str = ""
    author: str = ""
    license: str = ""
    commercial_use: bool = True
    attribution_required: bool = False
    original_width: int = 0
    original_height: int = 0
    duration: float = 0.0         # seconds
    score: int = 0                # Stock Scoring 점수
    tags: List[str] = field(default_factory=list)
    asset_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    downloaded_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def aspect_ratio(self) -> str:
        if self.original_height == 0:
            return "unknown"
        ratio = self.original_width / self.original_height
        if abs(ratio - 9/16) < 0.05:
            return "9:16"
        elif abs(ratio - 16/9) < 0.05:
            return "16:9"
        elif abs(ratio - 1.0) < 0.05:
            return "1:1"
        return f"{self.original_width}:{self.original_height}"

    @property
    def is_vertical(self) -> bool:
        return self.original_width < self.original_height

    @property
    def resolution_label(self) -> str:
        if self.original_height >= 2160:
            return "4K"
        elif self.original_height >= 1080:
            return "1080p"
        elif self.original_height >= 720:
            return "720p"
        return f"{self.original_height}p"

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "local_path": self.local_path,
            "source": self.source,
            "source_url": self.source_url,
            "author": self.author,
            "license": self.license,
            "commercial_use": int(self.commercial_use),
            "attribution_required": int(self.attribution_required),
            "original_width": self.original_width,
            "original_height": self.original_height,
            "duration": self.duration,
            "score": self.score,
            "tags": ",".join(self.tags),
            "downloaded_at": self.downloaded_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Asset":
        tags_raw = d.get("tags", "")
        return cls(
            asset_id=d["asset_id"],
            local_path=d["local_path"],
            source=d["source"],
            source_url=d.get("source_url", ""),
            author=d.get("author", ""),
            license=d.get("license", ""),
            commercial_use=bool(int(d.get("commercial_use", 1))),
            attribution_required=bool(int(d.get("attribution_required", 0))),
            original_width=int(d.get("original_width", 0)),
            original_height=int(d.get("original_height", 0)),
            duration=float(d.get("duration", 0.0)),
            score=int(d.get("score", 0)),
            tags=tags_raw.split(",") if tags_raw else [],
            downloaded_at=d.get("downloaded_at", datetime.now().isoformat()),
        )
