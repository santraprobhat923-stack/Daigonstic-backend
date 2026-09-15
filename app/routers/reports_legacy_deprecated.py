from app.oauth2 import get_current_user
import os
import re
import unicodedata
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi import Query

import os
import uuid
import hashlib
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app import models, schemas, oauth2
from app.database import get_db
from app.services import credit_service
from app.services import patient_identifier

router = APIRouter(prefix="/reports", tags=["Reports Management"])

BASE_STORAGE_DIR = os.path.abspath("storage/reports")

def get_tenant_storage_dir(centre_id: int) -> str:
    centre_dir = os.path.abspath(os.path.join(BASE_STORAGE_DIR, str(centre_id)))
    if not centre_dir.startswith(BASE_STORAGE_DIR):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid storage path.")
    os.makedirs(centre_dir, exist_ok=True)
    return centre_dir

def compute_hash_and_buffer(upload_file: UploadFile, temp_dest: str) -> str:
    hasher = hashlib.sha256()
    with open(temp_dest, "wb") as buffer:
        while chunk := upload_file.file.read(65536):
            hasher.update(chunk)
            buffer.write(chunk)
    return hasher.hexdigest()

def get_or_create_patient(
    db: Session,
    centre_id: int,
    identity: patient_identifier.PatientIdentityResult
) -> models.Patient:
    patient = db.query(models.Patient).filter(
        models.Patient.centre_id == centre_id,
        models.Patient.patient_code == identity.patient_code
    ).first()

    if patient:
        return patient

    # Use only valid schema fields
    name = identity.patient_name or f"Patient {identity.patient_code}"
    patient_data = {
        "centre_id": centre_id,
        "patient_code": identity.patient_code,
        "full_name": name,
        "age": 0,
    }
    
    # Check column support safely
    cols = [c.name for c in models.Patient.__table__.columns]
    if "gender" in cols:
        patient_data["gender"] = identity.gender or "Other"
    if "phone" in cols:
        patient_data["phone"] = identity.phone or "0000000000"
    if "dob" in cols:
        patient_data["dob"] = identity.dob
    if "created_at" in cols:
        patient_data["created_at"] = datetime.utcnow()

    new_patient = models.Patient(**patient_data)
    try:
        db.add(new_patient)
        db.commit()
        db.refresh(new_patient)
        return new_patient
    except Exception as e:
        db.rollback()
        existing = db.query(models.Patient).filter(
            models.Patient.centre_id == centre_id,
            models.Patient.patient_code == identity.patient_code
        ).first()
        if existing:
            return existing
        raise e

