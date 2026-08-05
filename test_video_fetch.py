import urllib.request
import re
import json

def fetch_pexels_public_videos(query: str, limit: int = 5):
    """
    API 키 없이도 Pexels 웹 페이지에서 세로 숏폼 MP4 릴스 영상 Direct URL을 자동으로 파싱합니다.
    """
    url = f"https://www.pexels.com/ko-kr/search/videos/{urllib.parse.quote(query)}/?orientation=portrait"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    
    try:
        with urllib.request.urlopen(req) as response:
            html = response.read().decode('utf-8')
            # Extract video src MP4 URLs
            video_urls = re.findall(r'https://videos\.pexels\.com/video-files/[^"\']+\.mp4', html)
            # Remove duplicates while preserving order
            seen = set()
            unique_urls = [u for u in video_urls if not (u in seen or seen.add(u))]
            print(f"Found {len(unique_urls)} direct video URLs for '{query}'")
            return unique_urls[:limit]
    except Exception as e:
        print(f"Error fetching videos: {e}")
        return []

if __name__ == "__main__":
    urls = fetch_pexels_public_videos("back pain", limit=5)
    for i, u in enumerate(urls, 1):
        print(f"{i}: {u}")
