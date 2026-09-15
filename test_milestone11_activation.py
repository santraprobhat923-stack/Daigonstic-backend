import threading
from app.database import SessionLocal
from app.models import Centre, User, CentreActivationKey, AuditEvent
from app.services.activation_service import generate_activation_key, activate_centre_account

def run_m11_tests():
    db = SessionLocal()
    try:
        print("=== SETUP M11 TEST DATA ===")
        # Recreate / cleanup test centre
        db.query(AuditEvent).filter(AuditEvent.centre_id == 8801).delete()
        db.query(CentreActivationKey).filter(CentreActivationKey.centre_id == 8801).delete()
        db.query(User).filter(User.centre_id == 8801).delete()
        db.query(Centre).filter(Centre.id == 8801).delete()
        db.commit()

        centre = Centre(id=8801, name="Activation Test Centre", address="Test Addr", phone="9111111111", account_status="PENDING_ACTIVATION")
        db.add(centre)
        db.commit()

        user = User(email="admin@activation.com", hashed_password="securepassword123", centre_id=8801, role="ADMIN", is_active=True)
        db.add(user)
        db.commit()

        print("=== TEST 1: GENERATE ACTIVATION KEY ===")
        plaintext_key = generate_activation_key(db, centre_id=8801)
        assert plaintext_key is not None
        print(f"PASS: Key generated successfully (len: {len(plaintext_key)})")

        print("=== TEST 2: INVALID CREDENTIALS / WRONG KEY REJECTION ===")
        res_fail = activate_centre_account(db, centre_id=8801, email="admin@activation.com", password_plain="wrongpassword", plaintext_key=plaintext_key)
        assert res_fail["success"] is False
        print("PASS: Activation rejected on wrong credentials.")

        print("=== TEST 3: SUCCESSFUL FIRST-TIME ACTIVATION ===")
        res_success = activate_centre_account(db, centre_id=8801, email="admin@activation.com", password_plain="securepassword123", plaintext_key=plaintext_key)
        assert res_success["success"] is True, f"Activation failed: {res_success}"
        assert centre.account_status == "ACTIVE"
        print("PASS: Account successfully activated and transitioned to ACTIVE.")

        print("=== TEST 4: ALREADY USED KEY REJECTION ===")
        # Try activating again with the same key
        res_reuse = activate_centre_account(db, centre_id=8801, email="admin@activation.com", password_plain="securepassword123", plaintext_key=plaintext_key)
        assert res_reuse["success"] is False
        print("PASS: Reusing consumed key correctly rejected.")

        print("=== TEST 5: CONCURRENT ACTIVATION RACE CONDITION TEST ===")
        # Setup a new pending centre for concurrency test
        c_conc = Centre(id=8802, name="Concurrent Centre", address="Addr", phone="9222222222", account_status="PENDING_ACTIVATION")
        db.add(c_conc)
        db.commit()
        u_conc = User(email="conc@activation.com", hashed_password="pw", centre_id=8802, role="ADMIN", is_active=True)
        db.add(u_conc)
        db.commit()
        conc_key = generate_activation_key(db, centre_id=8802)

        results = []
        def try_activate():
            s = SessionLocal()
            try:
                r = activate_centre_account(s, centre_id=8802, email="conc@activation.com", password_plain="pw", plaintext_key=conc_key)
                results.append(r["success"])
            finally:
                s.close()

        threads = [threading.Thread(target=try_activate) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        success_count = sum(1 for r in results if r is True)
        assert success_count == 1, f"Expected exactly 1 successful activation, got {success_count}"
        print("PASS: Concurrent activation successfully enforced exactly-one-success invariant.")

        print("\nALL MILESTONE 11 TESTS PASSED SUCCESSFULLY!")

    finally:
        db.close()

if __name__ == "__main__":
    run_m11_tests()
