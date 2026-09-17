from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
import os
import hashlib
import json

from app.database import get_db
from app.models import ReportIngestionJob, Patient, Centre, ReportDocument, ReportStorageStatusEnum
from app.oauth2 import require_technician
from app import schemas
from app.services.extraction import get_extraction_provider
from app.services.extraction.base import ExtractionProcessingError, ExtractionResult, ExtractedPatient
from app.services.patient_matching.service import resolve_or_provision_patient
from app.services.pdf_compiler import compile_and_save_report

router = APIRouter(prefix="/reports/ingest", tags=["Report Ingestion"])
STORAGE_DIR = "storage/source_images"


def _empty_extraction(provider_name="tesseract", provider_version="fault-tolerant"):
    return ExtractionResult(
        patient=ExtractedPatient(),
        panels=[],
        provider_name=provider_name,
        provider_version=provider_version,
        raw_text_summary="OCR returned no structured fields. Technician verification can be completed manually.",
    )


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


@router.get("/queue")
def get_verification_queue(db: Session = Depends(get_db), current_user=Depends(require_technician)):
    jobs = db.query(ReportIngestionJob).filter(
        ReportIngestionJob.centre_id == current_user.centre_id,
        ReportIngestionJob.status == "NEEDS_VERIFICATION",
    ).order_by(ReportIngestionJob.id.desc()).all()

    def parse_json(value):
        if value is None:
            return None
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return value

    return [{"job_id": job.id, "id": job.id, "status": job.status,
             "centre_id": job.centre_id, "technician_id": job.technician_id,
             "patient_id": job.patient_id, "original_filename": job.original_filename,
             "mime_type": job.mime_type, "file_size": job.file_size,
             "file_hash": job.source_image_hash,
             "extracted_data": parse_json(job.extracted_data),
             "verified_data": parse_json(job.verified_data),
             "verified_at": job.verified_at, "verified_by": job.verified_by,
             "final_report_id": job.final_report_id,
             "last_error": parse_json(job.last_error)} for job in jobs]


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
    ocr_warning = None
    try:
        extraction_result = extractor.extract(image_path=job.source_image_path, context={"centre_id": centre_id, "job_id": job.id})
    except ExtractionProcessingError as exc:
        # OCR is assistive, never a hard workflow boundary. Keep the job open for
        # technician entry even when Tesseract cannot produce structured output.
        extraction_result = _empty_extraction(getattr(extractor, "provider_name", "tesseract"), getattr(extractor, "provider_version", "fault-tolerant"))
        ocr_warning = {"code": exc.code, "message": exc.message}
        job.attempt_count = (job.attempt_count or 0) + 1
        job.last_error = json.dumps(ocr_warning, ensure_ascii=False)

    if extraction_result is None:
        extraction_result = _empty_extraction()
        ocr_warning = {"code": "EMPTY_RESULT", "message": "OCR returned no structured result"}

    patient_payload = extraction_result.patient.model_dump()
    patient = resolve_or_provision_patient(db=db, centre_id=centre_id,
        extracted_patient_data=patient_payload, ingestion_job_id=job.id)
    job.extracted_data = json.dumps(extraction_result.model_dump(), ensure_ascii=False, separators=(",", ":"))
    job.patient_id = patient.id
    job.status = "NEEDS_VERIFICATION"
    # A warning is informational; it must not prevent verification.
    if ocr_warning:
        job.last_error = json.dumps(ocr_warning, ensure_ascii=False)
    else:
        job.last_error = None
    db.commit(); db.refresh(job)
    return {"job_id": job.id, "id": job.id, "status": job.status, "matched_patient_id": patient.id,
            "patient_status": patient.status, "extracted_data": extraction_result.model_dump(), "ocr_warning": ocr_warning}


