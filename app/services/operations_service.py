from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models import Centre, User, AuditEvent
from app.services.audit_service import log_audit_event

def update_centre_profile(db: Session, centre_id: int, name: str = None, address: str = None, phone: str = None) -> Centre:
    try:
        db.execute(text("BEGIN IMMEDIATE"))
    except Exception:
        pass

    centre = db.query(Centre).filter(Centre.id == centre_id).first()
    if not centre:
        return None

    old_values = {"name": centre.name, "address": centre.address, "phone": centre.phone}

    if name is not None:
        centre.name = name
    if address is not None:
        centre.address = address
    if phone is not None:
        centre.phone = phone

    log_audit_event(
        db=db,
        centre_id=centre_id,
        event_type="CENTRE_PROFILE_UPDATED",
        entity_type="CENTRE",
        entity_id=centre_id,
        payload={"old": old_values, "new": {"name": centre.name, "address": centre.address, "phone": centre.phone}}
    )
    db.commit()
    db.refresh(centre)
    return centre

def create_technician_staff(db: Session, centre_id: int, email: str, password_plain: str, role: str = "TECHNICIAN") -> User:
    try:
        db.execute(text("BEGIN IMMEDIATE"))
    except Exception:
        pass

    # Ensure role is safe (only TECHNICIAN or CENTRE_ADMIN as allowed by business logic)
    if role not in ["TECHNICIAN", "CENTRE_ADMIN"]:
        role = "TECHNICIAN"

    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        return None

    user = User(
        email=email,
        hashed_password=password_plain, # Reusing existing plain/hashed pattern in repo
        centre_id=centre_id,
        role=role,
        is_active=True
    )
    db.add(user)
    db.flush()

    log_audit_event(
        db=db,
        centre_id=centre_id,
        event_type="STAFF_CREATED",
        entity_type="USER",
        entity_id=user.id,
        payload={"email": email, "role": role}
    )
    db.commit()
    db.refresh(user)
    return user

def set_staff_active_status(db: Session, centre_id: int, user_id: int, is_active: bool) -> User:
    try:
        db.execute(text("BEGIN IMMEDIATE"))
    except Exception:
        pass

    user = db.query(User).filter(User.id == user_id, User.centre_id == centre_id).first()
    if not user:
        return None

    user.is_active = is_active
    event_type = "STAFF_ENABLED" if is_active else "STAFF_DISABLED"

    log_audit_event(
        db=db,
        centre_id=centre_id,
        event_type=event_type,
        entity_type="USER",
        entity_id=user.id,
        payload={"is_active": is_active}
    )
    db.commit()
    db.refresh(user)
    return user
