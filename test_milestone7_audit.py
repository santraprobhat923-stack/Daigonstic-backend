import sqlite3
from datetime import datetime, timezone
from app.models import AuditEvent
from app.database import SessionLocal
from app.services.audit_service import log_audit_event

def test_sqlite_immutability_triggers():
    conn = sqlite3.connect("diagnostic.db")
    cur = conn.cursor()
    
    # 1. Insert a test record directly
    cur.execute(
        "INSERT INTO audit_events (centre_id, actor_user_id, event_type, entity_type, entity_id, timestamp, payload) "
        "VALUES (999, 1, 'TEST_EVENT', 'TEST_ENTITY', 42, ?, '{\"test\": true}')",
        (datetime.now(timezone.utc).isoformat(),)
    )
    conn.commit()
    test_id = cur.lastrowid

    # 2. Attempt UPDATE - Must be aborted by SQLite trigger
    update_failed = False
    try:
        cur.execute("UPDATE audit_events SET event_type = 'TAMPERED' WHERE id = ?", (test_id,))
        conn.commit()
    except sqlite3.IntegrityError as e:
        update_failed = True
        assert "immutable" in str(e).lower(), f"Unexpected error message: {e}"

    # 3. Attempt DELETE - Must be aborted by SQLite trigger
    delete_failed = False
    try:
        cur.execute("DELETE FROM audit_events WHERE id = ?", (test_id,))
        conn.commit()
    except sqlite3.IntegrityError as e:
        delete_failed = True
        assert "immutable" in str(e).lower(), f"Unexpected error message: {e}"

    conn.close()
    assert update_failed, "UPDATE on audit_events should have been blocked by SQLite trigger!"
    assert delete_failed, "DELETE on audit_events should have been blocked by SQLite trigger!"
    print("PASS: Immutability triggers blocked UPDATE and DELETE.")

def test_audit_service_append():
    db = SessionLocal()
    try:
        event = log_audit_event(
            db=db,
            centre_id=888,
            event_type="DIAGNOSTIC_VERIFIED",
            entity_type="REPORT",
            entity_id=101,
            actor_user_id=5,
            payload={"verified_by": "Dr. Test"}
        )
        db.commit()
        
        stored = db.query(AuditEvent).filter(AuditEvent.id == event.id).first()
        assert stored is not None
        assert stored.centre_id == 888
        assert stored.event_type == "DIAGNOSTIC_VERIFIED"
        assert stored.entity_id == 101
        print("PASS: log_audit_event wrote and retrieved correctly.")
    finally:
        db.close()

if __name__ == "__main__":
    test_sqlite_immutability_triggers()
    test_audit_service_append()
    print("\nALL MILESTONE 7 AUDIT VERIFICATIONS PASSED SUCCESSFULLY!")
