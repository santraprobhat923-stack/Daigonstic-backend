from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas, oauth2
from app.database import get_db

router = APIRouter(
    prefix="/patients",
    tags=["Patients"]
)


@router.post("/", response_model=schemas.PatientResponse, status_code=status.HTTP_201_CREATED)
def register_patient(
    patient: schemas.PatientCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    """Registers a new patient, bound to the authenticated user's diagnostic centre."""
    import uuid
    db_patient = models.Patient(
        full_name=patient.full_name,
        age=patient.age,
        gender=patient.gender,
        phone=patient.phone,
        email=patient.email,
        patient_code=f"P-{uuid.uuid4().hex[:10].upper()}",
        centre_id=current_user.centre_id
    )
    db.add(db_patient)
    db.commit()
    db.refresh(db_patient)
    return db_patient


@router.get("/", response_model=List[schemas.PatientResponse])
def get_patients(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    """Returns only patients that belong to the logged-in user's centre."""
    return db.query(models.Patient).filter(
        models.Patient.centre_id == current_user.centre_id
    ).all()


@router.get("/barcode/{barcode}", response_model=schemas.PatientResponse)
def get_patient_by_barcode(
    barcode: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    """Resolve a patient barcode/patient-code within the current centre only."""
    patient = db.query(models.Patient).filter(
        models.Patient.centre_id == current_user.centre_id,
        models.Patient.patient_code == barcode.strip(),
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="No patient found for this barcode")
    return patient


@router.put("/{patient_id}", response_model=schemas.PatientResponse)
def update_patient(
    patient_id: int,
    payload: schemas.PatientUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    """Edit patient demographics while enforcing centre/tenant isolation."""
    patient = db.query(models.Patient).filter(
        models.Patient.id == patient_id,
        models.Patient.centre_id == current_user.centre_id,
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    changes = payload.model_dump(exclude_unset=True)
    if "patient_code" in changes and changes["patient_code"]:
        duplicate = db.query(models.Patient).filter(
            models.Patient.centre_id == current_user.centre_id,
            models.Patient.patient_code == changes["patient_code"],
            models.Patient.id != patient_id,
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="Patient code already exists in this centre")

    for key, value in changes.items():
        setattr(patient, "name" if key == "full_name" else key, value)

    db.commit()
    db.refresh(patient)
    return patient
