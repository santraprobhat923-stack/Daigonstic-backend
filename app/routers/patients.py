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
    db_patient = models.Patient(
        full_name=patient.full_name,
        age=patient.age,
        gender=patient.gender,
        phone=patient.phone,
        email=patient.email,
        centre_id=current_user.centre_id  # Enforced tenant isolation
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
    patients = db.query(models.Patient).filter(
        models.Patient.centre_id == current_user.centre_id
    ).all()
    return patients
