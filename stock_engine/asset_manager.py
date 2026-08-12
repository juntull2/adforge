"""
AdForge V2 — Stock Asset Manager
다운로드된 Asset 메타데이터를 DB에 저장/조회
"""
from __future__ import annotations
from typing import List, Optional

from db.adforge_db import insert_asset, get_asset, get_all_assets
from models.asset import Asset
from stock_engine.base import StockVideoResult


def save_asset(result: StockVideoResult, local_path: str) -> Asset:
    """검색 결과 + 다운로드 경로 → Asset 생성 및 DB 저장"""
    asset = Asset(
        local_path=local_path,
        source=result.provider,
        source_url=result.url,
        author=result.author,
        license=result.license,
        commercial_use=result.commercial_use,
        attribution_required=result.attribution_required,
        original_width=result.width,
        original_height=result.height,
        duration=result.duration,
        score=result.score,
        tags=result.tags,
    )
    insert_asset(asset.to_dict())
    return asset


def get_asset_by_id(asset_id: str) -> Optional[Asset]:
    data = get_asset(asset_id)
    if data:
        return Asset.from_dict(data)
    return None


def list_assets(source: Optional[str] = None) -> List[Asset]:
    rows = get_all_assets(source)
    return [Asset.from_dict(r) for r in rows]
