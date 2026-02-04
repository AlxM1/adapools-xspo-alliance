"""
Celery tasks for pipeline execution.
"""

import asyncio
from datetime import datetime
from uuid import UUID
from typing import Optional

from celery import shared_task
from celery.utils.log import get_task_logger
import httpx

from workers.celery_app import celery_app

logger = get_task_logger(__name__)


def run_async(coro):
    """Helper to run async code in Celery tasks."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def run_pipeline(self, pipeline_job_id: str, user_id: str):
    """
    Run the complete newsletter-to-video pipeline.

    This is the main task that orchestrates all pipeline stages.
    """
    logger.info(f"Starting pipeline job: {pipeline_job_id}")

    try:
        result = run_async(_run_pipeline_async(pipeline_job_id, user_id, self.request.id))
        return result
    except Exception as exc:
        logger.exception(f"Pipeline failed: {exc}")
        run_async(_update_pipeline_status(pipeline_job_id, "failed", str(exc)))
        raise self.retry(exc=exc)


async def _run_pipeline_async(pipeline_job_id: str, user_id: str, celery_task_id: str):
    """Async implementation of pipeline execution."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select
    import os

    # Create database connection
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://nvp:nvp_password@localhost:5432/newsletter_video_pipeline"
    )
    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # Import here to avoid circular imports
        from database.models import PipelineJob, PipelineStage, PipelineStatus

        # Get pipeline job
        result = await db.execute(
            select(PipelineJob).where(PipelineJob.id == UUID(pipeline_job_id))
        )
        job = result.scalar_one_or_none()

        if not job:
            raise ValueError(f"Pipeline job not found: {pipeline_job_id}")

        # Update status
        job.status = PipelineStatus.GENERATING_SCRIPT
        job.celery_task_id = celery_task_id
        job.started_at = datetime.utcnow()
        await db.commit()

        # Service URLs
        voice_url = os.getenv("GPU_VOICE_URL", "http://192.168.1.100:5002")
        avatar_url = os.getenv("GPU_AVATAR_URL", "http://192.168.1.100:5003")
        video_processor_url = os.getenv("VIDEO_PROCESSOR_URL", "http://localhost:5005")
        script_generator_url = os.getenv("SCRIPT_GENERATOR_URL", "http://localhost:5007")
        social_publisher_url = os.getenv("SOCIAL_PUBLISHER_URL", "http://localhost:5006")

        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            stages_completed = []

            try:
                # Stage 1: Script Generation
                logger.info(f"[{pipeline_job_id}] Stage 1: Generating script...")
                stage1_start = datetime.utcnow()

                script_response = await client.post(
                    f"{script_generator_url}/generate",
                    json={
                        "newsletter_content": job.newsletter_content,
                        "newsletter_title": job.newsletter_title,
                        "format": "both" if job.generate_long_form and job.generate_shorts else (
                            "long_form" if job.generate_long_form else "short_form"
                        ),
                        "tone": job.script_tone,
                    },
                )
                script_response.raise_for_status()
                script_data = script_response.json()

                # Save script results
                if script_data.get("long_form"):
                    job.script_long_form = script_data["long_form"]["full_script"]
                if script_data.get("shorts_clips"):
                    job.script_shorts = [c["full_script"] for c in script_data["shorts_clips"]]

                job.progress_percent = 20
                job.status = PipelineStatus.SYNTHESIZING_VOICE
                await db.commit()

                # Record stage
                stage1 = PipelineStage(
                    pipeline_job_id=job.id,
                    stage_name="script",
                    status="success",
                    started_at=stage1_start,
                    completed_at=datetime.utcnow(),
                    duration_sec=(datetime.utcnow() - stage1_start).total_seconds(),
                    output_data={"tokens_used": script_data.get("tokens_used", 0)},
                )
                db.add(stage1)
                await db.commit()

                # Stage 2: Voice Synthesis
                logger.info(f"[{pipeline_job_id}] Stage 2: Synthesizing voice...")
                stage2_start = datetime.utcnow()

                # Synthesize long-form audio
                if job.script_long_form:
                    voice_response = await client.post(
                        f"{voice_url}/synthesize",
                        json={
                            "text": job.script_long_form,
                            "voice_id": str(job.voice_id) if job.voice_id else None,
                        },
                    )
                    voice_response.raise_for_status()
                    voice_data = voice_response.json()
                    job.audio_path = voice_data["audio_path"]

                job.progress_percent = 40
                job.status = PipelineStatus.GENERATING_VIDEO
                await db.commit()

                stage2 = PipelineStage(
                    pipeline_job_id=job.id,
                    stage_name="voice",
                    status="success",
                    started_at=stage2_start,
                    completed_at=datetime.utcnow(),
                    duration_sec=(datetime.utcnow() - stage2_start).total_seconds(),
                )
                db.add(stage2)
                await db.commit()

                # Stage 3: Avatar Video Generation
                logger.info(f"[{pipeline_job_id}] Stage 3: Generating avatar video...")
                stage3_start = datetime.utcnow()

                if job.audio_path:
                    avatar_response = await client.post(
                        f"{avatar_url}/generate",
                        json={
                            "avatar_id": str(job.avatar_id) if job.avatar_id else None,
                            "audio_path": job.audio_path,
                            "resolution": "1080p",
                        },
                    )
                    avatar_response.raise_for_status()
                    avatar_data = avatar_response.json()

                    # Create video record
                    from database.models import Video
                    video = Video(
                        pipeline_job_id=job.id,
                        video_type="long_form",
                        file_path=avatar_data["video_path"],
                        duration_sec=avatar_data.get("duration_sec"),
                        file_size_mb=avatar_data.get("file_size_mb"),
                        resolution=avatar_data.get("resolution"),
                    )
                    db.add(video)

                job.progress_percent = 60
                job.status = PipelineStatus.PROCESSING_VIDEO
                await db.commit()

                stage3 = PipelineStage(
                    pipeline_job_id=job.id,
                    stage_name="avatar",
                    status="success",
                    started_at=stage3_start,
                    completed_at=datetime.utcnow(),
                    duration_sec=(datetime.utcnow() - stage3_start).total_seconds(),
                )
                db.add(stage3)
                await db.commit()

                # Stage 4: Video Processing
                logger.info(f"[{pipeline_job_id}] Stage 4: Processing video...")
                stage4_start = datetime.utcnow()

                # Get videos for processing
                from database.models import Video
                videos_result = await db.execute(
                    select(Video).where(Video.pipeline_job_id == job.id)
                )
                videos = list(videos_result.scalars().all())

                for video in videos:
                    process_response = await client.post(
                        f"{video_processor_url}/process",
                        json={
                            "input_path": video.file_path,
                            "platforms": job.target_platforms or ["youtube"],
                        },
                    )
                    if process_response.status_code == 200:
                        process_data = process_response.json()
                        platform_versions = {}
                        for output in process_data.get("outputs", []):
                            platform_versions[output["platform"]] = output["path"]
                        video.platform_versions = platform_versions

                job.progress_percent = 80
                await db.commit()

                stage4 = PipelineStage(
                    pipeline_job_id=job.id,
                    stage_name="video_process",
                    status="success",
                    started_at=stage4_start,
                    completed_at=datetime.utcnow(),
                    duration_sec=(datetime.utcnow() - stage4_start).total_seconds(),
                )
                db.add(stage4)
                await db.commit()

                # Stage 5: Publishing (if enabled)
                stage5_start = datetime.utcnow()

                if job.auto_publish and job.publish_platforms:
                    logger.info(f"[{pipeline_job_id}] Stage 5: Publishing...")
                    job.status = PipelineStatus.PUBLISHING
                    await db.commit()

                    # Publish each video to each platform
                    from database.models import Publication, PublishStatus, Platform

                    for video in videos:
                        for platform_name in job.publish_platforms:
                            try:
                                platform = Platform(platform_name)
                                video_path = video.platform_versions.get(platform_name, video.file_path)

                                pub_response = await client.post(
                                    f"{social_publisher_url}/publish",
                                    json={
                                        "video_path": video_path,
                                        "platforms": [platform_name],
                                        "title": job.newsletter_title or "Video",
                                        "description": "",
                                        "privacy": "private",
                                    },
                                )

                                pub_status = PublishStatus.FAILED
                                platform_video_id = None
                                platform_url = None
                                error_message = None

                                if pub_response.status_code == 200:
                                    pub_data = pub_response.json()
                                    for result in pub_data.get("results", []):
                                        if result["platform"] == platform_name:
                                            if result["status"] == "published":
                                                pub_status = PublishStatus.PUBLISHED
                                            platform_video_id = result.get("video_id")
                                            platform_url = result.get("video_url")
                                            error_message = result.get("error_message")

                                publication = Publication(
                                    pipeline_job_id=job.id,
                                    video_id=video.id,
                                    platform=platform,
                                    status=pub_status,
                                    platform_video_id=platform_video_id,
                                    platform_url=platform_url,
                                    error_message=error_message,
                                    published_at=datetime.utcnow() if pub_status == PublishStatus.PUBLISHED else None,
                                )
                                db.add(publication)

                            except Exception as e:
                                logger.error(f"Publishing to {platform_name} failed: {e}")

                    stage5 = PipelineStage(
                        pipeline_job_id=job.id,
                        stage_name="publish",
                        status="success",
                        started_at=stage5_start,
                        completed_at=datetime.utcnow(),
                        duration_sec=(datetime.utcnow() - stage5_start).total_seconds(),
                    )
                else:
                    stage5 = PipelineStage(
                        pipeline_job_id=job.id,
                        stage_name="publish",
                        status="skipped",
                        started_at=stage5_start,
                        completed_at=datetime.utcnow(),
                        duration_sec=0,
                    )

                db.add(stage5)

                # Complete
                job.status = PipelineStatus.COMPLETED
                job.progress_percent = 100
                job.completed_at = datetime.utcnow()
                await db.commit()

                logger.info(f"Pipeline completed: {pipeline_job_id}")
                return {"status": "completed", "job_id": pipeline_job_id}

            except Exception as e:
                logger.exception(f"Pipeline stage failed: {e}")
                job.status = PipelineStatus.FAILED
                job.error_message = str(e)
                job.completed_at = datetime.utcnow()
                await db.commit()
                raise

    await engine.dispose()


async def _update_pipeline_status(pipeline_job_id: str, status: str, error_message: str = None):
    """Update pipeline job status."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select
    import os

    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://nvp:nvp_password@localhost:5432/newsletter_video_pipeline"
    )
    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        from database.models import PipelineJob, PipelineStatus

        result = await db.execute(
            select(PipelineJob).where(PipelineJob.id == UUID(pipeline_job_id))
        )
        job = result.scalar_one_or_none()

        if job:
            job.status = PipelineStatus(status)
            job.error_message = error_message
            job.completed_at = datetime.utcnow()
            await db.commit()

    await engine.dispose()


@celery_app.task(bind=True)
def run_pipeline_stage(self, pipeline_job_id: str, stage_name: str):
    """Run a specific pipeline stage (for manual re-runs)."""
    logger.info(f"Running stage {stage_name} for job {pipeline_job_id}")
    # Implementation for running individual stages
    pass
