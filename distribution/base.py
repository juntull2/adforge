from abc import ABC, abstractmethod
from distribution.models import UploadJob, UploadResult

class BaseUploader(ABC):
    @abstractmethod
    def upload(self, job: UploadJob) -> UploadResult:
        """
        Uploads a video to the specific platform.
        Returns an UploadResult object containing the outcome and URL.
        """
        pass
