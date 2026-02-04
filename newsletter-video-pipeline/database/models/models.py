"""
Database models for Newsletter Video Pipeline.
Uses SQLAlchemy ORM with PostgreSQL.
"""

from datetime import datetime
from typing import Optional, List
from enum import Enum as PyEnum
import uuid

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, JSON,
    ForeignKey, Enum, Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


# ============================================================
# Enums
# ============================================================

class UserRole(str, PyEnum):
    ADMIN = "admin"
    USER = "user"
    API = "api"  # API-only access


class PipelineStatus(str, PyEnum):
    PENDING = "pending"
    QUEUED = "queued"
    GENERATING_SCRIPT = "generating_script"
    SYNTHESIZING_VOICE = "synthesizing_voice"
    GENERATING_VIDEO = "generating_video"
    PROCESSING_VIDEO = "processing_video"
    PUBLISHING = "publishing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PublishStatus(str, PyEnum):
    PENDING = "pending"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    PUBLISHED = "published"
    SCHEDULED = "scheduled"
    FAILED = "failed"


class Platform(str, PyEnum):
    YOUTUBE = "youtube"
    YOUTUBE_SHORTS = "youtube_shorts"
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"
    X_TWITTER = "x"


# ============================================================
# User & Authentication Models
# ============================================================

class User(Base):
    """User account model."""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)

    # Profile
    full_name = Column(String(255))
    avatar_url = Column(String(500))

    # Role & Status
    role = Column(Enum(UserRole), default=UserRole.USER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)

    # Settings
    settings = Column(JSON, default=dict)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_login_at = Column(DateTime(timezone=True))

    # Relationships
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    voices = relationship("Voice", back_populates="user", cascade="all, delete-orphan")
    avatars = relationship("Avatar", back_populates="user", cascade="all, delete-orphan")
    pipelines = relationship("PipelineJob", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_users_email_active", "email", "is_active"),
    )


class APIKey(Base):
    """API key for programmatic access."""
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    name = Column(String(100), nullable=False)
    key_hash = Column(String(255), nullable=False, unique=True)
    key_prefix = Column(String(10), nullable=False)  # First 8 chars for identification

    # Permissions
    scopes = Column(ARRAY(String), default=["read", "write"])

    # Limits
    rate_limit = Column(Integer, default=1000)  # Requests per hour

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    expires_at = Column(DateTime(timezone=True))
    last_used_at = Column(DateTime(timezone=True))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="api_keys")

    __table_args__ = (
        Index("ix_api_keys_key_prefix", "key_prefix"),
        Index("ix_api_keys_user_active", "user_id", "is_active"),
    )


class RefreshToken(Base):
    """JWT refresh token storage."""
    __tablename__ = "refresh_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    token_hash = Column(String(255), nullable=False, unique=True)
    device_info = Column(String(500))
    ip_address = Column(String(45))

    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_refresh_tokens_user_id", "user_id"),
        Index("ix_refresh_tokens_expires", "expires_at"),
    )


# ============================================================
# Voice & Avatar Models
# ============================================================

class Voice(Base):
    """Cloned voice model."""
    __tablename__ = "voices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    name = Column(String(100), nullable=False)
    description = Column(Text)
    language = Column(String(10), default="en", nullable=False)

    # Audio characteristics
    sample_duration_sec = Column(Float, nullable=False)
    quality_score = Column(Float)  # 0-1 estimated quality

    # Storage
    samples_path = Column(String(500), nullable=False)
    model_path = Column(String(500))

    # Status
    is_default = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Metadata
    metadata = Column(JSON, default=dict)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="voices")

    __table_args__ = (
        Index("ix_voices_user_default", "user_id", "is_default"),
        UniqueConstraint("user_id", "name", name="uq_voices_user_name"),
    )


class Avatar(Base):
    """AI avatar model."""
    __tablename__ = "avatars"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    name = Column(String(100), nullable=False)
    description = Column(Text)

    # Source video info
    source_video_path = Column(String(500), nullable=False)
    source_duration_sec = Column(Float, nullable=False)

    # Processing results
    face_detected = Column(Boolean, default=True)
    has_body = Column(Boolean, default=False)
    background_removed = Column(Boolean, default=False)

    # Model paths
    motion_data_path = Column(String(500))
    face_embedding_path = Column(String(500))

    # Status
    is_default = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Metadata
    metadata = Column(JSON, default=dict)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="avatars")

    __table_args__ = (
        Index("ix_avatars_user_default", "user_id", "is_default"),
        UniqueConstraint("user_id", "name", name="uq_avatars_user_name"),
    )


# ============================================================
# Pipeline & Job Models
# ============================================================

