with open("app/services/background_worker.py", "r") as f:
    content = f.read()

# Let's find and replace the messy section in claim_next_job.
# We want the successful branch of "if result.rowcount == 1:" to query the job, log the audit event, and return the job cleanly.

old_snippet = """            if result.rowcount == 1:
                log_audit_event("""

# Alternatively, let us write a clean helper or script to fix lines 112 through 128
