"""
AdForge V2 — SQLite DB 관리자
기존 performance_log.db 와 분리된 별도 DB
"""
import sqlite3
import os
from pathlib import Path
from typing import List, Optional, Dict, Any

DB_PATH = Path(__file__).parent.parent / "adforge_v2.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """DB 초기화 — 최초 실행 시 테이블 생성"""
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            project_id          TEXT PRIMARY KEY,
            project_name        TEXT NOT NULL UNIQUE,
            target_audience     TEXT,
            platform            TEXT,
            content_category    TEXT,
            tone                TEXT,
            default_video_ratio TEXT,
            default_resolution  TEXT,
            default_tts         TEXT,
            subtitle_style      TEXT,
            hook_style          TEXT,
            stock_sources       TEXT,
            ai_video_provider   TEXT,
            daily_target        INTEGER DEFAULT 10,
            created_at          TEXT
        );

        CREATE TABLE IF NOT EXISTS references_tb (
            reference_id                TEXT PRIMARY KEY,
            project_id                  TEXT,
            platform                    TEXT,
            url                         TEXT NOT NULL,
            title                       TEXT,
            category                    TEXT,
            topic                       TEXT,
            memo                        TEXT,
            thumbnail_url               TEXT,
            tags                        TEXT,
            analysis_hook               TEXT,
            analysis_estimated_length   INTEGER DEFAULT 0,
            analysis_structure          TEXT,
            analysis_tone               TEXT,
            analysis_target             TEXT,
            analysis_topic              TEXT,
            created_at                  TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(project_id)
        );

        CREATE TABLE IF NOT EXISTS contents (
            content_id      TEXT PRIMARY KEY,
            project_id      TEXT,
            reference_id    TEXT,
            title           TEXT,
            category        TEXT,
            script          TEXT,
            status          TEXT DEFAULT 'draft',
            created_at      TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(project_id)
        );

        CREATE TABLE IF NOT EXISTS scenes (
            scene_id                TEXT PRIMARY KEY,
            content_id              TEXT,
            "order"                 INTEGER,
            narration               TEXT,
            visual_description      TEXT,
            search_keywords         TEXT,
            preferred_source        TEXT DEFAULT 'stock',
            start_time              REAL DEFAULT 0.0,
            end_time                REAL DEFAULT 0.0,
            aspect_ratio            TEXT DEFAULT '9:16',
            minimum_resolution      TEXT DEFAULT '1080x1920',
            stock_search_status     TEXT DEFAULT 'pending',
            stock_asset_id          TEXT,
            ai_video_required       INTEGER DEFAULT 0,
            ai_video_prompt         TEXT,
            ai_video_status         TEXT DEFAULT 'pending',
            status                  TEXT DEFAULT 'draft',
            created_at              TEXT,
            FOREIGN KEY (content_id) REFERENCES contents(content_id)
        );

        CREATE TABLE IF NOT EXISTS assets (
            asset_id            TEXT PRIMARY KEY,
            local_path          TEXT,
            source              TEXT,
            source_url          TEXT,
            author              TEXT,
            license             TEXT,
            commercial_use      INTEGER DEFAULT 1,
            attribution_required INTEGER DEFAULT 0,
            original_width      INTEGER DEFAULT 0,
            original_height     INTEGER DEFAULT 0,
            duration            REAL DEFAULT 0.0,
            score               INTEGER DEFAULT 0,
            tags                TEXT,
            downloaded_at       TEXT
        );
        """)
    return True


# ─────────────────── PROJECT ───────────────────

