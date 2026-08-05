import urllib.request
import re

def fetch_mixkit_videos(query: str, limit: int = 5):
    url = f"https://mixkit.co/free-stock-video/{query.replace(' ', '-')}/"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    
    try:
        with urllib.request.urlopen(req) as response:
            html = response.read().decode('utf-8')
            video_urls = re.findall(r'https://assets\.mixkit\.co/videos/[^"\']+\.mp4', html)
            seen = set()
            unique_urls = [u for u in video_urls if not (u in seen or seen.add(u))]
            print(f"Found {len(unique_urls)} Mixkit video URLs")
            return unique_urls[:limit]
    except Exception as e:
        print(f"Mixkit Error: {e}")
        return []

if __name__ == "__main__":
    urls = fetch_mixkit_videos("back pain", limit=5)
    for i, u in enumerate(urls, 1):
        print(f"{i}: {u}")
