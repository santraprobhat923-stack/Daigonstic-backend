import urllib.request
import urllib.parse
import urllib.error
import json
import sqlite3
import os
from pathlib import Path

BASE_URL = "http://127.0.0.1:8000"
DB_PATH = "diagnostic.db"

print("==================================================================")
print("PHASE 4 - MILESTONE 1: INGESTION PIPELINE BASELINE SUITE")
print("==================================================================")

def get_token(username, password):
    data = urllib.parse.urlencode({"username": username, "password": password}).encode()
    req = urllib.request.Request(f"{BASE_URL}/login", data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())["access_token"]

# Seed database with Centre 1 admin and Centre 2 technician
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("INSERT OR IGNORE INTO centres (id, name, address, phone) VALUES (1, 'Apex Diagnostics', 'Road 1', '9876543210')")
c.execute("INSERT OR IGNORE INTO centres (id, name, address, phone) VALUES (2, 'Apex Diagnostics Branch 2', 'Road 2', '9876543211')")

c.execute("SELECT hashed_password FROM users WHERE email = 'admin@apex.com'")
admin_hash = c.fetchone()[0]

c.execute("SELECT id FROM users WHERE email = 'tech2@apex.com'")
if not c.fetchone():
    c.execute("INSERT INTO users (id, centre_id, email, hashed_password, role, is_active) VALUES (999, 2, 'tech2@apex.com', ?, 'technician', 1)", (admin_hash,))
conn.commit()
conn.close()

token_c1 = get_token("admin@apex.com", "admin123")
token_c2 = get_token("tech2@apex.com", "admin123")

results = []
def record(name, passed, detail):
    results.append((name, passed, detail))
    print(f"[{'PASS' if passed else 'FAIL'}] {name}: {detail}")

def post_multipart(url, token, filename, content, mime="image/jpeg"):
    boundary = "----WebKitFormBoundaryX7b82q9L"
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode())
    body.extend(f"Content-Type: {mime}\r\n\r\n".encode())
    body.extend(content)
    body.extend(f"\r\n--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": f"Bearer {token}"
        }
    )
    return urllib.request.urlopen(req)

# Test 1: Valid Photo Upload
job_id_c1 = None
try:
    dummy_jpg = b"\xff\xd8\xff\xe0" + b"A" * 1024 + b"\xff\xd9"
    with post_multipart(f"{BASE_URL}/reports/ingest/photo", token_c1, "analyzer_sample.jpg", dummy_jpg) as resp:
        res = json.loads(resp.read().decode())
        job_id_c1 = res["job_id"]
        record("Valid Photo Upload (Centre 1)", resp.status == 201 and res["status"] == "PHOTO_UPLOADED", f"Created Job ID {job_id_c1}")
except Exception as e:
    record("Valid Photo Upload (Centre 1)", False, str(e))

# Test 2: Reject Executable Upload (.exe masquerading)
try:
    bad_content = b"MZ\x90\x00"
    post_multipart(f"{BASE_URL}/reports/ingest/photo", token_c1, "payload.exe", bad_content, mime="application/octet-stream")
    record("Reject Disallowed Extension (.exe)", False, "Failed to reject executable")
except urllib.error.HTTPError as e:
    record("Reject Disallowed Extension (.exe)", e.code == 400, f"Rejected with HTTP {e.code}")
except Exception as e:
    record("Reject Disallowed Extension (.exe)", False, str(e))

# Test 3: Path Traversal Filename Sanitization
try:
    with post_multipart(f"{BASE_URL}/reports/ingest/photo", token_c1, "../../etc/passwd.jpg", dummy_jpg) as resp:
        res = json.loads(resp.read().decode())
        safe_name = res["original_filename"]
        record("Path Traversal Filename Neutralization", "/" not in safe_name and ".." not in safe_name, f"Sanitized to: {safe_name}")
except Exception as e:
    record("Path Traversal Filename Neutralization", False, str(e))

# Test 4: Cross-Tenant Job Inspection Defense (Centre 2 querying Centre 1 job)
try:
    req = urllib.request.Request(
        f"{BASE_URL}/reports/ingest/{job_id_c1}",
        headers={"Authorization": f"Bearer {token_c2}"}
    )
    urllib.request.urlopen(req)
    record("Cross-Tenant Job Isolation", False, "BREACH: Centre 2 accessed Centre 1 ingestion job")
except urllib.error.HTTPError as e:
    record("Cross-Tenant Job Isolation", e.code == 404, f"Blocked with HTTP {e.code}")
except Exception as e:
    record("Cross-Tenant Job Isolation", False, str(e))

# Test 5: Storage Isolation (Verify file landed inside storage/source_images/1)
try:
    c1_dir = Path("/storage/emulated/0/diagnostic_backend/storage/source_images/1")
    files = list(c1_dir.glob("*.jpg"))
    record("Tenant Physical Directory Isolation", len(files) > 0, f"Found {len(files)} files strictly in tenant folder /1/")
except Exception as e:
    record("Tenant Physical Directory Isolation", False, str(e))

print("==================================================================")
passed = sum(1 for r in results if r[1])
total = len(results)
print(f"MILESTONE 1 SUMMARY: {passed}/{total} TESTS PASSED")
print("==================================================================")
