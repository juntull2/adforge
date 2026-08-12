import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

class Config:
    # Base paths
    BASE_DIR = Path(__file__).resolve().parent.parent
    TEMP_AUDIO_DIR = BASE_DIR / "temp_audio"
    
    # API Keys
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
    PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")
    
    # Try reading from nv_api_key.txt if env var is empty
    nv_key = os.environ.get("NVIDIA_API_KEY", "")
    if not nv_key:
        nv_key_path = BASE_DIR / "nv_api_key.txt"
        if nv_key_path.exists():
            nv_key = nv_key_path.read_text(encoding="utf-8-sig").strip()
    NVIDIA_API_KEY = nv_key

    # CapCut Settings
    LOCAL_APP_DATA = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
    CAPCUT_DRAFT_PATH = Path(LOCAL_APP_DATA) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"

    # Quality Thresholds
    MIN_RESOLUTION_HEIGHT = int(os.environ.get("MIN_RESOLUTION_HEIGHT", "1080"))
    MIN_RESOLUTION_WIDTH = int(os.environ.get("MIN_RESOLUTION_WIDTH", "1080"))

    # Asset Search
    MAX_SEARCH_RETRIES = int(os.environ.get("MAX_SEARCH_RETRIES", "3"))

config = Config()

# Ensure necessary directories exist
os.makedirs(config.TEMP_AUDIO_DIR, exist_ok=True)
