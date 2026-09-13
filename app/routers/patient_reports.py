import os
import re
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.routers.patient_auth import get_current_patient_session

router = APIRouter(prefix="/patient/reports", tags=["Patient Reports"])

BASE_STORAGE_PATH = Path("/storage/emulated/0/diagnostic_backend/storage/reports").resolve()

# Redacted Output Schema
class PatientReportItemSchema(BaseModel):
    id: int
    filename: str
    file_size: Optional[int] = None
    created_at: Optional[str] = None
    status: Optional[str] = "STORED"

def sanitize_content_disposition(filename: str) -> str:
    cleaned = re.sub(r'[\r\n\x00-\x1f\x7f]', '', filename)
    cleaned = cleaned.replace('"', '').strip()
    return cleaned or "report.pdf"

@router.get("", response_model=List[PatientReportItemSchema])
def list_patient_reports(
    session: models.PatientSession = Depends(get_current_patient_session),
    db: Session = Depends(get_db)
):
    # Strictly scoped by authenticated patient session
    reports = (
        db.query(models.ReportDocument)
        .filter(
            models.ReportDocument.centre_id == session.centre_id,
            models.ReportDocument.patient_id == session.patient_id
        )
        .order_by(models.ReportDocument.id.desc())
        .all()
    )

    out = []
    for r in reports:
        dt = r.created_at.isoformat() if hasattr(r, "created_at") and r.created_at else None
        fname = getattr(r, "original_filename", None) or getattr(r, "stored_filename", "report.pdf")
        stat = getattr(r, "storage_status", None) or getattr(r, "status", "STORED")
        out.append(
            PatientReportItemSchema(
                id=r.id,
                filename=sanitize_content_disposition(fname),
                file_size=getattr(r, "file_size", None),
                created_at=dt,
                status=stat
            )
        )
    return out

@router.get("/{report_id}/download")
def download_patient_report(
    report_id: int,
    inline: bool = Query(False),
    session: models.PatientSession = Depends(get_current_patient_session),
    db: Session = Depends(get_db)
):
    # Triple-bound authorization check: ID + Centre + Patient
    report = (
        db.query(models.ReportDocument)
        .filter(
            models.ReportDocument.id == report_id,
            models.ReportDocument.centre_id == session.centre_id,
            models.ReportDocument.patient_id == session.patient_id
        )
        .first()
    )

    # 404 Returned on tenant or patient mismatch (zero enumeration)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report document not found"
        )

    # Check storage status if attribute exists
    stat = getattr(report, "storage_status", None) or getattr(report, "status", None)
    if stat and stat.upper() not in ["STORED", "ACTIVE", "COMPLETED", "READY"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report document not found"
        )

    target_path = Path(report.file_path).resolve()
    tenant_root = (BASE_STORAGE_PATH / str(session.centre_id)).resolve()

    # Boundary check: enforce confinement in tenant folder
    try:
        target_path.relative_to(tenant_root)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report document not found"
        )

    if not target_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report document not found on storage"
        )

    safe_name = sanitize_content_disposition(
        getattr(report, "original_filename", None) or getattr(report, "stored_filename", "report.pdf")
    )
    disposition_type = "inline" if inline else "attachment"

    return FileResponse(
        path=str(target_path),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition_type}; filename="{safe_name}"'
        }
    )
