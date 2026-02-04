"""Data models for Voice Cloner Service."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


class VoiceLanguage(str, Enum):
    """Supported languages for XTTS-v2."""
    ENGLISH = "en"
    SPANISH = "es"
    FRENCH = "fr"
    GERMAN = "de"
    ITALIAN = "it"
    PORTUGUESE = "pt"
    POLISH = "pl"
    TURKISH = "tr"
    RUSSIAN = "ru"
    DUTCH = "nl"
    CZECH = "cs"
    ARABIC = "ar"
    CHINESE = "zh-cn"
    JAPANESE = "ja"
    HUNGARIAN = "hu"
    KOREAN = "ko"
    HINDI = "hi"


class VoiceModel(BaseModel):
    """Voice model metadata."""

    id: str = Field(..., description="Unique voice model ID")
    name: str = Field(..., description="Human-readable name")
    description: Optional[str] = Field(None, description="Voice description")
    language: VoiceLanguage = Field(default=VoiceLanguage.ENGLISH)
    sample_duration_sec: float = Field(..., description="Total duration of training samples")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_default: bool = Field(default=False)

    # Audio characteristics (extracted from samples)
    pitch_mean: Optional[float] = None
    pitch_std: Optional[float] = None
    speaking_rate: Optional[float] = None  # words per minute


class VoiceCloneRequest(BaseModel):
    """Request to create a new voice clone."""

    name: str = Field(..., description="Name for the voice model")
    description: Optional[str] = Field(None, description="Voice description")
    language: VoiceLanguage = Field(default=VoiceLanguage.ENGLISH)
    set_as_default: bool = Field(default=False, description="Set as default voice")
    # Audio files are uploaded separately via multipart form


class VoiceCloneResponse(BaseModel):
    """Response after creating a voice clone."""

    voice_id: str
    name: str
    message: str
    sample_duration_sec: float
    estimated_quality: str  # "basic", "good", "excellent"


class SynthesizeRequest(BaseModel):
    """Request to synthesize speech from text."""

    text: str = Field(..., description="Text to synthesize", max_length=10000)
    voice_id: Optional[str] = Field(None, description="Voice model ID (uses default if not specified)")
    language: Optional[VoiceLanguage] = Field(None, description="Override language")

    # Audio settings
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="Speaking speed multiplier")

    # Advanced settings
    temperature: float = Field(default=0.7, ge=0.1, le=1.0, description="Sampling temperature")
    top_p: float = Field(default=0.85, ge=0.1, le=1.0, description="Top-p sampling")
    top_k: int = Field(default=50, ge=1, le=100, description="Top-k sampling")
    repetition_penalty: float = Field(default=5.0, ge=1.0, le=10.0)
    length_penalty: float = Field(default=1.0, ge=0.5, le=2.0)

    # Output settings
    output_format: str = Field(default="wav", description="Output format: wav, mp3, ogg")
    sample_rate: int = Field(default=24000, description="Output sample rate")

    # Streaming
    stream: bool = Field(default=False, description="Enable streaming output")


class SynthesizeResponse(BaseModel):
    """Response after synthesis (non-streaming)."""

    audio_url: str = Field(..., description="URL to download the audio file")
    audio_path: str = Field(..., description="Server path to audio file")
    duration_sec: float = Field(..., description="Audio duration in seconds")
    voice_id: str
    language: str
    text_length: int
    processing_time_sec: float


class SynthesizeStreamChunk(BaseModel):
    """Chunk of streamed audio data."""

    chunk_index: int
    audio_data: bytes  # Base64 encoded in JSON response
    is_final: bool
    total_duration_sec: Optional[float] = None


class VoiceListResponse(BaseModel):
    """Response containing list of available voices."""

    voices: list[VoiceModel]
    default_voice_id: Optional[str]
    total_count: int


class VoiceDeleteResponse(BaseModel):
    """Response after deleting a voice."""

    voice_id: str
    message: str
    success: bool


class HealthResponse(BaseModel):
    """Health check response."""

    status: str  # "healthy", "degraded", "unhealthy"
    model_loaded: bool
    gpu_available: bool
    gpu_memory_used_gb: Optional[float]
    gpu_memory_total_gb: Optional[float]
    voices_count: int
    version: str
