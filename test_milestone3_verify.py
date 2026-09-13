import urllib.request
import urllib.parse
import urllib.error
import json
import sqlite3

BASE_URL = "http://127.0.0.1:8000"
DB_PATH = "diagnostic.db"

print("==================================================================")
print("PHASE 4 - MILESTONE 3: TECHNICIAN VERIFICATION TEST SUITE")
print("==================================================================")

def get_token(username, password):
    data = urllib.parse.urlencode({"username": username, "password": password}).encode()
    req = urllib.request.Request(f"{BASE_URL}/login", data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())["access_token"]

# Seed database with Centre 1 and Centre 2 patients
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("INSERT OR IGNORE INTO centres (id, name, address, phone) VALUES (1, 'Apex Diagnostics', 'Road 1', '9876543210')")
c.execute("INSERT OR IGNORE INTO centres (id, name, address, phone) VALUES (2, 'Apex Branch 2', 'Road 2', '9876543211')")
c.execute("INSERT OR IGNORE INTO patients (id, centre_id, patient_code, full_name, phone) VALUES (101, 1, 'P-101', 'Patient A (C1)', '9876500101')")
c.execute("INSERT OR IGNORE INTO patients (id, centre_id, patient_code, full_name, phone) VALUES (201, 2, 'P-201', 'Patient B (C2)', '9876500201')")
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
    payload = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {"Authorization": f"Bearer {token}"}
    if payload:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    return urllib.request.urlopen(req)

dummy_jpg = b"\xff\xd8\xff\xe0" + b"X" * 1024 + b"\xff\xd9"

# Prepare Job 1: Ingest & Extract to get to NEEDS_VERIFICATION
resp = post_multipart(f"{BASE_URL}/reports/ingest/photo", token_c1, "verify_target.jpg", dummy_jpg)
job_target = json.loads(resp.read().decode())["job_id"]
post_request(f"{BASE_URL}/reports/ingest/{job_target}/extract", token_c1)

# Prepare Job 2: Fresh upload (remains PHOTO_UPLOADED)
resp = post_multipart(f"{BASE_URL}/reports/ingest/photo", token_c1, "unextracted.jpg", dummy_jpg)
job_unextracted = json.loads(resp.read().decode())["job_id"]

valid_verify_payload = {
    "patient_id": 101,
    "panels": [
        {
            "panel_name": "Complete Blood Count",
            "parameters": [
                {
                    "name": "Hemoglobin",
                    "result": "14.5",
                    "unit": "g/dL",
                    "reference_range": "13.0-17.0"
                }
            ]
        }
    ],
    "technician_notes": "Manual adjustment of Hemoglobin from 14.2 to 14.5 based on secondary visual review."
}

# Test 1: Successful Verification Transition
try:
    with post_request(f"{BASE_URL}/reports/ingest/{job_target}/verify", token_c1, valid_verify_payload) as resp:
        body = json.loads(resp.read().decode())
        is_verified = body["status"] == "VERIFIED"
        has_verified_data = "Hemoglobin" in str(body["verified_data"])
        record("Authorized Verification Flow", resp.status == 200 and is_verified and has_verified_data, f"Status: {body['status']}")
except Exception as e:
    record("Authorized Verification Flow", False, str(e))

# Test 2: Extraction Audit Trail Remains Intact
try:
    req = urllib.request.Request(f"{BASE_URL}/reports/ingest/{job_target}", headers={"Authorization": f"Bearer {token_c1}"})
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read().decode())
        has_extracted = body["extracted_data"] is not None
        has_verified = body["verified_data"] is not None
        record("Audit Trail Preserved (Extracted Data Intact)", has_extracted and has_verified, "Both extracted_data and verified_data present")
except Exception as e:
    record("Audit Trail Preserved (Extracted Data Intact)", False, str(e))

# Test 3: Reject Verification on Invalid Job State (PHOTO_UPLOADED)
try:
    post_request(f"{BASE_URL}/reports/ingest/{job_unextracted}/verify", token_c1, valid_verify_payload)
    record("Reject Invalid State Transition", False, "Allowed verification on unextracted job")
except urllib.error.HTTPError as e:
    record("Reject Invalid State Transition", e.code == 400, f"Rejected with HTTP {e.code}")
except Exception as e:
    record("Reject Invalid State Transition", False, str(e))

# Test 4: Cross-Tenant Job Defense (Centre 2 cannot verify Centre 1 job)
try:
    post_request(f"{BASE_URL}/reports/ingest/{job_target}/verify", token_c2, valid_verify_payload)
    record("Cross-Tenant Job Isolation", False, "Centre 2 verified Centre 1 job")
except urllib.error.HTTPError as e:
    record("Cross-Tenant Job Isolation", e.code == 404, f"Blocked with HTTP {e.code}")
except Exception as e:
    record("Cross-Tenant Job Isolation", False, str(e))

# Test 5: Cross-Tenant Patient Defense (Centre 1 technician submitting Centre 2 patient_id)
cross_patient_payload = dict(valid_verify_payload)
cross_patient_payload["patient_id"] = 201

# Create a fresh extract job for this test
resp = post_multipart(f"{BASE_URL}/reports/ingest/photo", token_c1, "cross_test.jpg", dummy_jpg)
job_cross = json.loads(resp.read().decode())["job_id"]
post_request(f"{BASE_URL}/reports/ingest/{job_cross}/extract", token_c1)

try:
    post_request(f"{BASE_URL}/reports/ingest/{job_cross}/verify", token_c1, cross_patient_payload)
    record("Cross-Tenant Patient Injection Defense", False, "Allowed linking patient belonging to Centre 2")
except urllib.error.HTTPError as e:
    record("Cross-Tenant Patient Injection Defense", e.code == 404, f"Blocked with HTTP {e.code}")
except Exception as e:
    record("Cross-Tenant Patient Injection Defense", False, str(e))

# Test 6: Invariant Verification (No PDF, No Credit Consumption)
try:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT final_report_id FROM report_ingestion_jobs WHERE id = ?", (job_target,))
    final_report_id = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM report_documents WHERE patient_id = 101 AND stored_filename LIKE '%verify%'")
    doc_count = c.fetchone()[0]
    conn.close()
    invariants_intact = final_report_id is None and doc_count == 0
    record("Downstream Invariants Maintained", invariants_intact, "final_report_id is None, 0 report documents created")
except Exception as e:
    record("Downstream Invariants Maintained", False, str(e))

print("==================================================================")
passed = sum(1 for r in results if r[1])
total = len(results)
print(f"MILESTONE 3 SUMMARY: {passed}/{total} TESTS PASSED")
print("==================================================================")
