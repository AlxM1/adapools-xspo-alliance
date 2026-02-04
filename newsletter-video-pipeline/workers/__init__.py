"""
Newsletter Video Pipeline - Celery Workers Package.

This package contains all Celery tasks for async job processing.
"""

from .celery_app import celery_app

__all__ = ["celery_app"]
