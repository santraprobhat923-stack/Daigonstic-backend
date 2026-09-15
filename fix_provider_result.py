with open("app/services/background_worker.py", "r") as f:
    code = f.read()

old_code = """        try:
            if prov:
                success = prov.send(job.channel, job.recipient, job.message_payload)
                if not success:
                    raise Exception("Provider returned failure status.")"""

new_code = """        try:
            if prov:
                res = prov.send(job.channel, job.recipient, job.message_payload)
                # Handle both boolean returns and ProviderResult objects
                if isinstance(res, bool) and not res:
                    raise Exception("Provider returned failure status.")
                elif hasattr(res, 'success') and not res.success:
                    raise Exception(getattr(res, 'error', 'Provider returned failure status.'))"""

if old_code in code:
    code = code.replace(old_code, new_code, 1)
    with open("app/services/background_worker.py", "w") as f:
        f.write(code)
    print("Successfully patched process_job provider result handling.")
else:
    print("Could not find old_code block.")
