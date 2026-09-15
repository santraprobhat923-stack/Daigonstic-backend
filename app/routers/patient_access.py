import os
import time
from collections import defaultdict
from typing import Dict, List
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.patient_access_service import PatientAccessService

router = APIRouter(prefix="/patient-access", tags=["patient-access"])

_FAILED_ATTEMPTS: Dict[str, List[float]] = defaultdict(list)
_MAX_FAILS_PER_WINDOW = 20
_WINDOW_SECONDS = 60.0


def check_rate_limit(client_ip: str):
    now = time.time()
    attempts = _FAILED_ATTEMPTS[client_ip]
    _FAILED_ATTEMPTS[client_ip] = [t for t in attempts if now - t < _WINDOW_SECONDS]
    if len(_FAILED_ATTEMPTS[client_ip]) >= _MAX_FAILS_PER_WINDOW:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed access attempts. Please try again later.",
        )


def record_failed_rate_limit(client_ip: str):
    _FAILED_ATTEMPTS[client_ip].append(time.time())


@router.get("/download/{token}")
def download_patient_report(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    client_ip = request.client.host if request.client else "unknown"
    check_rate_limit(client_ip)

    valid, reason, report, token_record = PatientAccessService.validate_token_and_authorize(
        db=db, raw_token=token
    )

    if not valid:
        record_failed_rate_limit(client_ip)
        cid = token_record.centre_id if token_record else 1
        rid = token_record.report_id if token_record else 0
        PatientAccessService.record_access_failure(
            db=db, raw_token=token, reason=reason, centre_id=cid, report_id=rid
        )

        if reason in ("INVALID_TOKEN", "TOKEN_REVOKED", "TOKEN_EXPIRED"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access link is invalid or has expired.",
            )
        elif reason in ("REPORT_NOT_RELEASED", "PAYMENT_PENDING"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Report is not currently released for download.",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Requested document could not be retrieved.",
            )

    if not report.file_path:
        PatientAccessService.record_access_failure(
            db=db,
            raw_token=token,
            reason="PDF_PATH_NOT_RECORDED",
            centre_id=token_record.centre_id,
            report_id=report.id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Authoritative PDF file not found.",
        )

    real_path = os.path.realpath(report.file_path)
    if not os.path.exists(real_path) or not os.path.isfile(real_path):
        PatientAccessService.record_access_failure(
            db=db,
            raw_token=token,
            reason="PDF_FILE_MISSING_ON_DISK",
            centre_id=token_record.centre_id,
            report_id=report.id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Authoritative PDF file not found on disk.",
        )

    PatientAccessService.record_access_success(db=db, token_record=token_record, report=report)

    return FileResponse(
        path=real_path,
        media_type="application/pdf",
        filename=f"Report_{report.id}.pdf",
    )
