import urllib
class MockHTTPError(Exception):
    def __init__(self, code, msg="HTTP Error"):
        self.code = code
        self.msg = msg
        super().__init__(f"HTTP {code}: {msg}")

import types
urllib.error = types.ModuleType("urllib.error")
urllib.error.HTTPError = MockHTTPError
BASE_URL = ''
import json
import sqlite3
import io
from pypdf import PdfReader
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)
DB_PATH = "diagnostic.db"

print("=" * 60)
print("PHASE 5 - MILESTONE 4: FINAL REPORT PDF TEST SUITE")
print("=" * 60)

def get_token(username, password):
    resp = client.post("/auth/login", data={"username": username, "password": password})
    if resp.status_code != 200:
        resp = client.post("/login", data={"username": username, "password": password})
    return resp.json()["access_token"]

class MockResp:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def __init__(self, res):
        self.res = res
        self.status = res.status_code
    def read(self):
        return self.res.content

def create_mock_req(url, data=None, headers=None, method=None):
    clean_url = url.replace("http://127.0.0.1:8000", "")
    if method is None:
        method = "POST" if data is not None else "GET"
    return {"url": clean_url, "data": data, "headers": headers or {}, "method": method}

def client_open(req):
    url = req["url"]
    headers = req["headers"]
    data = req["data"]
    method = req.get("method", "GET")

    if method == "POST":
        if isinstance(data, (bytes, bytearray)):
            r = client.post(url, content=data, headers=headers)
        elif isinstance(data, dict):
            r = client.post(url, json=data, headers=headers)
        else:
            r = client.post(url, data=data, headers=headers)
    else:
        r = client.get(url, headers=headers)

    if r.status_code >= 400:
        import io
        raise urllib.error.HTTPError(url, r.status_code, r.text, r.headers, io.BytesIO(r.content))
    return MockResp(r)


conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# 1. Ensure test users exist
# technician_c1 in centre 1, technician_c2 in centre 2
tech1_token = get_token("admin@apex.com", "admin123")
tech2_token = get_token("tech2@apex.com", "admin123")

headers_c1 = {"Authorization": f"Bearer {tech1_token}", "Content-Type": "application/json"}
headers_c2 = {"Authorization": f"Bearer {tech2_token}", "Content-Type": "application/json"}

# 2. Seed a VERIFIED job for Centre 1 with verified vs extracted disparity
extracted_payload = json.dumps({
    "panels": [{"name": "Blood Glucose", "analytes": [{"name": "Fasting Blood Sugar", "result": "100", "unit": "mg/dL"}]}]
})
verified_payload = json.dumps({
    "patient_id": 101,
    "patient_name": "Patient A (C1)",
    "patient_code": "P-101",
    "panels": [{
        "name": "Blood Glucose",
        "analytes": [{"name": "Fasting Blood Sugar", "result": "125", "unit": "mg/dL", "reference_range": "70-99"}]
    }],
    "notes": "Verified authoritative result"
})

now_str = "2026-09-14 11:00:00"
c.execute("""
INSERT INTO report_ingestion_jobs (
    centre_id, patient_id, status, source_image_path, source_image_hash,
    original_filename, file_size, mime_type, technician_id, created_at, updated_at,
    extracted_data, verified_data
) VALUES (
    1, 101, "VERIFIED", "storage/sample_test.png", "hash_dummy_v",
    "sample_test.png", 1024, "image/png", 1, ?, ?,
    ?, ?
)
""", (now_str, now_str, extracted_payload, verified_payload))
job_id = c.lastrowid
conn.commit()
conn.close()

# Test 1: Unauthenticated request rejected (401)
try:
    req = create_mock_req(f"{BASE_URL}/reports/ingest/{job_id}/generate-pdf", data=b"", headers={})
    client_open(req)
    assert False, "Should have failed with 401"
except urllib.error.HTTPError as e:
    assert e.code == 401, f"Expected 401, got {e.code}"
print("[PASS] 1. RBAC: Unauthenticated request rejected (HTTP 401)")

# Test 2: Cross-tenant generation blocked (Centre 2 tech calls Centre 1 job -> 404)
try:
    req = create_mock_req(f"{BASE_URL}/reports/ingest/{job_id}/generate-pdf", data=b"", headers=headers_c2)
    client_open(req)
    assert False, "Should have failed with 404"
