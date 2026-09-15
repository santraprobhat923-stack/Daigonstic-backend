with open("app/routers/report_ingest.py", "r") as f:
    code = f.read()

target = 'storage_status="stored"'
replacement = 'storage_status="stored",\n        is_released=True,\n        release_status="RELEASED"'

if target in code:
    code = code.replace(target, replacement, 1)
    with open("app/routers/report_ingest.py", "w") as f:
        f.write(code)
    print("ReportDocument updated with is_released=True and release_status='RELEASED'.")
else:
    print("Target storage_status not found.")