def upsert_project(p: dict) -> None:
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO projects VALUES (
                :project_id, :project_name, :target_audience, :platform,
                :content_category, :tone, :default_video_ratio, :default_resolution,
                :default_tts, :subtitle_style, :hook_style, :stock_sources,
                :ai_video_provider, :daily_target, :created_at
            ) ON CONFLICT(project_id) DO UPDATE SET
                project_name        = excluded.project_name,
                target_audience     = excluded.target_audience,
                platform            = excluded.platform,
                content_category    = excluded.content_category,
                tone                = excluded.tone,
                default_video_ratio = excluded.default_video_ratio,
                default_resolution  = excluded.default_resolution,
                default_tts         = excluded.default_tts,
                subtitle_style      = excluded.subtitle_style,
                hook_style          = excluded.hook_style,
                stock_sources       = excluded.stock_sources,
                ai_video_provider   = excluded.ai_video_provider,
                daily_target        = excluded.daily_target
        """, p)


def get_all_projects() -> List[Dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]


def get_project(project_id: str) -> Optional[Dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
        return dict(row) if row else None


def get_project_by_name(name: str) -> Optional[Dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM projects WHERE project_name=?", (name,)).fetchone()
        return dict(row) if row else None


def delete_project(project_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM projects WHERE project_id=?", (project_id,))


# ─────────────────── REFERENCE ───────────────────

def insert_reference(r: dict) -> None:
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO references_tb VALUES (
                :reference_id, :project_id, :platform, :url, :title, :category,
                :topic, :memo, :thumbnail_url, :tags,
                :analysis_hook, :analysis_estimated_length, :analysis_structure,
                :analysis_tone, :analysis_target, :analysis_topic, :created_at
            )
        """, r)


def get_references(project_id: Optional[str] = None) -> List[Dict]:
    with get_conn() as conn:
        if project_id:
            rows = conn.execute(
                "SELECT * FROM references_tb WHERE project_id=? ORDER BY created_at DESC",
                (project_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM references_tb ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]


def delete_reference(reference_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM references_tb WHERE reference_id=?", (reference_id,))


def update_reference_memo(reference_id: str, memo: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE references_tb SET memo=? WHERE reference_id=?", (memo, reference_id))


# ─────────────────── CONTENT ───────────────────

def insert_content(c: dict) -> None:
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO contents VALUES (
                :content_id, :project_id, :reference_id,
                :title, :category, :script, :status, :created_at
            )
        """, c)


def get_contents(project_id: Optional[str] = None) -> List[Dict]:
    with get_conn() as conn:
        if project_id:
            rows = conn.execute(
                "SELECT * FROM contents WHERE project_id=? ORDER BY created_at DESC",
                (project_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM contents ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def update_content_status(content_id: str, status: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE contents SET status=? WHERE content_id=?", (status, content_id))


# ─────────────────── SCENE ───────────────────

def insert_scenes(scenes: List[dict]) -> None:
    with get_conn() as conn:
        conn.executemany("""
            INSERT INTO scenes VALUES (
                :scene_id, :content_id, :order, :narration, :visual_description,
                :search_keywords, :preferred_source, :start_time, :end_time,
                :aspect_ratio, :minimum_resolution, :stock_search_status,
                :stock_asset_id, :ai_video_required, :ai_video_prompt,
                :ai_video_status, :status, :created_at
            )
        """, scenes)


def get_scenes(content_id: str) -> List[Dict]:
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT * FROM scenes WHERE content_id=? ORDER BY "order"',
            (content_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def update_scene(scene_id: str, **kwargs) -> None:
    if not kwargs:
        return
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [scene_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE scenes SET {sets} WHERE scene_id=?", vals)


# ─────────────────── ASSET ───────────────────

def insert_asset(a: dict) -> None:
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO assets VALUES (
                :asset_id, :local_path, :source, :source_url, :author, :license,
                :commercial_use, :attribution_required, :original_width,
                :original_height, :duration, :score, :tags, :downloaded_at
            )
        """, a)


def get_asset(asset_id: str) -> Optional[Dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM assets WHERE asset_id=?", (asset_id,)).fetchone()
        return dict(row) if row else None


def get_all_assets(source: Optional[str] = None) -> List[Dict]:
    with get_conn() as conn:
        if source:
            rows = conn.execute(
                "SELECT * FROM assets WHERE source=? ORDER BY score DESC",
                (source,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM assets ORDER BY score DESC").fetchall()
        return [dict(r) for r in rows]
