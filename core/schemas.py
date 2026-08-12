from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any

# ─── Brand ────────────────────────────────────────────────────────────
class BrandProfile(BaseModel):
    brand_id: str = "bodycomfort"
    brand_name: str = "몸편한하루"
    platform: str = "naver_clip"
    domain: str = "health_lifestyle"
    target_profile: List[str] = Field(default_factory=list)
    tone: str = "쉽고 명확하며 신뢰감 있는 정보 전달"
    benchmark_dataset: str = "bodycomfort_benchmark_v0.1"

# ─── Benchmark ────────────────────────────────────────────────────────
class BenchmarkScene(BaseModel):
    scene_id: str
    start_sec: float = 0.0
    end_sec: float = 0.0
    purpose: str = ""           # hook / problem / solution / demo / cta
    visual_description: str = ""
    caption_text: str = ""
    subject: str = ""
    action: str = ""
    body_part: str = ""
    environment: str = ""

class BenchmarkVideo(BaseModel):
    video_id: str
    source_type: str = "benchmark_clip"
    status: str = "BENCHMARK_OBSERVED"   # BENCHMARK_OBSERVED | PERFORMANCE_VALIDATED | MODEL_INFERRED
    duration_sec: float = 0.0
    aspect_ratio: str = "9:16"
    resolution: str = ""
    transcript: str = ""
    hook: Dict[str, Any] = Field(default_factory=dict)
    target: List[str] = Field(default_factory=list)
    topic: List[str] = Field(default_factory=list)
    body_parts: List[str] = Field(default_factory=list)
    script_structure: List[str] = Field(default_factory=list)
    visual_patterns: List[str] = Field(default_factory=list)
    caption_patterns: List[str] = Field(default_factory=list)
    cta_patterns: List[str] = Field(default_factory=list)
    scenes: List[BenchmarkScene] = Field(default_factory=list)

class BenchmarkPattern(BaseModel):
    pattern_id: str
    name: str
    description: str = ""
    observed_count: int = 0
    confidence: float = 0.0
    generation_policy: str = "strategy_only"  # style_only | strategy_only | safe_to_generate | requires_evidence
    source_video_ids: List[str] = Field(default_factory=list)

class BenchmarkDNA(BaseModel):
    dataset_id: str = "bodycomfort_benchmark_v0.1"
    source_count: int = 0
    status: str = "BENCHMARK_OBSERVED"
    hook_patterns: List[BenchmarkPattern] = Field(default_factory=list)
    target_patterns: List[BenchmarkPattern] = Field(default_factory=list)
    topic_clusters: List[BenchmarkPattern] = Field(default_factory=list)
    script_structures: List[BenchmarkPattern] = Field(default_factory=list)
    visual_patterns: List[BenchmarkPattern] = Field(default_factory=list)
    caption_patterns: List[BenchmarkPattern] = Field(default_factory=list)
    cta_patterns: List[BenchmarkPattern] = Field(default_factory=list)

# ─── Product / Audience ───────────────────────────────────────────────
class ProductInfo(BaseModel):
    url: Optional[str] = None
    name: str = Field(..., description="Product name")
    category: str = Field(..., description="Product category")
    description: str = Field(..., description="Detailed description of the product and its benefits")

class AudienceProfile(BaseModel):
    age_group: str = Field(default="4050", description="Target age group")
    gender: str = Field(default="all", description="Target gender")
    core_problem: str = Field(..., description="The main problem the target audience is facing")

# ─── Hook ─────────────────────────────────────────────────────────────
class HookCandidate(BaseModel):
    strategy_id: str
    content: str
    reason: str
    score: Optional[int] = None

# ─── Scene ────────────────────────────────────────────────────────────
class SceneIntent(BaseModel):
    scene_id: str
    narration: str
    subject: str = ""
    age_group: str = ""
    action: str = ""
    location: str = ""
    object: str = ""
    body_part: str = ""
    symptom: str = ""
    emotion: str = ""
    context: str = ""
    visual_goal: str = ""
    avoid: List[str] = Field(default_factory=list)
    hard_requirements: Dict[str, str] = Field(default_factory=dict)

# ─── Script ───────────────────────────────────────────────────────────
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
    hard_gate_violations: List[str] = Field(default_factory=list)

# ─── Asset ────────────────────────────────────────────────────────────
class SearchQuery(BaseModel):
    scene_id: str
    queries: List[str]

class AssetScore(BaseModel):
    overall_semantic_match: int = 0
    narrative_match: int = 0
    subject_match: int = 0
    action_match: int = 0
    object_match: int = 0
    location_context_match: int = 0
    emotion_match: int = 0
    visual_quality: int = 0
    avoid_match: bool = False
    total_score: int = 0

class AssetCandidate(BaseModel):
    provider: str
    asset_id: str
    title: str = ""
    url: str
    download_url: str
    thumbnail_url: Optional[str] = None
    thumbnail_urls: List[str] = Field(default_factory=list)
    width: int
    height: int
    duration: float
    orientation: str
    score: Optional[AssetScore] = None
    is_rejected: bool = False
    rejection_reason: Optional[str] = None

class CropQualityResult(BaseModel):
    source_width: int
    source_height: int
    crop_width: int
    crop_height: int
    effective_resolution: str
    upscale_factor: float
    passes_quality: bool
    rejection_reason: Optional[str] = None

class CandidateDebugInfo(BaseModel):
    url: str
    title: str = ""
    duration: float
    resolution: str
    aspect_ratio: str
    pre_filter_score: int = 0
    overall_semantic_match: int = 0
    narrative_match: int = 0
    subject_match: int = 0
    action_match: int = 0
    object_match: int = 0
    location_context_match: int = 0
    emotion_match: int = 0
    visual_quality: int = 0
    avoid_match: bool = False
    total_score: int = 0
    decision: str = "PENDING"
    reject_reason: Optional[str] = None
    failure_type: Optional[str] = None
    retry_count: int = 0
    latency_ms: int = 0

class SceneDebugInfo(BaseModel):
    scene_id: str
    narration: str
    visual_goal: str
    search_queries: List[str] = Field(default_factory=list)
    candidate_count: int = 0
    candidates: List[CandidateDebugInfo] = Field(default_factory=list)
    selected_asset: Optional[AssetCandidate] = None
    final_decision: str = "PENDING"

# ─── Pipeline ─────────────────────────────────────────────────────────
class VideoPlan(BaseModel):
    job_id: str
    script: ScriptResult
    scenes: List[Dict[str, Any]]

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
    brand_id: str = "bodycomfort"
    platform: str = "naver_clip"
    duration: int
    resolution: str
    aspect_ratio: str = "9:16"
    hook_strategy: str
    script_score: int
    visual_score: int
    clip_optimization_score: int
    scenes: List[Dict[str, Any]]
    benchmark_patterns_used: List[str] = Field(default_factory=list)
