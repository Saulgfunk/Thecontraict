"""Celery application for background work (document pipeline, reminders, digests)."""

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "contraict",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        # Idempotent: each reminder point is sent once, so running often is safe.
        "send-due-reminders": {"task": "reminders.send_due", "schedule": crontab(minute=5)},
        "send-weekly-digests": {
            "task": "reminders.weekly_digest",
            "schedule": crontab(minute=0, hour=6, day_of_week="mon"),
        },
    },
)


@celery_app.task(name="system.ping")
def ping() -> str:
    return "pong"
