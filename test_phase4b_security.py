import urllib.request
import urllib.parse
import urllib.error
import json
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
import threading

BASE_URL = "http://127.0.0.1:8000"
DB_PATH = "/storage/emulated/0/diagnostic_backend/diagnostic.db"

print("==================================================================")
print("PHASE 4B: PATIENT-FACING TEMPORARY SECURE ACCESS HARNESS")
print("==================================================================")

# --- 1. SEED DUMMY DATA ---
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Centres
c.execute("INSERT OR IGNORE INTO centres (id, name, address, phone) VALUES (1, 'Apex Diagnostics', 'Main Rd', '9876543210')")
c.execute("INSERT OR IGNORE INTO centres (id, name, address, phone) VALUES (2, 'Apex Branch 2', 'City Center', '9999999999')")

# Patients
# Centre 1: Patient A, Patient B
# Centre 2: Patient C
c.execute("DELETE FROM patients WHERE id IN (101, 102, 201)")
c.execute("INSERT INTO patients (id, centre_id, patient_code, full_name, age, gender, phone) VALUES (101, 1, 'P-101', 'Patient A (C1)', 30, 'Male', '9876500101')")
c.execute("INSERT INTO patients (id, centre_id, patient_code, full_name, age, gender, phone) VALUES (102, 1, 'P-102', 'Patient B (C1)', 35, 'Female', '9876500102')")
c.execute("INSERT INTO patients (id, centre_id, patient_code, full_name, age, gender, phone) VALUES (201, 2, 'P-201', 'Patient C (C2)', 40, 'Male', '9876500201')")

# Storage Setup
c1_dir = Path("/storage/emulated/0/diagnostic_backend/storage/reports/1")
c2_dir = Path("/storage/emulated/0/diagnostic_backend/storage/reports/2")
c1_dir.mkdir(parents=True, exist_ok=True)
c2_dir.mkdir(parents=True, exist_ok=True)

f1 = c1_dir / "c1_p101_report.pdf"
f2 = c1_dir / "c1_p102_report.pdf"
f3 = c2_dir / "c2_p201_report.pdf"

f1.write_bytes(b"%PDF-1.4 Report 1 - Patient A (Centre 1)")
f2.write_bytes(b"%PDF-1.4 Report 2 - Patient B (Centre 1)")
f3.write_bytes(b"%PDF-1.4 Report 3 - Patient C (Centre 2)")

# Report Documents
c.execute("DELETE FROM report_documents WHERE id IN (501, 502, 503)")
c.execute("""
INSERT INTO report_documents (id, centre_id, patient_id, original_filename, stored_filename, file_path, file_size, file_checksum, file_hash, status, uploaded_by)
VALUES (501, 1, 101, 'report_A.pdf', 'c1_p101_report.pdf', ?, ?, 'chk1', 'chk1', 'STORED', 1)
""", (str(f1), len(f1.read_bytes())))

c.execute("""
INSERT INTO report_documents (id, centre_id, patient_id, original_filename, stored_filename, file_path, file_size, file_checksum, file_hash, status, uploaded_by)
VALUES (502, 1, 102, 'report_B.pdf', 'c1_p102_report.pdf', ?, ?, 'chk2', 'chk2', 'STORED', 1)
""", (str(f2), len(f2.read_bytes())))

c.execute("""
INSERT INTO report_documents (id, centre_id, patient_id, original_filename, stored_filename, file_path, file_size, file_checksum, file_hash, status, uploaded_by)
VALUES (503, 2, 201, 'report_C.pdf', 'c2_p201_report.pdf', ?, ?, 'chk3', 'chk3', 'STORED', 1)
""", (str(f3), len(f3.read_bytes())))

# Wipe any prior test OTPs / sessions for clean baseline
c.execute("DELETE FROM patient_access_otps WHERE patient_id IN (101, 102, 201)")
c.execute("DELETE FROM patient_sessions WHERE patient_id IN (101, 102, 201)")

conn.commit()
conn.close()

results = []
def record(test_name, success, detail):
    results.append((test_name, success, detail))
    mark = "PASS" if success else "FAIL"
    print(f"[{mark}] {test_name}: {detail}")

