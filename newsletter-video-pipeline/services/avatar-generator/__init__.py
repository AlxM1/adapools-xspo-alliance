"""Avatar Generator Service - MuseTalk + LivePortrait based video generation."""

from .service import AvatarGeneratorService
from .models import (
    AvatarModel,
    CreateAvatarRequest,
    GenerateVideoRequest,
    GenerateVideoResponse,
)

__all__ = [
    "AvatarGeneratorService",
    "AvatarModel",
    "CreateAvatarRequest",
    "GenerateVideoRequest",
    "GenerateVideoResponse",
]
