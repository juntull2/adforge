"""
AdForge V2 — Pexels Stock Provider
Pexels API v1 연동
"""
from __future__ import annotations
import os
import re
import requests
from pathlib import Path
from typing import List

from stock_engine.base import BaseStockProvider, StockVideoResult
from stock_engine.scorer import rank_results

PEXELS_API_BASE = "https://api.pexels.com/videos"
PEXELS_LICENSE = "Pexels License (Free, no attribution required)"


class PexelsProvider(BaseStockProvider):
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Pexels API Key가 필요합니다.")
        self.api_key = api_key
        self._session = requests.Session()
        self._session.headers.update({"Authorization": self.api_key})

    @property
    def name(self) -> str:
        return "pexels"

    def search(
        self,
        keywords: List[str],
        per_page: int = 15,
        min_duration: float = 3.0,
        max_duration: float = 30.0,
    ) -> List[StockVideoResult]:
        query = " ".join(keywords[:3])  # 최대 3개 키워드 조합
        results = []

        try:
            resp = self._session.get(
                f"{PEXELS_API_BASE}/search",
                params={
                    "query": query,
                    "per_page": per_page,
                    "orientation": "portrait",   # 세로 영상 우선
                    "size": "large",             # 고화질 우선
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            # 세로 필터 없이 재시도
            try:
                resp = self._session.get(
                    f"{PEXELS_API_BASE}/search",
                    params={"query": query, "per_page": per_page},
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                return []

        for video in data.get("videos", []):
            duration = float(video.get("duration", 0))
            if duration < min_duration or duration > max_duration:
                continue

            # 최고화질 파일 선택
            video_files = video.get("video_files", [])
            best_file = _pick_best_quality(video_files)
            if not best_file:
                continue

            author = video.get("user", {}).get("name", "")
            tags = [t.get("title", "") for t in video.get("tags", [])]
            # 태그가 없으면 검색어를 태그로 사용 (스코어링에 활용)
            if not tags:
                tags = keywords

            result = StockVideoResult(
                provider="pexels",
                video_id=str(video.get("id", "")),
                url=video.get("url", ""),
                download_url=best_file.get("link", ""),
                width=int(best_file.get("width", 0)),
                height=int(best_file.get("height", 0)),
                duration=duration,
                author=author,
                license=PEXELS_LICENSE,
                commercial_use=True,
                attribution_required=False,
                thumbnail_url=video.get("image", ""),
                tags=tags,
            )
            results.append(result)

        return results

    def download(self, result: StockVideoResult, dest_dir: str) -> str:
        Path(dest_dir).mkdir(parents=True, exist_ok=True)
        filename = f"pexels_{result.video_id}_{result.width}x{result.height}.mp4"
        dest_path = str(Path(dest_dir) / filename)

        if os.path.exists(dest_path):
            return dest_path  # 이미 다운로드된 경우 캐시 사용

        with self._session.get(result.download_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        return dest_path


def _pick_best_quality(video_files: list) -> dict:
    """
    파일 목록에서 최고화질을 선택.
    우선순위: 9:16 + 4K > 9:16 + 1080p > 16:9 + 4K > 16:9 + 1080p
    """
    if not video_files:
        return {}

    def priority(f):
        w = int(f.get("width", 0))
        h = int(f.get("height", 0))
        is_vertical = w < h if w > 0 and h > 0 else False
        res = h
        return (is_vertical, res)

    valid = [f for f in video_files if f.get("link") and f.get("width") and f.get("height")]
    if not valid:
        return video_files[0] if video_files else {}

    return max(valid, key=priority)
