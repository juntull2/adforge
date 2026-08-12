"""
AdForge V2 — Local Asset Provider
사용자가 직접 다운로드해서 local_assets/ 폴더에 넣은 영상을 검색.
"""
from __future__ import annotations
import os
import json
import subprocess
from pathlib import Path
from typing import List, Optional

from stock_engine.base import BaseStockProvider, StockVideoResult

LOCAL_ASSETS_DIR = Path(__file__).parent.parent / "local_assets"
LOCAL_META_FILE = LOCAL_ASSETS_DIR / "metadata.json"

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


class LocalAssetProvider(BaseStockProvider):
    def __init__(self):
        LOCAL_ASSETS_DIR.mkdir(exist_ok=True)
        self._meta = self._load_meta()

    @property
    def name(self) -> str:
        return "local"

    def _load_meta(self) -> dict:
        if LOCAL_META_FILE.exists():
            with open(LOCAL_META_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_meta(self) -> None:
        with open(LOCAL_META_FILE, "w", encoding="utf-8") as f:
            json.dump(self._meta, f, ensure_ascii=False, indent=2)

    def scan_folder(self) -> List[str]:
        """local_assets/ 폴더를 스캔해서 신규 영상을 메타에 등록"""
        added = []
        for f in LOCAL_ASSETS_DIR.iterdir():
            if f.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            key = f.name
            if key not in self._meta:
                info = _get_video_info(str(f))
                self._meta[key] = {
                    "filename": key,
                    "path": str(f),
                    "width": info.get("width", 0),
                    "height": info.get("height", 0),
                    "duration": info.get("duration", 0.0),
                    "tags": [],
                    "source": "local",
                    "source_url": "",
                    "author": "직접 보유",
                    "license": "Company Asset",
                    "commercial_use": True,
                    "attribution_required": False,
                }
                added.append(key)
        if added:
            self._save_meta()
        return added

    def update_tags(self, filename: str, tags: List[str]) -> None:
        if filename in self._meta:
            self._meta[filename]["tags"] = tags
            self._save_meta()

    def search(
        self,
        keywords: List[str],
        per_page: int = 15,
        min_duration: float = 3.0,
        max_duration: float = 30.0,
    ) -> List[StockVideoResult]:
        kw_lower = {k.lower() for k in keywords}
        results = []

        for key, meta in self._meta.items():
            duration = float(meta.get("duration", 0))
            if duration < min_duration or duration > max_duration:
                continue

            tags = [t.lower() for t in meta.get("tags", [])]
            filename_words = set(Path(key).stem.lower().replace("_", " ").split())
            combined = set(tags) | filename_words

            if not (kw_lower & combined):
                continue  # 키워드 매칭 없으면 제외

            result = StockVideoResult(
                provider="local",
                video_id=key,
                url=meta.get("path", ""),
                download_url=meta.get("path", ""),  # 이미 로컬
                width=int(meta.get("width", 0)),
                height=int(meta.get("height", 0)),
                duration=duration,
                author=meta.get("author", "직접 보유"),
                license=meta.get("license", "Company Asset"),
                commercial_use=bool(meta.get("commercial_use", True)),
                attribution_required=bool(meta.get("attribution_required", False)),
                tags=meta.get("tags", []),
            )
            results.append(result)

        return results

    def download(self, result: StockVideoResult, dest_dir: str) -> str:
        # 로컬 파일이므로 복사하지 않고 원본 경로 반환
        return result.download_url


def _get_video_info(path: str) -> dict:
    """ffprobe로 영상 해상도/길이 추출"""
    try:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {}
        data = json.loads(result.stdout)
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                return {
                    "width": int(stream.get("width", 0)),
                    "height": int(stream.get("height", 0)),
                    "duration": float(stream.get("duration", 0.0)),
                }
    except Exception:
        pass
    return {}
