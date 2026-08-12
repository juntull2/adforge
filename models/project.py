"""
AdForge V2 — Project 데이터 모델
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
import uuid
from datetime import datetime


@dataclass
class Project:
    project_name: str
    target_audience: str = "50~70대 시니어"
    platform: str = "Naver Clip"
    content_category: str = "건강 운동"
    tone: str = "친근하고 신뢰감 있는"
    default_video_ratio: str = "9:16"
    default_resolution: str = "1080x1920"
    default_tts: str = "ko-KR-SunHiNeural"
    subtitle_style: str = "default"
    hook_style: str = "WARNING"
    stock_sources: List[str] = field(default_factory=lambda: ["pexels", "pixabay"])
    ai_video_provider: str = "hailuo"
    daily_target: int = 10
    project_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @classmethod
    def default_mombyon(cls) -> "Project":
        """몸편한하루 기본 프로젝트"""
        return cls(
            project_name="몸편한하루",
            target_audience="50~70대 시니어",
            platform="Naver Clip",
            content_category="건강 운동",
            tone="친근하고 신뢰감 있는",
            default_video_ratio="9:16",
            default_resolution="1080x1920",
            default_tts="ko-KR-SunHiNeural",
            subtitle_style="default",
            hook_style="WARNING",
            stock_sources=["pexels", "pixabay"],
            ai_video_provider="hailuo",
            daily_target=10,
        )

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "target_audience": self.target_audience,
            "platform": self.platform,
            "content_category": self.content_category,
            "tone": self.tone,
            "default_video_ratio": self.default_video_ratio,
            "default_resolution": self.default_resolution,
            "default_tts": self.default_tts,
            "subtitle_style": self.subtitle_style,
            "hook_style": self.hook_style,
            "stock_sources": ",".join(self.stock_sources),
            "ai_video_provider": self.ai_video_provider,
            "daily_target": self.daily_target,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        sources = d.get("stock_sources", "pexels,pixabay")
        return cls(
            project_id=d["project_id"],
            project_name=d["project_name"],
            target_audience=d.get("target_audience", "50~70대 시니어"),
            platform=d.get("platform", "Naver Clip"),
            content_category=d.get("content_category", "건강 운동"),
            tone=d.get("tone", "친근하고 신뢰감 있는"),
            default_video_ratio=d.get("default_video_ratio", "9:16"),
            default_resolution=d.get("default_resolution", "1080x1920"),
            default_tts=d.get("default_tts", "ko-KR-SunHiNeural"),
            subtitle_style=d.get("subtitle_style", "default"),
            hook_style=d.get("hook_style", "WARNING"),
            stock_sources=sources.split(",") if isinstance(sources, str) else sources,
            ai_video_provider=d.get("ai_video_provider", "hailuo"),
            daily_target=int(d.get("daily_target", 10)),
            created_at=d.get("created_at", datetime.now().isoformat()),
        )
