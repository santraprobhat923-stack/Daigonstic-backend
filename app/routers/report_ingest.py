import os
import hashlib
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models, oauth2
from app.database import get_db
from app.services.extraction import get_extraction_provider
from app.services.extraction.base import ExtractionProcessingError
from app.services.pdf_compiler import compile_and_save_report

router = APIRouter(prefix="/reports/ingest", tags=["Report Ingestion"])

STORAGE_DIR = os.path.abspath("storage/source_images")
os.makedirs(STORAGE_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

class VerifyPayload(BaseModel):
    patient_id: Optional[int] = None
    patient_code: Optional[str] = None
    panels: List[Dict[str, Any]]

@router.post("/photo", status_code=status.HTTP_201_CREATED)
async def upload_photo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    centre_id = current_user.centre_id
    if not centre_id:
        raise HTTPException(status_code=400, detail="User not assigned to a centre")

    raw_filename = file.filename or "upload.jpg"
    safe_filename = os.path.basename(raw_filename).replace("/", "").replace("..", "")
    if not safe_filename:
        safe_filename = "upload.jpg"

    ext = os.path.splitext(safe_filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS or file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="Disallowed file type")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    if content[:2] == b"MZ":
        raise HTTPException(status_code=400, detail="Disallowed executable content")

    file_size = len(content)
    file_hash = hashlib.sha256(content).hexdigest()

    centre_dir = os.path.join(STORAGE_DIR, str(centre_id))
    os.makedirs(centre_dir, exist_ok=True)
    saved_name = f"{file_hash[:16]}_{safe_filename}"
    saved_path = os.path.join(centre_dir, saved_name)

    with open(saved_path, "wb") as f:
        f.write(content)

    job = models.ReportIngestionJob(
        centre_id=centre_id,
        technician_id=current_user.id,
        source_image_path=saved_path,
        source_image_hash=file_hash,
        original_filename=safe_filename,
        file_size=file_size,
        mime_type=file.content_type or "image/jpeg",
        status="PHOTO_UPLOADED"
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    return {
        "job_id": job.id,
        "id": job.id,
        "status": job.status,
        "original_filename": safe_filename,
        "filename": safe_filename,
        "file_size": file_size,
        "file_hash": file_hash
    }

@router.get("/{job_id}", status_code=status.HTTP_200_OK)
def get_job_status(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    job = db.query(models.ReportIngestionJob).filter(models.ReportIngestionJob.id == job_id).first()
    if not job or job.centre_id != current_user.centre_id:
        raise HTTPException(status_code=404, detail="Ingestion job not found")

    return {
        "job_id": job.id,
        "id": job.id,
        "centre_id": job.centre_id,
        "patient_id": job.patient_id,
        "status": job.status,
        "original_filename": job.original_filename,
        "file_size": job.file_size,
        "extracted_data": json.loads(job.extracted_data) if job.extracted_data else None,
        "verified_data": json.loads(job.verified_data) if job.verified_data else None,
        "final_report_id": job.final_report_id
    }

@router.post("/{job_id}/extract", status_code=status.HTTP_200_OK)
def run_extraction(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    job = db.query(models.ReportIngestionJob).filter(models.ReportIngestionJob.id == job_id).first()
    if not job or job.centre_id != current_user.centre_id:
        raise HTTPException(status_code=404, detail="Ingestion job not found")

    # Idempotency check
    if job.status in ["EXTRACTED", "NEEDS_VERIFICATION", "VERIFIED", "FINALIZED"]:
        extracted_data = json.loads(job.extracted_data) if job.extracted_data else {}
        return {
            "message": "Job already extracted",
            "job_id": job.id,
            "id": job.id,
            "status": job.status,
            "matched_patient_id": job.patient_id,
            "extracted_data": extracted_data
        }

    provider = get_extraction_provider()
    try:
        result = provider.extract(
            Path(job.source_image_path),
            context={
                "centre_id": job.centre_id,
                "original_filename": job.original_filename
            }
        )
    except ExtractionProcessingError as e:
        job.status = "EXTRACTION_FAILED"
        job.error_code = e.code or "UNREADABLE_SCAN"
        job.error_message = e.message or "Extraction failed"
        db.commit()
        db.refresh(job)
        raise HTTPException(
            status_code=422,
            detail={"error_code": job.error_code, "message": job.error_message}
        )
    except Exception as e:
        job.status = "EXTRACTION_FAILED"
        job.error_code = "UNREADABLE_SCAN"
        job.error_message = str(e)
        db.commit()
        db.refresh(job)
        raise HTTPException(
            status_code=422,
            detail={"error_code": "UNREADABLE_SCAN", "message": str(e)}
        )

    if hasattr(result, "model_dump"):
        extracted_dict = result.model_dump()
    elif hasattr(result, "dict"):
        extracted_dict = result.dict()
    else:
        extracted_dict = {
            "patient": getattr(result, "patient", {}),
            "panels": getattr(result, "panels", []),
            "provider_name": getattr(result, "provider_name", "mock"),
            "provider_version": getattr(result, "provider_version", "1.0.0"),
            "raw_text_summary": getattr(result, "raw_text_summary", None)
        }

    matched_patient = None
    patient_info = extracted_dict.get("patient", {})
    patient_code_val = None
    patient_name_val = None

    if isinstance(patient_info, dict):
        p_code = patient_info.get("patient_code")
        if isinstance(p_code, dict):
            patient_code_val = p_code.get("value")
        elif isinstance(p_code, str):
            patient_code_val = p_code

        p_name = patient_info.get("patient_name")
        if isinstance(p_name, dict):
            patient_name_val = p_name.get("value")
        elif isinstance(p_name, str):
            patient_name_val = p_name

    if patient_code_val:
        matched_patient = db.query(models.Patient).filter(
            models.Patient.patient_code == patient_code_val,
            models.Patient.centre_id == current_user.centre_id
        ).first()

    if not matched_patient and patient_name_val:
        matched_patient = db.query(models.Patient).filter(
            models.Patient.full_name == patient_name_val,
            models.Patient.centre_id == current_user.centre_id
        ).first()

    if matched_patient:
        job.patient_id = matched_patient.id

    job.extracted_data = json.dumps(extracted_dict, default=str)
    job.status = "NEEDS_VERIFICATION"
    db.commit()
    db.refresh(job)

    return {
        "job_id": job.id,
        "id": job.id,
        "status": job.status,
        "matched_patient_id": job.patient_id,
        "extracted_data": extracted_dict
    }

@router.post("/{job_id}/verify", status_code=status.HTTP_200_OK)
def verify_job(
    job_id: int,
    payload: VerifyPayload,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    job = db.query(models.ReportIngestionJob).filter(models.ReportIngestionJob.id == job_id).first()
    if not job or job.centre_id != current_user.centre_id:
        raise HTTPException(status_code=404, detail="Ingestion job not found")

    # Reject invalid state transitions (must be extracted first)
    if job.status not in ["EXTRACTED", "NEEDS_VERIFICATION"]:
        raise HTTPException(status_code=400, detail="Job is not in an extractable/verifiable state")

    patient = None
    if payload.patient_id:
        patient = db.query(models.Patient).filter(
            models.Patient.id == payload.patient_id,
            models.Patient.centre_id == current_user.centre_id
        ).first()
    elif payload.patient_code:
        patient = db.query(models.Patient).filter(
            models.Patient.patient_code == payload.patient_code,
            models.Patient.centre_id == current_user.centre_id
        ).first()

    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found or belongs to another centre")

    verified_data = {
        "patient_id": patient.id,
        "patient_name": patient.name if hasattr(patient, "name") else getattr(patient, "full_name", ""),
        "patient_code": patient.patient_code,
        "panels": payload.panels
    }

    job.patient_id = patient.id
    job.verified_data = json.dumps(verified_data, default=str)
    job.technician_id = current_user.id
    job.verified_at = datetime.utcnow()
    job.status = "VERIFIED"

    db.commit()
    db.refresh(job)

    return {
        "job_id": job.id,
        "id": job.id,
        "status": job.status,
        "verified_data": verified_data
    }

@router.post("/{job_id}/finalize", status_code=status.HTTP_200_OK)
def finalize_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    job = db.query(models.ReportIngestionJob).filter(models.ReportIngestionJob.id == job_id).first()
    if not job or job.centre_id != current_user.centre_id:
        raise HTTPException(status_code=404, detail="Ingestion job not found")

    if job.status == "FINALIZED" and job.final_report_id:
        doc = db.query(models.ReportDocument).filter(models.ReportDocument.id == job.final_report_id).first()
        if doc:
            return {
                "job_id": job.id,
                "id": job.id,
                "status": job.status,
                "report_id": doc.id,
                "file_path": doc.file_path
            }

    if job.status != "VERIFIED" or not job.verified_data:
        raise HTTPException(status_code=400, detail="Cannot finalize unverified job")

    patient = db.query(models.Patient).filter(models.Patient.id == job.patient_id).first()
    centre = db.query(models.Centre).filter(models.Centre.id == job.centre_id).first()
    if not patient or not centre:
        raise HTTPException(status_code=400, detail="Missing centre or patient reference")

    verified_payload = json.loads(job.verified_data) if isinstance(job.verified_data, str) else job.verified_data

    patient_name = patient.name if hasattr(patient, "name") else getattr(patient, "full_name", "")
    compiled = compile_and_save_report(
        centre_id=centre.id,
        centre_name=centre.name,
        patient_name=patient_name,
        patient_code=patient.patient_code,
        verified_data=verified_payload
    )

    doc = models.ReportDocument(
        centre_id=centre.id,
        patient_code=patient.patient_code,
        patient_id=patient.id,
        uploaded_by=current_user.id,
        original_filename=compiled["filename"],
        stored_filename=compiled["filename"],
        file_path=compiled["file_path"],
        file_size=compiled["file_size"],
        file_hash=compiled["file_hash"],
        file_checksum=compiled["file_hash"],
        identification_method="INGESTION_OCR",
        storage_status="stored"
    )
    db.add(doc)
    db.flush()

    job.final_report_id = doc.id
    job.status = "FINALIZED"
    db.commit()
    db.refresh(job)

    return {
        "job_id": job.id,
        "id": job.id,
        "status": job.status,
        "report_id": doc.id,
        "file_path": doc.file_path
    }