# --- Helper Functions ---
def make_request(url, method="GET", headers=None, data=None):
    if headers is None:
        headers = {}
    encoded_data = json.dumps(data).encode("utf-8") if data else None
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=encoded_data, headers=headers, method=method)
    return urllib.request.urlopen(req)

# --- Test 1: Request OTP (Valid Patient A) ---
try:
    payload = {"centre_id": 1, "patient_code": "P-101", "phone": "9876500101"}
    with make_request(f"{BASE_URL}/patient/auth/otp/request", method="POST", data=payload) as resp:
        body = json.loads(resp.read().decode())
        dev_file = Path("/storage/emulated/0/diagnostic_backend/.dev_otp_101")
        record("OTP Request (Valid Patient)", resp.status == 200 and dev_file.exists(), f"Status {resp.status}, dev token logged")
except Exception as e:
    record("OTP Request (Valid Patient)", False, str(e))

# Read the generated OTP from secure dev sink
otp_a = Path("/storage/emulated/0/diagnostic_backend/.dev_otp_101").read_text().strip()

# --- Test 2: Safe Enumeration Resistance (Invalid Patient) ---
try:
    payload = {"centre_id": 1, "patient_code": "P-NONEXISTENT", "phone": "9999999999"}
    with make_request(f"{BASE_URL}/patient/auth/otp/request", method="POST", data=payload) as resp:
        body = json.loads(resp.read().decode())
        record("Safe Patient Enumeration Defense", resp.status == 200 and "dispatched" in body["message"], "Returned neutral message without leaking identity absence")
except Exception as e:
    record("Safe Patient Enumeration Defense", False, str(e))

# --- Test 3: OTP Request Rate Limiting (Cooldown) ---
try:
    payload = {"centre_id": 1, "patient_code": "P-101", "phone": "9876500101"}
    make_request(f"{BASE_URL}/patient/auth/otp/request", method="POST", data=payload)
    record("OTP Request Rate Limiting", False, "Expected 429 cooldown rejection")
except urllib.error.HTTPError as e:
    record("OTP Request Rate Limiting", e.code == 429, f"Blocked repeated request with HTTP {e.code}")
except Exception as e:
    record("OTP Request Rate Limiting", False, str(e))

# --- Test 4: Wrong OTP Handling & Attempt Counter ---
try:
    payload = {"centre_id": 1, "patient_code": "P-101", "otp": "000000"}
    make_request(f"{BASE_URL}/patient/auth/otp/verify", method="POST", data=payload)
    record("Wrong OTP Handling", False, "Accepted invalid OTP")
except urllib.error.HTTPError as e:
    record("Wrong OTP Handling", e.code == 400, f"Rejected wrong OTP with HTTP {e.code}")
except Exception as e:
    record("Wrong OTP Handling", False, str(e))

# --- Test 5: Verify Correct OTP & Obtain Session Token ---
token_a = None
try:
    payload = {"centre_id": 1, "patient_code": "P-101", "otp": otp_a}
    with make_request(f"{BASE_URL}/patient/auth/otp/verify", method="POST", data=payload) as resp:
        body = json.loads(resp.read().decode())
        token_a = body.get("session_token")
        record("Correct OTP Verification & Session Issuance", bool(token_a) and len(token_a) > 20, f"Issued session token: {token_a[:10]}...")
except Exception as e:
    record("Correct OTP Verification & Session Issuance", False, str(e))

# --- Test 6: Single-Use OTP Enforcement (Replay Rejection) ---
try:
    payload = {"centre_id": 1, "patient_code": "P-101", "otp": otp_a}
    make_request(f"{BASE_URL}/patient/auth/otp/verify", method="POST", data=payload)
    record("Single-Use OTP (Replay Rejection)", False, "Allowed reuse of already-consumed OTP")
except urllib.error.HTTPError as e:
    record("Single-Use OTP (Replay Rejection)", e.code == 400, f"Blocked replay attack with HTTP {e.code}")
except Exception as e:
    record("Single-Use OTP (Replay Rejection)", False, str(e))

