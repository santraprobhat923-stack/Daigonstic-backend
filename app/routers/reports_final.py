import os
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, oauth2
from app.services.release_service import ReleaseService

router = APIRouter(prefix="/reports", tags=["Reports Release & Generation"])

@router.get("/final/{report_id}/status")
def get_report_release_status(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    if getattr(current_user, "role", None) not in ["technician", "centre_admin", "admin", "receptionist"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    eligible, reason, report = ReleaseService.evaluate_release_eligibility(
        db, report_id, current_user.centre_id
    )

    return {
        "report_id": report.id,
        "is_released": report.is_released,
        "release_status": report.release_status,
        "released_at": report.released_at,
        "released_by": report.released_by,
        "is_eligible_for_release": eligible,
        "eligibility_reason": reason
    }

@router.post("/final/{report_id}/release")
def release_final_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    if getattr(current_user, "role", None) not in ["technician", "centre_admin", "admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    released_report = ReleaseService.release_report(
        db,
        report_id=report_id,
        centre_id=current_user.centre_id,
        released_by_user_id=current_user.id
    )

    return {
        "message": "Report released successfully",
        "report_id": released_report.id,
        "is_released": released_report.is_released,
        "release_status": released_report.release_status,
        "released_at": released_report.released_at,
        "released_by": released_report.released_by
    }

@router.get("/final/{report_id}/download")
def download_final_report_pdf(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    if getattr(current_user, "role", None) not in ["technician", "centre_admin", "admin", "receptionist"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    report = db.query(models.ReportDocument).filter(
        models.ReportDocument.id == report_id,
        models.ReportDocument.centre_id == current_user.centre_id
    ).first()

    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report document not found")

    if not report.is_released:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Report is not released. Payment pending or release sign-off required."
        )

    if not os.path.exists(report.file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Physical report file not found")

    return FileResponse(
        report.file_path,
        media_type="application/pdf",
        filename=f"report_{report.id}.pdf"
    )
