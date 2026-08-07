import os

class Config:
    """
    AdForge Centralized Configuration
    """
    APP_NAME = "AdForge: Naver Clip Creative OS"
    VERSION = "v3.0.0-architecture"
    
    # Base paths
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    AGENTS_DIR = os.path.join(BASE_DIR, "agents")
    PROMPTS_DIR = os.path.join(BASE_DIR, "prompts")
    
    # DB & Memory paths
    MEMORY_DB_PATH = os.path.join(AGENTS_DIR, "creative_memory.db")
    MEMORY_JSON_PATH = os.path.join(AGENTS_DIR, "creative_memory.json")
    
    # Scoring Thresholds
    SEO_PASS_SCORE_THRESHOLD = 80
    MAX_RETRY_ATTEMPTS = 3
    
    # Brand default links
    DAPIDA_STORE_LINK = "https://smartstore.naver.com/all-envy/products/12566869835"
    PAULINA_STORE_LINK = "https://smartstore.naver.com/martinishop/products/7095386764"

config = Config()
