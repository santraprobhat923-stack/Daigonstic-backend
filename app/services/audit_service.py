import json
import hashlib
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models import AuditEvent

def canonicalize_event(data: dict) -> str:
    """Produces a deterministic canonical JSON string with sorted keys and no whitespace."""
    return json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False)

def log_audit_event(
    db: Session,
    centre_id: int,
    event_type: str,
    entity_type: str,
    entity_id: int,
    payload: dict,
    actor_type: str = "SYSTEM",
    actor_id: str = "worker-1"
) -> AuditEvent:
    # Acquire immediate lock to serialize concurrent audit event creation in SQLite
    try:
        db.execute(text("BEGIN IMMEDIATE"))
    except Exception:
        pass

    # Sanitize payload: strip secrets, passwords, tokens, API keys
    sanitized_payload = {
        k: v for k, v in payload.items() 
        if not any(sec in k.lower() for sec in ["password", "token", "secret", "key", "auth"])
    }
    canonical_payload_str = canonicalize_event(sanitized_payload)

    # Fetch latest chained audit event for this specific tenant to establish cryptographic link
    last_event = db.query(AuditEvent).filter(
        AuditEvent.centre_id == centre_id,
        AuditEvent.is_chained == True
    ).order_by(AuditEvent.sequence_id.desc()).first()

    sequence_id = (last_event.sequence_id + 1) if last_event and last_event.sequence_id is not None else 1
    previous_event_hash = last_event.event_hash if last_event else None

    timestamp_str = datetime.now(timezone.utc).isoformat()

    # Exact hash construction structure
    hash_input_dict = {
        "actor_id": str(actor_id),
        "actor_type": str(actor_type),
        "canonical_payload": canonical_payload_str,
        "entity_id": int(entity_id),
        "entity_type": str(entity_type),
        "event_type": str(event_type),
        "previous_event_hash": previous_event_hash or "",
        "schema_version": 1,
        "tenant_id": int(centre_id),
        "timestamp": timestamp_str
    }

    canonical_string = canonicalize_event(hash_input_dict)
    event_hash = hashlib.sha256(canonical_string.encode('utf-8')).hexdigest()

    audit_event = AuditEvent(
        centre_id=centre_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=sanitized_payload,
        schema_version=1,
        canonical_payload=canonical_payload_str,
        previous_event_hash=previous_event_hash,
        event_hash=event_hash,
        is_chained=True,
        sequence_id=sequence_id
    )

    db.add(audit_event)
    db.flush()
    return audit_event
