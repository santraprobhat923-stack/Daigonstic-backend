from sqlalchemy.orm import Session
from app.models import Patient
from typing import Dict, Any

def resolve_or_provision_patient(
    db: Session,
    centre_id: int,
    extracted_patient_data: Dict[str, Any],
    ingestion_job_id: int
) -> Patient:
    """
    Tenant-scoped patient resolution service.
    Dynamically maps attributes to match the exact columns defined in the Patient model.
    """
    patient_code = extracted_patient_data.get("patient_code", {}).get("value")
    if not patient_code:
        patient_code = f"PROV-JOB-{ingestion_job_id}"
        
    name = extracted_patient_data.get("patient_name", {}).get("value", "Unidentified Patient")
    age = extracted_patient_data.get("age", {}).get("value")
    gender = extracted_patient_data.get("gender", {}).get("value")

    # Strict tenant boundary check
    patient = db.query(Patient).filter(
        Patient.centre_id == centre_id,
        Patient.patient_code == patient_code
    ).first()

    if patient:
        return patient

    # Dynamically inspect Patient table columns to prevent invalid keyword arguments
    valid_columns = {c.name for c in Patient.__table__.columns}
    
    kwargs = {
        "centre_id": centre_id,
        "patient_code": patient_code,
    }
    
    if "status" in valid_columns:
        kwargs["status"] = "PROVISIONAL"
        
    if "created_from_ingestion_job_id" in valid_columns:
        kwargs["created_from_ingestion_job_id"] = ingestion_job_id
        
    if "age" in valid_columns and age is not None:
        try:
            kwargs["age"] = int(age)
        except ValueError:
            pass
            
    if "gender" in valid_columns and gender is not None:
        kwargs["gender"] = str(gender)

    # Map name to whichever field exists in the Patient model
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
