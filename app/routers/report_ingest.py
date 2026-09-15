from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
import os
import hashlib
from app.database import get_db
from app.models import ReportIngestionJob, Patient
from app.services.extraction.mock_provider import MockExtractionProvider
from app.services.patient_matching.service import resolve_or_provision_patient

router = APIRouter(prefix="/reports/ingest", tags=["Report Ingestion"])
STORAGE_DIR = "storage/source_images"

@router.post("/photo", status_code=status.HTTP_201_CREATED)
def upload_photo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    centre_id = 9901 # Authenticated tenant context
    technician_id = 1

    os.makedirs(f"{STORAGE_DIR}/{centre_id}", exist_ok=True)
    
    contents = file.file.read()
    file_size = len(contents)
    file_hash = hashlib.sha256(contents).hexdigest()
    
    filename = f"{file_hash[:16]}_{file.filename}"
    save_path = f"{STORAGE_DIR}/{centre_id}/{filename}"
    
    with open(save_path, "wb") as f:
        f.write(contents)
        
    job = ReportIngestionJob(
        centre_id=centre_id,
        technician_id=technician_id,
        original_filename=file.filename,
        mime_type=file.content_type or "image/png",
        file_size=file_size,
        source_image_path=save_path,
        source_image_hash=file_hash,
        status="PHOTO_UPLOADED",
        created_at=datetime.utcnow()
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
        "file_hash": job.source_image_hash
    }

@router.post("/{job_id}/extract")
def extract_report(
    job_id: int,
    db: Session = Depends(get_db)
):
    centre_id = 9901
    job = db.query(ReportIngestionJob).filter(
        ReportIngestionJob.id == job_id,
        ReportIngestionJob.centre_id == centre_id
    ).first()
    
    if not job:
        raise HTTPException(status_code=404, detail="Ingestion job not found or unauthorized")
        
    # Execute extraction provider (Staging Mock)
    extractor = MockExtractionProvider()
    extraction_result = extractor.extract(job.source_image_path)
    
    job.status = "NEEDS_VERIFICATION"
    db.commit()
    
    # Automatically provision provisional patient
    patient_payload = extraction_result.get("patient", {})
    patient = resolve_or_provision_patient(
        db=db,
        centre_id=centre_id,
        extracted_patient_data=patient_payload,
        ingestion_job_id=job.id
    )
    
    return {
        "job_id": job.id,
        "id": job.id,
        "status": job.status,
        "matched_patient_id": patient.id,
        "patient_status": patient.status,
        "extracted_data": extraction_result
    }

@router.delete("/{job_id}", status_code=status.HTTP_200_OK)
def delete_ingestion_job(
    job_id: int,
    db: Session = Depends(get_db)
):
    centre_id = 9901
    job = db.query(ReportIngestionJob).filter(
        ReportIngestionJob.id == job_id,
        ReportIngestionJob.centre_id == centre_id
    ).first()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or unauthorized")
        
    if job.status not in ["PHOTO_UPLOADED", "NEEDS_VERIFICATION"]:
        raise HTTPException(status_code=400, detail="Cannot delete job after authoritative verification boundary")
        
    # Clean up physical file
    if job.source_image_path and os.path.exists(job.source_image_path):
        try:
            os.remove(job.source_image_path)
        except Exception:
            pass
            
    # Clean up orphan provisional patient if created solely for this job
    provisional_patient = db.query(Patient).filter(
        Patient.created_from_ingestion_job_id == job.id,
        Patient.status == "PROVISIONAL"
    ).first()
    
    if provisional_patient:
        db.delete(provisional_patient)
        
    db.delete(job)
    db.commit()
    return {"message": f"Ingestion job {job_id} and provisional artifacts successfully deleted."}
