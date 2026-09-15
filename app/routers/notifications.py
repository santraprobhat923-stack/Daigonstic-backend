from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, oauth2
from app.services.notification_dispatcher import NotificationDispatcher
from app.services.notification_provider import MockNotificationProvider

router = APIRouter(prefix="/notifications", tags=["Notifications"])

# Shared mock provider instance for dispatching and testing
default_mock_provider = MockNotificationProvider()

@router.get("/jobs")
def list_notification_jobs(
    report_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    query = db.query(models.NotificationJob).filter(
        models.NotificationJob.centre_id == current_user.centre_id
    )
    if report_id:
        query = query.filter(models.NotificationJob.report_id == report_id)
    return query.all()

@router.post("/jobs/{job_id}/dispatch")
def dispatch_notification_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    job = db.query(models.NotificationJob).filter(
        models.NotificationJob.id == job_id,
        models.NotificationJob.centre_id == current_user.centre_id
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification job not found"
        )

    updated_job = NotificationDispatcher.dispatch_job(
        db=db,
        job_id=job.id,
        centre_id=current_user.centre_id,
        provider=default_mock_provider
    )
    return {
        "job_id": updated_job.id,
        "status": updated_job.status,
        "attempt_count": updated_job.attempt_count,
        "last_error": updated_job.last_error,
        "sent_at": updated_job.sent_at
    }


@router.get("/dlq", status_code=status.HTTP_200_OK)
def list_dead_letter_jobs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    """List dead-lettered jobs strictly scoped to the caller centre."""
    jobs = db.query(models.NotificationJob).filter(
        models.NotificationJob.centre_id == current_user.centre_id,
        models.NotificationJob.status == "DEAD_LETTER"
    ).all()
    return [
        {
            "id": j.id,
            "centre_id": j.centre_id,
            "recipient": j.recipient,
            "channel": j.channel,
            "attempt_count": j.attempt_count,
            "last_error": j.last_error,
            "dead_lettered_at": j.dead_lettered_at,
            "created_at": j.created_at
        }
        for j in jobs
    ]

@router.post("/dlq/{job_id}/replay", status_code=status.HTTP_200_OK)
def replay_dead_letter_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    """Replays a dead-lettered job within the caller tenant context."""
    job = db.query(models.NotificationJob).filter(
        models.NotificationJob.id == job_id
    ).first()

    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification job not found")

    # Strict multi-tenant isolation
    if job.centre_id != current_user.centre_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access forbidden")

    if job.status != "DEAD_LETTER":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job is not in DEAD_LETTER status")

    job.status = "PENDING"
    job.attempt_count = 0
    job.next_attempt_at = None
    job.locked_at = None
    job.locked_by = None
    job.dead_lettered_at = None
    job.last_error = f"Replayed by user {current_user.id}"
    db.commit()

    from app.services.audit_service import log_audit_event
    log_audit_event(
        db=db,
        centre_id=current_user.centre_id,
        event_type="JOB_REPLAYED",
        entity_type="NOTIFICATION_JOB",
        entity_id=job.id,
        actor_user_id=current_user.id,
        payload={"job_id": job.id, "replayed_by_user": current_user.id}
    )
    db.commit()

    return {"message": "Job replayed successfully", "job_id": job.id, "status": "PENDING"}
