import re

with open("test_milestone4_pdf.py", "r") as f:
    content = f.read()

target = '# Test 5: PDF Content Integrity Check'
settle_code = '''# Simulate M5 Payment Settlement prior to testing downstream download
import sqlite3
_conn = sqlite3.connect(DB_PATH)
_conn.execute("UPDATE report_documents SET is_released=1, release_status='RELEASED' WHERE id=?", (report_id,))
_conn.commit()
_conn.close()

# Test 5: PDF Content Integrity Check'''

if target in content and "Simulate M5 Payment Settlement" not in content:
    content = content.replace(target, settle_code, 1)
    with open("test_milestone4_pdf.py", "w") as f:
        f.write(content)
    print("test_milestone4_pdf.py updated with M5 simulation step.")
else:
    print("Target already present or not found.")
