"""
Google Drive 연동 모듈 (Service Account 방식)
- Meta 광고 원본 영상 다운로드
- Google Drive 지정 폴더에 자동 업로드
- 공유 가능한 webViewLink 추출
"""

import os
import re
import time
import requests
from typing import Optional, Dict, Any
from urllib.parse import urlparse, parse_qs

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    GOOGLE_DRIVE_AVAILABLE = True
except ImportError:
    GOOGLE_DRIVE_AVAILABLE = False

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]


def extract_folder_id(folder_url_or_id: str) -> str:
    """구글 드라이브 폴더 URL 또는 ID에서 순수 폴더 ID를 추출합니다."""
    if not folder_url_or_id:
        return ""
    text = folder_url_or_id.strip()
    m = re.search(r"folders/([a-zA-Z0-9_-]+)", text)
    if m:
        return m.group(1)
    if "?" in text:
        text = text.split("?")[0]
    return text.strip()


def get_drive_service(credentials_path: str = "service_account.json"):
    """Service Account 또는 OAuth2 사용자 인증 기반 Google Drive API 서비스 인스턴스 반환"""
    if not GOOGLE_DRIVE_AVAILABLE:
        raise ImportError("google-api-python-client 또는 google-auth가 설치되어 있지 않습니다.")

    base_dir = os.path.dirname(os.path.abspath(__file__))

    # 1. OAuth2 사용자 토큰(token.json)이 있으면 최우선 사용 (개인 내 드라이브 업로드 가능)
    token_path = os.path.join(base_dir, "token.json")
    if os.path.exists(token_path):
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            creds = Credentials.from_authorized_user_file(token_path, DRIVE_SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            if creds and creds.valid:
                return build("drive", "v3", credentials=creds, cache_discovery=False)
        except Exception:
            pass

    # 2. Service Account 키 파일 사용
    if not os.path.isabs(credentials_path):
        credentials_path = os.path.join(base_dir, credentials_path)

    if not os.path.exists(credentials_path):
        raise FileNotFoundError(f"서비스 계정 키 파일을 찾을 수 없습니다: {credentials_path}")

    creds = service_account.Credentials.from_service_account_file(
        credentials_path, scopes=DRIVE_SCOPES
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def test_gdrive_folder_access(folder_id_or_url: str, credentials_path: str = "service_account.json") -> Dict[str, Any]:
    """구글 드라이브 폴더 접근 및 업로드 권한을 테스트합니다."""
    folder_id = extract_folder_id(folder_id_or_url)
    if not folder_id:
        return {"ok": False, "error": "폴더 ID 또는 URL이 입력되지 않았습니다."}

    try:
        service = get_drive_service(credentials_path)
        folder = service.files().get(
            fileId=folder_id,
            fields="id, name, capabilities, shared, driveId, owners",
            supportsAllDrives=True
        ).execute()

        can_add = folder.get("capabilities", {}).get("canAddChildren", False)
        folder_name = folder.get("name", "Unknown Folder")
        is_shared_drive = bool(folder.get("driveId"))

        # token.json이 아닌 Service Account를 사용할 때 개인 내 드라이브인 경우 안내
        base_dir = os.path.dirname(os.path.abspath(__file__))
        has_oauth = os.path.exists(os.path.join(base_dir, "token.json"))

        if not can_add:
            return {
                "ok": False,
                "folder_name": folder_name,
                "error": "폴더 조회는 가능하나 쓰기(업로드) 권한이 없습니다. 서비스 계정을 '편집자'로 공유해주세요.",
            }

        if not is_shared_drive and not has_oauth:
            return {
                "ok": False,
                "folder_name": folder_name,
                "is_personal_drive": True,
                "error": "현재 폴더는 개인 '내 드라이브'에 있습니다. Google 정책상 서비스 계정은 용량 할당이 0Byte여서 '공유 드라이브(Shared Drive)' 폴더에서만 업로드가 가능합니다.",
            }

        return {"ok": True, "folder_id": folder_id, "folder_name": folder_name, "is_shared_drive": is_shared_drive}

    except Exception as e:
        err_msg = str(e)
        if "Google Drive API has not been used" in err_msg or "accessNotConfigured" in err_msg:
            # API 활성화 링크 추출
            link_m = re.search(r"https://console\.developers\.google\.com/apis/api/drive\.googleapis\.com[^\s\"]+", err_msg)
            enable_url = link_m.group(0) if link_m else "https://console.cloud.google.com/apis/library/drive.googleapis.com"
            return {
                "ok": False,
                "api_disabled": True,
                "enable_url": enable_url,
                "error": "Google Cloud 프로젝트에서 Google Drive API가 활성화되어 있지 않습니다.",
            }
        if "File not found" in err_msg or "404" in err_msg:
            return {
                "ok": False,
                "error": "폴더를 찾을 수 없습니다. 구글 드라이브 폴더의 '공유'에 서비스 계정 이메일을 추가했는지 확인해주세요.",
            }
        return {"ok": False, "error": err_msg}


def download_video_file(video_url: str, output_path: str, timeout: int = 30) -> bool:
    """메타 CDN 등에서 mp4 영상을 로컬 경로로 스트리밍 다운로드합니다."""
    if not video_url:
        return False

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }
    try:
        with requests.get(video_url, headers=headers, stream=True, timeout=timeout) as resp:
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        print(f"[gdrive_sync] 비디오 다운로드 실패 ({video_url[:60]}...): {e}")
        return False


def upload_video_to_gdrive(
    local_path: str,
    file_name: str,
    folder_id_or_url: str,
    credentials_path: str = "service_account.json",
) -> Dict[str, Any]:
    """
    로컬 비디오 파일을 Google Drive 폴더에 업로드하고 공유 가능한 webViewLink를 반환합니다.
    """
    folder_id = extract_folder_id(folder_id_or_url)
    if not folder_id:
        return {"ok": False, "error": "유효한 구글 드라이브 폴더 ID가 없습니다."}

    if not os.path.exists(local_path):
        return {"ok": False, "error": f"업로드할 파일이 없습니다: {local_path}"}

    try:
        service = get_drive_service(credentials_path)

        file_metadata = {
            "name": file_name,
            "parents": [folder_id],
        }

        media = MediaFileUpload(local_path, mimetype="video/mp4", resumable=True)

        # 1. 파일 업로드
        drive_file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, name, webViewLink, webContentLink",
            supportsAllDrives=True,
        ).execute()

        file_id = drive_file.get("id")

        # 2. 링크가 있는 모든 사용자 읽기 권한 추가 (노션에서 바로 열릴 수 있도록)
        try:
            service.permissions().create(
                fileId=file_id,
                body={"type": "anyone", "role": "reader"},
                fields="id",
                supportsAllDrives=True,
            ).execute()
        except Exception:
            pass  # 조직 정책상 공개가 제한된 경우 폴더 공유 권한 상속

        # webViewLink 재조회 (권한 부여 후 링크)
        view_link = drive_file.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"

        return {
            "ok": True,
            "file_id": file_id,
            "file_name": file_name,
            "web_view_link": view_link,
        }

    except Exception as e:
        err_msg = str(e)
        if "Google Drive API has not been used" in err_msg or "accessNotConfigured" in err_msg:
            return {"ok": False, "error": "Google Cloud에서 Google Drive API 활성화가 필요합니다."}
        return {"ok": False, "error": f"구글 드라이브 업로드 실패: {err_msg}"}
