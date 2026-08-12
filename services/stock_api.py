import requests
import urllib.parse
from typing import List
from core.config import config
from core.schemas import AssetCandidate
from core.logging import logger

class StockAPI:
    def __init__(self):
        self.pexels_key = config.PEXELS_API_KEY
        self.pixabay_key = config.PIXABAY_API_KEY
        self.min_width = config.MIN_RESOLUTION_WIDTH
        self.min_height = config.MIN_RESOLUTION_HEIGHT

    def search_videos(self, query: str, limit: int = 30) -> List[AssetCandidate]:
        candidates = []
        if self.pexels_key:
            candidates.extend(self._search_pexels(query, limit))
        if self.pixabay_key:
            # Pixabay returns max 200 per page, but we'll limit to `limit`
            candidates.extend(self._search_pixabay(query, limit))
        
        # Hard Filter by resolution early
        valid_candidates = []
        for c in candidates:
            # We don't blindly reject landscapes here; the AssetQuality gate will handle Smart Crop decisions.
            # Just basic sanity check:
            if c.width >= 640 and c.height >= 640:
                valid_candidates.append(c)
                
        # Primary Sorting:
        # 1. Native Portrait (w < h, h >= 1920)
        # 2. Portrait (w < h, h < 1920)
        # 3. High-res Landscape (w > h, w >= 1920)
        # 4. Crop Landscape (w > h, w < 1920)
        def get_sort_key(c: AssetCandidate):
            if c.orientation == "portrait":
                if c.height >= 1920: return 1
                return 2
            else:
                if c.width >= 1920: return 3
                return 4

        valid_candidates.sort(key=get_sort_key)
        
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
                    thumbnail = v.get("image")
                    
                    # Try to extract multiple thumbnail frames if available
                    thumbnail_urls = [thumbnail] if thumbnail else []
                    for pic in v.get("video_pictures", []):
                        if pic.get("picture"):
                            thumbnail_urls.append(pic.get("picture"))
                    thumbnail_urls = list(dict.fromkeys(thumbnail_urls))[:3] # Up to 3 unique frames
                    
                    candidates.append(AssetCandidate(
                        provider="pexels",
                        asset_id=str(v.get("id")),
                        title=", ".join(v.get("tags", [])) if "tags" in v else "",
                        url=v.get("url"),
                        download_url=best_file.get("link"),
                        thumbnail_url=thumbnail,
                        thumbnail_urls=thumbnail_urls,
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
                    
                    # Pixabay returns a picture_id. We can try to construct a vimeo thumbnail URL.
                    # This is a bit of a hack, but works for Pixabay.
                    picture_id = v.get("picture_id")
                    thumbnail = f"https://i.vimeocdn.com/video/{picture_id}_640x360.jpg" if picture_id else None
                    thumbnail_urls = [thumbnail] if thumbnail else []
                    
                    candidates.append(AssetCandidate(
                        provider="pixabay",
                        asset_id=str(v.get("id")),
                        title=v.get("tags", ""),
                        url=v.get("pageURL"),
                        download_url=best_file.get("url"),
                        thumbnail_url=thumbnail,
                        thumbnail_urls=thumbnail_urls,
                        width=best_file.get("width", 0),
                        height=best_file.get("height", 0),
                        duration=v.get("duration", 0.0),
                        orientation=orientation
                    ))
        except Exception as e:
            logger.error(f"Pixabay API error: {e}")
        return candidates
