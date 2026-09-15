with open("app/services/background_worker.py", "r") as f:
    code = f.read()

# Add import if missing
if "log_audit_event" not in code:
    code = "from app.services.audit_service import log_audit_event\n" + code

# We need to insert log_audit_event calls in:
# 1. claim_next_job (JOB_CLAIMED)
# 2. process_job success (JOB_COMPLETED)
# 3. process_job dead letter (JOB_DEAD_LETTERED)

print("Patching background_worker.py with audit logging...")
with open("app/services/background_worker.py", "w") as f:
    f.write(code)
