import urllib.request
import urllib.parse
import urllib.error
import json
import sqlite3

BASE_URL = "http://127.0.0.1:8000"
DB_PATH = "diagnostic.db"

print("==================================================================")
print("PHASE 4 - MILESTONE 2: EXTRACTION PROVIDER TEST SUITE")
print("==================================================================")

def get_token(username, password):
    data = urllib.parse.urlencode({"username": username, "password": password}).encode()
    req = urllib.request.Request(f"{BASE_URL}/login", data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())["access_token"]

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("INSERT OR IGNORE INTO centres (id, name, address, phone) VALUES (1, 'Apex Diagnostics', 'Road 1', '9876543210')")
c.execute("INSERT OR IGNORE INTO centres (id, name, address, phone) VALUES (2, 'Apex Branch 2', 'Road 2', '9876543211')")
c.execute("INSERT OR IGNORE INTO patients (id, centre_id, patient_code, full_name, phone) VALUES (101, 1, 'P-101', 'Patient A (C1)', '9876500101')")
c.execute("INSERT OR IGNORE INTO patients (id, centre_id, patient_code, full_name, phone) VALUES (201, 2, 'P-101', 'Cross Tenant Patient', '9876500201')")
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

def post_request(url, token, data=None):
    payload = json.dumps(data).encode("utf-8") if data else None
    headers = {"Authorization": f"Bearer {token}"}
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    return urllib.request.urlopen(req)

dummy_jpg = b"\xff\xd8\xff\xe0" + b"X" * 1024 + b"\xff\xd9"

resp = post_multipart(f"{BASE_URL}/reports/ingest/photo", token_c1, "cbc_standard.jpg", dummy_jpg)
job_cbc = json.loads(resp.read().decode())["job_id"]

resp = post_multipart(f"{BASE_URL}/reports/ingest/photo", token_c1, "lipid_partial.jpg", dummy_jpg)
job_partial = json.loads(resp.read().decode())["job_id"]

resp = post_multipart(f"{BASE_URL}/reports/ingest/photo", token_c1, "fail_scan.jpg", dummy_jpg)
job_fail = json.loads(resp.read().decode())["job_id"]

# Test 1: Authorized Extraction of Valid Fixture
try:
    with post_request(f"{BASE_URL}/reports/ingest/{job_cbc}/extract", token_c1) as resp:
        body = json.loads(resp.read().decode())
        p_match = body["matched_patient_id"]
        status_ok = body["status"] == "NEEDS_VERIFICATION"
        record("Authorized Extract (CBC Fixture)", status_ok and p_match == 101, f"Status: {body['status']}, Matched patient_id: {p_match}")
except Exception as e:
    record("Authorized Extract (CBC Fixture)", False, str(e))

# Test 2: Unauthenticated Request Rejected
try:
    req = urllib.request.Request(f"{BASE_URL}/reports/ingest/{job_cbc}/extract", data=b"", method="POST")
    urllib.request.urlopen(req)
    record("Unauthenticated Request Defense", False, "Allowed unauthenticated extraction")
except urllib.error.HTTPError as e:
    record("Unauthenticated Request Defense", e.code == 401, f"Rejected with HTTP {e.code}")
except Exception as e:
    record("Unauthenticated Request Defense", False, str(e))

# Test 3: Cross-Tenant Extraction Defense
try:
    post_request(f"{BASE_URL}/reports/ingest/{job_cbc}/extract", token_c2)
    record("Cross-Tenant Extraction Defense", False, "Centre 2 extracted Centre 1 job")
except urllib.error.HTTPError as e:
    record("Cross-Tenant Extraction Defense", e.code == 404, f"Blocked with HTTP {e.code}")
except Exception as e:
    record("Cross-Tenant Extraction Defense", False, str(e))

# Test 4: Missing Demographic Preservation (No fabricated values)
try:
    with post_request(f"{BASE_URL}/reports/ingest/{job_partial}/extract", token_c1) as resp:
        body = json.loads(resp.read().decode())
        p_info = body["extracted_data"]["patient"]
        no_fab = p_info["patient_name"]["value"] is None and p_info["age"]["value"] is None
        record("Demographic Preservation (No Fabrication)", no_fab, f"Name: {p_info['patient_name']['value']}, Age: {p_info['age']['value']}")
except Exception as e:
    record("Demographic Preservation (No Fabrication)", False, str(e))

# Test 5: Controlled Extraction Failure Handling
try:
    post_request(f"{BASE_URL}/reports/ingest/{job_fail}/extract", token_c1)
    record("Controlled Failure Handling", False, "Failing scan did not raise 422")
except urllib.error.HTTPError as e:
    body = json.loads(e.read().decode())
    record("Controlled Failure Handling", e.code == 422 and "UNREADABLE_SCAN" in str(body), f"Handled with HTTP {e.code}: {body}")
except Exception as e:
    record("Controlled Failure Handling", False, str(e))

# Test 6: Verify Database Status on Failure
try:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT status, error_code FROM report_ingestion_jobs WHERE id = ?", (job_fail,))
    row = c.fetchone()
    conn.close()
    record("Failure Status Persistence", row[0] == "EXTRACTION_FAILED" and row[1] == "UNREADABLE_SCAN", f"DB state: status={row[0]}, error_code={row[1]}")
except Exception as e:
    record("Failure Status Persistence", False, str(e))

# Test 7: Idempotent Extraction
try:
    with post_request(f"{BASE_URL}/reports/ingest/{job_cbc}/extract", token_c1) as resp:
        body = json.loads(resp.read().decode())
        is_idempotent = "already extracted" in body.get("message", "")
        record("Extraction Idempotency", is_idempotent, f"Response: {body.get('message')}")
except Exception as e:
    record("Extraction Idempotency", False, str(e))

# Test 8: Invariant Check: No Final Report or Credit Deduction
try:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT final_report_id, verified_data FROM report_ingestion_jobs WHERE id = ?", (job_cbc,))
    row = c.fetchone()
    c.execute("SELECT COUNT(*) FROM report_documents WHERE patient_id = 101 AND stored_filename LIKE '%cbc%'")
    doc_count = c.fetchone()[0]
    conn.close()
    invariants_held = row[0] is None and row[1] is None and doc_count == 0
    record("Pipeline Invariants Held", invariants_held, "No final report document created, verified_data is None")
except Exception as e:
    record("Pipeline Invariants Held", False, str(e))

print("==================================================================")
passed = sum(1 for r in results if r[1])
total = len(results)
print(f"MILESTONE 2 SUMMARY: {passed}/{total} TESTS PASSED")
print("==================================================================")