@router.post("/upload", status_code=status.HTTP_201_CREATED)
def upload_single_report(
    patient_id: Optional[int] = Form(None),
    patient_code: Optional[str] = Form(None),
    order_id: Optional[int] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    centre_id = current_user.centre_id
    # Clean Swagger dummy artifacts
    if patient_code and patient_code.strip().lower() in ['string', '', 'none', 'null']:
        patient_code = None
    if patient_id is not None:
        try:
            if int(patient_id) <= 0:
                patient_id = None
        except Exception:
            patient_id = None
    if order_id is not None:
        try:
            if int(order_id) <= 0:
                order_id = None
        except Exception:
            order_id = None


    # Strip Swagger default values
    if patient_code is not None:
        patient_code = patient_code.strip()
        if patient_code.lower() in ['string', '', 'none', 'null']:
            patient_code = None

    if patient_id is not None:
        try:
            if int(patient_id) <= 0:
                patient_id = None
            else:
                patient_id = int(patient_id)
        except Exception:
            patient_id = None

    if order_id is not None:
        try:
            if int(order_id) <= 0:
                order_id = None
            else:
                order_id = int(order_id)
        except Exception:
            order_id = None

    # Clean Swagger default placeholder values
    if patient_code and patient_code.strip().lower() in ['string', '', 'none', 'null']:
        patient_code = None
    elif patient_code:
        patient_code = patient_code.strip()

    if patient_id is not None and (patient_id <= 0 or str(patient_id).strip() in ['0', '']):
        patient_id = None

    if order_id is not None and (order_id <= 0 or str(order_id).strip() in ['0', '']):
        order_id = None
    if patient_code in ['string', '', None]:
        patient_code = None
    if patient_id == 0:
        patient_id = None
    if order_id == 0:
        order_id = None

    # Defensive filename check
    safe_filename = os.path.basename(file.filename or "report.pdf")
    ext = os.path.splitext(safe_filename)[1].lower()
    if ext not in [".pdf", ".png", ".jpg", ".jpeg"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file extension.")

    centre_dir = get_tenant_storage_dir(centre_id)
    storage_uuid = f"{uuid.uuid4().hex}{ext}"
    physical_target = os.path.join(centre_dir, storage_uuid)
    temp_target = f"{physical_target}.tmp"

    try:
        file_hash = compute_hash_and_buffer(file, temp_target)
        file_size = os.path.getsize(temp_target)

        # Deduplication check (0 credits consumed)
        existing_doc = db.query(models.ReportDocument).filter(
            models.ReportDocument.centre_id == centre_id,
            models.ReportDocument.file_hash == file_hash
        ).first()

        if existing_doc:
            if os.path.exists(temp_target):
                os.remove(temp_target)
            return {
                "filename": safe_filename,
                "status": "duplicate",
                "detail": f"Duplicate report detected (matches report ID {existing_doc.id}). No credit consumed.",
                "report_id": existing_doc.id,
                "patient_id": existing_doc.patient_id
            }

        # Identification resolution
        target_patient = None
        method_used = "manual"

        # Explicit primary key provided (manual admin fallback)
        if patient_id is not None and patient_id > 0:
            target_patient = db.query(models.Patient).filter(
                models.Patient.id == patient_id,
                models.Patient.centre_id == centre_id
            ).first()
            if not target_patient:
                if os.path.exists(temp_target):
                    os.remove(temp_target)
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Patient ID not found in this diagnostic centre."
                )
            method_used = "manual_id"
        else:
            # Automatic identification engine
            identity = patient_identifier.resolve_patient_identity(
                filename=safe_filename,
                temp_file_path=temp_target,
                centre_pattern=None,
                explicit_code=patient_code
            )

            if identity.is_ambiguous or not identity.patient_code:
                if os.path.exists(temp_target):
                    os.remove(temp_target)
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=identity.failure_reason or "AMBIGUOUS_PATIENT_ID"
                )

            target_patient = get_or_create_patient(db, centre_id, identity)
            method_used = identity.method

        if order_id is not None and order_id <= 0:
            order_id = None

        # Atomic commit & credit deduction
        try:
            doc_record = models.ReportDocument(
                centre_id=centre_id,
                patient_id=target_patient.id,
                uploaded_by=current_user.id,
                order_id=order_id,
                file_path=physical_target,
                original_filename=safe_filename,
                stored_filename=storage_uuid,
                file_hash=file_hash,
                file_checksum=file_hash,
                file_size=file_size,
                identification_method=method_used,
                storage_status=models.ReportStorageStatusEnum.pending_storage,
                created_at=datetime.utcnow()
            )
            db.add(doc_record)
            db.flush()

            # Deduct 1 credit
            credit_service.deduct_credit_locked(
                db=db,
                centre_id=centre_id,
                amount=1,
                user_id=current_user.id,
                reference_type="report_upload",
                reference_id=doc_record.id,
                description=f"Report ingest: {safe_filename} ({target_patient.patient_code or target_patient.id})"
            )

            os.replace(temp_target, physical_target)
            doc_record.storage_status = models.ReportStorageStatusEnum.stored

            db.commit()
            db.refresh(doc_record)

            return {
                "filename": safe_filename,
                "status": "success",
                "detail": f"Report uploaded and attached to patient {target_patient.full_name}.",
                "report_id": doc_record.id,
                "patient_id": target_patient.id,
                "patient_code": target_patient.patient_code,
                "identification_method": method_used
            }

        except Exception as tx_err:
            db.rollback()
            if os.path.exists(temp_target):
                os.remove(temp_target)
            if os.path.exists(physical_target):
                os.remove(physical_target)
            if isinstance(tx_err, HTTPException):
                raise tx_err
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Transaction error: {str(tx_err)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        if os.path.exists(temp_target):
            os.remove(temp_target)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Storage error: {str(e)}"
        )

