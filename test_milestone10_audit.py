import threading
from app.database import SessionLocal
from app.models import AuditEvent, Centre
from app.services.audit_service import log_audit_event, canonicalize_event
from app.services.audit_verifier import verify_audit_chain

def run_tests():
    db = SessionLocal()
    try:
        # Setup test centres
        c1 = db.query(Centre).filter(Centre.id == 9901).first()
        if not c1:
            db.add(Centre(id=9901, name="Audit Centre Alpha", address="A1", phone="9000000001"))
        c2 = db.query(Centre).filter(Centre.id == 9902).first()
        if not c2:
            db.add(Centre(id=9902, name="Audit Centre Beta", address="A2", phone="9000000002"))
        db.commit()

        # Clean existing audit events for test centres
        db.query(AuditEvent).filter(AuditEvent.centre_id.in_([9901, 9902])).delete()
        db.commit()

        print("=== TEST 1: CANONICAL SERIALIZATION DETERMINISM ===")
        d1 = {"b": 2, "a": 1, "z": 9}
        d2 = {"z": 9, "a": 1, "b": 2}
        s1 = canonicalize_event(d1)
        s2 = canonicalize_event(d2)
        assert s1 == s2, "Canonical serialization must be key-order invariant"
        assert s1 == '{"a":1,"b":2,"z":9}', f"Unexpected canonical string: {s1}"
        print("PASS: Canonical serialization is deterministic.")

        print("=== TEST 2: HASH CHAINING & GENESIS EVENT ===")
        ev1 = log_audit_event(db, centre_id=9901, event_type="JOB_CLAIMED", entity_type="JOB", entity_id=1, payload={"status": "PROCESSING"})
        db.commit()
        assert ev1.sequence_id == 1
        assert ev1.previous_event_hash is None
        assert ev1.is_chained is True
        assert ev1.event_hash is not None
        print("PASS: Genesis event correctly initialized.")

        print("=== TEST 3: SUBSEQUENT CHAINED EVENTS ===")
        ev2 = log_audit_event(db, centre_id=9901, event_type="JOB_COMPLETED", entity_type="JOB", entity_id=1, payload={"status": "SENT"})
        db.commit()
        assert ev2.sequence_id == 2
        assert ev2.previous_event_hash == ev1.event_hash
        print("PASS: Subsequent event correctly chained to previous event hash.")

        print("=== TEST 4: TENANT ISOLATION ===")
        ev_beta = log_audit_event(db, centre_id=9902, event_type="JOB_CLAIMED", entity_type="JOB", entity_id=10, payload={"status": "PROCESSING"})
        db.commit()
        assert ev_beta.sequence_id == 1
        assert ev_beta.previous_event_hash is None
        print("PASS: Tenant audit streams remain strictly isolated.")

        print("=== TEST 5: CHAIN VERIFICATION UTILITY ===")
        res = verify_audit_chain(db, 9901)
        assert res["valid"] is True, f"Chain verification failed: {res}"
        print("PASS: Audit chain successfully verified.")

        print("=== TEST 6: CONCURRENT AUDIT CREATION ===")
        def concurrent_log():
            session = SessionLocal()
            try:
                log_audit_event(session, centre_id=9901, event_type="CONCURRENT_EVENT", entity_type="JOB", entity_id=99, payload={"test": "concurrency"})
                session.commit()
            finally:
                session.close()

        threads = [threading.Thread(target=concurrent_log) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        res_concurrent = verify_audit_chain(db, 9901)
        assert res_concurrent["valid"] is True, f"Concurrent chain verification failed: {res_concurrent}"
        print("PASS: Concurrent audit event creation successfully verified without chain corruption.")

        print("\nALL MILESTONE 10 TESTS PASSED SUCCESSFULLY!")

    finally:
        db.close()

if __name__ == "__main__":
    run_tests()
