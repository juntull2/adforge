from core.schemas import AssetCandidate, CropQualityResult
from core.config import config
from core.logging import logger

class AssetQualityGate:
    def __init__(self):
        self.min_width = config.MIN_RESOLUTION_WIDTH
        self.min_height = config.MIN_RESOLUTION_HEIGHT
        
        # We target 1080x1920 (9:16)
        self.target_w = 1080
        self.target_h = 1920

    def evaluate_asset(self, asset: AssetCandidate) -> CropQualityResult:
        """
        Evaluate if an asset meets the 9:16 high-quality standard.
        Calculates effective resolution and upscale factor if cropping is needed.
        """
        w = asset.width
        h = asset.height
        
        if w == 0 or h == 0:
            return CropQualityResult(
                source_width=w, source_height=h, crop_width=0, crop_height=0,
                effective_resolution="0x0", upscale_factor=0, passes_quality=False,
                rejection_reason="Invalid resolution (0x0)"
            )
            
        # 1. Native Portrait
        if h > w:
            aspect = h / w
            target_aspect = self.target_h / self.target_w # 1.777...
            
            # If it's already 9:16 or close
            if abs(aspect - target_aspect) < 0.1:
                upscale = max(1.0, self.target_h / h)
                passes = upscale <= 1.5 # Allow up to 150% upscale for portrait
                
                return CropQualityResult(
                    source_width=w, source_height=h, crop_width=w, crop_height=h,
                    effective_resolution=f"{w}x{h}", upscale_factor=round(upscale, 2),
                    passes_quality=passes,
                    rejection_reason=None if passes else f"Upscale factor too high ({upscale:.2f}x)"
                )
            
        # 2. Landscape to Portrait Crop
        # To get a 9:16 crop from landscape, the height remains the same, width is cropped
        crop_h = h
        crop_w = int(h * (self.target_w / self.target_h))
        
        # If crop_w is somehow larger than source width, we are constrained by width
        if crop_w > w:
            crop_w = w
            crop_h = int(w * (self.target_h / self.target_w))
            
        upscale = self.target_h / crop_h
        
        # For landscape -> portrait, we are much stricter with upscale
        passes = upscale <= 1.3 # Max 1.3x upscale from crop
        
        # Also check absolute minimum crop resolution
        if crop_h < 720:
            passes = False
            reason = f"Effective crop height too low ({crop_h}px)"
        elif not passes:
            reason = f"Upscale factor too high after crop ({upscale:.2f}x)"
        else:
            reason = None
            
        return CropQualityResult(
            source_width=w, source_height=h, crop_width=crop_w, crop_height=crop_h,
            effective_resolution=f"{crop_w}x{crop_h}", upscale_factor=round(upscale, 2),
            passes_quality=passes,
            rejection_reason=reason
        )
