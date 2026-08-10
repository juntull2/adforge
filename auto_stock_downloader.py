import os
import re
import requests
import urllib.request

def fetch_pexels_portrait_videos(query: str, api_key: str, count: int = 5, output_dir: str = "stock_videos"):
    """
    Pexels API를 이용해 세로(portrait/9:16) 무료 스톡 영상을 검색하고 다운로드합니다.
    orientation=portrait 파라미터로 세로 영상만 필터링합니다.
    """
    os.makedirs(output_dir, exist_ok=True)

    headers = {"Authorization": api_key}
    params = {
        "query": query,
        "orientation": "portrait",
        "per_page": max(count * 2, 10),
        "size": "medium"
    }

    print(f"[Pexels] '{query}' 세로(9:16) 스톡 영상 검색 중...")

    try:
        resp = requests.get(
            "https://api.pexels.com/videos/search",
            headers=headers,
            params=params,
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        videos = data.get("videos", [])

        downloaded = []
        for idx, video in enumerate(videos[:count], 1):
            # height > width 인 portrait 파일 선택
            portrait_files = [
                f for f in video.get("video_files", [])
                if f.get("height", 0) > f.get("width", 0) and f.get("quality") in ("hd", "sd")
            ]
            if not portrait_files:
                portrait_files = sorted(
                    video.get("video_files", []),
                    key=lambda x: x.get("height", 0),
                    reverse=True
                )

            if not portrait_files:
                continue

            file_url = portrait_files[0]["link"]
            file_name = f"{query.replace(' ', '_')}_{idx}.mp4"
            file_path = os.path.join(output_dir, file_name)

            print(f"  [{idx}] 다운로드 중... -> {file_path}")
            urllib.request.urlretrieve(file_url, file_path)
            downloaded.append(file_path)

        print(f"[완료] Pexels 세로 영상 {len(downloaded)}개 저장 완료.\n")
        return downloaded

    except Exception as e:
        print(f"[Pexels 오류] {e}")
        return []


def fetch_and_download_mixkit_stock_videos(query: str = "back pain", count: int = 5, output_dir: str = "stock_videos"):
    """
    Mixkit 무료 스톡 비디오 다운로더 (Pexels API 키 없을 때 Fallback)
    세로 키워드 우선 탐색 후 일반 720p fallback
    """
    os.makedirs(output_dir, exist_ok=True)
    url = f"https://mixkit.co/free-stock-video/{query.replace(' ', '-')}/"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })

    print(f"[Mixkit] '{query}' 무료 상업용 HD 스톡 비디오 자동 파싱 중...")

    try:
        with urllib.request.urlopen(req) as response:
            html = response.read().decode('utf-8')
            # 세로(portrait/vertical) MP4 링크 우선 탐색 — 숏폼 9:16 전용
            portrait_urls = re.findall(r'https://assets\.mixkit\.co/videos/[^"\']*(?:vertical|portrait|mobile|9x16|story)[^"\']*-720\.mp4', html)
            # fallback: 일반 720p
            all_urls = re.findall(r'https://assets\.mixkit\.co/videos/[^"\']+?-720\.mp4', html)

            video_urls = portrait_urls + all_urls
            seen = set()
            unique_urls = [u for u in video_urls if not (u in seen or seen.add(u))]
            target_urls = unique_urls[:count]
            print(f"Found {len(target_urls)} HD stock video files.")

            downloaded_files = []
            for idx, video_url in enumerate(target_urls, 1):
                file_name = f"{query.replace(' ', '_')}_{idx}.mp4"
                file_path = os.path.join(output_dir, file_name)
                print(f"  [{idx}/{len(target_urls)}] 다운로드 중... -> {file_path}")
                urllib.request.urlretrieve(video_url, file_path)
                downloaded_files.append(file_path)

            print(f"[완료] '{output_dir}' 폴더에 {len(downloaded_files)}개의 비디오 소스가 자동 저장되었습니다.\n")
            return downloaded_files

    except Exception as e:
        print(f"다운로드 에러: {e}")
        return []


if __name__ == "__main__":
    # Pexels API 키가 있으면 세로 영상 우선 다운로드
    # fetch_pexels_portrait_videos("back pain", api_key="YOUR_PEXELS_KEY", count=4)
    fetch_and_download_mixkit_stock_videos("back pain", count=4)
    fetch_and_download_mixkit_stock_videos("massage", count=4)