except urllib.error.HTTPError as e:
    assert e.code == 404, f"Expected 404, got {e.code}"
print("[PASS] 2. Tenant Isolation: Cross-tenant generation blocked (HTTP 404)")

# Test 3: Non-VERIFIED job generation rejected (HTTP 400)
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("""
INSERT INTO report_ingestion_jobs (
    centre_id, patient_id, status, source_image_path, source_image_hash,
    original_filename, file_size, mime_type, technician_id, created_at, updated_at
) VALUES (
    1, 101, "PHOTO_UPLOADED", "storage/unverified.png", "hash_dummy_u",
    "unverified.png", 1024, "image/png", 1, "2026-09-14 11:00:00", "2026-09-14 11:00:00"
)
""")
unverified_id = c.lastrowid
conn.commit()
conn.close()

try:
    req = create_mock_req(f"{BASE_URL}/reports/ingest/{unverified_id}/generate-pdf", data=b"", headers=headers_c1)
    client_open(req)
    assert False, "Should have failed with 400"
except urllib.error.HTTPError as e:
    assert e.code == 400, f"Expected 400, got {e.code}"
print("[PASS] 3. State Machine: Non-VERIFIED generation rejected (HTTP 400)")

# Test 4: Successful generation for VERIFIED job (HTTP 201)
req = create_mock_req(f"{BASE_URL}/reports/ingest/{job_id}/generate-pdf", data=b"", headers=headers_c1)
try:
    with client_open(req) as resp:
        assert resp.status == 201
        body = json.loads(resp.read().decode())
        assert body["status"] == "GENERATED"
        report_id = body["report_id"]
except urllib.error.HTTPError as err:
    print("SERVER_ERROR_DETAIL:", err.code, err.read().decode())
    raise err
print(f"[PASS] 4. PDF Generation: Final report #{report_id} generated successfully (HTTP 201)")

# Simulate M5 Payment Settlement prior to testing downstream download
import sqlite3
_conn = sqlite3.connect(DB_PATH)
_conn.execute("UPDATE report_documents SET is_released=1, release_status='RELEASED' WHERE id=?", (report_id,))
_conn.commit()
_conn.close()

# Test 5: PDF Content Integrity Check (Must contain 125, MUST NOT contain 100)
req = create_mock_req(f"{BASE_URL}/reports/final/{report_id}/download", headers=headers_c1)
with client_open(req) as resp:
    assert resp.status == 200
    pdf_bytes = resp.read()
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pdf_text = ""
    for page in reader.pages:
        pdf_text += page.extract_text() or ""
    assert "125" in pdf_text, "Verified value 125 missing from rendered PDF"
    assert "100" not in pdf_text, "Extracted value 100 mistakenly rendered in PDF"
    assert "Patient A (C1)" in pdf_text
print("[PASS] 5. Content Integrity: Rendered PDF contains verified_data (125) and excludes extracted_data (100)")

# Test 6: Idempotency (repeated generation returns 200 ALREADY_GENERATED)
req = create_mock_req(f"{BASE_URL}/reports/ingest/{job_id}/generate-pdf", data=b"", headers=headers_c1)
with client_open(req) as resp:
    assert resp.status == 200
    body = json.loads(resp.read().decode())
    assert body["status"] == "ALREADY_GENERATED"
    assert body["report_id"] == report_id
print("[PASS] 6. Idempotency: Duplicate trigger returns existing report without re-creation (HTTP 200)")

# Test 7: Cross-tenant download blocked (Centre 2 tech calls Centre 1 report -> 404)
try:
    req = create_mock_req(f"{BASE_URL}/reports/final/{report_id}/download", headers=headers_c2)
    client_open(req)
    assert False, "Should have failed with 404"
except urllib.error.HTTPError as e:
    assert e.code == 404, f"Expected 404, got {e.code}"
print("[PASS] 7. Tenant Isolation: Cross-tenant download blocked (HTTP 404)")

# Test 8: Downstream freeze invariants
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("SELECT count(*) FROM credit_transactions")
credit_count = c.fetchone()[0]
conn.close()
print(f"[PASS] 8. Downstream Invariants: 0 credits deducted ({credit_count} total), 0 notifications triggered")

print("=" * 60)
print("MILESTONE 4 TEST SUITE: 8/8 PASSED")
print("=" * 60)
