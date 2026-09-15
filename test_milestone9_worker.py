import os
import uuid
import threading
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import text

from main import app
from app.database import SessionLocal
from app.models import NotificationJob, AuditEvent, User, Centre
from app.services.background_worker import BackgroundWorker
from app.services.notification_provider import MockNotificationProvider
from app import oauth2

import jwt as pyjwt
try:
    from jose import jwt
except ImportError:
    jwt = pyjwt

client = TestClient(app)

# Use distinct Centre & User IDs for clean test isolation
C_ALPHA = 9101
C_BETA = 9102
U_ALPHA = 9201
U_BETA = 9202

def setup_m9_fixtures():
    db = SessionLocal()
    try:
        # Note: Do NOT delete from audit_events (enforced immutable by M7 triggers)
        db.execute(text(f"DELETE FROM notification_jobs WHERE centre_id IN ({C_ALPHA}, {C_BETA});"))
        db.execute(text(f"DELETE FROM users WHERE id IN ({U_ALPHA}, {U_BETA});"))
        db.execute(text(f"DELETE FROM centres WHERE id IN ({C_ALPHA}, {C_BETA});"))
        db.commit()

        # Centres
        db.execute(text(f"INSERT INTO centres (id, name, address, phone) VALUES ({C_ALPHA}, 'Centre Alpha M9', 'Street 1', '9000000001');"))
        db.execute(text(f"INSERT INTO centres (id, name, address, phone) VALUES ({C_BETA}, 'Centre Beta M9', 'Street 2', '9000000002');"))

        # Staff Users
        db.execute(text(f"INSERT INTO users (id, email, hashed_password, centre_id, role, is_active) VALUES ({U_ALPHA}, 'staff_alpha@m9.com', 'dummy_hash', {C_ALPHA}, 'technician', 1);"))
        db.execute(text(f"INSERT INTO users (id, email, hashed_password, centre_id, role, is_active) VALUES ({U_BETA}, 'staff_beta@m9.com', 'dummy_hash', {C_BETA}, 'technician', 1);"))

        db.commit()
    finally:
        db.close()

