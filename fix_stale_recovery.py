with open("app/services/background_worker.py", "r") as f:
    code = f.read()

old_recover = """    def recover_stale_jobs(self, db: Session) -> int:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=self.stale_timeout_minutes)
        try:
            stale_jobs = db.query(NotificationJob).filter(
                NotificationJob.status == "PROCESSING",
                NotificationJob.locked_at < cutoff
            ).all()"""

new_recover = """    def recover_stale_jobs(self, db: Session) -> int:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=self.stale_timeout_minutes)
        try:
            # Fetch all PROCESSING jobs and filter in Python to avoid timezone comparison issues in SQLite
            processing_jobs = db.query(NotificationJob).filter(
                NotificationJob.status == "PROCESSING",
                NotificationJob.locked_at != None
            ).all()
            
            stale_jobs = []
            for job in processing_jobs:
                lat = job.locked_at
                if lat:
                    if lat.tzinfo is None:
                        lat = lat.replace(tzinfo=timezone.utc)
                    if lat < cutoff:
                        stale_jobs.append(job)"""

if old_recover in code:
    code = code.replace(old_recover, new_recover, 1)
    with open("app/services/background_worker.py", "w") as f:
        f.write(code)
    print("Successfully patched recover_stale_jobs.")
else:
    print("Could not find old_recover block.")
