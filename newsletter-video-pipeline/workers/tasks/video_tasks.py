"""
Celery tasks for video generation and processing.
"""

import os
from datetime import datetime
from uuid import UUID

from celery.utils.log import get_task_logger
import httpx

from workers.celery_app import celery_app
from .pipeline_tasks import run_async

logger = get_task_logger(__name__)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=120)
def generate_video(self, video_id: str, audio_path: str, avatar_id: str = None):
    """
    Generate an avatar video from audio.
    """
    logger.info(f"Generating video for audio: {audio_path}")

    try:
        result = run_async(_generate_video_async(video_id, audio_path, avatar_id))
        return result
    except Exception as exc:
        logger.exception(f"Video generation failed: {exc}")
        raise self.retry(exc=exc)


async def _generate_video_async(video_id: str, audio_path: str, avatar_id: str = None):
    """Async video generation."""
    avatar_url = os.getenv("GPU_AVATAR_URL", "http://192.168.1.100:5003")

    async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
        response = await client.post(
            f"{avatar_url}/generate",
            json={
                "audio_path": audio_path,
                "avatar_id": avatar_id,
                "resolution": "1080p",
                "fps": 30,
            },
        )
        response.raise_for_status()
        return response.json()


@celery_app.task(bind=True, max_retries=2, default_retry_delay=60)
def process_video(self, video_id: str, input_path: str, platforms: list):
    """
    Process a video for multiple platforms.
    """
    logger.info(f"Processing video: {input_path} for platforms: {platforms}")

    try:
        result = run_async(_process_video_async(video_id, input_path, platforms))
        return result
    except Exception as exc:
        logger.exception(f"Video processing failed: {exc}")
        raise self.retry(exc=exc)


async def _process_video_async(video_id: str, input_path: str, platforms: list):
    """Async video processing."""
    video_processor_url = os.getenv("VIDEO_PROCESSOR_URL", "http://localhost:5005")

    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
        response = await client.post(
            f"{video_processor_url}/process",
            json={
                "input_path": input_path,
                "platforms": platforms,
                "normalize_audio": True,
            },
        )
        response.raise_for_status()
        data = response.json()

        # Update video record in database
        await _update_video_record(video_id, data)

        return data


async def _update_video_record(video_id: str, process_data: dict):
    """Update video record with processing results."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select

    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://nvp:nvp_password@localhost:5432/newsletter_video_pipeline"
    )
    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        from database.models import Video

        result = await db.execute(
            select(Video).where(Video.id == UUID(video_id))
        )
        video = result.scalar_one_or_none()

        if video:
            platform_versions = {}
            for output in process_data.get("outputs", []):
                platform_versions[output["platform"]] = output["path"]

            video.platform_versions = platform_versions
            await db.commit()

    await engine.dispose()


@celery_app.task
def generate_thumbnail(video_path: str, output_path: str, timestamp: float = 1.0):
    """Generate a thumbnail from a video."""
    import subprocess

    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(timestamp),
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"Thumbnail generation failed: {result.stderr.decode()}")

    return output_path


@celery_app.task
def generate_shorts_from_long_form(video_id: str, video_path: str, count: int = 3):
    """Generate short clips from a long-form video."""
    logger.info(f"Generating {count} shorts from video: {video_path}")

    result = run_async(_generate_shorts_async(video_id, video_path, count))
    return result


async def _generate_shorts_async(video_id: str, video_path: str, count: int):
    """Async shorts generation."""
    video_processor_url = os.getenv("VIDEO_PROCESSOR_URL", "http://localhost:5005")

    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
        response = await client.post(
            f"{video_processor_url}/process",
            json={
                "input_path": video_path,
                "platforms": ["tiktok"],
                "generate_shorts": True,
                "shorts_count": count,
            },
        )
        response.raise_for_status()
        return response.json()
