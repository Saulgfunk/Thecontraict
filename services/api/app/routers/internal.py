"""Endpoints for an external scheduler (e.g. a GitHub Actions cron) on hosts without a
background worker. Protected by ``CRON_SECRET``; disabled when it is empty."""

import hmac
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, status

from app.config import get_settings
from app.reminders import send_due_reminders, send_weekly_digests

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


@router.post("/jobs/{job}")
def run_job(
    job: Literal["reminders", "digests"], x_cron_secret: str = Header(default="")
) -> dict[str, int]:
    secret = get_settings().cron_secret
    if not secret or not hmac.compare_digest(x_cron_secret.encode(), secret.encode()):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    count = send_due_reminders() if job == "reminders" else send_weekly_digests()
    return {"sent": count}
