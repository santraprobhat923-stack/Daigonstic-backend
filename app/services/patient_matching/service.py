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
    Searches strictly by centre_id + patient_code. 
    If unmatched, automatically provisions a PROVISIONAL patient record.
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

    # Automatically provision provisional patient
    new_patient = Patient(
        centre_id=centre_id,
        patient_code=patient_code,
        name=name,
        age=age,
        gender=gender,
        status="PROVISIONAL",
        created_from_ingestion_job_id=ingestion_job_id
    )
    db.add(new_patient)
    db.commit()
    db.refresh(new_patient)
    return new_patient
