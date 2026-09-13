import urllib.request
import urllib.parse
import json
import mimetypes
import uuid
import os

BASE_URL = "http://127.0.0.1:8000"

# 1. Check Server Liveness
try:
    with urllib.request.urlopen(f"{BASE_URL}/", timeout=2) as r:
        print("✓ Server is alive:", r.read().decode())
except Exception as e:
    print("✗ Cannot reach server! Make sure uvicorn is running.")
    print("Error:", e)
    exit(1)

# 2. Authenticate
login_data = urllib.parse.urlencode({
    "username": "admin@apex.com",
    "password": "admin123"
}).encode("utf-8")

req = urllib.request.Request(
    f"{BASE_URL}/login",
    data=login_data,
    headers={"Content-Type": "application/x-www-form-urlencoded"}
)

try:
    with urllib.request.urlopen(req) as resp:
        token_info = json.loads(resp.read().decode("utf-8"))
        token = token_info["access_token"]
        print("✓ Authenticated successfully.")
except Exception as e:
    print("✗ Login failed:", e)
    exit(1)

# 3. Multipart Form-Data Construction for 3 Files
boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
body = bytearray()

files_to_upload = [
    "test_reports/PAT-10452_CBC.pdf",
    "test_reports/LAB-88301_Thyroid.pdf",
    "test_reports/2026_09_12_1_cbc.pdf"
]

for file_path in files_to_upload:
    if not os.path.exists(file_path):
        print(f"✗ File missing: {file_path}")
        continue
    filename = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'.encode("utf-8"))
    body.extend(b"Content-Type: application/pdf\r\n\r\n")
    body.extend(file_bytes)
    body.extend(b"\r\n")

body.extend(f"--{boundary}--\r\n".encode("utf-8"))

upload_req = urllib.request.Request(
    f"{BASE_URL}/reports/bulk-upload",
    data=bytes(body),
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}"
    }
)

print(f"Uploading {len(files_to_upload)} files to /reports/bulk-upload...")
try:
    with urllib.request.urlopen(upload_req) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        print("\n=== BULK INGESTION RESULT ===")
        print(json.dumps(result, indent=2))
except urllib.error.HTTPError as he:
    print(f"✗ HTTP Error {he.code}:", he.read().decode("utf-8"))
except Exception as e:
    print("✗ Request failed:", e)
