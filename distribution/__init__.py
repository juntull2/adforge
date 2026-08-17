# distribution module
from distribution.registry import register_uploader
from distribution.naver_clip.uploader import NaverClipUploader

# Register available uploaders
register_uploader("naver_clip", NaverClipUploader())
