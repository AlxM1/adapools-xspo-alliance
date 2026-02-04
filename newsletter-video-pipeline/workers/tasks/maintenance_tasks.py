"""
Celery tasks for system maintenance.
"""

import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from celery.utils.log import get_task_logger

from workers.celery_app import celery_app
from .pipeline_tasks import run_async

logger = get_task_logger(__name__)


@celery_app.task
def cleanup_temp_files():
    """
    Clean up temporary files older than 24 hours.
    """
    logger.info("Starting temp file cleanup...")

    temp_dirs = [
        os.getenv("TEMP_DIR", "/tmp/pipeline"),
        os.getenv("VIDEO_TEMP_DIR", "/tmp/video_processor"),
        os.getenv("VOICE_TEMP_DIR", "/tmp/voice_cloner"),
        os.getenv("AVATAR_TEMP_DIR", "/tmp/avatar_generator"),
    ]

    cutoff = datetime.utcnow() - timedelta(hours=24)
    deleted_count = 0
    freed_bytes = 0

    for temp_dir in temp_dirs:
        temp_path = Path(temp_dir)
        if not temp_path.exists():
            continue

        for item in temp_path.iterdir():
            try:
                stat = item.stat()
                mtime = datetime.fromtimestamp(stat.st_mtime)

                if mtime < cutoff:
                    if item.is_file():
                        freed_bytes += stat.st_size
                        item.unlink()
                        deleted_count += 1
                    elif item.is_dir():
                        dir_size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                        freed_bytes += dir_size
                        shutil.rmtree(item)
                        deleted_count += 1

            except Exception as e:
                logger.warning(f"Failed to clean up {item}: {e}")

    freed_mb = freed_bytes / (1024 * 1024)
    logger.info(f"Cleanup complete: {deleted_count} items deleted, {freed_mb:.2f} MB freed")

    return {
        "deleted_count": deleted_count,
        "freed_mb": round(freed_mb, 2),
    }


@celery_app.task
def cleanup_expired_tokens():
    """
    Clean up expired refresh tokens and API keys.
    """
    logger.info("Starting token cleanup...")
    result = run_async(_cleanup_tokens_async())
    return result


async def _cleanup_tokens_async():
    """Async token cleanup."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import delete

    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://nvp:nvp_password@localhost:5432/newsletter_video_pipeline"
    )
    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        from database.models import RefreshToken, APIKey

        now = datetime.utcnow()

        # Delete expired refresh tokens
        result1 = await db.execute(
            delete(RefreshToken).where(RefreshToken.expires_at < now)
        )
        refresh_deleted = result1.rowcount

        # Delete revoked refresh tokens older than 7 days
        result2 = await db.execute(
            delete(RefreshToken).where(
                RefreshToken.revoked_at < now - timedelta(days=7)
            )
        )
        revoked_deleted = result2.rowcount

        # Delete expired API keys
        result3 = await db.execute(
            delete(APIKey).where(
                (APIKey.expires_at != None) & (APIKey.expires_at < now)
            )
        )
        api_keys_deleted = result3.rowcount

        await db.commit()

        logger.info(
            f"Token cleanup: {refresh_deleted} expired, "
            f"{revoked_deleted} revoked refresh tokens, "
            f"{api_keys_deleted} expired API keys"
        )

    await engine.dispose()

    return {
        "refresh_tokens_deleted": refresh_deleted + revoked_deleted,
        "api_keys_deleted": api_keys_deleted,
    }


@celery_app.task
def generate_usage_stats():
    """
    Generate hourly usage statistics for all users.
    """
    logger.info("Generating usage statistics...")
    result = run_async(_generate_stats_async())
    return result


async def _generate_stats_async():
    """Async usage stats generation."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select, func

    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://nvp:nvp_password@localhost:5432/newsletter_video_pipeline"
    )
    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        from database.models import User, PipelineJob, Video, Publication, UsageStats, PipelineStatus

        now = datetime.utcnow()
        period_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
        period_end = now.replace(minute=0, second=0, microsecond=0)

        # Get all active users
        users_result = await db.execute(
            select(User).where(User.is_active == True)
        )
        users = list(users_result.scalars().all())

        stats_created = 0

        for user in users:
            # Count pipelines created in period
            pipelines_result = await db.execute(
                select(func.count(PipelineJob.id)).where(
                    (PipelineJob.user_id == user.id)
                    & (PipelineJob.created_at >= period_start)
                    & (PipelineJob.created_at < period_end)
                )
            )
            pipelines_count = pipelines_result.scalar() or 0

            # Count videos generated
            videos_result = await db.execute(
                select(func.count(Video.id)).where(
                    Video.pipeline_job_id.in_(
                        select(PipelineJob.id).where(
                            (PipelineJob.user_id == user.id)
                            & (PipelineJob.created_at >= period_start)
                            & (PipelineJob.created_at < period_end)
                        )
                    )
                )
            )
            videos_count = videos_result.scalar() or 0

            # Sum video minutes
            video_minutes_result = await db.execute(
                select(func.sum(Video.duration_sec)).where(
                    Video.pipeline_job_id.in_(
                        select(PipelineJob.id).where(
                            (PipelineJob.user_id == user.id)
                            & (PipelineJob.created_at >= period_start)
                            & (PipelineJob.created_at < period_end)
                        )
                    )
                )
            )
            video_seconds = video_minutes_result.scalar() or 0

            # Count publications
            publications_result = await db.execute(
                select(func.count(Publication.id)).where(
                    (Publication.pipeline_job_id.in_(
                        select(PipelineJob.id).where(PipelineJob.user_id == user.id)
                    ))
                    & (Publication.created_at >= period_start)
                    & (Publication.created_at < period_end)
                )
            )
            publications_count = publications_result.scalar() or 0

            # Only create stats if there's activity
            if pipelines_count > 0 or videos_count > 0 or publications_count > 0:
                usage_stat = UsageStats(
                    user_id=user.id,
                    period_start=period_start,
                    period_end=period_end,
                    pipelines_created=pipelines_count,
                    videos_generated=videos_count,
                    video_minutes_generated=video_seconds / 60,
                    publications_count=publications_count,
                )
                db.add(usage_stat)
                stats_created += 1

        await db.commit()
        logger.info(f"Generated {stats_created} usage stat records")

    await engine.dispose()

    return {"stats_created": stats_created}


