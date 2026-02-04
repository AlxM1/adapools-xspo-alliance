"""Data models for Script Generator Service."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


class ScriptFormat(str, Enum):
    """Script output format."""
    LONG_FORM = "long_form"       # Full video (3-10 minutes)
    SHORT_FORM = "short_form"     # TikTok/Reels (15-60 seconds)
    BOTH = "both"                 # Generate both versions


class ScriptTone(str, Enum):
    """Script tone/style."""
    PROFESSIONAL = "professional"
    CASUAL = "casual"
    ENTHUSIASTIC = "enthusiastic"
    EDUCATIONAL = "educational"
    CONVERSATIONAL = "conversational"


class GenerateScriptRequest(BaseModel):
    """Request to generate video script from newsletter."""

    # Input content
    newsletter_content: str = Field(..., description="Newsletter text content")
    newsletter_title: Optional[str] = Field(None, description="Newsletter title/subject")
    newsletter_url: Optional[str] = Field(None, description="Original newsletter URL")

    # Script settings
    format: ScriptFormat = Field(default=ScriptFormat.BOTH)
    tone: ScriptTone = Field(default=ScriptTone.PROFESSIONAL)

    # Length settings
    target_long_duration_sec: int = Field(
        default=300,  # 5 minutes
        ge=60,
        le=1800,
        description="Target duration for long-form video in seconds"
    )
    target_short_duration_sec: int = Field(
        default=45,
        ge=15,
        le=90,
        description="Target duration for short-form video in seconds"
    )

    # Content options
    include_hook: bool = Field(default=True, description="Include attention-grabbing hook")
    include_cta: bool = Field(default=True, description="Include call-to-action")
    include_timestamps: bool = Field(default=True, description="Include section timestamps")

    # Advanced
    custom_instructions: Optional[str] = Field(
        None,
        description="Additional instructions for script generation"
    )
    persona_description: Optional[str] = Field(
        None,
        description="Description of the speaker persona/style"
    )


class ScriptSection(BaseModel):
    """A section of the script."""

    title: str
    content: str
    duration_estimate_sec: int
    timestamp: Optional[str] = None  # e.g., "0:00", "1:30"


class GeneratedScript(BaseModel):
    """Generated video script."""

    title: str
    description: str
    hook: Optional[str] = None
    sections: list[ScriptSection]
    cta: Optional[str] = None
    full_script: str
    word_count: int
    estimated_duration_sec: int
    hashtags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class GenerateScriptResponse(BaseModel):
    """Response after script generation."""

    long_form: Optional[GeneratedScript] = None
    short_form: Optional[GeneratedScript] = None
    shorts_clips: list[GeneratedScript] = Field(
        default_factory=list,
        description="Multiple short clips extracted from long-form"
    )
    processing_time_sec: float
    tokens_used: int
    message: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    llm_provider: str
    llm_model: str
    llm_available: bool
    version: str
