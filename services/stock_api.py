import requests
import urllib.parse
from typing import List, Optional
from core.config import config
from core.schemas import AssetCandidate
from core.logging import logger

class StockAPI:
    def __init__(self):
        self.pexels_key = config.PEXELS_API_KEY
        self.pixabay_key = config.PIXABAY_API_KEY
        self.min_width = config.MIN_RESOLUTION_WIDTH
        self.min_height = config.MIN_RESOLUTION_HEIGHT

    def search_videos(self, query: str, limit: int = 15) -> List[AssetCandidate]:
        candidates = []
        if self.pexels_key:
            candidates.extend(self._search_pexels(query, limit))
        if self.pixabay_key:
            candidates.extend(self._search_pixabay(query, limit))
        
        # Hard Filter by resolution early
        valid_candidates = []
        for c in candidates:
            # We don't blindly reject landscapes here; the AssetQuality gate will handle Smart Crop decisions.
            # Just basic sanity check:
            if c.width >= 640 and c.height >= 640:
                valid_candidates.append(c)
                
        return valid_candidates

    def _search_pexels(self, query: str, limit: int) -> List[AssetCandidate]:
        candidates = []
        headers = {"Authorization": self.pexels_key}
        url = f"https://api.pexels.com/videos/search?query={urllib.parse.quote(query)}&per_page={limit}"
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for v in data.get("videos", []):
                    # Find highest quality video file
                    video_files = v.get("video_files", [])
                    if not video_files:
                        continue
                    
                    # Sort by resolution (width * height)
                    best_file = sorted(video_files, key=lambda x: x.get("width", 0) * x.get("height", 0), reverse=True)[0]
                    
                    orientation = "landscape" if best_file.get("width", 0) > best_file.get("height", 0) else "portrait"
                    
                    candidates.append(AssetCandidate(
                        provider="pexels",
                        asset_id=str(v.get("id")),
                        url=v.get("url"),
                        download_url=best_file.get("link"),
                        width=best_file.get("width", 0),
                        height=best_file.get("height", 0),
                        duration=v.get("duration", 0.0),
                        orientation=orientation
                    ))
        except Exception as e:
            logger.error(f"Pexels API error: {e}")
        return candidates

    def _search_pixabay(self, query: str, limit: int) -> List[AssetCandidate]:
        candidates = []
        url = f"https://pixabay.com/api/videos/?key={self.pixabay_key}&q={urllib.parse.quote(query)}&per_page={min(limit, 20)}"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for v in data.get("hits", []):
                    videos = v.get("videos", {})
                    # Prefer large, then medium
                    best_file = None
                    for quality in ["large", "medium", "small", "tiny"]:
                        if quality in videos and videos[quality].get("url"):
                            best_file = videos[quality]
                            break
                            
                    if not best_file:
                        continue
                        
                    orientation = "landscape" if best_file.get("width", 0) > best_file.get("height", 0) else "portrait"
                    
                    candidates.append(AssetCandidate(
                        provider="pixabay",
                        asset_id=str(v.get("id")),
                        url=v.get("pageURL"),
                        download_url=best_file.get("url"),
                        width=best_file.get("width", 0),
                        height=best_file.get("height", 0),
                        duration=v.get("duration", 0.0),
                        orientation=orientation
                    ))
        except Exception as e:
            logger.error(f"Pixabay API error: {e}")
        return candidates
