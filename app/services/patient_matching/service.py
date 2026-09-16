from sqlalchemy.orm import Session
from app.models import Patient
from typing import Dict, Any


def _field_value(data: Dict[str, Any], key: str):
    value = data.get(key)
    if isinstance(value, dict):
        return value.get("value")
    return value


def resolve_or_provision_patient(
    db: Session,
    centre_id: int,
    extracted_patient_data: Dict[str, Any],
    ingestion_job_id: int
) -> Patient:
    """Resolve or provision a tenant-scoped patient from OCR demographics."""
    patient_code = _field_value(extracted_patient_data, "patient_code")
    if not patient_code:
        patient_code = f"PROV-JOB-{ingestion_job_id}"

    name = _field_value(extracted_patient_data, "patient_name") or "Unidentified Patient"
    age = _field_value(extracted_patient_data, "age")
    gender = _field_value(extracted_patient_data, "gender")
    phone = _field_value(extracted_patient_data, "phone")
    email = _field_value(extracted_patient_data, "email")

    patient = db.query(Patient).filter(
        Patient.centre_id == centre_id,
        Patient.patient_code == patient_code
    ).first()

    if patient:
        # OCR may have discovered previously missing demographics.
        for field, value in (("name", name), ("age", age), ("gender", gender), ("phone", phone), ("email", email)):
            if value is not None and (getattr(patient, field, None) in (None, "", "Unidentified Patient")):
                setattr(patient, field, int(value) if field == "age" else str(value))
        db.commit()
        db.refresh(patient)
        return patient

    valid_columns = {c.name for c in Patient.__table__.columns}
    kwargs = {"centre_id": centre_id, "patient_code": patient_code}

    if "status" in valid_columns:
        kwargs["status"] = "PROVISIONAL"
    if "created_from_ingestion_job_id" in valid_columns:
        kwargs["created_from_ingestion_job_id"] = ingestion_job_id
    if "age" in valid_columns and age is not None:
        try:
            kwargs["age"] = int(age)
        except (TypeError, ValueError):
            pass
    if "gender" in valid_columns and gender is not None:
        kwargs["gender"] = str(gender)
    if "phone" in valid_columns and phone is not None:
        kwargs["phone"] = str(phone)
    if "email" in valid_columns and email is not None:
        kwargs["email"] = str(email)

    if "name" in valid_columns:
        kwargs["name"] = name
    elif "full_name" in valid_columns:
        kwargs["full_name"] = name
    elif "patient_name" in valid_columns:
        kwargs["patient_name"] = name

    new_patient = Patient(**kwargs)
    db.add(new_patient)
    db.commit()
    db.refresh(new_patient)
    return new_patient
