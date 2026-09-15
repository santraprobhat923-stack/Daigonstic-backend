import secrets
import hashlib
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text, update
from app.models import Centre, User, CentreActivationKey
from app.services.audit_service import log_audit_event

def generate_activation_key(db: Session, centre_id: int) -> str:
    raw_token = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()

    act_key = CentreActivationKey(
        centre_id=centre_id,
        key_hash=key_hash,
        status="UNUSED",
        created_at=datetime.now(timezone.utc)
    )
    db.add(act_key)
    db.commit()

    log_audit_event(
        db=db,
        centre_id=centre_id,
        event_type="ACCOUNT_ACTIVATION_KEY_ISSUED",
        entity_type="CENTRE",
        entity_id=centre_id,
        payload={"status": "UNUSED"}
    )
    db.commit()

    return raw_token

def activate_centre_account(db: Session, centre_id: int, email: str, password_plain: str, plaintext_key: str) -> dict:
    try:
        db.execute(text("BEGIN IMMEDIATE"))
    except Exception:
        pass

    user = db.query(User).filter(User.email == email, User.centre_id == centre_id).first()
    if not user or user.hashed_password != password_plain:
        log_audit_event(
            db=db,
            centre_id=centre_id,
            event_type="ACCOUNT_ACTIVATION_FAILED",
            entity_type="CENTRE",
            entity_id=centre_id,
            payload={"reason": "INVALID_CREDENTIALS"}
        )
        db.commit()
        return {"success": False, "error": "Invalid activation credentials or key."}

    centre = db.query(Centre).filter(Centre.id == centre_id).first()
    if not centre or centre.account_status == "ACTIVE":
        return {"success": False, "error": "Account already active or invalid centre."}

    key_hash = hashlib.sha256(plaintext_key.encode('utf-8')).hexdigest()
    act_key = db.query(CentreActivationKey).filter(
        CentreActivationKey.centre_id == centre_id,
        CentreActivationKey.key_hash == key_hash,
        CentreActivationKey.status == "UNUSED"
    ).first()

    if not act_key:
        log_audit_event(
            db=db,
            centre_id=centre_id,
            event_type="ACCOUNT_ACTIVATION_FAILED",
            entity_type="CENTRE",
            entity_id=centre_id,
            payload={"reason": "INVALID_OR_USED_KEY"}
        )
        db.commit()
        return {"success": False, "error": "Invalid activation credentials or key."}

    now = datetime.now(timezone.utc)

    result = db.execute(
        update(CentreActivationKey)
        .where(CentreActivationKey.id == act_key.id, CentreActivationKey.status == "UNUSED")
        .values(status="USED", activated_at=now)
    )

    if result.rowcount != 1:
        db.rollback()
        return {"success": False, "error": "Activation key already consumed or invalid."}

    centre.account_status = "ACTIVE"

    log_audit_event(
        db=db,
        centre_id=centre_id,
        event_type="ACCOUNT_ACTIVATED",
        entity_type="CENTRE",
        entity_id=centre_id,
        payload={"activated_at": now.isoformat()}
    )
    db.commit()

    return {"success": True, "message": "Account successfully activated."}
