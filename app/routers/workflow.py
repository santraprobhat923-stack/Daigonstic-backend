import hashlib
import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models, oauth2
from app.database import get_db

router = APIRouter(prefix="/workflow", tags=["Centre Workflow"])
TEMPLATE_DIR = Path("storage/templates")
TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)


def ensure_settings_table(db: Session):
    db.execute(text("""CREATE TABLE IF NOT EXISTS centre_workflow_settings (
        centre_id INTEGER PRIMARY KEY,
        whatsapp_enabled INTEGER NOT NULL DEFAULT 0,
        upi_id TEXT,
        public_base_url TEXT,
        updated_at TEXT
    )"""))
    db.commit()


def settings_row(db: Session, centre_id: int):
    ensure_settings_table(db)
    row = db.execute(text("SELECT centre_id, whatsapp_enabled, upi_id, public_base_url, updated_at FROM centre_workflow_settings WHERE centre_id=:cid"), {"cid": centre_id}).mappings().first()
    if row:
        return dict(row)
    db.execute(text("INSERT INTO centre_workflow_settings (centre_id, whatsapp_enabled, updated_at) VALUES (:cid,0,:now)"), {"cid": centre_id, "now": datetime.utcnow().isoformat()})
    db.commit()
    return {"centre_id": centre_id, "whatsapp_enabled": 0, "upi_id": None, "public_base_url": None, "updated_at": datetime.utcnow().isoformat()}


def _require_user(db: Session, current_user):
    if not current_user.centre_id:
        raise HTTPException(status_code=403, detail="Centre account required")
    return settings_row(db, current_user.centre_id)


def template_path(centre_id: int) -> Path:
    return TEMPLATE_DIR / str(centre_id) / "template.pdf"


@router.get("/settings")
def get_workflow_settings(db: Session = Depends(get_db), current_user=Depends(oauth2.get_current_user)):
    row = _require_user(db, current_user)
    return {**row, "template_uploaded": template_path(current_user.centre_id).is_file()}


@router.put("/settings")
def update_workflow_settings(payload: dict, db: Session = Depends(get_db), current_user=Depends(oauth2.require_technician)):
    row = _require_user(db, current_user)
    enabled = bool(payload.get("whatsapp_enabled", bool(row["whatsapp_enabled"])))
    upi_id = (payload.get("upi_id") or row.get("upi_id") or "").strip() or None
    public_base_url = (payload.get("public_base_url") or row.get("public_base_url") or "").strip() or None
    if enabled and not upi_id:
        raise HTTPException(status_code=400, detail="UPI ID is required before WhatsApp payment messaging can be enabled")
    db.execute(text("UPDATE centre_workflow_settings SET whatsapp_enabled=:enabled, upi_id=:upi, public_base_url=:url, updated_at=:now WHERE centre_id=:cid"),
               {"enabled": 1 if enabled else 0, "upi": upi_id, "url": public_base_url, "now": datetime.utcnow().isoformat(), "cid": current_user.centre_id})
    db.commit()
    return {"centre_id": current_user.centre_id, "whatsapp_enabled": enabled, "upi_id": upi_id, "public_base_url": public_base_url,
            "template_uploaded": template_path(current_user.centre_id).is_file()}


