with open("app/services/background_worker.py", "r") as f:
    code = f.read()

# Replace the exception handling block in process_job
old_block = """        except Exception as exc:
            now_exc = datetime.now(timezone.utc)
            job.attempt_count = (job.attempt_count or 0)
            job.last_error = f"Unexpected worker error: {str(exc)}"
            max_retries = job.max_retries or self.max_retries

            if job.attempt_count >= max_retries:"""

new_block = """        except Exception as exc:
            now_exc = datetime.now(timezone.utc)
            job.attempt_count = (job.attempt_count or 0) + 1
            job.last_error = f"Unexpected worker error: {str(exc)}"
            max_retries = job.max_retries or self.max_retries

            if job.attempt_count >= max_retries:"""

if old_block in code:
    code = code.replace(old_block, new_block, 1)
    with open("app/services/background_worker.py", "w") as f:
        f.write(code)
    print("Successfully patched process_job attempt_count increment.")
else:
    print("Could not find old_block.")
