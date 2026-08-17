import traceback
from typing import List, Dict
from distribution.models import UploadJob, UploadResult
from distribution.registry import get_uploader

class Orchestrator:
    def __init__(self):
        pass

    def upload(self, job: UploadJob, platforms: List[str]) -> List[UploadResult]:
        """
        Uploads the job to the specified platforms sequentially.
        Isolates failures so that one platform failing doesn't affect others.
        """
        results = []
        for platform in platforms:
            try:
                uploader = get_uploader(platform)
                if not uploader:
                    results.append(UploadResult(
                        platform=platform,
                        status="failed",
                        error="Uploader not found in registry"
                    ))
                    continue
                
                print(f"[Orchestrator] Starting upload for {platform}...")
                result = uploader.upload(job)
                results.append(result)
                print(f"[Orchestrator] Upload for {platform} finished with status: {result.status}")
                
            except Exception as e:
                error_msg = f"{str(e)}\n{traceback.format_exc()}"
                print(f"[Orchestrator] Exception occurred while uploading to {platform}:\n{error_msg}")
                results.append(UploadResult(
                    platform=platform,
                    status="failed",
                    error=str(e)
                ))
        return results
