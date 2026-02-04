"""
Central configuration for Newsletter Video Pipeline.
Supports split architecture: Linux VM (orchestration) + Windows GPU Server (inference)
"""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GPUServerSettings(BaseSettings):
    """Settings for the Windows GPU server running inference services."""

    model_config = SettingsConfigDict(env_prefix="GPU_")

    host: str = Field(default="192.168.1.100", description="Windows GPU server IP address")
    voice_port: int = Field(default=5002, description="Voice cloning service port")
    avatar_port: int = Field(default=5003, description="Avatar generation service port")
    health_check_interval: int = Field(default=30, description="Health check interval in seconds")
    timeout: int = Field(default=300, description="Request timeout in seconds")
    max_retries: int = Field(default=3, description="Max retries for failed requests")


class VoiceClonerSettings(BaseSettings):
    """Settings for the voice cloning service (XTTS-v2)."""

    model_config = SettingsConfigDict(env_prefix="VOICE_")

    model_name: str = Field(default="tts_models/multilingual/multi-dataset/xtts_v2")
    default_language: str = Field(default="en")
    sample_rate: int = Field(default=24000)
    use_deepspeed: bool = Field(default=True)
    use_streaming: bool = Field(default=True)
    max_audio_length_sec: int = Field(default=600)  # 10 minutes max
    voice_samples_dir: str = Field(default="/data/voices")
    temp_dir: str = Field(default="/tmp/voice_cloner")


class AvatarGeneratorSettings(BaseSettings):
    """Settings for avatar generation service (MuseTalk + LivePortrait)."""

    model_config = SettingsConfigDict(env_prefix="AVATAR_")

    musetalk_model_path: str = Field(default="/models/musetalk")
    liveportrait_model_path: str = Field(default="/models/liveportrait")
    output_resolution: str = Field(default="1080p")  # 720p, 1080p, 4k
    fps: int = Field(default=30)
    use_face_enhancement: bool = Field(default=True)
    use_background_removal: bool = Field(default=False)
    avatar_data_dir: str = Field(default="/data/avatars")
    temp_dir: str = Field(default="/tmp/avatar_generator")
    max_video_length_sec: int = Field(default=3600)  # 1 hour max


class VideoProcessorSettings(BaseSettings):
    """Settings for video post-processing service."""

    model_config = SettingsConfigDict(env_prefix="VIDEO_")

    ffmpeg_path: str = Field(default="ffmpeg")
    output_dir: str = Field(default="/data/videos/output")
    temp_dir: str = Field(default="/tmp/video_processor")

    # Platform-specific output settings
    youtube_resolution: str = Field(default="1920x1080")
    youtube_fps: int = Field(default=30)
    youtube_bitrate: str = Field(default="8M")

    tiktok_resolution: str = Field(default="1080x1920")
    tiktok_fps: int = Field(default=30)
    tiktok_bitrate: str = Field(default="6M")
    tiktok_max_duration: int = Field(default=600)  # 10 minutes

    instagram_resolution: str = Field(default="1080x1920")
    instagram_fps: int = Field(default=30)
    instagram_bitrate: str = Field(default="5M")
    instagram_max_duration: int = Field(default=90)  # 90 seconds for reels

    x_resolution: str = Field(default="1920x1080")
    x_fps: int = Field(default=30)
    x_bitrate: str = Field(default="5M")
    x_max_duration: int = Field(default=140)  # 2:20

    shorts_resolution: str = Field(default="1080x1920")
    shorts_fps: int = Field(default=30)
    shorts_bitrate: str = Field(default="5M")
    shorts_max_duration: int = Field(default=60)


class SocialPublisherSettings(BaseSettings):
    """Settings for multi-platform social media publishing."""

    model_config = SettingsConfigDict(env_prefix="SOCIAL_")

    # YouTube
    youtube_client_secrets_file: str = Field(default="/configs/youtube_client_secrets.json")
    youtube_credentials_file: str = Field(default="/data/youtube_credentials.json")
    youtube_default_privacy: str = Field(default="private")
    youtube_default_category: str = Field(default="22")  # People & Blogs

    # TikTok
    tiktok_client_key: Optional[str] = Field(default=None)
    tiktok_client_secret: Optional[str] = Field(default=None)
    tiktok_redirect_uri: str = Field(default="http://localhost:8080/tiktok/callback")

    # Instagram
    instagram_username: Optional[str] = Field(default=None)
    instagram_password: Optional[str] = Field(default=None)
    instagram_2fa_seed: Optional[str] = Field(default=None)

    # X/Twitter
    x_api_key: Optional[str] = Field(default=None)
    x_api_secret: Optional[str] = Field(default=None)
    x_access_token: Optional[str] = Field(default=None)
    x_access_token_secret: Optional[str] = Field(default=None)
    x_bearer_token: Optional[str] = Field(default=None)

    # General
    max_retries: int = Field(default=3)
    retry_delay: int = Field(default=5)


class ScriptGeneratorSettings(BaseSettings):
    """Settings for newsletter-to-script conversion."""

    model_config = SettingsConfigDict(env_prefix="SCRIPT_")

    llm_provider: str = Field(default="local")  # local, openai, anthropic
    llm_model: str = Field(default="qwen2.5:7b")  # For local Ollama
    llm_base_url: str = Field(default="http://localhost:11434")
    openai_api_key: Optional[str] = Field(default=None)
    anthropic_api_key: Optional[str] = Field(default=None)

    # Script generation settings
    max_long_form_words: int = Field(default=2000)
    max_short_form_words: int = Field(default=150)
    default_tone: str = Field(default="professional")  # casual, professional, enthusiastic
    include_hooks: bool = Field(default=True)
    include_cta: bool = Field(default=True)


class RedisSettings(BaseSettings):
    """Redis connection settings for job queue."""

    model_config = SettingsConfigDict(env_prefix="REDIS_")

    host: str = Field(default="localhost")
    port: int = Field(default=6379)
    db: int = Field(default=0)
    password: Optional[str] = Field(default=None)

    @property
    def url(self) -> str:
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


class APISettings(BaseSettings):
    """API Gateway settings."""

    model_config = SettingsConfigDict(env_prefix="API_")

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    debug: bool = Field(default=False)
    cors_origins: list[str] = Field(default=["*"])
    api_key: Optional[str] = Field(default=None)
    rate_limit_requests: int = Field(default=100)
    rate_limit_period: int = Field(default=60)


class Settings(BaseSettings):
    """Main settings container."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Environment
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")

    # Sub-settings
    gpu_server: GPUServerSettings = Field(default_factory=GPUServerSettings)
    voice_cloner: VoiceClonerSettings = Field(default_factory=VoiceClonerSettings)
    avatar_generator: AvatarGeneratorSettings = Field(default_factory=AvatarGeneratorSettings)
    video_processor: VideoProcessorSettings = Field(default_factory=VideoProcessorSettings)
    social_publisher: SocialPublisherSettings = Field(default_factory=SocialPublisherSettings)
    script_generator: ScriptGeneratorSettings = Field(default_factory=ScriptGeneratorSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    api: APISettings = Field(default_factory=APISettings)


# Global settings instance
settings = Settings()