@router.post("/template")
def upload_pdf_template(file: UploadFile = File(...), db: Session = Depends(get_db), current_user=Depends(oauth2.require_technician)):
    if file.content_type != "application/pdf" and not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF templates are supported")
    contents = file.file.read()
    if not contents or not contents.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid PDF")
    if len(contents) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Template is too large. Maximum allowed size is 15 MB")
    target_dir = TEMPLATE_DIR / str(current_user.centre_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "template.pdf"
    with open(target, "wb") as handle:
        handle.write(contents)
    return {"centre_id": current_user.centre_id, "template_uploaded": True, "filename": file.filename,
            "size": len(contents), "sha256": hashlib.sha256(contents).hexdigest()}


@router.get("/template")
def download_template(db: Session = Depends(get_db), current_user=Depends(oauth2.get_current_user)):
    path = template_path(current_user.centre_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No centre PDF template has been uploaded")
    return FileResponse(str(path), media_type="application/pdf", filename="centre_template.pdf")


@router.get("/reports/{report_id}/download")
def technician_download_report(report_id: int, db: Session = Depends(get_db), current_user=Depends(oauth2.require_technician)):
    report = db.query(models.ReportDocument).filter(models.ReportDocument.id == report_id,
        models.ReportDocument.centre_id == current_user.centre_id).first()
    if not report or not report.file_path or not os.path.isfile(report.file_path):
        raise HTTPException(status_code=404, detail="Generated report not found")
    return FileResponse(report.file_path, media_type="application/pdf", filename=report.pdf_filename or f"report_{report.id}.pdf")


def _public_report_token(db: Session, report: models.ReportDocument, patient: models.Patient, base_url: str | None):
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    access = models.PatientReportAccessToken(
        centre_id=report.centre_id, patient_id=patient.id, report_id=report.id,
        token_hash=token_hash, expires_at=datetime.utcnow() + timedelta(days=7), status="ACTIVE", created_at=datetime.utcnow()
    )
    db.add(access)
    db.flush()
    path = f"/public/reports/{raw}"
    return f"{base_url.rstrip('/')}{path}" if base_url else path


def prepare_whatsapp_for_report(db: Session, report: models.ReportDocument, current_user, allow_pending: bool = True):
    row = _require_user(db, current_user)
    if not bool(row["whatsapp_enabled"]):
        raise HTTPException(status_code=400, detail="WhatsApp sending is disabled for this centre")
    if not row.get("upi_id"):
        raise HTTPException(status_code=400, detail="Centre UPI ID is not configured")
    patient = db.query(models.Patient).filter(models.Patient.id == report.patient_id, models.Patient.centre_id == current_user.centre_id).first()
    if not patient or not patient.phone:
        raise HTTPException(status_code=400, detail="Patient phone number is required for WhatsApp")

    billing = None
    if report.order_id:
        billing = db.query(models.Billing).filter(models.Billing.order_id == report.order_id,
            models.Billing.centre_id == current_user.centre_id).first()
    if not billing:
        raise HTTPException(status_code=400, detail="Create or link the report billing record before WhatsApp sending")

    base_url = row.get("public_base_url")
    if str(billing.payment_status).upper().endswith("PAID") and float(billing.pending_amount or 0) == 0:
        link = _public_report_token(db, report, patient, base_url)
        message = f"{patient.name or 'Patient'}, your diagnostic report is ready. Download: {link}"
        notification_type = "REPORT_READY_PAID"
    elif allow_pending:
        message = (f"{patient.name or 'Patient'}, your diagnostic report is ready. Pending amount: ₹{float(billing.pending_amount or 0):g}. "
                   f"Pay via UPI: {row['upi_id']}. After payment is confirmed by the centre, your report will be sent on WhatsApp.")
        notification_type = "REPORT_PAYMENT_PENDING"
    else:
        raise HTTPException(status_code=400, detail="Payment is still pending")

    job = models.NotificationJob(
        centre_id=current_user.centre_id, report_id=report.id, patient_id=patient.id,
        notification_type=notification_type, channel="WHATSAPP", recipient=patient.phone,
        message_payload=message, status="PENDING", created_at=datetime.utcnow()
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return {"notification_id": job.id, "status": job.status, "notification_type": notification_type,
            "recipient": patient.phone, "message": message}


@router.post("/whatsapp/report/{report_id}")
def whatsapp_report(report_id: int, db: Session = Depends(get_db), current_user=Depends(oauth2.require_technician)):
    report = db.query(models.ReportDocument).filter(models.ReportDocument.id == report_id,
        models.ReportDocument.centre_id == current_user.centre_id).first()
    if not report: raise HTTPException(status_code=404, detail="Report not found")
    return prepare_whatsapp_for_report(db, report, current_user)


@router.post("/whatsapp/bulk")
def whatsapp_bulk(payload: dict, db: Session = Depends(get_db), current_user=Depends(oauth2.require_technician)):
    ids = payload.get("report_ids") or []
    if not ids: raise HTTPException(status_code=400, detail="report_ids is required")
    results = []
    for report_id in ids:
        report = db.query(models.ReportDocument).filter(models.ReportDocument.id == int(report_id),
            models.ReportDocument.centre_id == current_user.centre_id).first()
        if not report:
            results.append({"report_id": report_id, "status": "FAILED", "detail": "Report not found"})
            continue
        try:
            results.append({"report_id": report.id, **prepare_whatsapp_for_report(db, report, current_user)})
        except HTTPException as exc:
            db.rollback()
            results.append({"report_id": report.id, "status": "FAILED", "detail": str(exc.detail)})
    return {"total": len(ids), "queued": sum(1 for x in results if x.get("status") == "PENDING"), "results": results}


@router.get("/whatsapp/notifications")
def list_whatsapp_notifications(db: Session = Depends(get_db), current_user=Depends(oauth2.get_current_user)):
    return db.query(models.NotificationJob).filter(
        models.NotificationJob.centre_id == current_user.centre_id,
        models.NotificationJob.channel == "WHATSAPP"
    ).order_by(models.NotificationJob.id.desc()).limit(100).all()


@router.get("/public/reports/{token}")
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
    if not report or not os.path.isfile(report.file_path):
        raise HTTPException(status_code=404, detail="Report is not available")
    access.used_at = datetime.utcnow()
    db.commit()
    return FileResponse(report.file_path, media_type="application/pdf", filename=report.pdf_filename or f"report_{report.id}.pdf")
