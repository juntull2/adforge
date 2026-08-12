"""
AdForge V2 — Stock Search Cache
같은 키워드 재검색 방지 (SQLite 기반)
"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional

CACHE_DB = Path(__file__).parent.parent / "stock_cache.db"
CACHE_TTL_HOURS = 24  # 24시간 캐시


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(CACHE_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_cache (
            cache_key   TEXT PRIMARY KEY,
            provider    TEXT,
            keywords    TEXT,
            results     TEXT,
            created_at  TEXT
        )
    """)
    conn.commit()
    return conn


def _make_key(provider: str, keywords: List[str]) -> str:
    return f"{provider}::{','.join(sorted(k.lower() for k in keywords))}"


def get_cached(provider: str, keywords: List[str]) -> Optional[list]:
    """캐시된 결과 반환. 없거나 만료되면 None."""
    key = _make_key(provider, keywords)
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT results, created_at FROM stock_cache WHERE cache_key=?", (key,)
        ).fetchone()
    if not row:
        return None
    # TTL 체크
    created = datetime.fromisoformat(row[1])
    if datetime.now() - created > timedelta(hours=CACHE_TTL_HOURS):
        return None
    return json.loads(row[0])


def set_cache(provider: str, keywords: List[str], results: list) -> None:
    key = _make_key(provider, keywords)
    with _get_conn() as conn:
        conn.execute("""
            INSERT INTO stock_cache VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                results=excluded.results,
                created_at=excluded.created_at
        """, (
            key, provider,
            ",".join(keywords),
            json.dumps(results, ensure_ascii=False),
            datetime.now().isoformat(),
        ))


def clear_cache(provider: Optional[str] = None) -> None:
    with _get_conn() as conn:
        if provider:
            conn.execute("DELETE FROM stock_cache WHERE provider=?", (provider,))
        else:
            conn.execute("DELETE FROM stock_cache")
