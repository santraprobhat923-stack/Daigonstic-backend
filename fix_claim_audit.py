with open("app/services/background_worker.py", "r") as f:
    code = f.read()

# Replace the return block in claim_next_job to include audit logging safely
old_block = """            if result.rowcount == 1:
                job = db.query(NotificationJob).filter(NotificationJob.id == job_id).first()
                return job"""

new_block = """            if result.rowcount == 1:
                job = db.query(NotificationJob).filter(NotificationJob.id == job_id).first()
                if job:
                    try:
                        log_audit_event(
                            db=db,
                            centre_id=job.centre_id,
                            event_type="JOB_CLAIMED",
                            entity_type="NOTIFICATION_JOB",
                            entity_id=job.id,
                            payload={"job_id": job.id, "worker_id": self.worker_id}
                        )
                        db.commit()
                    except Exception:
                        pass
                return job"""

if old_block in code:
    code = code.replace(old_block, new_block, 1)
    with open("app/services/background_worker.py", "w") as f:
        f.write(code)
    print("Successfully fixed claim_next_job audit logging and return.")
else:
    print("Could not find old_block in background_worker.py.")
