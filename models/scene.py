"""
AdForge V2 — Scene 데이터 모델
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
import uuid
from datetime import datetime


@dataclass
class Scene:
    content_id: str           # 소속 Content Job ID
    order: int                # 장면 번호 (1-based)
    narration: str            # 해당 구간 나레이션/자막
    visual_description: str   # 화면 묘사 (한국어)
    search_keywords: List[str] = field(default_factory=list)  # 영어 검색어
    preferred_source: str = "stock"       # "stock" | "ai_video"
    start_time: float = 0.0
    end_time: float = 0.0
    aspect_ratio: str = "9:16"
    minimum_resolution: str = "1080x1920"

    # Stock 검색 결과
    stock_search_status: str = "pending"  # pending | searching | found | not_found
    stock_asset_id: Optional[str] = None

    # Hailuo
    ai_video_required: bool = False
    ai_video_prompt: Optional[str] = None
    ai_video_status: str = "pending"  # pending | generating | done | failed

    status: str = "draft"  # draft | stock_assigned | ai_assigned | ready

    scene_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "scene_id": self.scene_id,
            "content_id": self.content_id,
            "order": self.order,
            "narration": self.narration,
            "visual_description": self.visual_description,
            "search_keywords": ",".join(self.search_keywords),
            "preferred_source": self.preferred_source,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "aspect_ratio": self.aspect_ratio,
            "minimum_resolution": self.minimum_resolution,
            "stock_search_status": self.stock_search_status,
            "stock_asset_id": self.stock_asset_id or "",
            "ai_video_required": int(self.ai_video_required),
            "ai_video_prompt": self.ai_video_prompt or "",
            "ai_video_status": self.ai_video_status,
            "status": self.status,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Scene":
        kw_raw = d.get("search_keywords", "")
        return cls(
            scene_id=d["scene_id"],
            content_id=d["content_id"],
            order=int(d["order"]),
            narration=d["narration"],
            visual_description=d["visual_description"],
            search_keywords=kw_raw.split(",") if kw_raw else [],
            preferred_source=d.get("preferred_source", "stock"),
            start_time=float(d.get("start_time", 0.0)),
            end_time=float(d.get("end_time", 0.0)),
            aspect_ratio=d.get("aspect_ratio", "9:16"),
            minimum_resolution=d.get("minimum_resolution", "1080x1920"),
            stock_search_status=d.get("stock_search_status", "pending"),
            stock_asset_id=d.get("stock_asset_id") or None,
            ai_video_required=bool(int(d.get("ai_video_required", 0))),
            ai_video_prompt=d.get("ai_video_prompt") or None,
            ai_video_status=d.get("ai_video_status", "pending"),
            status=d.get("status", "draft"),
            created_at=d.get("created_at", datetime.now().isoformat()),
        )
