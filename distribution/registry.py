from typing import Dict, Type
from distribution.base import BaseUploader

_uploaders: Dict[str, BaseUploader] = {}

def register_uploader(platform_name: str, uploader_instance: BaseUploader):
    """
    Registers an uploader instance for a given platform name.
    """
    _uploaders[platform_name] = uploader_instance

def get_uploader(platform_name: str) -> BaseUploader:
    """
    Retrieves the registered uploader for a given platform name.
    """
    return _uploaders.get(platform_name)
