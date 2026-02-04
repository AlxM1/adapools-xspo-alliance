"""Data models for API Gateway / Pipeline Orchestrator."""

from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field
from enum import Enum


class PipelineStatus(str, Enum):
    """Pipeline execution status."""
    PENDING = "pending"
    GENERATING_SCRIPT = "generating_script"
    SYNTHESIZING_VOICE = "synthesizing_voice"
    GENERATING_VIDEO = "generating_video"
    PROCESSING_VIDEO = "processing_video"
    PUBLISHING = "publishing"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineStage(str, Enum):
    """Pipeline stages."""
    SCRIPT = "script"
    VOICE = "voice"
    AVATAR = "avatar"
    VIDEO_PROCESS = "video_process"
    PUBLISH = "publish"


class PipelineRequest(BaseModel):
    """Request to execute the full newsletter-to-video pipeline."""

    # Newsletter input
    newsletter_content: str = Field(..., description="Newsletter text content")
    newsletter_title: Optional[str] = Field(None, description="Newsletter title")
    newsletter_url: Optional[str] = Field(None, description="Original URL")

    # Pipeline configuration
    generate_long_form: bool = Field(default=True, description="Generate long-form video")
    generate_shorts: bool = Field(default=True, description="Generate short-form videos")
    shorts_count: int = Field(default=3, ge=1, le=10, description="Number of shorts to generate")

    # Voice settings
    voice_id: Optional[str] = Field(None, description="Voice ID to use (default if not specified)")

    # Avatar settings
    avatar_id: Optional[str] = Field(None, description="Avatar ID to use (default if not specified)")

    # Output settings
    target_platforms: list[str] = Field(
        default=["youtube", "tiktok", "instagram", "x"],
        description="Platforms to optimize for"
    )

    # Publishing settings
    auto_publish: bool = Field(default=False, description="Automatically publish after generation")
    publish_platforms: list[str] = Field(default_factory=list, description="Platforms to publish to")
    publish_privacy: str = Field(default="private", description="Privacy setting for published videos")
    scheduled_time: Optional[datetime] = Field(None, description="Schedule publish time")

    # Script settings
    script_tone: str = Field(default="professional", description="Script tone")
    include_cta: bool = Field(default=True, description="Include call-to-action")

    # Advanced
    custom_instructions: Optional[str] = Field(None, description="Custom script instructions")
    webhook_url: Optional[str] = Field(None, description="Webhook URL for completion notification")


class StageResult(BaseModel):
    """Result from a pipeline stage."""

    stage: PipelineStage
    status: str  # "success", "failed", "skipped"
    duration_sec: float
    output_data: Optional[dict] = None
    error_message: Optional[str] = None


class VideoOutput(BaseModel):
    """Generated video output."""

    video_type: str  # "long_form", "short_1", "short_2", etc.
    video_path: str
    video_url: Optional[str] = None
    duration_sec: float
    file_size_mb: float
    platform_versions: dict[str, str] = Field(default_factory=dict)  # platform -> path


class PublishResult(BaseModel):
    """Publishing result for a single video."""

    video_type: str
    platform: str
    status: str
    video_id: Optional[str] = None
    video_url: Optional[str] = None
    error_message: Optional[str] = None


class PipelineResponse(BaseModel):
    """Response from pipeline execution."""

    job_id: str
    status: PipelineStatus
    progress_percent: float
    current_stage: Optional[str] = None

    # Stage results
    stages: list[StageResult] = Field(default_factory=list)

    # Outputs
    script_long_form: Optional[str] = None
    script_shorts: list[str] = Field(default_factory=list)
    audio_path: Optional[str] = None
    videos: list[VideoOutput] = Field(default_factory=list)
    publish_results: list[PublishResult] = Field(default_factory=list)

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_duration_sec: Optional[float] = None

    # Errors
    error_message: Optional[str] = None


class PipelineJob(BaseModel):
    """Pipeline job for tracking."""

    job_id: str
    request: PipelineRequest
    status: PipelineStatus
    progress_percent: float = 0
    current_stage: Optional[PipelineStage] = None
    stages: list[StageResult] = Field(default_factory=list)
    outputs: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class ServiceStatus(BaseModel):
    """Status of a backend service."""

    name: str
    url: str
    status: str  # "healthy", "degraded", "unhealthy", "unknown"
    latency_ms: Optional[float] = None
    last_check: datetime


class SystemHealthResponse(BaseModel):
    """Overall system health response."""

    status: str  # "healthy", "degraded", "unhealthy"
    services: list[ServiceStatus]
    active_jobs: int
    completed_jobs_24h: int
    version: str
