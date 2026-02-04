"""Data models for Video Processor Service."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


class Platform(str, Enum):
    """Target platform for video output."""
    YOUTUBE = "youtube"
    YOUTUBE_SHORTS = "youtube_shorts"
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"
    INSTAGRAM_REELS = "instagram_reels"
    X_TWITTER = "x"
    ALL = "all"


class VideoFormat(str, Enum):
    """Video output format."""
    MP4 = "mp4"
    MOV = "mov"
    WEBM = "webm"


class CaptionStyle(str, Enum):
    """Caption/subtitle style."""
    NONE = "none"
    STANDARD = "standard"
    BOLD = "bold"
    OUTLINE = "outline"
    KARAOKE = "karaoke"


class ProcessVideoRequest(BaseModel):
    """Request to process a video for specific platform(s)."""

    input_path: str = Field(..., description="Path to input video")
    platforms: list[Platform] = Field(
        default=[Platform.ALL],
        description="Target platforms"
    )

    # Output settings
    output_format: VideoFormat = Field(default=VideoFormat.MP4)
    output_dir: Optional[str] = Field(None, description="Output directory (uses temp if not specified)")

    # Content modifications
    add_intro: bool = Field(default=False, description="Add intro clip")
    intro_path: Optional[str] = Field(None, description="Path to intro video")
    intro_duration_sec: float = Field(default=3.0, description="Intro duration")

    add_outro: bool = Field(default=False, description="Add outro clip")
    outro_path: Optional[str] = Field(None, description="Path to outro video")
    outro_duration_sec: float = Field(default=5.0, description="Outro duration")

    # Captions
    add_captions: bool = Field(default=False, description="Add captions/subtitles")
    caption_style: CaptionStyle = Field(default=CaptionStyle.STANDARD)
    caption_text: Optional[str] = Field(None, description="Caption text (SRT format or plain)")
    auto_generate_captions: bool = Field(default=False, description="Auto-generate from audio")

    # Watermark
    add_watermark: bool = Field(default=False)
    watermark_path: Optional[str] = Field(None, description="Path to watermark image")
    watermark_position: str = Field(default="bottom_right")  # top_left, top_right, bottom_left, bottom_right
    watermark_opacity: float = Field(default=0.7, ge=0.0, le=1.0)

    # Audio
    normalize_audio: bool = Field(default=True, description="Normalize audio levels")
    target_loudness: float = Field(default=-14.0, description="Target LUFS for normalization")

    # Shorts generation
    generate_shorts: bool = Field(default=False, description="Generate short clips from long video")
    shorts_max_duration: int = Field(default=60, description="Max duration for shorts")
    shorts_count: int = Field(default=3, description="Number of shorts to generate")


class VideoOutput(BaseModel):
    """Single processed video output."""

    platform: Platform
    path: str
    filename: str
    resolution: str
    duration_sec: float
    file_size_mb: float
    fps: int
    bitrate: str


class ProcessVideoResponse(BaseModel):
    """Response after video processing."""

    outputs: list[VideoOutput] = Field(default_factory=list)
    shorts: list[VideoOutput] = Field(default_factory=list)
    processing_time_sec: float
    input_duration_sec: float
    message: str


class VideoInfoResponse(BaseModel):
    """Video information response."""

    path: str
    duration_sec: float
    width: int
    height: int
    fps: float
    codec: str
    bitrate: Optional[str]
    file_size_mb: float
    has_audio: bool
    audio_codec: Optional[str]


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    ffmpeg_available: bool
    ffmpeg_version: Optional[str]
    temp_dir_writable: bool
    version: str
