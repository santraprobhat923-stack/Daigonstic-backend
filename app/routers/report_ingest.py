from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
import os
import hashlib
import json

from app.database import get_db
from app.models import ReportIngestionJob, Patient
from app.services.extraction.mock_provider import MockExtractionProvider
from app.services.patient_matching.service import resolve_or_provision_patient


router = APIRouter(
    prefix="/reports/ingest",
    tags=["Report Ingestion"],
)

STORAGE_DIR = "storage/source_images"


@router.post("/photo", status_code=status.HTTP_201_CREATED)
def upload_photo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    # STAGING ONLY:
    # Authentication/tenant context will replace these hardcoded values
    # in the security phase.
    centre_id = 9901
    technician_id = 1

    os.makedirs(
        f"{STORAGE_DIR}/{centre_id}",
        exist_ok=True,
    )

    contents = file.file.read()

    if not contents:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty",
        )

    file_size = len(contents)
    file_hash = hashlib.sha256(contents).hexdigest()

    original_filename = file.filename or "uploaded_image"

    filename = f"{file_hash[:16]}_{original_filename}"
    save_path = f"{STORAGE_DIR}/{centre_id}/{filename}"

    with open(save_path, "wb") as f:
        f.write(contents)

    job = ReportIngestionJob(
        centre_id=centre_id,
        technician_id=technician_id,
        original_filename=original_filename,
        mime_type=file.content_type or "application/octet-stream",
        file_size=file_size,
        source_image_path=save_path,
        source_image_hash=file_hash,
        status="PHOTO_UPLOADED",
        created_at=datetime.utcnow(),
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    return {
        "job_id": job.id,
        "id": job.id,
        "status": job.status,
        "original_filename": job.original_filename,
        "filename": job.original_filename,
        "file_size": job.file_size,
        "file_hash": job.source_image_hash,
    }


@router.post("/{job_id}/extract")
def extract_report(
    job_id: int,
    db: Session = Depends(get_db),
):
    # STAGING ONLY:
    # Authentication/tenant context will replace this hardcoded value.
    centre_id = 9901

    job = (
        db.query(ReportIngestionJob)
        .filter(
            ReportIngestionJob.id == job_id,
            ReportIngestionJob.centre_id == centre_id,
        )
        .first()
    )

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Ingestion job not found or unauthorized",
        )

    if not job.source_image_path:
        raise HTTPException(
            status_code=400,
            detail="Ingestion job has no source image",
        )

    if not os.path.exists(job.source_image_path):
        raise HTTPException(
            status_code=404,
            detail="Source image file not found",
        )

    if job.status == "VERIFIED":
        raise HTTPException(
            status_code=400,
            detail="Cannot extract an already verified ingestion job",
        )

    # --------------------------------------------------------
    # 1. Execute extraction against THIS job's source image.
    # --------------------------------------------------------
    extractor = MockExtractionProvider()

    extraction_result = extractor.extract(
        job.source_image_path
    )

    if not isinstance(extraction_result, dict):
        raise HTTPException(
            status_code=500,
            detail="Extraction provider returned invalid data",
        )

    # --------------------------------------------------------
    # 2. Resolve or provision the patient.
    # --------------------------------------------------------
    patient_payload = extraction_result.get("patient", {})

    patient = resolve_or_provision_patient(
        db=db,
        centre_id=centre_id,
        extracted_patient_data=patient_payload,
        ingestion_job_id=job.id,
    )

    # --------------------------------------------------------
    # 3. Persist extraction + patient linkage together.
    #
    # extracted_data is TEXT in the current SQLite schema,
    # therefore serialize the provider result explicitly.
    # --------------------------------------------------------
    job.extracted_data = json.dumps(
        extraction_result,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    job.patient_id = patient.id
    job.status = "NEEDS_VERIFICATION"

    db.commit()
    db.refresh(job)

    return {
        "job_id": job.id,
        "id": job.id,
        "status": job.status,
        "matched_patient_id": patient.id,
        "patient_status": patient.status,
        "extracted_data": extraction_result,
    }


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_200_OK,
)
def delete_ingestion_job(
    job_id: int,
    db: Session = Depends(get_db),
):
    # STAGING ONLY:
    # Authentication/tenant context will replace this hardcoded value.
    centre_id = 9901

    job = (
        db.query(ReportIngestionJob)
        .filter(
            ReportIngestionJob.id == job_id,
            ReportIngestionJob.centre_id == centre_id,
        )
        .first()
    )

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job not found or unauthorized",
        )

    if job.status not in [
        "PHOTO_UPLOADED",
        "NEEDS_VERIFICATION",
    ]:
        raise HTTPException(
            status_code=400,
            detail=(
                "Cannot delete job after authoritative "
                "verification boundary"
            ),
        )

    # Clean up physical source image.
    if (
        job.source_image_path
        and os.path.exists(job.source_image_path)
    ):
        try:
            os.remove(job.source_image_path)
        except Exception:
            pass

    # Clean up provisional patient created solely for this job.
    provisional_patient = (
        db.query(Patient)
        .filter(
            Patient.created_from_ingestion_job_id == job.id,
            Patient.status == "PROVISIONAL",
        )
        .first()
    )

    if provisional_patient:
        db.delete(provisional_patient)

    db.delete(job)
    db.commit()

    return {
        "message": (
            f"Ingestion job {job_id} and provisional "
            "artifacts successfully deleted."
        )
    }
