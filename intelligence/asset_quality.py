from core.schemas import AssetCandidate
from core.config import config
from core.logging import logger

class AssetQualityGate:
    def __init__(self):
        self.min_w = config.MIN_RESOLUTION_WIDTH
        self.min_h = config.MIN_RESOLUTION_HEIGHT

    def evaluate_and_crop(self, candidate: AssetCandidate) -> bool:
        """
        Evaluate if an asset meets the quality gate for a 9:16 video.
        If it's landscape, determine if it can be safely cropped.
        Updates candidate.is_rejected and candidate.rejection_reason.
        Returns True if it passes.
        """
        target_ratio = 9 / 16.0
        source_ratio = candidate.width / candidate.height if candidate.height > 0 else 1.0

        if candidate.width < 640 or candidate.height < 640:
            candidate.is_rejected = True
            candidate.rejection_reason = f"Resolution too low ({candidate.width}x{candidate.height})"
            return False

        if candidate.orientation == "portrait":
            # If native portrait, just check if it's high enough res
            if candidate.height < 1280: # Just a basic threshold for portrait
                pass # Accept it anyway, we prefer portrait
            return True

        # Landscape processing (Smart Crop evaluation)
        # We need a 9:16 crop out of this landscape.
        # Max crop height is the source height.
        crop_h = candidate.height
        crop_w = int(crop_h * target_ratio)
        
        # Effective resolution check
        # If we need to upscale this crop to 1080x1920, what is the upscale factor?
        # Target output is usually 1080x1920
        upscale_factor = 1920.0 / crop_h
        
        if upscale_factor > 2.5: # Hard limit on upscaling
            candidate.is_rejected = True
            candidate.rejection_reason = f"Required upscale factor {upscale_factor:.2f}x is too high for landscape crop."
            return False
            
        # Optional: AI Reframe detection could go here (Phase 4.1)
        
        return True