# --- Test 7: Patient A Lists Own Reports (Tenant & Patient Bound) ---
try:
    headers = {"Authorization": f"Bearer {token_a}"}
    with make_request(f"{BASE_URL}/patient/reports", headers=headers) as resp:
        items = json.loads(resp.read().decode())
        only_own = len(items) == 1 and items[0]["id"] == 501
        leaked = any("/storage" in json.dumps(it) for it in items)
        record("Patient Own Report Listing & Path Redaction", only_own and not leaked, f"Returned 1 report, internal paths redacted: {items[0]['filename']}")
except Exception as e:
    record("Patient Own Report Listing & Path Redaction", False, str(e))

# --- Test 8: Patient A Downloads Own Report (501) ---
try:
    headers = {"Authorization": f"Bearer {token_a}"}
    with make_request(f"{BASE_URL}/patient/reports/501/download", headers=headers) as resp:
        content = resp.read()
        ctype = resp.headers.get("Content-Type", "")
        record("Patient Download Own Report", len(content) > 0 and "application/pdf" in ctype, f"Retrieved {len(content)} bytes")
except Exception as e:
    record("Patient Download Own Report", False, str(e))

# --- Test 9: IDOR Attack - Patient A Requests Patient B's Report (502) ---
try:
    headers = {"Authorization": f"Bearer {token_a}"}
    make_request(f"{BASE_URL}/patient/reports/502/download", headers=headers)
    record("IDOR Defense (Patient A -> Patient B Report)", False, "BREACH: Patient A accessed Patient B report")
except urllib.error.HTTPError as e:
    record("IDOR Defense (Patient A -> Patient B Report)", e.code == 404, f"Zero-leakage neutralization with HTTP {e.code}")
except Exception as e:
    record("IDOR Defense (Patient A -> Patient B Report)", False, str(e))

# --- Test 10: Cross-Tenant Attack - Patient A Requests Centre 2 Report (503) ---
try:
    headers = {"Authorization": f"Bearer {token_a}"}
    make_request(f"{BASE_URL}/patient/reports/503/download", headers=headers)
    record("Cross-Tenant Defense (Patient A [C1] -> Report [C2])", False, "BREACH: Cross-tenant access permitted")
except urllib.error.HTTPError as e:
    record("Cross-Tenant Defense (Patient A [C1] -> Report [C2])", e.code == 404, f"Cross-tenant access denied with HTTP {e.code}")
except Exception as e:
    record("Cross-Tenant Defense (Patient A [C1] -> Report [C2])", False, str(e))

# --- Test 11: Session Revocation (Logout) ---
try:
    headers = {"Authorization": f"Bearer {token_a}"}
    with make_request(f"{BASE_URL}/patient/auth/logout", method="POST", headers=headers) as resp:
        pass
    # Now try accessing with revoked token
    make_request(f"{BASE_URL}/patient/reports", headers=headers)
    record("Session Revocation (Post-Logout)", False, "Revoked session still allowed access")
except urllib.error.HTTPError as e:
    record("Session Revocation (Post-Logout)", e.code == 401, f"Terminated session rejected with HTTP {e.code}")
except Exception as e:
    record("Session Revocation (Post-Logout)", False, str(e))

# --- Test 12: Regression Verification (Phase 4A Centre Admin Still Operates) ---
try:
    # Use standard centre admin login
    login_data = urllib.parse.urlencode({"username": "admin@apex.com", "password": "admin123"}).encode()
    req_admin = urllib.request.Request(f"{BASE_URL}/login", data=login_data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req_admin) as lresp:
        admin_token = json.loads(lresp.read().decode())["access_token"]
    
    admin_req = urllib.request.Request(f"{BASE_URL}/reports/501/download", headers={"Authorization": f"Bearer {admin_token}"})
    with urllib.request.urlopen(admin_req) as dresp:
        data = dresp.read()
        record("Phase 4A Regression Check (Centre Admin Access)", len(data) > 0, f"Centre staff download intact ({len(data)} bytes)")
except Exception as e:
    record("Phase 4A Regression Check (Centre Admin Access)", False, str(e))

print("==================================================================")
passed = sum(1 for r in results if r[1])
total = len(results)
print(f"SUMMARY: {passed}/{total} TESTS PASSED")
print("==================================================================")
