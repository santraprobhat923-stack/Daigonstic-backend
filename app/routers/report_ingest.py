from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
import os
import hashlib
import json

from app.database import get_db
from app.models import ReportIngestionJob, Patient
from app.oauth2 import require_technician
from app import schemas
from app.services.extraction import get_extraction_provider
from app.services.extraction.base import ExtractionProcessingError
from app.services.patient_matching.service import resolve_or_provision_patient

router = APIRouter(prefix="/reports/ingest", tags=["Report Ingestion"])
STORAGE_DIR = "storage/source_images"

@router.post("/photo", status_code=status.HTTP_201_CREATED)
def upload_photo(file: UploadFile = File(...), db: Session = Depends(get_db), current_user=Depends(require_technician)):
    centre_id = current_user.centre_id
    technician_id = current_user.id
    allowed_mime_types = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed_mime_types:
        raise HTTPException(status_code=415, detail="Only JPEG, PNG, and WebP report images are supported")
    contents = file.file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    max_size = 15 * 1024 * 1024
    if len(contents) > max_size:
        raise HTTPException(status_code=413, detail="Image is too large. Maximum allowed size is 15 MB")
    file_hash = hashlib.sha256(contents).hexdigest()
    existing_job = db.query(ReportIngestionJob).filter(
        ReportIngestionJob.centre_id == centre_id,
        ReportIngestionJob.source_image_hash == file_hash,
    ).order_by(ReportIngestionJob.id.desc()).first()
    if existing_job:
        return {"job_id": existing_job.id, "id": existing_job.id, "status": existing_job.status,
                "original_filename": existing_job.original_filename, "filename": existing_job.original_filename,
                "file_size": existing_job.file_size, "file_hash": existing_job.source_image_hash,
                "duplicate": True, "message": "This image has already been uploaded for this centre"}
    original_filename = os.path.basename(file.filename or "uploaded_image")
    filename = f"{file_hash[:16]}_{original_filename}"
    centre_dir = os.path.join(STORAGE_DIR, str(centre_id))
    os.makedirs(centre_dir, exist_ok=True)
    save_path = os.path.join(centre_dir, filename)
    with open(save_path, "wb") as f:
        f.write(contents)
    try:
        job = ReportIngestionJob(centre_id=centre_id, technician_id=technician_id,
            original_filename=original_filename, mime_type=file.content_type, file_size=len(contents),
            source_image_path=save_path, source_image_hash=file_hash, status="PHOTO_UPLOADED", created_at=datetime.utcnow())
        db.add(job); db.commit(); db.refresh(job)
    except Exception:
        db.rollback()
        if os.path.exists(save_path):
            try: os.remove(save_path)
            except OSError: pass
        raise
    return {"job_id": job.id, "id": job.id, "status": job.status, "original_filename": job.original_filename,
            "filename": job.original_filename, "file_size": job.file_size, "file_hash": job.source_image_hash, "duplicate": False}

@router.get("/{job_id}")
def get_ingestion_job(job_id: int, db: Session = Depends(get_db), current_user=Depends(require_technician)):
    job = db.query(ReportIngestionJob).filter(ReportIngestionJob.id == job_id,
        ReportIngestionJob.centre_id == current_user.centre_id).first()
    if not job: raise HTTPException(status_code=404, detail="Ingestion job not found")
    def parse_json(value):
        if value is None: return None
        try: return json.loads(value)
        except (TypeError, json.JSONDecodeError): return value
    return {"job_id": job.id, "id": job.id, "status": job.status, "centre_id": job.centre_id,
            "technician_id": job.technician_id, "patient_id": job.patient_id,
            "original_filename": job.original_filename, "mime_type": job.mime_type, "file_size": job.file_size,
            "file_hash": job.source_image_hash, "extracted_data": parse_json(job.extracted_data),
            "verified_data": parse_json(job.verified_data), "verified_at": job.verified_at,
            "verified_by": job.verified_by, "final_report_id": job.final_report_id, "last_error": parse_json(job.last_error)}

