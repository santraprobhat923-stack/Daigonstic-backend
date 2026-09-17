import hashlib
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import models
from app.database import get_db

router = APIRouter(prefix="/public", tags=["Public Report Links"])


@router.get("/reports/{token}")
def public_report_download(token: str, db: Session = Depends(get_db)):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    access = db.query(models.PatientReportAccessToken).filter(
        models.PatientReportAccessToken.token_hash == token_hash,
        models.PatientReportAccessToken.status == "ACTIVE"
    ).first()
    if not access or (access.expires_at and access.expires_at < datetime.utcnow()):
        raise HTTPException(status_code=404, detail="Report link is invalid or expired")
    report = db.query(models.ReportDocument).filter(
        models.ReportDocument.id == access.report_id,
        models.ReportDocument.centre_id == access.centre_id,
        models.ReportDocument.patient_id == access.patient_id,
        models.ReportDocument.is_released == True,
    ).first()
    if not report or not report.file_path or not os.path.isfile(report.file_path):
        raise HTTPException(status_code=404, detail="Report is not available")
    access.used_at = datetime.utcnow()
    db.commit()
    return FileResponse(report.file_path, media_type="application/pdf", filename=report.pdf_filename or f"report_{report.id}.pdf")
