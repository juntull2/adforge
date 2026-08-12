"""
AdForge V2 — Reference 데이터 모델
네이버 클립 등 레퍼런스 URL/메타데이터만 저장.
영상 파일 다운로드/저장 없음.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
import uuid
from datetime import datetime


@dataclass
class Reference:
    project_id: str
    url: str
    platform: str = "Naver Clip"
    title: str = ""
    category: str = ""
    topic: str = ""
    memo: str = ""
    thumbnail_url: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    # 향후 AI 분석 결과 (구조만 준비, 현재는 저장만)
    analysis_hook: Optional[str] = None
    analysis_estimated_length: Optional[int] = None  # seconds
    analysis_structure: Optional[str] = None
    analysis_tone: Optional[str] = None
    analysis_target: Optional[str] = None
    analysis_topic: Optional[str] = None

    reference_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "reference_id": self.reference_id,
            "project_id": self.project_id,
            "platform": self.platform,
            "url": self.url,
            "title": self.title,
            "category": self.category,
            "topic": self.topic,
            "memo": self.memo,
            "thumbnail_url": self.thumbnail_url or "",
            "tags": ",".join(self.tags),
            "analysis_hook": self.analysis_hook or "",
            "analysis_estimated_length": self.analysis_estimated_length or 0,
            "analysis_structure": self.analysis_structure or "",
            "analysis_tone": self.analysis_tone or "",
            "analysis_target": self.analysis_target or "",
            "analysis_topic": self.analysis_topic or "",
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Reference":
        tags_raw = d.get("tags", "")
        return cls(
            reference_id=d["reference_id"],
            project_id=d["project_id"],
            platform=d.get("platform", "Naver Clip"),
            url=d["url"],
            title=d.get("title", ""),
            category=d.get("category", ""),
            topic=d.get("topic", ""),
            memo=d.get("memo", ""),
            thumbnail_url=d.get("thumbnail_url") or None,
            tags=tags_raw.split(",") if tags_raw else [],
            analysis_hook=d.get("analysis_hook") or None,
            analysis_estimated_length=int(d["analysis_estimated_length"]) if d.get("analysis_estimated_length") else None,
            analysis_structure=d.get("analysis_structure") or None,
            analysis_tone=d.get("analysis_tone") or None,
            analysis_target=d.get("analysis_target") or None,
            analysis_topic=d.get("analysis_topic") or None,
            created_at=d.get("created_at", datetime.now().isoformat()),
        )
