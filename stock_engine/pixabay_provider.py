"""
AdForge V2 — Pixabay Stock Provider
Pixabay API v3 연동 (무료 API Key)
"""
from __future__ import annotations
import os
import requests
from pathlib import Path
from typing import List

from stock_engine.base import BaseStockProvider, StockVideoResult

PIXABAY_API_BASE = "https://pixabay.com/api/videos/"
PIXABAY_LICENSE = "Pixabay License (Free for commercial use, no attribution required)"


class PixabayProvider(BaseStockProvider):
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Pixabay API Key가 필요합니다.")
        self.api_key = api_key

    @property
    def name(self) -> str:
        return "pixabay"

    def search(
        self,
        keywords: List[str],
        per_page: int = 15,
        min_duration: float = 3.0,
        max_duration: float = 30.0,
    ) -> List[StockVideoResult]:
        query = "+".join(keywords[:3])
        results = []

        try:
            resp = requests.get(
                PIXABAY_API_BASE,
                params={
                    "key": self.api_key,
                    "q": query,
                    "per_page": min(per_page, 200),
                    "video_type": "film",        # 실사 영상만
                    "safesearch": "true",
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return []

        for video in data.get("hits", []):
            duration = float(video.get("duration", 0))
            if duration < min_duration or duration > max_duration:
                continue

            videos_dict = video.get("videos", {})
            best = _pick_best_quality_pixabay(videos_dict)
            if not best:
                continue

            w = int(best.get("width", 0))
            h = int(best.get("height", 0))
            if w == 0 or h == 0:
                continue

            tags_raw = video.get("tags", "")
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
            if not tags:
                tags = keywords

            result = StockVideoResult(
                provider="pixabay",
                video_id=str(video.get("id", "")),
                url=video.get("pageURL", ""),
                download_url=best.get("url", ""),
                width=w,
                height=h,
                duration=duration,
                author=video.get("user", ""),
                license=PIXABAY_LICENSE,
                commercial_use=True,
                attribution_required=False,
                thumbnail_url=video.get("picture_id", ""),
                tags=tags,
            )
            results.append(result)

        return results

    def download(self, result: StockVideoResult, dest_dir: str) -> str:
        Path(dest_dir).mkdir(parents=True, exist_ok=True)
        filename = f"pixabay_{result.video_id}_{result.width}x{result.height}.mp4"
        dest_path = str(Path(dest_dir) / filename)

        if os.path.exists(dest_path):
            return dest_path

        with requests.get(result.download_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        return dest_path


def _pick_best_quality_pixabay(videos_dict: dict) -> dict:
    """
    Pixabay는 large, medium, small, tiny 등의 키로 품질 구분
    우선순위: large4K > large > medium > small
    """
    priority = ["large4K", "large", "medium", "small", "tiny"]
    for key in priority:
        v = videos_dict.get(key)
        if v and v.get("url") and int(v.get("width", 0)) > 0:
            return v
    return {}
