"""
AdForge V2 — Stock Provider 추상 기본 클래스
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Dict, Optional


class StockVideoResult:
    """개별 검색 결과"""
    def __init__(
        self,
        provider: str,
        video_id: str,
        url: str,             # 재생 URL (미리보기)
        download_url: str,    # 실제 다운로드 URL
        width: int,
        height: int,
        duration: float,      # seconds
        author: str = "",
        license: str = "",
        commercial_use: bool = True,
        attribution_required: bool = False,
        thumbnail_url: str = "",
        tags: List[str] = None,
    ):
        self.provider = provider
        self.video_id = video_id
        self.url = url
        self.download_url = download_url
        self.width = width
        self.height = height
        self.duration = duration
        self.author = author
        self.license = license
        self.commercial_use = commercial_use
        self.attribution_required = attribution_required
        self.thumbnail_url = thumbnail_url
        self.tags = tags or []
        self.score: int = 0   # Scorer가 채워줌

    @property
    def aspect_ratio(self) -> float:
        if self.height == 0:
            return 0.0
        return self.width / self.height

    @property
    def is_vertical(self) -> bool:
        return self.width < self.height

    @property
    def resolution_label(self) -> str:
        if self.height >= 2160:
            return "4K"
        elif self.height >= 1080:
            return "1080p"
        elif self.height >= 720:
            return "720p"
        return f"{self.height}p"

    def __repr__(self) -> str:
        return (f"<StockVideoResult {self.provider}:{self.video_id} "
                f"{self.width}x{self.height} {self.duration:.1f}s score={self.score}>")


class BaseStockProvider(ABC):
    """모든 Stock Provider의 공통 인터페이스"""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def search(
        self,
        keywords: List[str],
        per_page: int = 15,
        min_duration: float = 3.0,
        max_duration: float = 30.0,
    ) -> List[StockVideoResult]:
        """키워드로 영상 검색, 결과 반환"""
        ...

    @abstractmethod
    def download(
        self,
        result: StockVideoResult,
        dest_dir: str,
    ) -> str:
        """영상 다운로드, 저장된 로컬 경로 반환"""
        ...
