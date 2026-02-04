"""Configuration module for Newsletter Video Pipeline."""

from .settings import (
    Settings,
    settings,
    GPUServerSettings,
    VoiceClonerSettings,
    AvatarGeneratorSettings,
    VideoProcessorSettings,
    SocialPublisherSettings,
    ScriptGeneratorSettings,
    RedisSettings,
    APISettings,
)

__all__ = [
    "Settings",
    "settings",
    "GPUServerSettings",
    "VoiceClonerSettings",
    "AvatarGeneratorSettings",
    "VideoProcessorSettings",
    "SocialPublisherSettings",
    "ScriptGeneratorSettings",
    "RedisSettings",
    "APISettings",
]
