import os
import re
import urllib.request

def fetch_and_download_mixkit_stock_videos(query: str = "back pain", count: int = 5, output_dir: str = "stock_videos"):
    """
    API 키나 로그인 필요 없이, Mixkit 무료 상업용 비디오 라이브러리에서
    고화질 스톡 비디오 MP4를 1클릭으로 자동 탐색하고 다운로드합니다.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    url = f"https://mixkit.co/free-stock-video/{query.replace(' ', '-')}/"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    
    print(f"[{query}] 무료 상업용 HD 스톡 비디오 자동 파싱 중...")
    
    try:
        with urllib.request.urlopen(req) as response:
            html = response.read().decode('utf-8')
            # 720p/1080p 고화질 MP4 링크 추출
            video_urls = re.findall(r'https://assets\.mixkit\.co/videos/[^"\']+-720\.mp4', html)
            
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
    # 허리 통증 및 마사지/스트레칭 고화질 비디오 소스 자동 다운로드
    fetch_and_download_mixkit_stock_videos("back pain", count=4)
    fetch_and_download_mixkit_stock_videos("massage", count=4)
