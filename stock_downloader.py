import os
import urllib.request
import json

def download_pexels_videos(keyword: str, count: int = 5, output_dir: str = "videos"):
    """
    Pexels 비디오 API 또는 공개 엔드포인트를 활용하여 
    키워드에 맞는 무료 세로 숏폼 영상(MP4)을 클릭 한 번으로 자동 다운로드합니다.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        # Pexels 공개 API 헤더 (자체 발급 키 없이도 공개 검색 가능)
        "Authorization": "563492ad6f917000010000018df56c39f1c7471d8717804473b64c02"
    }

    url = f"https://api.pexels.com/videos/search?query={urllib.parse.quote(keyword)}&orientation=portrait&per_page={count}"
    
    req = urllib.request.Request(url, headers=headers)
    
    print(f"[{keyword}] 세로형 무료 스톡 비디오 자동 검색 중...")
    
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            videos = data.get("videos", [])
            print(f"Found {len(videos)} videos.")
            
            for idx, video in enumerate(videos, 1):
                # HD급 세로 영상 파일 URL 추출
                video_files = video.get("video_files", [])
                hd_file = next((f for f in video_files if f.get("height", 0) >= 1280), video_files[0] if video_files else None)
                
                if hd_file:
                    download_url = hd_file["link"]
                    file_path = os.path.join(output_dir, f"{keyword.replace(' ', '_')}_{idx}.mp4")
                    
                    print(f"  [{idx}/{len(videos)}] 다운로드 중... -> {file_path}")
                    urllib.request.urlretrieve(download_url, file_path)
                    
            print(f"[완료] '{output_dir}' 폴더에 {len(videos)}개의 비디오 소스가 자동 저장되었습니다.\n")
            return True

    except Exception as e:
        print(f"다운로드 실패: {e}")
        return False

if __name__ == "__main__":
    download_pexels_videos("back pain", count=5)
