import os
import re
import requests
import urllib.request
import shutil

def translate_ko_to_en(text: str) -> str:
    import re
    if not re.search('[가-힣]', text):
        return text
    try:
        import urllib.request, urllib.parse, json
        url = f'https://translate.googleapis.com/translate_a/single?client=gtx&sl=ko&tl=en&dt=t&q={urllib.parse.quote(text)}'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as r:
            response = json.loads(r.read().decode('utf-8'))
            return response[0][0][0]
    except Exception as e:
        print(f"Translation failed: {e}")
        return text

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
            try:
                with requests.get(file_url, stream=True, timeout=30, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}) as r:
                    r.raise_for_status()
                    with open(file_path, 'wb') as f:
                        shutil.copyfileobj(r.raw, f)
                downloaded.append(file_path)
            except Exception as e:
                print(f"  [{idx}] 다운로드 실패: {e}")
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
    english_query = translate_ko_to_en(query)
    import urllib.parse
    encoded_query = urllib.parse.quote(english_query.replace(' ', '-'))
    url = f"https://mixkit.co/free-stock-video/{encoded_query}/"
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

            if len(target_urls) == 0 and query.lower() not in ["fitness", "workout", "background"]:
                print("No specific results found in Mixkit. Falling back to generic 'fitness' videos.")
                return fetch_and_download_mixkit_stock_videos("fitness", count, output_dir)

            downloaded_files = []
            for idx, video_url in enumerate(target_urls, 1):
                file_name = f"{query.replace(' ', '_')}_{idx}.mp4"
                file_path = os.path.join(output_dir, file_name)
                print(f"  [{idx}/{len(target_urls)}] 다운로드 중... -> {file_path}")
                try:
                    with requests.get(video_url, stream=True, timeout=30, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}) as r:
                        r.raise_for_status()
                        with open(file_path, 'wb') as f:
                            shutil.copyfileobj(r.raw, f)
                    downloaded_files.append(file_path)
                except Exception as e:
                    print(f"  [{idx}/{len(target_urls)}] 다운로드 실패: {e}")

            print(f"[완료] '{output_dir}' 폴더에 {len(downloaded_files)}개의 비디오 소스가 자동 저장되었습니다.\n")
            return downloaded_files

    except Exception as e:
        print(f"다운로드 에러: {e}")
        return []

def fetch_pixabay_portrait_videos(query: str, api_key: str, count: int = 5, output_dir: str = "stock_videos"):
    """
    Pixabay API를 이용해 무료 스톡 영상을 검색하고 다운로드합니다.
    """
    if not api_key:
        return []
        
    os.makedirs(output_dir, exist_ok=True)
    english_query = translate_ko_to_en(query)
    import urllib.parse
    
    print(f"[Pixabay] '{english_query}' 스톡 영상 검색 중...")
    
    try:
        url = f"https://pixabay.com/api/videos/?key={api_key}&q={urllib.parse.quote(english_query)}&video_type=film&per_page={max(count * 2, 10)}"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        hits = data.get("hits", [])
        
        downloaded = []
        for idx, hit in enumerate(hits[:count], 1):
            videos = hit.get("videos", {})
            # 가장 화질이 좋은 세로(portrait)나 모바일 사이즈, 혹은 medium 찾기
            best_video = videos.get("large") or videos.get("medium") or videos.get("small")
            
            if not best_video or not best_video.get("url"):
                continue
                
            file_url = best_video["url"]
            file_name = f"pixabay_{query.replace(' ', '_')}_{idx}.mp4"
            file_path = os.path.join(output_dir, file_name)
            
            print(f"  [{idx}] 다운로드 중... -> {file_path}")
            try:
                with requests.get(file_url, stream=True, timeout=30, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}) as r:
                    r.raise_for_status()
                    with open(file_path, 'wb') as f:
                        shutil.copyfileobj(r.raw, f)
                downloaded.append(file_path)
            except Exception as e:
                print(f"  [{idx}] 다운로드 실패: {e}")
            
        print(f"[완료] Pixabay 영상 {len(downloaded)}개 저장 완료.\n")
        return downloaded
    except Exception as e:
        print(f"[Pixabay 오류] {e}")
        return []


if __name__ == "__main__":
    # Pexels API 키가 있으면 세로 영상 우선 다운로드
    # fetch_pexels_portrait_videos("back pain", api_key="YOUR_PEXELS_KEY", count=4)
    fetch_and_download_mixkit_stock_videos("back pain", count=4)
    fetch_and_download_mixkit_stock_videos("massage", count=4)

