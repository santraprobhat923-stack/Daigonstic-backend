from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from app.models import NotificationJob, ReportDocument
from app.services.audit_service import log_audit_event


class BaseNotificationProvider:
    def send(self, recipient: str, channel: str, message: str):
        raise NotImplementedError


class ProviderResult:
    def __init__(self, success: bool, error: Optional[str] = None):
        self.success = success
        self.error = error


class NotificationDispatcher:
    @classmethod
    def dispatch_job(
        cls,
        db: Session,
        job_id: int,
        centre_id: int,
        provider: BaseNotificationProvider,
    ) -> NotificationJob:
        job = (
            db.query(NotificationJob)
            .filter(
                NotificationJob.id == job_id,
                NotificationJob.centre_id == centre_id,
            )
            .first()
        )

        if not job:
            raise ValueError("Notification job not found or tenant unauthorized.")

        if job.status in ["SENT", "SKIPPED"]:
            return job

        # Verify report is RELEASED before dispatching
        report = (
            db.query(ReportDocument)
            .filter(
                ReportDocument.id == job.report_id,
                ReportDocument.centre_id == centre_id,
            )
            .first()
        )

        if not report or not report.is_released or report.release_status != "RELEASED":
            job.status = "FAILED"
            job.last_error = "Integrity violation: Report is not in RELEASED status."
            db.commit()
            db.refresh(job)
            return job

        job.status = "PROCESSING"
        job.attempt_count += 1
        job.last_attempt_at = datetime.utcnow()
        db.commit()

        # Dispatch via provider
        try:
            res = provider.send(
                recipient=job.recipient,
                channel=job.channel,
                message=job.message_payload,
            )
        except Exception as exc:
            res = ProviderResult(success=False, error=str(exc))

        if res.success:
            job.status = "SENT"
            job.sent_at = datetime.utcnow()
            job.last_error = None
            log_audit_event(
                db=db,
                centre_id=centre_id,
                event_type="NOTIFICATION_SENT",
                entity_type="NOTIFICATION_JOB",
                entity_id=job.id,
                actor_user_id=None,
                payload={
                    "recipient": job.recipient,
                    "channel": job.channel,
                    "attempt_count": job.attempt_count,
                },
            )
        else:
            job.last_error = str(res.error) if res.error else "Unknown provider failure"
            job.status = "FAILED"

            log_audit_event(
                db=db,
                centre_id=centre_id,
                event_type="NOTIFICATION_FAILED",
                entity_type="NOTIFICATION_JOB",
                entity_id=job.id,
                actor_user_id=None,
                payload={
                    "recipient": job.recipient,
                    "last_error": job.last_error,
                    "attempt_count": job.attempt_count,
                    "status": job.status,
                },
            )

        db.commit()
        db.refresh(job)
        return job