class PipelineJob(Base):
    """Pipeline execution job."""
    __tablename__ = "pipeline_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Input
    newsletter_title = Column(String(255))
    newsletter_content = Column(Text, nullable=False)
    newsletter_url = Column(String(500))

    # Configuration
    voice_id = Column(UUID(as_uuid=True), ForeignKey("voices.id", ondelete="SET NULL"))
    avatar_id = Column(UUID(as_uuid=True), ForeignKey("avatars.id", ondelete="SET NULL"))

    generate_long_form = Column(Boolean, default=True)
    generate_shorts = Column(Boolean, default=True)
    shorts_count = Column(Integer, default=3)
    target_platforms = Column(ARRAY(String), default=list)

    auto_publish = Column(Boolean, default=False)
    publish_platforms = Column(ARRAY(String), default=list)
    scheduled_publish_at = Column(DateTime(timezone=True))

    # Settings
    script_tone = Column(String(50), default="professional")
    config = Column(JSON, default=dict)

    # Status
    status = Column(Enum(PipelineStatus), default=PipelineStatus.PENDING, nullable=False, index=True)
    progress_percent = Column(Float, default=0)
    current_stage = Column(String(50))
    error_message = Column(Text)

    # Results
    script_long_form = Column(Text)
    script_shorts = Column(JSON)  # Array of short scripts
    audio_path = Column(String(500))

    # Timing
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    # Celery task ID
    celery_task_id = Column(String(100), index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="pipelines")
    voice = relationship("Voice")
    avatar = relationship("Avatar")
    videos = relationship("Video", back_populates="pipeline_job", cascade="all, delete-orphan")
    publications = relationship("Publication", back_populates="pipeline_job", cascade="all, delete-orphan")
    stages = relationship("PipelineStage", back_populates="pipeline_job", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_pipeline_jobs_user_status", "user_id", "status"),
        Index("ix_pipeline_jobs_created", "created_at"),
    )


class PipelineStage(Base):
    """Individual stage within a pipeline job."""
    __tablename__ = "pipeline_stages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_job_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_jobs.id", ondelete="CASCADE"), nullable=False)

    stage_name = Column(String(50), nullable=False)  # script, voice, avatar, video_process, publish
    status = Column(String(20), default="pending")  # pending, running, success, failed, skipped

    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    duration_sec = Column(Float)

    output_data = Column(JSON)
    error_message = Column(Text)

    # Relationships
    pipeline_job = relationship("PipelineJob", back_populates="stages")

    __table_args__ = (
        Index("ix_pipeline_stages_job", "pipeline_job_id"),
    )


class Video(Base):
    """Generated video."""
    __tablename__ = "videos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_job_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_jobs.id", ondelete="CASCADE"), nullable=False)

    video_type = Column(String(50), nullable=False)  # long_form, short_1, short_2, etc.

    # File info
    file_path = Column(String(500), nullable=False)
    file_size_mb = Column(Float)
    duration_sec = Column(Float)
    resolution = Column(String(20))
    fps = Column(Integer)

    # Platform versions
    platform_versions = Column(JSON, default=dict)  # {platform: path}

    # Thumbnail
    thumbnail_path = Column(String(500))

    # Metadata
    title = Column(String(255))
    description = Column(Text)
    tags = Column(ARRAY(String))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    pipeline_job = relationship("PipelineJob", back_populates="videos")
    publications = relationship("Publication", back_populates="video")

    __table_args__ = (
        Index("ix_videos_pipeline", "pipeline_job_id"),
    )


class Publication(Base):
    """Social media publication record."""
    __tablename__ = "publications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_job_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_jobs.id", ondelete="CASCADE"), nullable=False)
    video_id = Column(UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)

    platform = Column(Enum(Platform), nullable=False)
    status = Column(Enum(PublishStatus), default=PublishStatus.PENDING, nullable=False)

    # Platform-specific IDs
    platform_video_id = Column(String(100))
    platform_url = Column(String(500))

    # Scheduling
    scheduled_for = Column(DateTime(timezone=True))
    published_at = Column(DateTime(timezone=True))

    # Error tracking
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    pipeline_job = relationship("PipelineJob", back_populates="publications")
    video = relationship("Video", back_populates="publications")

    __table_args__ = (
        Index("ix_publications_pipeline", "pipeline_job_id"),
        Index("ix_publications_status", "status"),
        Index("ix_publications_scheduled", "scheduled_for"),
        UniqueConstraint("video_id", "platform", name="uq_publications_video_platform"),
    )


# ============================================================
# Social Media Credentials
# ============================================================

class SocialCredential(Base):
    """OAuth credentials for social media platforms."""
    __tablename__ = "social_credentials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    platform = Column(Enum(Platform), nullable=False)

    # OAuth tokens (encrypted)
    access_token = Column(Text)  # Encrypted
    refresh_token = Column(Text)  # Encrypted
    token_expires_at = Column(DateTime(timezone=True))

    # Platform user info
    platform_user_id = Column(String(100))
    platform_username = Column(String(100))

    # Status
    is_active = Column(Boolean, default=True)
    last_verified_at = Column(DateTime(timezone=True))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "platform", name="uq_social_credentials_user_platform"),
        Index("ix_social_credentials_user", "user_id"),
    )


# ============================================================
# System & Audit Models
# ============================================================

class AuditLog(Base):
    """Audit log for tracking user actions."""
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    action = Column(String(100), nullable=False)  # e.g., "pipeline.create", "voice.delete"
    resource_type = Column(String(50))  # e.g., "pipeline", "voice", "user"
    resource_id = Column(UUID(as_uuid=True))

    # Request context
    ip_address = Column(String(45))
    user_agent = Column(String(500))

    # Details
    details = Column(JSON)

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_audit_logs_user", "user_id"),
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_created", "created_at"),
    )


class SystemSetting(Base):
    """System-wide settings."""
    __tablename__ = "system_settings"

    key = Column(String(100), primary_key=True)
    value = Column(JSON, nullable=False)
    description = Column(Text)

    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))


class UsageStats(Base):
    """Usage statistics for billing/monitoring."""
    __tablename__ = "usage_stats"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Period
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)

    # Counts
    pipelines_created = Column(Integer, default=0)
    videos_generated = Column(Integer, default=0)
    audio_minutes_generated = Column(Float, default=0)
    video_minutes_generated = Column(Float, default=0)
    publications_count = Column(Integer, default=0)

    # Storage
    storage_used_mb = Column(Float, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_usage_stats_user_period", "user_id", "period_start"),
    )
