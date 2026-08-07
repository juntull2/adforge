from agents.base import BaseAgent
from config import config
import sqlite3
import os
import json

class CreativeMemoryAgent(BaseAgent):
    """
    CreativeMemoryAgent (agents/memory.py) - AdForge Signature Engine
    BaseAgent 상속 및 SQLite3 데이터베이스 기반 성과 아카이빙 & Top 20 고효율 쿼리 튜닝
    """
    def __init__(self):
        super().__init__("CreativeMemoryAgent")
        self.db_path = config.MEMORY_DB_PATH
        self._init_db()

    def _init_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS creative_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hook TEXT NOT NULL,
                    cta TEXT NOT NULL,
                    tags TEXT,
                    ctr REAL,
                    cvr REAL,
                    weight REAL DEFAULT 1.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[Creative Memory Warning] DB init error: {e}")

    def run(self, context: dict) -> dict:
        # PerformanceAgent의 성과 데이터가 넘어온 경우 쿼리 업데이트
        perf = context.get("performance", {})
        if perf and perf.get("is_high_performer"):
            metrics = perf.get("metrics", {})
            self.record_memory(
                hook=perf.get("tracked_hook", ""),
                cta=perf.get("tracked_cta", ""),
                tags=context.get("keyword", {}).get("seo_tags", ""),
                ctr=metrics.get("ctr", 4.0),
                cvr=metrics.get("cvr", 2.5)
            )

        context["memory"] = self.get_top_performing_memories(limit=20)
        return context

    def record_memory(self, hook: str, cta: str, tags: str, ctr: float, cvr: float):
        """
        새로운 고효율 성과 기록 저장
        """
        weight = round(1.0 + (ctr / 20.0), 2)
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO creative_memory (hook, cta, tags, ctr, cvr, weight)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (hook, cta, tags, ctr, cvr, weight))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[Creative Memory Warning] DB record error: {e}")

    def get_top_performing_memories(self, limit: int = 20) -> dict:
        """
        SQLite3 SQL Query로 CTR / CVR 높은 TOP N 기억 인텔리전스 인출
        """
        top_hooks = []
        top_ctas = []
        total_logs = 0

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT hook, ctr, weight FROM creative_memory ORDER BY ctr DESC LIMIT ?", (limit,))
            for row in cursor.fetchall():
                top_hooks.append({"hook": row[0], "ctr_avg": f"{row[1]}%", "score_weight": row[2]})

            cursor.execute("SELECT cta, cvr FROM creative_memory ORDER BY cvr DESC LIMIT ?", (limit,))
            for row in cursor.fetchall():
                top_ctas.append({"cta": row[0], "cvr_avg": f"{row[1]}%"})

            cursor.execute("SELECT COUNT(*) FROM creative_memory")
            total_logs = cursor.fetchone()[0]
            conn.close()
        except Exception as e:
            print(f"[Creative Memory Warning] DB query error: {e}")

        return {
            "top_hooks": top_hooks,
            "top_ctas": top_ctas,
            "total_remembered_logs": total_logs
        }
