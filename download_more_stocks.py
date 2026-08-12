import os
import sys

# c:\adforge 경로 추가
sys.path.insert(0, r"c:\adforge")

from auto_stock_downloader import fetch_and_download_mixkit_stock_videos, fetch_pexels_portrait_videos, fetch_pixabay_portrait_videos

def main():
    stock_dir = r"c:\adforge\stock_videos"
    os.makedirs(stock_dir, exist_ok=True)
    
    # API 키 읽기
    pexels_key = ""
    pixabay_key = ""
    
    if os.path.exists(r"c:\adforge\pexels_api_key.txt"):
        with open(r"c:\adforge\pexels_api_key.txt", "r", encoding="utf-8-sig") as f:
            pexels_key = f.read().strip()
            
    if os.path.exists(r"c:\adforge\pixabay_api_key.txt"):
        with open(r"c:\adforge\pixabay_api_key.txt", "r", encoding="utf-8-sig") as f:
            pixabay_key = f.read().strip()

    keywords = [
        "senior exercise",
        "elderly stretching",
        "back pain relief",
        "senior yoga",
        "older adult workout",
        "gentle movement",
        "senior fitness",
        "healthy lifestyle",
        "stretching",
        "massage",
        "leg workout",
        "yoga",
        "meditation",
        "morning routine"
    ]
    
    # 각 키워드당 10개씩 시도하여 100개 이상 채우기
    count_per_source = 7 
    
    for kw in keywords:
        print(f"Downloading for keyword: {kw}")
        
        # Pexels
        if pexels_key:
            try:
                fetch_pexels_portrait_videos(kw, api_key=pexels_key, count=count_per_source, output_dir=stock_dir)
            except Exception as e:
                print(f"Pexels Error for {kw}: {e}")
                
        # Pixabay
        if pixabay_key:
            try:
                fetch_pixabay_portrait_videos(kw, api_key=pixabay_key, count=count_per_source, output_dir=stock_dir)
            except Exception as e:
                print(f"Pixabay Error for {kw}: {e}")
                
        # Mixkit
        try:
            fetch_and_download_mixkit_stock_videos(kw, count=3, output_dir=stock_dir)
        except Exception as e:
            print(f"Mixkit Error for {kw}: {e}")
            
    print("Done downloading MASSIVE stock videos.")

if __name__ == "__main__":
    main()
