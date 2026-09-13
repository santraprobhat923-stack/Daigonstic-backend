import urllib.request
import urllib.parse
import urllib.error
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

BASE_URL = "http://127.0.0.1:8000"

print("==========================================================")
print("PHASE 4A COMPREHENSIVE SECURITY & TENANT ISOLATION SUITE")
print("==========================================================")

def get_token(username, password):
    data = urllib.parse.urlencode({"username": username, "password": password}).encode()
    for endpoint in ["/login", "/auth/login", "/token", "/auth/token"]:
        try:
            req = urllib.request.Request(
                f"{BASE_URL}{endpoint}",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            with urllib.request.urlopen(req) as resp:
                body = json.loads(resp.read().decode())
                if "access_token" in body:
                    return body["access_token"]
        except Exception:
            continue
    print(f"Failed to authenticate user: {username}")
    return None

DB_PATH = "/storage/emulated/0/diagnostic_backend/diagnostic.db"
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# 1. Centres
cursor.execute("SELECT id FROM centres WHERE id = 1")
if not cursor.fetchone():
    cursor.execute("INSERT INTO centres (id, name, address, phone) VALUES (1, 'Apex Diagnostics', 'Main Road', '9876543210')")

cursor.execute("SELECT id FROM centres WHERE id = 2")
if not cursor.fetchone():
    cursor.execute("INSERT INTO centres (id, name, address, phone) VALUES (2, 'Apex Branch 2', 'City Center', '9999999999')")

# 2. Users (ensure valid password hash and lowercase enum)
cursor.execute("SELECT hashed_password FROM users WHERE email = 'admin@apex.com'")
row = cursor.fetchone()
admin_hash = row[0] if row else "$2b$12$2Gv/b0CgupIbZFi60opvru6Ch.eyubUFfwa7IlPLgcUEI0bOJaMOYm"

cursor.execute("SELECT id FROM users WHERE email = 'tech2@apex.com'")
if not cursor.fetchone():
    cursor.execute("""
        INSERT INTO users (id, centre_id, email, hashed_password, role, is_active, created_at)
        VALUES (999, 2, 'tech2@apex.com', ?, 'technician', 1, ?)
    """, (admin_hash, datetime.utcnow().isoformat()))
else:
    cursor.execute("""
        UPDATE users 
        SET hashed_password = ?, role = 'technician', is_active = 1, centre_id = 2 
        WHERE email = 'tech2@apex.com'
    """, (admin_hash,))

# 3. Patients
cursor.execute("SELECT id FROM patients WHERE id = 1")
if not cursor.fetchone():
    cursor.execute("""
        INSERT INTO patients (id, centre_id, patient_code, full_name, age, gender, phone)
        VALUES (1, 1, 'P-1001', 'Test Patient 1', 30, 'Male', '9876500001')
    """)

cursor.execute("SELECT id FROM patients WHERE id = 2")
if not cursor.fetchone():
    cursor.execute("""
        INSERT INTO patients (id, centre_id, patient_code, full_name, age, gender, phone)
        VALUES (2, 2, 'P-1002', 'Test Patient 2', 28, 'Female', '9876500002')
    """)

# 4. Storage Setup
c1_dir = Path("/storage/emulated/0/diagnostic_backend/storage/reports/1")
c2_dir = Path("/storage/emulated/0/diagnostic_backend/storage/reports/2")
c1_dir.mkdir(parents=True, exist_ok=True)
c2_dir.mkdir(parents=True, exist_ok=True)

pdf_c1 = c1_dir / "c1_test_report.pdf"
pdf_c2 = c2_dir / "c2_test_report.pdf"

data1 = b"%PDF-1.4 Phase 4A Centre 1 Data"
data2 = b"%PDF-1.4 Phase 4A Centre 2 Data"

if not pdf_c1.exists():
    pdf_c1.write_bytes(data1)
if not pdf_c2.exists():
    pdf_c2.write_bytes(data2)

sz1 = len(data1)
sz2 = len(data2)

# 5. Documents
cursor.execute("SELECT id FROM report_documents WHERE stored_filename = 'c1_test_report.pdf' AND centre_id = 1")
row = cursor.fetchone()
if not row:
    cursor.execute("""
        INSERT INTO report_documents (
            centre_id, patient_id, original_filename, stored_filename,
            file_path, file_size, file_checksum, file_hash, status, uploaded_by
        ) VALUES (1, 1, 'c1_report.pdf', 'c1_test_report.pdf', ?, ?, 'chk123', 'chk123', 'STORED', 1)
    """, (str(pdf_c1), sz1))
    rep1_id = cursor.lastrowid
else:
    rep1_id = row[0]

cursor.execute("SELECT id FROM report_documents WHERE stored_filename = 'c2_test_report.pdf' AND centre_id = 2")
row = cursor.fetchone()
if not row:
    cursor.execute("""
        INSERT INTO report_documents (
            centre_id, patient_id, original_filename, stored_filename,
            file_path, file_size, file_checksum, file_hash, status, uploaded_by
        ) VALUES (2, 2, 'c2_report.pdf', 'c2_test_report.pdf', ?, ?, 'chk456', 'chk456', 'STORED', 999)
    """, (str(pdf_c2), sz2))
    rep2_id = cursor.lastrowid
else:
    rep2_id = row[0]

conn.commit()
conn.close()

token_c1 = get_token("admin@apex.com", "admin123")
token_c2 = get_token("tech2@apex.com", "admin123")

results = []

def record(test_name, success, detail):
    results.append((test_name, success, detail))
    mark = "PASS" if success else "FAIL"
    print(f"[{mark}] {test_name}: {detail}")

# Test 1: Unauthenticated Download
try:
    req = urllib.request.Request(f"{BASE_URL}/reports/{rep1_id}/download")
    urllib.request.urlopen(req)
    record("Unauthenticated Download", False, "Allowed without token")
except urllib.error.HTTPError as e:
    record("Unauthenticated Download", e.code == 401, f"Blocked with HTTP {e.code}")
except Exception as e:
    record("Unauthenticated Download", False, str(e))

# Test 2: Malformed JWT Rejection
try:
    req = urllib.request.Request(
        f"{BASE_URL}/reports/{rep1_id}/download",
        headers={"Authorization": "Bearer bad_invalid_token"}
    )
    urllib.request.urlopen(req)
    record("Malformed JWT Rejection", False, "Allowed with bad token")
except urllib.error.HTTPError as e:
    record("Malformed JWT Rejection", e.code == 401, f"Blocked with HTTP {e.code}")
except Exception as e:
    record("Malformed JWT Rejection", False, str(e))

# Test 3: Own Tenant Access
try:
    req = urllib.request.Request(
        f"{BASE_URL}/reports/{rep1_id}/download",
        headers={"Authorization": f"Bearer {token_c1}"}
    )
    with urllib.request.urlopen(req) as resp:
        data = resp.read()
        ctype = resp.headers.get("Content-Type", "")
        record("Legitimate Own-Tenant Access", len(data) > 0 and "application/pdf" in ctype, f"Fetched {len(data)} bytes, Content-Type: {ctype}")
except Exception as e:
    record("Legitimate Own-Tenant Access", False, str(e))

# Test 4: Cross Tenant Isolation (Centre 1 accessing Centre 2)
try:
    req = urllib.request.Request(
        f"{BASE_URL}/reports/{rep2_id}/download",
        headers={"Authorization": f"Bearer {token_c1}"}
    )
    urllib.request.urlopen(req)
    record("Cross-Tenant Isolation (C1 -> C2)", False, "Breach: Centre 1 accessed Centre 2 report")
except urllib.error.HTTPError as e:
    record("Cross-Tenant Isolation (C1 -> C2)", e.code in [403, 404], f"Properly isolated with HTTP {e.code}")
except Exception as e:
    record("Cross-Tenant Isolation (C1 -> C2)", False, str(e))

# Test 5: Cross Tenant Isolation (Centre 2 accessing Centre 1)
try:
    req = urllib.request.Request(
        f"{BASE_URL}/reports/{rep1_id}/download",
        headers={"Authorization": f"Bearer {token_c2}"}
    )
    urllib.request.urlopen(req)
    record("Cross-Tenant Isolation (C2 -> C1)", False, "Breach: Centre 2 accessed Centre 1 report")
except urllib.error.HTTPError as e:
    record("Cross-Tenant Isolation (C2 -> C1)", e.code in [403, 404], f"Properly isolated with HTTP {e.code}")
except Exception as e:
    record("Cross-Tenant Isolation (C2 -> C1)", False, str(e))

# Test 6: Metadata Path Redaction
try:
    req = urllib.request.Request(
        f"{BASE_URL}/reports/{rep1_id}",
        headers={"Authorization": f"Bearer {token_c1}"}
    )
    with urllib.request.urlopen(req) as resp:
        meta = json.loads(resp.read().decode())
        meta_str = json.dumps(meta)
        leaked = "/storage" in meta_str or "diagnostic_backend" in meta_str
        record("Filesystem Path Redaction", not leaked, "Clean metadata returned without internal storage path leak")
except Exception as e:
    record("Filesystem Path Redaction", False, str(e))

# Test 7: Path Traversal Attack Injection & Defense
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("""
    INSERT INTO report_documents (
        centre_id, patient_id, original_filename, stored_filename,
        file_path, file_size, file_checksum, file_hash, status, uploaded_by
    ) VALUES (1, 1, 'traversal.pdf', 'traversal.pdf', '/storage/emulated/0/diagnostic_backend/diagnostic.db', 1024, 'chk_t', 'chk_t', 'STORED', 1)
""")
traversal_id = cursor.lastrowid
conn.commit()
conn.close()

try:
    req = urllib.request.Request(
        f"{BASE_URL}/reports/{traversal_id}/download",
        headers={"Authorization": f"Bearer {token_c1}"}
    )
    urllib.request.urlopen(req)
    record("Path Traversal Defense", False, "VULNERABILITY: Traversal escaped tenant directory")
except urllib.error.HTTPError as e:
    record("Path Traversal Defense", e.code in [403, 404], f"Trapped with HTTP {e.code}")
except Exception as e:
    record("Path Traversal Defense", False, str(e))

# Test 8: CRLF Header Injection Protection
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("""
    INSERT INTO report_documents (
        centre_id, patient_id, original_filename, stored_filename,
        file_path, file_size, file_checksum, file_hash, status, uploaded_by
    ) VALUES (1, 1, 'evil\r\nSet-Cookie: pwned=true\r\n.pdf', 'crlf.pdf', ?, ?, 'chk_c', 'chk_c', 'STORED', 1)
""", (str(pdf_c1), sz1))
crlf_id = cursor.lastrowid
conn.commit()
conn.close()

try:
    req = urllib.request.Request(
        f"{BASE_URL}/reports/{crlf_id}/download",
        headers={"Authorization": f"Bearer {token_c1}"}
    )
    with urllib.request.urlopen(req) as resp:
        cdisp = resp.headers.get("Content-Disposition", "")
        cookies = resp.headers.get("Set-Cookie")
        safe = ("\r" not in cdisp) and ("\n" not in cdisp) and (cookies is None or "pwned" not in str(cookies))
        record("CRLF Header Injection Protection", safe, f"Header sanitized: {cdisp}")
except Exception as e:
    record("CRLF Header Injection Protection", False, str(e))

# Cleanup temporary exploit test rows
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("DELETE FROM report_documents WHERE id IN (?, ?)", (traversal_id, crlf_id))
conn.commit()
conn.close()

print("==========================================================")
passed = sum(1 for r in results if r[1])
total = len(results)
print(f"SUMMARY: {passed}/{total} TESTS PASSED")
print("==========================================================")
