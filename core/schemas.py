from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any

class ProductInfo(BaseModel):
    url: Optional[str] = None
    name: str = Field(..., description="Product name")
    category: str = Field(..., description="Product category")
    description: str = Field(..., description="Detailed description of the product and its benefits")

class AudienceProfile(BaseModel):
    age_group: str = Field(default="4050", description="Target age group")
    gender: str = Field(default="all", description="Target gender")
    core_problem: str = Field(..., description="The main problem the target audience is facing")

class HookCandidate(BaseModel):
    strategy_id: str
    content: str
    reason: str

class SceneIntent(BaseModel):
    scene_id: str
    narration: str
    subject: str = ""
    action: str = ""
    location: str = ""
    object: str = ""
    emotion: str = ""
    context: str = ""
    visual_goal: str = ""
    avoid: List[str] = Field(default_factory=list)

class ScriptResult(BaseModel):
    title: str
    hook_strategy: str
    hook: str
    body: List[SceneIntent]
    cta: str
    duration_target: int = Field(default=25)

class ScriptScore(BaseModel):
    hook_strength: int
    target_specificity: int
    clarity: int
    curiosity: int
    credibility: int
    emotional_relevance: int
    product_relevance: int
    pacing: int
    cta_strength: int
    factual_safety: int
    total_score: int
    is_approved: bool
    rejection_reason: Optional[str] = None

class SearchQuery(BaseModel):
    scene_id: str
    queries: List[str]

class AssetScore(BaseModel):
    semantic_relevance: int
    action_match: int
    object_match: int
    emotion_match: int
    context_match: int
    video_quality: int
    total_score: int

class AssetCandidate(BaseModel):
    provider: str
    asset_id: str
    url: str
    download_url: str
    width: int
    height: int
    duration: float
    orientation: str
    score: Optional[AssetScore] = None
    is_rejected: bool = False
    rejection_reason: Optional[str] = None

class VideoPlan(BaseModel):
    job_id: str
    script: ScriptResult
    scenes: List[Dict[str, Any]] # Will hold scene_id, narration, queries, candidates, selected_asset

class ClipOptimizationResult(BaseModel):
    title: str
    description: str
    hashtags: List[str]
    optimization_score: int
    score_breakdown: Dict[str, int]
    improvement_suggestions: List[str]

class GenerationReport(BaseModel):
    job_id: str
    product: str
    platform: str = "naver_clip"
    duration: int
    resolution: str
    aspect_ratio: str = "9:16"
    hook_strategy: str
    script_score: int
    visual_score: int
    clip_optimization_score: int
    scenes: List[Dict[str, Any]]
