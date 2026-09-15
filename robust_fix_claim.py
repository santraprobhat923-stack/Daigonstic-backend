with open("app/services/background_worker.py", "r") as f:
    code = f.read()

# Let us find where claim_next_job returns the job and rewrite that section cleanly
if "def claim_next_job" in code:
    # Find the return statement inside claim_next_job
    target = "if result.rowcount == 1:"
    replacement = """if result.rowcount == 1:
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
    
    if target in code and "JOB_CLAIMED" not in code:
        code = code.replace(target, replacement, 1)
        with open("app/services/background_worker.py", "w") as f:
            f.write(code)
        print("Successfully applied robust claim and audit patch.")
    else:
        print("Target already patched or not found.")
else:
    print("claim_next_job not found.")
