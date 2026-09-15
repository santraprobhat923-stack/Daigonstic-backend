with open("app/routers/report_ingest.py", "r") as f:
    code = f.read()

target = """storage_status="stored",
        is_released=True,
        release_status="RELEASED\""""

replacement = """storage_status="stored",
        is_released=False,
        release_status="HELD_PAYMENT\""""

if target in code:
    code = code.replace(target, replacement, 1)
    with open("app/routers/report_ingest.py", "w") as f:
        f.write(code)
    print("M4 successfully reverted to: is_released=False, release_status='HELD_PAYMENT'")
else:
    print("Target release block not found. Checking alternate formatting...")
    # Fallback replacement if single line
    code = code.replace('is_released=True', 'is_released=False')
    code = code.replace('release_status="RELEASED"', 'release_status="HELD_PAYMENT"')
    with open("app/routers/report_ingest.py", "w") as f:
        f.write(code)
    print("M4 flags set to HELD_PAYMENT.")
