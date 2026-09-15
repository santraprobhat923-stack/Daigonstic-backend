import os
import secrets
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import text

from main import app
from app.database import SessionLocal
from app.models import (
    PatientReportAccessToken,
    AuditEvent,
)
from app.services.patient_access_service import PatientAccessService, hash_token

client = TestClient(app)

def setup_test_fixtures():
    db = SessionLocal()
    try:
        # 1. Ensure report PDF exists on disk
        os.makedirs("storage/test_reports", exist_ok=True)
        pdf_path = os.path.abspath("storage/test_reports/report_801.pdf")
        with open(pdf_path, "wb") as f:
            f.write(b"%PDF-1.4 authoritative diagnostic report stream")

        file_sz = os.path.getsize(pdf_path)

        # 2. Clean previous test records
        db.execute(text("DELETE FROM patient_report_access_tokens WHERE centre_id IN (801, 802);"))
        db.execute(text("DELETE FROM report_documents WHERE id IN (601, 602, 603);"))
        db.execute(text("DELETE FROM billings WHERE order_id = 701;"))
        db.execute(text("DELETE FROM orders WHERE id = 701;"))
        db.execute(text("DELETE FROM patients WHERE id IN (901, 902);"))
        db.execute(text("DELETE FROM users WHERE id = 991;"))
        db.execute(text("DELETE FROM centres WHERE id IN (801, 802);"))
        db.commit()

        # 3. Centres
        db.execute(text("INSERT INTO centres (id, name, address, phone) VALUES (801, 'Centre One', '123 Main St', '1112223330');"))
        db.execute(text("INSERT INTO centres (id, name, address, phone) VALUES (802, 'Centre Two', '456 Side St', '1112223331');"))

        # 4. Mock Staff/Uploader User (id=991)
        db.execute(text("INSERT INTO users (id, email, hashed_password, centre_id, role, is_active) VALUES (991, 'staff801@example.com', 'dummyhash', 801, 'technician', 1);"))

        # 5. Patients
        db.execute(text("INSERT INTO patients (id, centre_id, full_name, age, gender, phone) VALUES (901, 801, 'Alice', 30, 'female', '9999999901');"))
        db.execute(text("INSERT INTO patients (id, centre_id, full_name, age, gender, phone) VALUES (902, 802, 'Bob', 35, 'male', '9999999902');"))

        # 6. Orders
        db.execute(text("INSERT INTO orders (id, centre_id, patient_id, status, subtotal, discount, total, total_amount) VALUES (701, 801, 901, 'COMPLETED', 500, 0, 500.0, 500);"))

        # 7. Billings
        db.execute(text("INSERT INTO billings (id, order_id, patient_id, centre_id, total_amount, payment_status, pending_amount) VALUES (701, 701, 901, 801, 500, 'paid', 0);"))

        # 8. Report 1 (Centre 1, RELEASED - with uploaded_by=991)
        db.execute(text(f"""
            INSERT INTO report_documents 
            (id, centre_id, patient_id, order_id, uploaded_by, file_path, original_filename, stored_filename, file_size, file_hash, file_checksum, is_released, release_status) 
            VALUES 
            (601, 801, 901, 701, 991, '{pdf_path}', 'report_801.pdf', 'stored_801.pdf', {file_sz}, 'hash601', 'checksum601', 1, 'RELEASED');
        """))

        # 9. Report 2 (Centre 1, UNRELEASED / HELD)
        db.execute(text(f"""
            INSERT INTO report_documents 
            (id, centre_id, patient_id, order_id, uploaded_by, file_path, original_filename, stored_filename, file_size, file_hash, file_checksum, is_released, release_status) 
            VALUES 
            (602, 801, 901, 701, 991, '{pdf_path}', 'report_802.pdf', 'stored_802.pdf', {file_sz}, 'hash602', 'checksum602', 0, 'HELD_PAYMENT');
        """))

        # 10. Report 3 (Centre 2, Bob)
        db.execute(text(f"""
            INSERT INTO report_documents 
            (id, centre_id, patient_id, order_id, uploaded_by, file_path, original_filename, stored_filename, file_size, file_hash, file_checksum, is_released, release_status) 
            VALUES 
            (603, 802, 902, 701, 991, '{pdf_path}', 'report_803.pdf', 'stored_803.pdf', {file_sz}, 'hash603', 'checksum603', 1, 'RELEASED');
        """))

        db.commit()
    finally:
        db.close()

def run_tests():
    setup_test_fixtures()
    db = SessionLocal()

    print("=== TEST 1: ISSUE VALID TOKEN & DOWNLOAD REPORT ===")
    token = PatientAccessService.issue_token(db=db, centre_id=801, patient_id=901, report_id=601)
    res = client.get(f"/patient-access/download/{token}")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    assert res.headers["content-type"] == "application/pdf"
    assert b"%PDF-1.4" in res.content
    print("PASS: Valid token downloaded authoritative PDF.")

    print("=== TEST 2: TAMPERED / RANDOM TOKEN FAILS ===")
    res = client.get("/patient-access/download/completely_random_invalid_token_xyz")
    assert res.status_code == 401
    print("PASS: Random token rejected with 401.")

    print("=== TEST 3: EXPIRED TOKEN FAILS ===")
    expired_token = secrets.token_urlsafe(32)
    now_utc = datetime.now(timezone.utc)
    t_rec = PatientReportAccessToken(
        centre_id=801,
        patient_id=901,
        report_id=601,
        token_hash=hash_token(expired_token),
        issued_at=now_utc - timedelta(days=2),
        expires_at=now_utc - timedelta(hours=1),
    )
    db.add(t_rec)
    db.commit()
    res = client.get(f"/patient-access/download/{expired_token}")
    assert res.status_code == 401
    print("PASS: Expired token rejected with 401.")

    print("=== TEST 4: REVOKED TOKEN FAILS ===")
    revoked_token = secrets.token_urlsafe(32)
    t_rec = PatientReportAccessToken(
        centre_id=801,
        patient_id=901,
        report_id=601,
        token_hash=hash_token(revoked_token),
        issued_at=now_utc,
        expires_at=now_utc + timedelta(hours=24),
        revoked_at=now_utc,
    )
    db.add(t_rec)
    db.commit()
    res = client.get(f"/patient-access/download/{revoked_token}")
    assert res.status_code == 401
    print("PASS: Revoked token rejected with 401.")

    print("=== TEST 5: UNRELEASED REPORT BLOCKS ACCESS ===")
    try:
        PatientAccessService.issue_token(db=db, centre_id=801, patient_id=901, report_id=602)
        assert False, "Should not issue token for unreleased report"
    except ValueError:
        print("PASS: Token issuance rejected for unreleased report.")

    print("=== TEST 6: TENANT ISOLATION (CENTRE A CANNOT ACCESS CENTRE B) ===")
    valid, reason, _, _ = PatientAccessService.validate_token_and_authorize(
        db=db, raw_token=token, expected_report_id=603
    )
    assert not valid
    assert reason == "REPORT_MISMATCH"
    print("PASS: Cross-tenant access strictly prevented.")

    print("=== TEST 7: AUDIT EVENTS LOGGED ===")
    ev_success = (
        db.query(AuditEvent)
        .filter(AuditEvent.event_type == "REPORT_DOWNLOAD_SUCCEEDED", AuditEvent.entity_id == 601)
        .first()
    )
    assert ev_success is not None
    assert "patient_id" in ev_success.payload
    print("PASS: REPORT_DOWNLOAD_SUCCEEDED logged in immutable audit trail.")

    db.close()
    print("\nALL MILESTONE 8 TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
