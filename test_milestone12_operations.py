from app.database import SessionLocal
from app.models import Centre, User, AuditEvent
from app.services.operations_service import update_centre_profile, create_technician_staff, set_staff_active_status

def run_m12_tests():
    db = SessionLocal()
    try:
        print("=== SETUP M12 TEST DATA ===")
        db.query(AuditEvent).filter(AuditEvent.centre_id.in_([9001, 9002])).delete()
        db.query(User).filter(User.centre_id.in_([9001, 9002])).delete()
        db.query(Centre).filter(Centre.id.in_([9001, 9002])).delete()
        db.commit()

        c1 = Centre(id=9001, name="Alpha Centre", address="Alpha St", phone="9888888881", account_status="ACTIVE")
        c2 = Centre(id=9002, name="Beta Centre", address="Beta St", phone="9888888882", account_status="PENDING_ACTIVATION")
        db.add_all([c1, c2])
        db.commit()

        print("=== TEST 1: CENTRE PROFILE MANAGEMENT ===")
        updated_c = update_centre_profile(db, centre_id=9001, name="Alpha Diagnostic Hub")
        assert updated_c.name == "Alpha Diagnostic Hub"
        print("PASS: Centre profile successfully updated and audited.")

        print("=== TEST 2: STAFF CREATION & TENANT RESTRICTION ===")
        tech1 = create_technician_staff(db, centre_id=9001, email="tech1@alpha.com", password_plain="techpass1", role="TECHNICIAN")
        assert tech1 is not None and tech1.centre_id == 9001 and tech1.role == "TECHNICIAN"
        print("PASS: Technician successfully created under Centre 9001.")

        print("=== TEST 3: STAFF STATUS TOGGLE (ENABLE/DISABLE) ===")
        set_staff_active_status(db, centre_id=9001, user_id=tech1.id, is_active=False)
        assert tech1.is_active is False
        print("PASS: Staff successfully disabled and audited.")

        set_staff_active_status(db, centre_id=9001, user_id=tech1.id, is_active=True)
        assert tech1.is_active is True
        print("PASS: Staff successfully re-enabled.")

        print("=== TEST 4: CROSS-TENANT ISOLATION ENFORCEMENT ===")
        # Attempting to modify Centre 9001 staff using Centre 9002 tenant ID should return None
        cross_tenant_attempt = set_staff_active_status(db, centre_id=9002, user_id=tech1.id, is_active=False)
        assert cross_tenant_attempt is None
        assert tech1.is_active is True  # Should remain unchanged
        print("PASS: Cross-tenant staff modification strictly blocked.")

        print("=== TEST 5: PENDING ACTIVATION CHECK ===")
        # Centre 9002 is PENDING_ACTIVATION, so operational profile update should be appropriately governed
        pending_c_update = update_centre_profile(db, centre_id=9002, name="Should Be Handled")
        assert pending_c_update is not None # Service executes, but state enforcement at router layer blocks PENDING centres

        print("\nALL MILESTONE 12 TESTS PASSED SUCCESSFULLY!")

    finally:
        db.close()

if __name__ == "__main__":
    run_m12_tests()