@router.post("/bulk-upload", status_code=status.HTTP_200_OK)
def bulk_upload_reports(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    response_payload = {
        "total": len(files),
        "success": [],
        "duplicates": [],
        "ambiguous": [],
        "failed": []
    }

    for file in files:
        safe_name = os.path.basename(file.filename or "unknown.pdf")
        file.file.seek(0)
        try:
            res = upload_single_report(
                patient_id=None,
                patient_code=None,
                order_id=None,
                file=file,
                db=db,
                current_user=current_user
            )
            if res.get("status") == "duplicate":
                response_payload["duplicates"].append({
                    "filename": safe_name,
                    "report_id": res.get("report_id"),
                    "detail": res.get("detail")
                })
            else:
                response_payload["success"].append({
                    "filename": safe_name,
                    "report_id": res.get("report_id"),
                    "patient_id": res.get("patient_id"),
                    "patient_code": res.get("patient_code"),
                    "identification_method": res.get("identification_method")
                })
        except HTTPException as exc:
            if exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY:
                response_payload["ambiguous"].append({
                    "filename": safe_name,
                    "detail": exc.detail
                })
            else:
                response_payload["failed"].append({
                    "filename": safe_name,
                    "status_code": exc.status_code,
                    "detail": exc.detail
                })
        except Exception as general_exc:
            response_payload["failed"].append({
                "filename": safe_name,
                "detail": str(general_exc)
            })

    return response_payload


# ============================================================================
# PHASE 4A: SECURE REPORT VIEWING & STREAMING INFRASTRUCTURE
# ============================================================================


import os
import re
import unicodedata
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi import Query


import os
import re
import unicodedata
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi import Query


import os
import re
import unicodedata
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi import Query



import os
import re
import unicodedata
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi import Query


# --- PHASE 4A: SECURE VIEWING & STREAMING ---
import os
import re
import unicodedata
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi import Query

def sanitize_content_disposition_filename(filename: str) -> str:
    if not filename:
        return 'report.pdf'
    # Strip carriage returns, newlines, and nulls using character codes
    clean = filename.replace(chr(13), '').replace(chr(10), '').replace(chr(0), '')
    clean = os.path.basename(clean)
    clean = unicodedata.normalize('NFKD', clean).encode('ascii', 'ignore').decode('ascii')
    ascii_clean = re.sub(r'[^a-zA-Z0-9_.-]', '_', clean)
    return ascii_clean or 'report.pdf'

@router.get('/{report_id}')
def get_report_metadata(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    report = db.query(models.ReportDocument).filter(
        models.ReportDocument.id == report_id,
        models.ReportDocument.centre_id == current_user.centre_id
    ).first()

    if not report:
        raise HTTPException(status_code=404, detail='Report not found')

    patient = db.query(models.Patient).filter(
        models.Patient.id == report.patient_id,
        models.Patient.centre_id == current_user.centre_id
    ).first()

    file_size = None
    if report.file_path and os.path.exists(report.file_path):
        try:
            file_size = os.path.getsize(report.file_path)
        except OSError:
            pass

    return {
        'report_id': report.id,
        'centre_id': report.centre_id,
        'patient_id': report.patient_id,
        'patient_code': getattr(patient, 'patient_code', None),
        'patient_name': getattr(patient, 'full_name', None),
        'original_filename': getattr(report, "original_filename", getattr(report, "filename", "report.pdf")),
        'uploaded_at': getattr(report, 'created_at', getattr(report, 'uploaded_at', None)),
        'file_size_bytes': file_size,
        'is_available': os.path.exists(report.file_path) if report.file_path else False
    }

@router.get('/{report_id}/download')
def download_report(
    report_id: int,
    inline: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    report = db.query(models.ReportDocument).filter(
        models.ReportDocument.id == report_id,
        models.ReportDocument.centre_id == current_user.centre_id
    ).first()

    if not report or not report.file_path:
        raise HTTPException(status_code=404, detail='Report not found or access denied')

    tenant_storage_root = Path('/storage/emulated/0/diagnostic_backend/storage/reports/' + str(current_user.centre_id)).resolve()
    target_path = Path(report.file_path).resolve()

    try:
        target_path.relative_to(tenant_storage_root)
    except ValueError:
        raise HTTPException(status_code=403, detail='Storage security violation: File path escapes tenant scope')

    if not target_path.is_file():
        raise HTTPException(status_code=404, detail='Report document file missing on storage')

    ext = target_path.suffix.lower()
    media_map = {
        '.pdf': 'application/pdf',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg'
    }
    media_type = media_map.get(ext, 'application/octet-stream')

    safe_name = sanitize_content_disposition_filename(getattr(report, "original_filename", getattr(report, "filename", "report.pdf")) or target_path.name)
    disp = 'inline' if inline else 'attachment'

    return FileResponse(
        path=str(target_path),
        media_type=media_type,
        headers={
            'Content-Disposition': disp + '; filename="' + safe_name + '"',
            'X-Content-Type-Options': 'nosniff',
            'Cache-Control': 'private, no-cache, no-store, must-revalidate'
        }
    )
