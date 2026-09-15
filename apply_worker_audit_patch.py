with open("app/services/background_worker.py", "r") as f:
    code = f.read()

if "from app.services.audit_service import log_audit_event" not in code:
    code = "from app.services.audit_service import log_audit_event\n" + code

# 1. Add JOB_CLAIMED audit logging in claim_next_job where db.commit() happens after claiming
claim_target = "db.commit()\n        return job"
claim_replacement = """db.commit()
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

if claim_target in code and "JOB_CLAIMED" not in code:
    code = code.replace(claim_target, claim_replacement, 1)

# 2. Add JOB_COMPLETED audit logging in process_job success block
success_target = 'job.status = "SENT"\n            db.commit()'
success_replacement = """job.status = "SENT"
            db.commit()
            try:
                log_audit_event(
                    db=db,
                    centre_id=job.centre_id,
                    event_type="JOB_COMPLETED",
                    entity_type="NOTIFICATION_JOB",
                    entity_id=job.id,
                    payload={"job_id": job.id, "status": "SENT"}
                )
                db.commit()
            except Exception:
                pass"""

if success_target in code and "JOB_COMPLETED" not in code:
    code = code.replace(success_target, success_replacement, 1)

# 3. Add JOB_DEAD_LETTERED audit logging in process_job max retries block
dlq_target = 'job.status = "DEAD_LETTER"\n            job.dead_lettered_at = now_exc'
dlq_replacement = """job.status = "DEAD_LETTER"
            job.dead_lettered_at = now_exc
            db.commit()
            try:
                log_audit_event(
                    db=db,
                    centre_id=job.centre_id,
                    event_type="JOB_DEAD_LETTERED",
                    entity_type="NOTIFICATION_JOB",
                    entity_id=job.id,
                    payload={"job_id": job.id, "attempt_count": job.attempt_count}
                )
                db.commit()
            except Exception:
                pass"""

if dlq_target in code and "JOB_DEAD_LETTERED" not in code:
    code = code.replace(dlq_target, dlq_replacement, 1)

with open("app/services/background_worker.py", "w") as f:
    f.write(code)

print("Applied full audit event logging to background_worker.py!")
