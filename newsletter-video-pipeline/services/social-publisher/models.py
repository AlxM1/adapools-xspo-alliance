"""Data models for Social Publisher Service."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


class SocialPlatform(str, Enum):
    """Supported social media platforms."""
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"
    X_TWITTER = "x"


class PrivacyStatus(str, Enum):
    """Video privacy/visibility status."""
    PUBLIC = "public"
    PRIVATE = "private"
    UNLISTED = "unlisted"  # YouTube only


class PublishStatus(str, Enum):
    """Publishing status."""
    PENDING = "pending"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    PUBLISHED = "published"
    FAILED = "failed"
    SCHEDULED = "scheduled"


class YouTubeMetadata(BaseModel):
    """YouTube-specific metadata."""
    category_id: str = Field(default="22", description="YouTube category ID (22 = People & Blogs)")
    tags: list[str] = Field(default_factory=list, max_length=500)
    playlist_id: Optional[str] = Field(None, description="Playlist to add video to")
    made_for_kids: bool = Field(default=False)
    embeddable: bool = Field(default=True)
    license: str = Field(default="youtube", description="youtube or creativeCommon")
    notify_subscribers: bool = Field(default=True)


class TikTokMetadata(BaseModel):
    """TikTok-specific metadata."""
    allow_comments: bool = Field(default=True)
    allow_duet: bool = Field(default=True)
    allow_stitch: bool = Field(default=True)
    # Note: TikTok API doesn't support hashtags in API - include in description


class InstagramMetadata(BaseModel):
    """Instagram-specific metadata."""
    share_to_feed: bool = Field(default=True, description="Share Reel to main feed")
    # Note: Instagram Reels have limited API options


class XTwitterMetadata(BaseModel):
    """X/Twitter-specific metadata."""
    reply_settings: str = Field(default="everyone", description="everyone, mentionedUsers, following")
    quote_tweet_id: Optional[str] = Field(None, description="ID of tweet to quote")


class PublishRequest(BaseModel):
    """Request to publish a video to social media platform(s)."""

    video_path: str = Field(..., description="Path to video file")
    platforms: list[SocialPlatform] = Field(..., description="Target platforms")

    # Content metadata
    title: str = Field(..., description="Video title", max_length=100)
    description: str = Field(default="", description="Video description", max_length=5000)
    tags: list[str] = Field(default_factory=list, description="Tags/hashtags")

    # Scheduling
    privacy: PrivacyStatus = Field(default=PrivacyStatus.PUBLIC)
    scheduled_time: Optional[datetime] = Field(None, description="Schedule publish time (UTC)")

    # Platform-specific metadata
    youtube: Optional[YouTubeMetadata] = Field(default_factory=YouTubeMetadata)
    tiktok: Optional[TikTokMetadata] = Field(default_factory=TikTokMetadata)
    instagram: Optional[InstagramMetadata] = Field(default_factory=InstagramMetadata)
    x_twitter: Optional[XTwitterMetadata] = Field(default_factory=XTwitterMetadata)

    # Thumbnail
    thumbnail_path: Optional[str] = Field(None, description="Path to custom thumbnail image")


class PlatformPublishResult(BaseModel):
    """Result for a single platform."""

    platform: SocialPlatform
    status: PublishStatus
    video_id: Optional[str] = None
    video_url: Optional[str] = None
    error_message: Optional[str] = None
    published_at: Optional[datetime] = None
    scheduled_for: Optional[datetime] = None


class PublishResponse(BaseModel):
    """Response after publishing."""

    job_id: str
    results: list[PlatformPublishResult]
    successful_count: int
    failed_count: int
    message: str


class PublishProgress(BaseModel):
    """Progress update during publishing."""

    job_id: str
    platform: SocialPlatform
    status: PublishStatus
    progress_percent: float
    message: str


class OAuthCallbackRequest(BaseModel):
    """OAuth callback data."""

    platform: SocialPlatform
    code: str
    state: Optional[str] = None


class OAuthStatusResponse(BaseModel):
    """OAuth connection status for platforms."""

    platform: SocialPlatform
    connected: bool
    username: Optional[str] = None
    expires_at: Optional[datetime] = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    platforms: dict[str, bool]  # Platform -> connected status
    version: str
