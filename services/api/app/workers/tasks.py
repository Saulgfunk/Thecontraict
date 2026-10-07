import uuid

from fastapi import BackgroundTasks

from app.config import get_settings
from app.pipeline.run import process_document
from app.reminders import send_due_reminders, send_weekly_digests
from app.workers.celery_app import celery_app


@celery_app.task(name="documents.process", acks_late=True)
def process_document_task(org_id: str, document_id: str) -> None:
    process_document(uuid.UUID(org_id), uuid.UUID(document_id))


@celery_app.task(name="reminders.send_due")
def send_due_reminders_task() -> int:
    return send_due_reminders()


@celery_app.task(name="reminders.weekly_digest")
def send_weekly_digests_task() -> int:
    return send_weekly_digests()


def enqueue_document(
    background: BackgroundTasks, org_id: uuid.UUID, document_id: uuid.UUID
) -> None:
    """Process on the Celery worker, or in-process after the response when TASKS_EAGER is
    set (development without a worker, and tests)."""
    if get_settings().tasks_eager:
        background.add_task(process_document, org_id, document_id)
    else:
        process_document_task.delay(str(org_id), str(document_id))
