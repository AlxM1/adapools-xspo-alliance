"""Data models for Avatar Generator Service."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


class OutputResolution(str, Enum):
    """Output video resolution options."""
    SD = "480p"
    HD = "720p"
    FHD = "1080p"
    QHD = "1440p"
    UHD = "4k"


class AspectRatio(str, Enum):
    """Video aspect ratio options."""
    LANDSCAPE = "16:9"
    PORTRAIT = "9:16"
    SQUARE = "1:1"


class AvatarModel(BaseModel):
    """Avatar model metadata."""

    id: str = Field(..., description="Unique avatar ID")
    name: str = Field(..., description="Human-readable name")
    description: Optional[str] = Field(None)
    source_video_duration_sec: float = Field(..., description="Duration of source video")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_default: bool = Field(default=False)

    # Avatar characteristics
    face_detected: bool = Field(default=True)
    has_body: bool = Field(default=False)  # Full body or just face
    background_removed: bool = Field(default=False)

    # Model paths (internal)
    motion_data_path: Optional[str] = None
    face_embedding_path: Optional[str] = None


class CreateAvatarRequest(BaseModel):
    """Request to create a new avatar from video."""

    name: str = Field(..., description="Name for the avatar")
    description: Optional[str] = Field(None)
    set_as_default: bool = Field(default=False)
    remove_background: bool = Field(default=False, description="Remove video background")
    extract_body: bool = Field(default=False, description="Extract full body motion")
    # Video file uploaded separately via multipart form


class CreateAvatarResponse(BaseModel):
    """Response after creating an avatar."""

    avatar_id: str
    name: str
    message: str
    source_duration_sec: float
    face_detected: bool
    processing_time_sec: float


class GenerateVideoRequest(BaseModel):
    """Request to generate a video with avatar."""

    avatar_id: Optional[str] = Field(None, description="Avatar ID (uses default if not specified)")
    audio_path: str = Field(..., description="Path to audio file")

    # Output settings
    resolution: OutputResolution = Field(default=OutputResolution.FHD)
    aspect_ratio: AspectRatio = Field(default=AspectRatio.LANDSCAPE)
    fps: int = Field(default=30, ge=15, le=60)
    output_format: str = Field(default="mp4")

    # Enhancement settings
    enhance_face: bool = Field(default=True, description="Apply face enhancement")
    enhance_audio: bool = Field(default=False, description="Apply audio enhancement")
    use_liveportrait: bool = Field(default=True, description="Use LivePortrait for natural motion")

    # Advanced settings
    face_det_threshold: float = Field(default=0.5, ge=0.1, le=1.0)
    batch_size: int = Field(default=8, ge=1, le=32)


class GenerateVideoResponse(BaseModel):
    """Response after video generation."""

    video_url: str = Field(..., description="URL to download the video")
    video_path: str = Field(..., description="Server path to video file")
    duration_sec: float = Field(..., description="Video duration")
    resolution: str
    fps: int
    file_size_mb: float
    avatar_id: str
    processing_time_sec: float


class GenerateVideoProgress(BaseModel):
    """Progress update during video generation."""

    job_id: str
    status: str  # "processing", "completed", "failed"
    progress_percent: float
    current_step: str
    estimated_remaining_sec: Optional[float]
    error_message: Optional[str] = None


class AvatarListResponse(BaseModel):
    """Response containing list of available avatars."""

    avatars: list[AvatarModel]
    default_avatar_id: Optional[str]
    total_count: int


class AvatarDeleteResponse(BaseModel):
    """Response after deleting an avatar."""

    avatar_id: str
    message: str
    success: bool


class HealthResponse(BaseModel):
    """Health check response."""

    status: str  # "healthy", "degraded", "unhealthy"
    musetalk_loaded: bool
    liveportrait_loaded: bool
    gpu_available: bool
    gpu_memory_used_gb: Optional[float]
    gpu_memory_total_gb: Optional[float]
    avatars_count: int
    version: str
