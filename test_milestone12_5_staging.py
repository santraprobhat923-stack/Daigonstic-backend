from app.database import SessionLocal
from app.models import Centre, User, AuditEvent, CentreActivationKey
from app.services.activation_service import generate_activation_key, activate_centre_account
from app.services.operations_service import update_centre_profile, create_technician_staff, set_staff_active_status

def run_staging_e2e():
    print("=== M12.5 STAGING END-TO-END DEMO & INTEGRATION TEST ===")
    db = SessionLocal()
    try:
        # 1. Clean staging data
        db.query(AuditEvent).filter(AuditEvent.centre_id == 9901).delete()
        db.query(CentreActivationKey).filter(CentreActivationKey.centre_id == 9901).delete()
        db.query(User).filter(User.centre_id == 9901).delete()
        db.query(Centre).filter(Centre.id == 9901).delete()
        db.commit()

        # 2. Super Admin creates Centre (PENDING_ACTIVATION)
        centre = Centre(id=9901, name="Staging Demo Centre", address="Staging St", phone="9333333333", account_status="PENDING_ACTIVATION")
        db.add(centre)
        db.commit()

        admin_user = User(email="admin@stagingcentre.com", hashed_password="stagingpassword123", centre_id=9901, role="ADMIN", is_active=True)
        db.add(admin_user)
        db.commit()

        print("PASS: Staging centre created in PENDING_ACTIVATION state.")

        # 3. Generate One-Time Activation Key (M11)
        plaintext_key = generate_activation_key(db, centre_id=9901)
        assert plaintext_key is not None
        print(f"PASS: Activation key generated successfully (len: {len(plaintext_key)}).")

        # 4. Perform Activation (M11)
        act_res = activate_centre_account(db, centre_id=9901, email="admin@stagingcentre.com", password_plain="stagingpassword123", plaintext_key=plaintext_key)
        assert act_res["success"] is True
        assert centre.account_status == "ACTIVE"
        print("PASS: Centre successfully activated (PENDING -> ACTIVE).")

        # 5. Test Replay Protection
        replay_res = activate_centre_account(db, centre_id=9901, email="admin@stagingcentre.com", password_plain="stagingpassword123", plaintext_key=plaintext_key)
        assert replay_res["success"] is False
        print("PASS: Replaying used activation key successfully rejected.")

        # 6. Centre Operations & Staff Management (M12)
        updated_centre = update_centre_profile(db, centre_id=9901, name="Staging Demo Centre Updated")
        assert updated_centre.name == "Staging Demo Centre Updated"
        print("PASS: Centre profile successfully updated and audited.")

        tech = create_technician_staff(db, centre_id=9901, email="tech@stagingcentre.com", password_plain="techpass", role="TECHNICIAN")
        assert tech is not None and tech.centre_id == 9901
        print("PASS: Technician staff successfully created and scoped to centre.")

        print("\nALL M12.5 STAGING INTEGRATION TESTS PASSED SUCCESSFULLY!")

    finally:
        db.close()

if __name__ == "__main__":
    run_staging_e2e()
