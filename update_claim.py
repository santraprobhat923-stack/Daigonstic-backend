with open("app/services/background_worker.py", "r") as f:
    code = f.read()

# Replace claim_next_job implementation with bulletproof atomic claim
import re

claim_fn = '''    def claim_next_job(self, db: Session) -> Optional[NotificationJob]:
        now = datetime.now(timezone.utc)
        now_iso = now.strftime("%Y-%m-%d %H:%M:%S")

        raw_conn = db.connection().connection
        cursor = raw_conn.cursor()
        claimed_id = None
        try:
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("""
                SELECT id FROM notification_jobs
                WHERE status = 'PENDING'
                  AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                ORDER BY created_at ASC
                LIMIT 1
            """, (now_iso,))
            row = cursor.fetchone()
            if row:
                job_id = row[0]
                cursor.execute("""
                    UPDATE notification_jobs
                    SET status = 'PROCESSING',
                        locked_at = ?,
                        locked_by = ?
                    WHERE id = ? AND status = 'PENDING'
                """, (now_iso, self.worker_id, job_id))
                if cursor.rowcount == 1:
                    claimed_id = job_id
            raw_conn.commit()
        except Exception:
            try:
                raw_conn.rollback()
            except Exception:
                pass
            claimed_id = None

        if claimed_id:
            # Expire session cache to read latest committed state
            db.expire_all()
            claimed = db.query(NotificationJob).filter(NotificationJob.id == claimed_id).first()
            if claimed:
                log_audit_event(
                    db=db,
                    centre_id=claimed.centre_id,
                    event_type="JOB_CLAIMED",
                    entity_type="NOTIFICATION_JOB",
                    entity_id=claimed.id,
                    actor_user_id=None,
                    payload={"worker_id": self.worker_id, "claimed_at": now_iso}
                )
                db.commit()
                return claimed

        return None'''

code = re.sub(
    r"    def claim_next_job\(self, db: Session\) -> Optional\[NotificationJob\]:.*?(?=    def calculate_backoff)",
    claim_fn + "\n\n",
    code,
    flags=re.DOTALL
)

with open("app/services/background_worker.py", "w") as f:
    f.write(code)

print("Applied robust serialized BEGIN IMMEDIATE claim_next_job.")