@router.post("/{job_id}/verify")
def verify_ingestion_job(job_id: int, payload: schemas.VerificationPayload,
    db: Session = Depends(get_db), current_user=Depends(require_technician)):
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

    patient_changes = {
        "name": payload.patient_name,
        "age": payload.patient_age,
        "gender": payload.patient_gender,
        "phone": payload.patient_phone,
        "email": payload.patient_email,
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


@router.post("/{job_id}/finalize")
def finalize_verified_report(job_id: int, db: Session = Depends(get_db), current_user=Depends(require_technician)):
    """Generate the paid-by-credit PDF. Patient payment/WhatsApp happens only afterwards."""
    job = db.query(ReportIngestionJob).filter(
        ReportIngestionJob.id == job_id,
        ReportIngestionJob.centre_id == current_user.centre_id,
    ).first()
    if not job: raise HTTPException(status_code=404, detail="Ingestion job not found")

    if job.final_report_id:
        existing = db.query(ReportDocument).filter(
            ReportDocument.id == job.final_report_id,
            ReportDocument.centre_id == current_user.centre_id,
        ).first()
        if existing:
            return {"job_id": job.id, "report_id": existing.id, "status": job.status,
                    "release_status": existing.release_status, "file_path": existing.pdf_path or existing.file_path,
                    "filename": existing.pdf_filename or existing.original_filename,
                    "file_size": existing.pdf_size or existing.file_size,
                    "file_hash": existing.pdf_hash or existing.file_hash, "idempotent": True}

    if job.status != "VERIFIED":
        raise HTTPException(status_code=400, detail=f"Job must be VERIFIED before PDF generation; current state is {job.status}")
    if not job.verified_data: raise HTTPException(status_code=400, detail="Verified data is missing; PDF cannot be generated")
    if not job.patient_id: raise HTTPException(status_code=400, detail="Patient linkage is missing; PDF cannot be generated")

    patient = db.query(Patient).filter(Patient.id == job.patient_id, Patient.centre_id == current_user.centre_id).first()
    if not patient: raise HTTPException(status_code=404, detail="Verified patient not found")
    centre = db.query(Centre).filter(Centre.id == current_user.centre_id).first()
    if not centre: raise HTTPException(status_code=404, detail="Diagnostic centre not found")

    from app.services import credit_service
    # One report = one credit. Credit is consumed only when the authoritative PDF is generated.
    credit_service.deduct_credit_locked(
        db=db, centre_id=current_user.centre_id, amount=1, user_id=current_user.id,
        reference_type="report_pdf", reference_id=job.id,
        description="One credit consumed for authoritative PDF generation"
    )
    try:
        verified_data = json.loads(job.verified_data)
        compiled = compile_and_save_report(
            centre_id=current_user.centre_id,
            centre_name=centre.name,
            patient_name=patient.name or f"Patient {patient.patient_code}",
            patient_code=patient.patient_code,
            verified_data=verified_data,
        )
        report = ReportDocument(
            centre_id=current_user.centre_id, patient_code=patient.patient_code, patient_id=patient.id,
            uploaded_by=current_user.id, file_path=compiled["file_path"], original_filename=compiled["filename"],
            stored_filename=compiled["filename"], file_size=compiled["file_size"], file_hash=compiled["file_hash"],
            file_checksum=compiled["file_hash"], identification_method="technician_verified_ingestion",
            storage_status=ReportStorageStatusEnum.stored, created_at=datetime.utcnow(),
            release_status="HELD_PAYMENT", is_released=False, pdf_path=compiled["file_path"],
            pdf_filename=compiled["filename"], pdf_hash=compiled["file_hash"], pdf_size=compiled["file_size"],
            ingestion_job_id=job.id, verified_at=job.verified_at, verified_by=job.verified_by,
        )
        db.add(report); db.flush(); job.final_report_id = report.id; job.status = "HELD_PAYMENT"; job.completed_at = datetime.utcnow()
        db.commit(); db.refresh(report); db.refresh(job)
        return {"job_id": job.id, "report_id": report.id, "status": job.status,
                "release_status": report.release_status, "file_path": report.pdf_path, "filename": report.pdf_filename,
                "file_size": report.pdf_size, "file_hash": report.pdf_hash, "idempotent": False,
                "credits_consumed": 1}
    except HTTPException:
        db.rollback(); raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}") from exc


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
