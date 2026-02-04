"""
Celery tasks for social media publishing.
"""

import os
from datetime import datetime, timedelta
from uuid import UUID

from celery.utils.log import get_task_logger
import httpx

from workers.celery_app import celery_app
from .pipeline_tasks import run_async

logger = get_task_logger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def publish_to_platform(
    self,
    publication_id: str,
    video_path: str,
    platform: str,
    title: str,
    description: str,
    tags: list = None,
    privacy: str = "public",
):
    """
    Publish a video to a specific platform.
    """
    logger.info(f"Publishing to {platform}: {title}")

    try:
        result = run_async(_publish_async(
            publication_id, video_path, platform, title, description, tags, privacy
        ))
        return result
    except Exception as exc:
        logger.exception(f"Publishing failed: {exc}")
        run_async(_update_publication_status(publication_id, "failed", str(exc)))
        raise self.retry(exc=exc)


async def _publish_async(
    publication_id: str,
    video_path: str,
    platform: str,
    title: str,
    description: str,
    tags: list,
    privacy: str,
):
    """Async publishing."""
    social_publisher_url = os.getenv("SOCIAL_PUBLISHER_URL", "http://localhost:5006")

    async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
        response = await client.post(
            f"{social_publisher_url}/publish",
            json={
                "video_path": video_path,
                "platforms": [platform],
                "title": title,
                "description": description,
                "tags": tags or [],
                "privacy": privacy,
            },
        )
        response.raise_for_status()
        data = response.json()

        # Update publication record
        for result in data.get("results", []):
            if result["platform"] == platform:
                await _update_publication_status(
                    publication_id,
                    result["status"],
                    result.get("error_message"),
                    result.get("video_id"),
                    result.get("video_url"),
                )

        return data


async def _update_publication_status(
    publication_id: str,
    status: str,
    error_message: str = None,
    platform_video_id: str = None,
    platform_url: str = None,
):
    """Update publication status in database."""
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
        from database.models import Publication, PublishStatus

        result = await db.execute(
            select(Publication).where(Publication.id == UUID(publication_id))
        )
        publication = result.scalar_one_or_none()

        if publication:
            publication.status = PublishStatus(status)
            publication.error_message = error_message
            publication.platform_video_id = platform_video_id
            publication.platform_url = platform_url

            if status == "published":
                publication.published_at = datetime.utcnow()

            await db.commit()

    await engine.dispose()


@celery_app.task
def retry_failed_publications():
    """
    Retry failed publications (periodic task).
    """
    logger.info("Checking for failed publications to retry...")
    result = run_async(_retry_failed_publications_async())
    return result


async def _retry_failed_publications_async():
    """Async retry of failed publications."""
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
        from database.models import Publication, PublishStatus, Video

        # Find failed publications with retry_count < 3
        result = await db.execute(
            select(Publication)
            .where(Publication.status == PublishStatus.FAILED)
            .where(Publication.retry_count < 3)
            .where(Publication.created_at > datetime.utcnow() - timedelta(days=1))
        )
        publications = list(result.scalars().all())

        retried = 0
        for pub in publications:
            # Get video
            video_result = await db.execute(
                select(Video).where(Video.id == pub.video_id)
            )
            video = video_result.scalar_one_or_none()

            if video:
                # Increment retry count
                pub.retry_count += 1
                pub.status = PublishStatus.PENDING
                await db.commit()

                # Queue retry task
                publish_to_platform.delay(
                    publication_id=str(pub.id),
                    video_path=video.platform_versions.get(pub.platform.value, video.file_path),
                    platform=pub.platform.value,
                    title=video.title or "Video",
                    description=video.description or "",
                    tags=video.tags,
                )
                retried += 1

        logger.info(f"Retried {retried} failed publications")

    await engine.dispose()
    return {"retried": retried}


@celery_app.task
def schedule_publication(
    publication_id: str,
    scheduled_time: str,
):
    """
    Schedule a publication for a specific time.
    """
    from datetime import datetime

    scheduled_dt = datetime.fromisoformat(scheduled_time)
    delay = (scheduled_dt - datetime.utcnow()).total_seconds()

    if delay > 0:
        # Schedule the actual publish task
        publish_scheduled_publication.apply_async(
            args=[publication_id],
            countdown=delay,
        )
        logger.info(f"Scheduled publication {publication_id} for {scheduled_time}")
    else:
        # Publish immediately if time has passed
        publish_scheduled_publication.delay(publication_id)


@celery_app.task(bind=True, max_retries=3)
def publish_scheduled_publication(self, publication_id: str):
    """
    Publish a scheduled publication.
    """
    logger.info(f"Publishing scheduled publication: {publication_id}")

    result = run_async(_publish_scheduled_async(publication_id))
    return result


async def _publish_scheduled_async(publication_id: str):
    """Async scheduled publication."""
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
        from database.models import Publication, Video, PublishStatus

        result = await db.execute(
            select(Publication).where(Publication.id == UUID(publication_id))
        )
        pub = result.scalar_one_or_none()

        if not pub:
            return {"error": "Publication not found"}

        if pub.status != PublishStatus.SCHEDULED:
            return {"error": "Publication not in scheduled status"}

        # Get video
        video_result = await db.execute(
            select(Video).where(Video.id == pub.video_id)
        )
        video = video_result.scalar_one_or_none()

        if not video:
            return {"error": "Video not found"}

        # Update status and trigger publish
        pub.status = PublishStatus.PENDING
        await db.commit()

        # Trigger actual publish
        publish_to_platform.delay(
            publication_id=str(pub.id),
            video_path=video.platform_versions.get(pub.platform.value, video.file_path),
            platform=pub.platform.value,
            title=video.title or "Video",
            description=video.description or "",
            tags=video.tags,
        )

    await engine.dispose()
    return {"status": "publishing"}