@celery_app.task
def cleanup_old_jobs():
    """
    Clean up completed jobs older than 30 days.
    """
    logger.info("Cleaning up old jobs...")
    result = run_async(_cleanup_old_jobs_async())
    return result


async def _cleanup_old_jobs_async():
    """Async old job cleanup."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import delete

    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://nvp:nvp_password@localhost:5432/newsletter_video_pipeline"
    )
    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        from database.models import PipelineJob, PipelineStatus

        cutoff = datetime.utcnow() - timedelta(days=30)

        # Delete old completed/failed jobs
        result = await db.execute(
            delete(PipelineJob).where(
                (PipelineJob.completed_at < cutoff)
                & (PipelineJob.status.in_([PipelineStatus.COMPLETED, PipelineStatus.FAILED]))
            )
        )
        deleted = result.rowcount
        await db.commit()

        logger.info(f"Deleted {deleted} old pipeline jobs")

    await engine.dispose()

    return {"deleted_jobs": deleted}


@celery_app.task
def backup_database():
    """
    Create a database backup.
    """
    import subprocess
    from datetime import datetime

    logger.info("Creating database backup...")

    backup_dir = os.getenv("BACKUP_DIR", "/opt/nvp/backups")
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_dir, f"nvp_backup_{timestamp}.sql.gz")

    db_host = os.getenv("DATABASE_HOST", "localhost")
    db_port = os.getenv("DATABASE_PORT", "5432")
    db_name = os.getenv("DATABASE_NAME", "newsletter_video_pipeline")
    db_user = os.getenv("DATABASE_USER", "nvp")
    db_password = os.getenv("DATABASE_PASSWORD", "nvp_password")

    # Set password in environment
    env = os.environ.copy()
    env["PGPASSWORD"] = db_password

    cmd = f"pg_dump -h {db_host} -p {db_port} -U {db_user} -d {db_name} | gzip > {backup_file}"

    result = subprocess.run(cmd, shell=True, env=env, capture_output=True)

    if result.returncode != 0:
        logger.error(f"Backup failed: {result.stderr.decode()}")
        raise RuntimeError(f"Backup failed: {result.stderr.decode()}")

    # Get backup size
    backup_size = os.path.getsize(backup_file) / (1024 * 1024)

    logger.info(f"Backup created: {backup_file} ({backup_size:.2f} MB)")

    # Clean up old backups (keep last 7)
    backups = sorted(Path(backup_dir).glob("nvp_backup_*.sql.gz"))
    for old_backup in backups[:-7]:
        old_backup.unlink()
        logger.info(f"Deleted old backup: {old_backup}")

    return {
        "backup_file": backup_file,
        "size_mb": round(backup_size, 2),
    }
