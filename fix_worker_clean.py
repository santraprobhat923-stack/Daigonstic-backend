import time
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import update, or_
import sqlite3
from app.models import NotificationJob

class BackgroundWorker:
    def __init__(
        self,
        worker_id: str = "worker-1",
        base_backoff_seconds: int = 2,
        max_retries: int = 3,
        stale_timeout_minutes: int = 15,
        provider = None
    ):
        self.worker_id = worker_id
        self.base_backoff_seconds = base_backoff_seconds
        self.max_retries = max_retries
        self.stale_timeout_minutes = stale_timeout_minutes
        self.provider = provider

    def recover_stale_jobs(self, db: Session) -> int:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=self.stale_timeout_minutes)
        try:
            stale_jobs = db.query(NotificationJob).filter(
                NotificationJob.status == "PROCESSING",
                NotificationJob.locked_at < cutoff
            ).all()
            count = 0
            for job in stale_jobs:
                job.status = "PENDING"
                job.locked_at = None
                job.locked_by = None
                job.last_error = (job.last_error or "") + " [Recovered from stale PROCESSING state]"
                count += 1
            if count > 0:
                db.commit()
            return count
        except Exception:
            db.rollback()
            return 0

    def claim_next_job(self, db: Session) -> Optional[NotificationJob]:
        self.recover_stale_jobs(db)
        now = datetime.now(timezone.utc)

        for attempt in range(5):
            try:
                candidate = db.query(NotificationJob.id).filter(
                    NotificationJob.status == "PENDING",
                    or_(
                        NotificationJob.next_attempt_at == None,
                        NotificationJob.next_attempt_at <= now
                    )
                ).order_by(NotificationJob.id.asc()).first()

                if not candidate:
                    return None

                job_id = candidate[0]

                stmt = (
                    update(NotificationJob)
                    .where(
                        NotificationJob.id == job_id,
                        NotificationJob.status == "PENDING"
                    )
                    .values(
                        status="PROCESSING",
                        locked_by=self.worker_id,
                        locked_at=now,
                        attempt_count=NotificationJob.attempt_count + 1
                    )
                    .execution_options(synchronize_session=False)
                )

                result = db.execute(stmt)
                db.commit()

                if result.rowcount == 1:
                    job = db.query(NotificationJob).filter(NotificationJob.id == job_id).first()
                    return job
                else:
                    db.rollback()
                    return None
            except sqlite3.OperationalError:
                db.rollback()
                time.sleep(0.01 * (attempt + 1))
                continue
            except Exception:
                db.rollback()
                break
        return None

    def process_job(self, db: Session, job: NotificationJob, provider=None) -> str:
        prov = provider or self.provider
        now = datetime.now(timezone.utc)
        job.started_at = now
        try:
            if prov:
                success = prov.send(job.channel, job.recipient, job.message_payload)
                if not success:
                    raise Exception("Provider returned failure status.")
            
            job.status = "SENT"
            job.sent_at = datetime.now(timezone.utc)
            job.completed_at = datetime.now(timezone.utc)
            job.locked_at = None
            job.locked_by = None
            db.commit()
            return "SENT"
        except Exception as exc:
            now_exc = datetime.now(timezone.utc)
            job.attempt_count = (job.attempt_count or 0)
            job.last_error = f"Unexpected worker error: {str(exc)}"
            max_retries = job.max_retries or self.max_retries

            if job.attempt_count >= max_retries:
                job.status = "DEAD_LETTER"
                job.dead_lettered_at = now_exc
                job.locked_at = None
                job.locked_by = None
            else:
                job.status = "PENDING"
                backoff = self.base_backoff_seconds * (2 ** (job.attempt_count - 1))
                job.next_attempt_at = now_exc + timedelta(seconds=backoff)
                job.locked_at = None
                job.locked_by = None
            db.commit()
            return job.status

    def process_one_batch(self, db: Session, limit: int = 10, provider=None) -> int:
        self.recover_stale_jobs(db)
        processed = 0
        for _ in range(limit):
            job = self.claim_next_job(db)
            if not job:
                break
            self.process_job(db, job, provider)
            processed += 1
        return processed
'''-with open("app/services/background_worker.py", "w") as f:
    f.write(worker_code) if 'worker_code' in globals() else None
