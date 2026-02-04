"""
Celery application configuration.
"""

import os
from celery import Celery

# Redis connection
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_BACKEND = os.getenv("REDIS_BACKEND", "redis://localhost:6379/1")

# Create Celery app
celery_app = Celery(
    "newsletter_video_pipeline",
    broker=REDIS_URL,
    backend=REDIS_BACKEND,
    include=[
        "workers.tasks.pipeline_tasks",
        "workers.tasks.video_tasks",
        "workers.tasks.publish_tasks",
        "workers.tasks.maintenance_tasks",
    ],
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Task execution
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=3600,  # 1 hour max
    task_soft_time_limit=3300,  # 55 minutes soft limit

    # Worker settings
    worker_prefetch_multiplier=1,
    worker_concurrency=int(os.getenv("CELERY_CONCURRENCY", "4")),

    # Result backend
    result_expires=86400,  # 24 hours

    # Task routes
    task_routes={
        "workers.tasks.pipeline_tasks.*": {"queue": "pipeline"},
        "workers.tasks.video_tasks.*": {"queue": "video"},
        "workers.tasks.publish_tasks.*": {"queue": "publish"},
        "workers.tasks.maintenance_tasks.*": {"queue": "maintenance"},
    },

    # Beat schedule (periodic tasks)
    beat_schedule={
        "cleanup-temp-files": {
            "task": "workers.tasks.maintenance_tasks.cleanup_temp_files",
            "schedule": 3600.0,  # Every hour
        },
        "cleanup-expired-tokens": {
            "task": "workers.tasks.maintenance_tasks.cleanup_expired_tokens",
            "schedule": 86400.0,  # Every day
        },
        "generate-usage-stats": {
            "task": "workers.tasks.maintenance_tasks.generate_usage_stats",
            "schedule": 3600.0,  # Every hour
        },
        "retry-failed-publications": {
            "task": "workers.tasks.publish_tasks.retry_failed_publications",
            "schedule": 900.0,  # Every 15 minutes
        },
    },
)


def get_celery_app() -> Celery:
    """Get the Celery app instance."""
    return celery_app