@router.post("/{job_id}/extract")
def extract_report(job_id: int, db: Session = Depends(get_db), current_user=Depends(require_technician)):
    centre_id = current_user.centre_id
    job = db.query(ReportIngestionJob).filter(ReportIngestionJob.id == job_id,
        ReportIngestionJob.centre_id == centre_id).first()
    if not job: raise HTTPException(status_code=404, detail="Ingestion job not found or unauthorized")
    if not job.source_image_path: raise HTTPException(status_code=400, detail="Ingestion job has no source image")
    if not os.path.exists(job.source_image_path): raise HTTPException(status_code=404, detail="Source image file not found")
    if job.status == "VERIFIED": raise HTTPException(status_code=400, detail="Cannot extract an already verified ingestion job")
    extractor = get_extraction_provider()
    try:
        extraction_result = extractor.extract(image_path=job.source_image_path, context={"centre_id": centre_id, "job_id": job.id})
    except ExtractionProcessingError as exc:
        job.status = "EXTRACTION_FAILED"
        job.last_error = json.dumps({"code": exc.code, "message": exc.message}, ensure_ascii=False)
        job.attempt_count = (job.attempt_count or 0) + 1; db.commit()
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    if extraction_result is None: raise HTTPException(status_code=500, detail="Extraction provider returned no result")
    patient_payload = extraction_result.patient.model_dump()
    patient = resolve_or_provision_patient(db=db, centre_id=centre_id,
        extracted_patient_data=patient_payload, ingestion_job_id=job.id)
    job.extracted_data = json.dumps(extraction_result.model_dump(), ensure_ascii=False, separators=(",", ":"))
    job.patient_id = patient.id; job.status = "NEEDS_VERIFICATION"
    db.commit(); db.refresh(job)
    return {"job_id": job.id, "id": job.id, "status": job.status, "matched_patient_id": patient.id,
            "patient_status": patient.status, "extracted_data": extraction_result.model_dump()}

@router.post("/{job_id}/verify")
def verify_ingestion_job(job_id: int, payload: schemas.VerificationPayload,
    db: Session = Depends(get_db), current_user=Depends(require_technician)):
    """Store an authoritative technician snapshot after editable patient and result review."""
    job = db.query(ReportIngestionJob).filter(ReportIngestionJob.id == job_id,
        ReportIngestionJob.centre_id == current_user.centre_id).first()
    if not job: raise HTTPException(status_code=404, detail="Ingestion job not found")
    if job.status != "NEEDS_VERIFICATION":
        raise HTTPException(status_code=400, detail=f"Job must be in NEEDS_VERIFICATION state; current state is {job.status}")
    patient = db.query(Patient).filter(Patient.id == payload.patient_id,
        Patient.centre_id == current_user.centre_id).first()
    if not patient: raise HTTPException(status_code=404, detail="Patient not found for this centre")
    if job.verified_data is not None or job.verified_at is not None or job.verified_by is not None:
        raise HTTPException(status_code=409, detail="Verification has already been recorded")

    # Patient demographics are editable during verification. The original OCR
    # snapshot remains untouched; only the authoritative patient record changes.
    patient_changes = {
        "name": payload.patient_name,
        "age": payload.patient_age,
        "gender": payload.patient_gender,
        "phone": payload.patient_phone,
        "email": str(payload.patient_email) if payload.patient_email is not None else None,
    }
    for field, value in patient_changes.items():
        if value is not None:
            setattr(patient, field, value)
    if payload.patient_code:
        duplicate = db.query(Patient).filter(Patient.centre_id == current_user.centre_id,
            Patient.patient_code == payload.patient_code, Patient.id != patient.id).first()
        if duplicate: raise HTTPException(status_code=409, detail="Patient code already exists in this centre")
        patient.patient_code = payload.patient_code

    verified_payload = payload.model_dump()
    job.verified_data = json.dumps(verified_payload, ensure_ascii=False, separators=(",", ":"))
    job.patient_id = patient.id; job.verified_at = datetime.utcnow(); job.verified_by = current_user.id; job.status = "VERIFIED"
    db.commit(); db.refresh(job)
    return {"job_id": job.id, "id": job.id, "status": job.status, "patient_id": job.patient_id,
            "verified_by": job.verified_by, "verified_at": job.verified_at, "verified_data": verified_payload}

@router.delete("/{job_id}", status_code=status.HTTP_200_OK)
def delete_ingestion_job(job_id: int, db: Session = Depends(get_db), current_user=Depends(require_technician)):
    job = db.query(ReportIngestionJob).filter(ReportIngestionJob.id == job_id,
        ReportIngestionJob.centre_id == current_user.centre_id).first()
    if not job: raise HTTPException(status_code=404, detail="Job not found or unauthorized")
    if job.status not in ["PHOTO_UPLOADED", "NEEDS_VERIFICATION"]:
        raise HTTPException(status_code=400, detail="Cannot delete job after authoritative verification boundary")
    if job.source_image_path and os.path.exists(job.source_image_path):
        try: os.remove(job.source_image_path)
        except OSError: pass
    provisional_patient = db.query(Patient).filter(Patient.created_from_ingestion_job_id == job.id,
        Patient.status == "PROVISIONAL").first()
    if provisional_patient: db.delete(provisional_patient)
    db.delete(job); db.commit()
    return {"message": f"Ingestion job {job_id} and provisional artifacts successfully deleted."}
