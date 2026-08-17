from pydantic import BaseModel
from typing import Optional

class UploadJob(BaseModel):
    video_path: str
    title: str
    description: str

class UploadResult(BaseModel):
    platform: str
    status: str  # queued, uploading, processing, published, url_verified, failed
    post_id: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None
