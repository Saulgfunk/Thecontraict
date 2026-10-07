"""Celery application for background work (document pipeline, reminders, digests)."""

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery("contraict", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Reminder scanning and digests are added to the beat schedule in Phase 1.
    beat_schedule={},
)


@celery_app.task(name="system.ping")
def ping() -> str:
    return "pong"
