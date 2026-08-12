import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

class Config:
    # Base paths
    BASE_DIR = Path(__file__).resolve().parent.parent
    TEMP_AUDIO_DIR = BASE_DIR / "temp_audio"
    
    # Benchmark paths
    BENCHMARK_DIR = BASE_DIR / "benchmark"
    BENCHMARK_RAW_DIR = BENCHMARK_DIR / "raw"
    BENCHMARK_ANALYZED_DIR = BENCHMARK_DIR / "analyzed"
    BENCHMARK_DNA_PATH = BENCHMARK_DIR / "benchmark_dna.json"
    BENCHMARK_INDEX_PATH = BENCHMARK_DIR / "benchmark_index.json"
    
    # API Keys
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not openrouter_key:
        _or_path = BASE_DIR / "openrouter_api_key.txt"
        if _or_path.exists():
            openrouter_key = _or_path.read_text(encoding="utf-8-sig").strip()
    OPENROUTER_API_KEY = openrouter_key

    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if not openai_key:
        _openai_path = BASE_DIR / "openai_api_key.txt"
        if _openai_path.exists():
            openai_key = _openai_path.read_text(encoding="utf-8-sig").strip()
    OPENAI_API_KEY = openai_key
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    
    # Pexels — env first, then txt fallback
    pexels_key = os.environ.get("PEXELS_API_KEY", "")
    if not pexels_key:
        _pexels_path = BASE_DIR / "pexels_api_key.txt"
        if _pexels_path.exists():
            pexels_key = _pexels_path.read_text(encoding="utf-8-sig").strip()
    PEXELS_API_KEY = pexels_key
    
    # Pixabay — env first, then txt fallback
    pixabay_key = os.environ.get("PIXABAY_API_KEY", "")
    if not pixabay_key:
        _pixabay_path = BASE_DIR / "pixabay_api_key.txt"
        if _pixabay_path.exists():
            pixabay_key = _pixabay_path.read_text(encoding="utf-8-sig").strip()
    PIXABAY_API_KEY = pixabay_key
    
    # NVIDIA — env first, then txt fallback
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
    MIN_RESOLUTION_WIDTH = int(os.environ.get("MIN_RESOLUTION_WIDTH", "1080"))
    MIN_RESOLUTION_HEIGHT = int(os.environ.get("MIN_RESOLUTION_HEIGHT", "1080"))

    # Asset Search
    MAX_SEARCH_RETRIES = int(os.environ.get("MAX_SEARCH_RETRIES", "3"))
    VLM_THRESHOLD = int(os.environ.get("VLM_THRESHOLD", "75"))
    VLM_TIMEOUT_SEC = int(os.environ.get("VLM_TIMEOUT_SEC", "20"))

config = Config()

# Ensure necessary directories exist
os.makedirs(config.TEMP_AUDIO_DIR, exist_ok=True)
os.makedirs(config.BENCHMARK_RAW_DIR, exist_ok=True)
os.makedirs(config.BENCHMARK_ANALYZED_DIR, exist_ok=True)

