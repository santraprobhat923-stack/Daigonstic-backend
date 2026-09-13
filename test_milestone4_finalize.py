import urllib.request
import urllib.parse
import json
import os

BASE_URL = "http://127.0.0.1:8000"

def get_token(username, password):
    data = urllib.parse.urlencode({"username": username, "password": password}).encode()
    req = urllib.request.Request(f"{BASE_URL}/login", data=data)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())["access_token"]

def make_request(url, method="GET", data=None, headers=None):
    if headers is None:
        headers = {}
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        try:
            return e.code, json.loads(err_body)
        except Exception:
            return e.code, {"detail": err_body}

def run_tests():
    print("=== STARTING MILESTONE 4 TEST SUITE (FINALIZATION & PDF) ===")
    
    token1 = get_token("admin@apex.com", "admin123")
    token2 = get_token("tech2@apex.com", "admin123")
    auth1 = {"Authorization": f"Bearer {token1}"}
    auth2 = {"Authorization": f"Bearer {token2}"}

    # 1. Ingest dummy image for Centre 1
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="file"; filename="test_scan.jpg"\r\n')
    body.extend(b"Content-Type: image/jpeg\r\n\r\n")
    body.extend(b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xFF\xDB\x00C\x00")
    body.extend(f"\r\n--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        f"{BASE_URL}/reports/ingest/photo",
        data=bytes(body),
        headers={"Authorization": f"Bearer {token1}", "Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        job = json.loads(resp.read().decode())
    job_id = job["job_id"]
    print(f"[SETUP] Created Job {job_id} in state {job['status']}")

    # Test 1: Finalize before verify -> Expect HTTP 400
    code, res = make_request(f"{BASE_URL}/reports/ingest/{job_id}/finalize", method="POST", headers=auth1)
    assert code == 400, f"Expected 400, got {code}: {res}"
    print("[PASS] Test 1: Blocked finalization on unverified job (HTTP 400)")

    # Run extraction
    code, ext_res = make_request(f"{BASE_URL}/reports/ingest/{job_id}/extract", method="POST", headers=auth1)
    assert code == 200, f"Extraction failed: {ext_res}"

    # Get patient for Centre 1
    import sqlite3
    conn = sqlite3.connect('diagnostic.db')
    cur = conn.cursor()
    cur.execute('SELECT id FROM patients WHERE centre_id = 1 LIMIT 1')
    row = cur.fetchone()
    patient_id = row[0] if row else 101
    conn.close()

    # Submit verification with corrected WBC 7200
    verify_payload = {
        "patient_id": patient_id,
        "panels": [
            {
                "panel_name": "Complete Blood Count",
                "parameters": [
                    {"name": "Hemoglobin", "result": "14.2", "unit": "g/dL", "reference_range": "13.0-17.0"},
                    {"name": "Total WBC", "result": "7200", "unit": "/cumm", "reference_range": "4000-11000"}
                ]
            }
        ],
        "technician_notes": "Corrected WBC to 7200 per physical sheet."
    }
    code, v_res = make_request(f"{BASE_URL}/reports/ingest/{job_id}/verify", method="POST", data=verify_payload, headers=auth1)
    assert code == 200, f"Verification failed: {v_res}"
    print(f"[SETUP] Job {job_id} transitioned to VERIFIED")

    # Test 2: Cross-tenant Finalize -> Centre 2 cannot finalize Centre 1 job -> Expect HTTP 404
    code, cross_res = make_request(f"{BASE_URL}/reports/ingest/{job_id}/finalize", method="POST", headers=auth2)
    assert code == 404, f"Expected 404 for cross-tenant finalize, got {code}: {cross_res}"
    print("[PASS] Test 2: Blocked cross-tenant finalization (HTTP 404)")

    # Test 3: Successful Finalization (Compile PDF & Record)
    code, fin_res = make_request(f"{BASE_URL}/reports/ingest/{job_id}/finalize", method="POST", headers=auth1)
    assert code == 200, f"Finalize failed: {fin_res}"
    assert fin_res["status"] == "FINALIZED"
    report_id = fin_res["report_id"]
    pdf_path = fin_res["file_path"]
    assert os.path.exists(pdf_path), f"PDF was not written to {pdf_path}"
    print(f"[PASS] Test 3: Successfully finalized job, created ReportDocument #{report_id} at {pdf_path}")

    # Test 4: Verify PDF content contains verified data (WBC 7200)
    with open(pdf_path, "rb") as f:
        content = f.read().decode("latin-1", errors="ignore")
        assert "7200" in content, "Verified WBC 7200 missing in compiled PDF!"
        assert "Complete Blood Count" in content, "Panel name missing in compiled PDF!"
    print("[PASS] Test 4: PDF content integrity confirmed (contains verified WBC 7200)")

    # Test 5: Idempotency (calling finalize again returns existing document without duplicate deduction)
    code, re_res = make_request(f"{BASE_URL}/reports/ingest/{job_id}/finalize", method="POST", headers=auth1)
    assert code == 200, f"Idempotent finalize failed: {re_res}"
    assert re_res["report_id"] == report_id, "Report ID changed on repeated finalize call!"
    assert re_res["job_id"] == job_id
    print("[PASS] Test 5: Finalization idempotency verified")

    print("\n=======================================================")
    print("MILESTONE 4 SUMMARY: 5/5 TESTS PASSED")
    print("=======================================================")

if __name__ == "__main__":
    run_tests()
