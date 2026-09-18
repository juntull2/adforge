import os
import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional

HISTORY_FILE_PATH = os.path.join(os.path.dirname(__file__), "outputs", "capcut_history.json")

def _ensure_dir():
    os.makedirs(os.path.dirname(HISTORY_FILE_PATH), exist_ok=True)

def load_project_history(limit: int = 30) -> List[Dict]:
    """저장된 캡컷 프로젝트 생성 이력을 최신순으로 반환합니다."""
    _ensure_dir()
    if not os.path.exists(HISTORY_FILE_PATH):
        return []
    try:
        with open(HISTORY_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                # 최신순 정렬 후 limit개 반환
                data.sort(key=lambda x: x.get("created_at", ""), reverse=True)
                return data[:limit]
    except Exception as e:
        print(f"⚠️ 캡컷 히스토리 로드 실패: {e}")
    return []

def save_project_history(
    project_name: str,
    keyword: str = "",
    product: str = "",
    target: str = "",
    script_text: str = "",
    voice: str = "",
    cut_count: int = 0,
    template: str = ""
) -> Dict:
    """새로운 캡컷 프로젝트 생성 이력을 파일에 영구 기록합니다."""
    _ensure_dir()
    history = load_project_history(limit=200)
    
    new_entry = {
        "id": str(uuid.uuid4())[:8],
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "project_name": project_name,
        "keyword": keyword,
        "product": product,
        "target": target,
        "voice": voice,
        "cut_count": cut_count,
        "template": template,
        "script_preview": (script_text[:100] + "...") if len(script_text) > 100 else script_text,
        "full_script": script_text,
    }
    
    # 맨 앞에 추가
    history.insert(0, new_entry)
    
    # 최대 100개 유지
    history = history[:100]
    
    try:
        with open(HISTORY_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ 캡컷 히스토리 저장 실패: {e}")
        
    return new_entry

def delete_project_history(entry_id: str) -> bool:
    """특정 ID의 이력 항목을 삭제합니다."""
    history = load_project_history(limit=200)
    new_history = [item for item in history if item.get("id") != entry_id]
    if len(new_history) != len(history):
        try:
            with open(HISTORY_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(new_history, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"⚠️ 캡컷 히스토리 삭제 실패: {e}")
    return False

def clear_all_history() -> bool:
    """전체 생성 이력을 초기화합니다."""
    _ensure_dir()
    try:
        with open(HISTORY_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"⚠️ 캡컷 히스토리 초기화 실패: {e}")
        return False