def run_tests():
    setup_m9_fixtures()
    db = SessionLocal()
    test_start_utc = datetime.now(timezone.utc)

    print("=== TEST 1: JOB DISCOVERY & ATOMIC CLAIMING ===")
    job1 = NotificationJob(
        centre_id=C_ALPHA,
        report_id=101,
        patient_id=201,
        recipient="9999990001",
        channel="SMS",
        message_payload="Test 1 message",
        status="PENDING",
        attempt_count=0,
        max_retries=3
    )
    db.add(job1)
    db.commit()
    db.expire_all()
    job1 = db.query(NotificationJob).filter_by(id=job1.id).first()

    worker_a = BackgroundWorker(worker_id="worker-A")
    worker_b = BackgroundWorker(worker_id="worker-B")

    claim_results = []
    def try_claim(w):
        d = SessionLocal()
        c = w.claim_next_job(d)
        if c:
            claim_results.append((w.worker_id, c.id))
        d.close()

    t1 = threading.Thread(target=try_claim, args=(worker_a,))
    t2 = threading.Thread(target=try_claim, args=(worker_b,))
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert len(claim_results) == 1, f"Expected exactly 1 atomic claim, got {len(claim_results)}"
    db.rollback()
    job1 = db.query(NotificationJob).filter_by(id=job1.id).first()
    assert job1.status == "PROCESSING"
    assert job1.locked_by in ["worker-A", "worker-B"]
    print("PASS: Atomic claiming prevented race condition.")

    print("=== TEST 2: SUCCESSFUL EXECUTION ===")
    mock_prov = MockNotificationProvider(mode=MockNotificationProvider.MODE_SUCCESS)
    worker_success = BackgroundWorker(worker_id="worker-S", provider=mock_prov)
    final_status = worker_success.process_job(db, job1)
    assert final_status == "SENT"
    assert job1.status == "SENT"
    assert job1.sent_at is not None
    assert job1.locked_at is None
    print("PASS: Successful job moved to terminal SENT state.")

    print("=== TEST 3: RETRYABLE FAILURE & EXPONENTIAL BACKOFF ===")
    job_retry = NotificationJob(
        centre_id=C_ALPHA,
        report_id=102,
        patient_id=202,
        recipient="9999990002",
        channel="SMS",
        message_payload="Temporary failure test",
        status="PROCESSING",
        attempt_count=0,
        max_retries=3
    )
    db.add(job_retry)
    db.commit()

    mock_fail = MockNotificationProvider(mode=MockNotificationProvider.MODE_TEMPORARY_FAILURE)
    worker_fail = BackgroundWorker(worker_id="worker-F", provider=mock_fail, base_backoff_seconds=5)
    st = worker_fail.process_job(db, job_retry)
    assert st == "PENDING"
    assert job_retry.attempt_count == 1
    assert job_retry.next_attempt_at is not None
    print("PASS: Retryable failure scheduled next attempt with backoff.")

    print("=== TEST 4: DEAD LETTER QUEUE TRANSITION ===")
    job_dlq = NotificationJob(
        centre_id=C_ALPHA,
        report_id=103,
        patient_id=203,
        recipient="9999990003",
        channel="SMS",
        message_payload="DLQ test",
        status="PROCESSING",
        attempt_count=2,
        max_retries=3
    )
    db.add(job_dlq)
    db.commit()

    st_dlq = worker_fail.process_job(db, job_dlq)
    assert st_dlq == "DEAD_LETTER"
    assert job_dlq.status == "DEAD_LETTER"
    assert job_dlq.dead_lettered_at is not None
    print("PASS: Max retries exhausted cleanly transitioned to DEAD_LETTER.")

    print("=== TEST 5: STALE JOB RECOVERY ===")
    old_time = datetime.now(timezone.utc) - timedelta(minutes=20)
    job_stale = NotificationJob(
        centre_id=C_ALPHA,
        report_id=104,
        patient_id=204,
        recipient="9999990004",
        channel="SMS",
        message_payload="Stale job",
        status="PROCESSING",
        locked_at=old_time,
        locked_by="crashed-worker"
    )
    db.add(job_stale)
    db.commit()

    recovered = worker_a.recover_stale_jobs(db)
    assert recovered >= 1
    db.refresh(job_stale)
    assert job_stale.status == "PENDING"
    assert job_stale.locked_by is None
    print("PASS: Stale job recovered to PENDING.")

    print("=== TEST 6: DLQ REPLAY & TENANT ISOLATION ===")
    token_a = jwt.encode({"user_id": U_ALPHA, "centre_id": C_ALPHA, "sub": str(U_ALPHA)}, oauth2.SECRET_KEY, algorithm=oauth2.ALGORITHM)
    headers_a = {"Authorization": f"Bearer {token_a}"}

    res = client.get("/notifications/dlq", headers=headers_a)
    assert res.status_code == 200
    dlq_list = res.json()
    assert any(j["id"] == job_dlq.id for j in dlq_list)

    token_b = jwt.encode({"user_id": U_BETA, "centre_id": C_BETA, "sub": str(U_BETA)}, oauth2.SECRET_KEY, algorithm=oauth2.ALGORITHM)
    headers_b = {"Authorization": f"Bearer {token_b}"}

    res_cross = client.post(f"/notifications/dlq/{job_dlq.id}/replay", headers=headers_b)
    assert res_cross.status_code == 403, f"Expected 403, got {res_cross.status_code}"
    print("PASS: Cross-tenant DLQ replay strictly forbidden.")

    res_replay = client.post(f"/notifications/dlq/{job_dlq.id}/replay", headers=headers_a)
    assert res_replay.status_code == 200
    db.refresh(job_dlq)
    assert job_dlq.status == "PENDING"
    assert job_dlq.attempt_count == 0
    print("PASS: Authorized tenant successfully replayed dead-lettered job.")

    print("=== TEST 7: AUDIT EVENTS VERIFICATION ===")
    audit_events = db.query(AuditEvent).filter(
        AuditEvent.centre_id == C_ALPHA,
        AuditEvent.entity_type == "NOTIFICATION_JOB",
        AuditEvent.timestamp >= test_start_utc - timedelta(seconds=5)
    ).all()
    event_types = [e.event_type for e in audit_events]
    assert "JOB_CLAIMED" in event_types
    assert "JOB_COMPLETED" in event_types
    assert "JOB_DEAD_LETTERED" in event_types
    assert "JOB_REPLAYED" in event_types
    print("PASS: All lifecycle audit events verified.")

    db.close()
    print("\nALL MILESTONE 9 TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
