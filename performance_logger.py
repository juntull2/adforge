import sqlite3
import os
from datetime import datetime

DB_PATH = "performance_log.db"

def init_db():
    """성과 기록을 위한 SQLite DB 테이블 초기화"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clip_performance (
            content_id TEXT PRIMARY KEY,
            topic TEXT,
            hook TEXT,
            title TEXT,
            hook_type TEXT,
            visual_hook TEXT,
            expert_present BOOLEAN,
            hashtags TEXT,
            duration INTEGER,
            cta TEXT,
            shopping_tag BOOLEAN,
            upload_datetime TEXT,
            views INTEGER,
            completion_rate REAL,
            likes INTEGER,
            comments INTEGER,
            saves INTEGER,
            shares INTEGER,
            product_clicks INTEGER,
            orders INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    
    # 안전한 스키마 업그레이드 (기존 DB 호환성)
    try:
        cursor.execute("ALTER TABLE clip_performance ADD COLUMN hook_type TEXT;")
        cursor.execute("ALTER TABLE clip_performance ADD COLUMN visual_hook TEXT;")
        cursor.execute("ALTER TABLE clip_performance ADD COLUMN expert_present BOOLEAN;")
        conn.commit()
    except sqlite3.OperationalError:
        pass # 컬럼이 이미 존재함
        
    conn.close()

def log_performance(data: dict):
    """지정된 스키마에 따라 성과 데이터 기록 (NULL 허용)"""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 누락된 키가 있으면 None(NULL)으로 처리
    columns = [
        "content_id", "topic", "hook", "title", "hook_type", "visual_hook", "expert_present", 
        "hashtags", "duration", "cta", "shopping_tag", "upload_datetime", "views", "completion_rate", 
        "likes", "comments", "saves", "shares", "product_clicks", "orders"
    ]
    
    filtered_data = {col: data.get(col, None) for col in columns}
    
    cols_str = ', '.join(filtered_data.keys())
    placeholders = ', '.join(['?' for _ in filtered_data])
    sql = f"INSERT OR REPLACE INTO clip_performance ({cols_str}) VALUES ({placeholders})"
    
    cursor.execute(sql, tuple(filtered_data.values()))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
