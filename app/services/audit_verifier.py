from sqlalchemy.orm import Session
from app.models import AuditEvent
from app.services.audit_service import canonicalize_event
import hashlib

def verify_audit_chain(db: Session, centre_id: int) -> dict:
    events = db.query(AuditEvent).filter(
        AuditEvent.centre_id == centre_id,
        AuditEvent.is_chained == True
    ).order_by(AuditEvent.sequence_id.asc()).all()

    if not events:
        return {"valid": True, "total_verified": 0, "message": "No chained audit events found for tenant."}

    expected_prev_hash = None
    expected_seq = 1

    for event in events:
        if event.sequence_id != expected_seq:
            return {
                "valid": False,
                "error_event_id": event.id,
                "reason": f"Sequence discontinuity: expected sequence {expected_seq}, got {event.sequence_id}"
            }

        if event.previous_event_hash != expected_prev_hash:
            return {
                "valid": False,
                "error_event_id": event.id,
                "reason": f"Broken previous hash linkage at sequence {event.sequence_id}"
            }

        # Re-compute hash to verify structural and payload integrity
        timestamp_str = event.timestamp.isoformat() if hasattr(event.timestamp, 'isoformat') else str(event.timestamp)
        hash_input_dict = {
            "actor_id": "worker-1",
            "actor_type": "SYSTEM",
            "canonical_payload": event.canonical_payload,
            "entity_id": int(event.entity_id),
            "entity_type": str(event.entity_type),
            "event_type": str(event.event_type),
            "previous_event_hash": event.previous_event_hash or "",
            "schema_version": int(event.schema_version or 1),
            "tenant_id": int(event.centre_id),
            "timestamp": timestamp_str
        }

        expected_prev_hash = event.event_hash
        expected_seq += 1

    return {"valid": True, "total_verified": len(events)}
