import os
import shutil
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session

from app import models, schemas, oauth2
from app.database import get_db
from app.routers.workflow import prepare_whatsapp_for_report
from app.services.release_service import ReleaseService

router = APIRouter(prefix="/billing", tags=["Billing & Payments"])
BILL_STORAGE_DIR = "storage/bills"
os.makedirs(BILL_STORAGE_DIR, exist_ok=True)


def _queue_whatsapp_if_enabled(db: Session, order_id: int, current_user):
    report = db.query(models.ReportDocument).filter(
        models.ReportDocument.order_id == order_id,
        models.ReportDocument.centre_id == current_user.centre_id
    ).order_by(models.ReportDocument.id.desc()).first()
    if not report:
        return None

    billing = db.query(models.Billing).filter(models.Billing.order_id == order_id,
        models.Billing.centre_id == current_user.centre_id).first()
    if billing and str(billing.payment_status).upper().endswith("PAID") and float(billing.pending_amount or 0) == 0:
        if not report.is_released:
            ReleaseService.release_report(db, report_id=report.id, centre_id=current_user.centre_id,
                                          released_by_user_id=current_user.id)
            db.refresh(report)
        try:
            return prepare_whatsapp_for_report(db, report, current_user)
        except HTTPException:
            db.rollback()
            return None

    try:
        return prepare_whatsapp_for_report(db, report, current_user)
    except HTTPException:
        db.rollback()
        return None


@router.post("/", response_model=schemas.BillingResponse, status_code=status.HTTP_201_CREATED)
def record_billing(order_id: int = Form(...), payment_status: models.PaymentStatusEnum = Form(...),
                   pending_amount: int = Form(0), bill_file: Optional[UploadFile] = File(None),
                   db: Session = Depends(get_db), current_user: models.User = Depends(oauth2.require_technician)):
    if payment_status == models.PaymentStatusEnum.paid and pending_amount != 0:
        raise HTTPException(status_code=400, detail="When payment status is 'paid', pending_amount must be 0.")
    if payment_status == models.PaymentStatusEnum.pending and pending_amount <= 0:
        raise HTTPException(status_code=400, detail="When payment status is 'pending', pending_amount must be > 0.")
    order = db.query(models.Order).filter(models.Order.id == order_id, models.Order.centre_id == current_user.centre_id).first()
    if not order: raise HTTPException(status_code=404, detail=f"Order {order_id} not found in this centre.")
    if db.query(models.Billing).filter(models.Billing.order_id == order_id).first():
        raise HTTPException(status_code=400, detail=f"Billing record already exists for order {order_id}.")
    saved_file_path = None
    if bill_file and bill_file.filename:
        tenant_dir = os.path.join(BILL_STORAGE_DIR, str(current_user.centre_id)); os.makedirs(tenant_dir, exist_ok=True)
        saved_file_path = os.path.join(tenant_dir, f"bill_order_{order_id}_{os.path.basename(bill_file.filename)}")
        with open(saved_file_path, "wb") as buffer: shutil.copyfileobj(bill_file.file, buffer)
    total_amount = float(order.total_amount or 0)
    billing = models.Billing(order_id=order.id, patient_id=order.patient_id, centre_id=current_user.centre_id,
        total_amount=total_amount, paid_amount=max(0.0, total_amount-float(pending_amount)),
        pending_amount=pending_amount, payment_status=payment_status, bill_file_path=saved_file_path)
    db.add(billing); db.commit(); db.refresh(billing)
    _queue_whatsapp_if_enabled(db, order.id, current_user)
    return billing


@router.put("/{order_id}/payment", response_model=schemas.BillingResponse)
def update_payment_status(order_id: int, payment_status: models.PaymentStatusEnum = Form(...), pending_amount: int = Form(0),
                          db: Session = Depends(get_db), current_user: models.User = Depends(oauth2.require_technician)):
    if payment_status == models.PaymentStatusEnum.paid and pending_amount != 0:
        raise HTTPException(status_code=400, detail="Paid payment must have pending_amount=0")
    if payment_status == models.PaymentStatusEnum.pending and pending_amount <= 0:
        raise HTTPException(status_code=400, detail="Pending payment must have pending_amount>0")
    billing = db.query(models.Billing).filter(models.Billing.order_id == order_id,
        models.Billing.centre_id == current_user.centre_id).first()
    if not billing: raise HTTPException(status_code=404, detail="Billing record not found for this order")
    billing.payment_status = payment_status
    billing.pending_amount = float(pending_amount)
    billing.paid_amount = max(0.0, float(billing.total_amount or 0) - float(pending_amount))
    db.commit(); db.refresh(billing)
    _queue_whatsapp_if_enabled(db, order_id, current_user)
    return billing


@router.get("/order/{order_id}", response_model=schemas.BillingResponse)
def get_order_billing(order_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(oauth2.get_current_user)):
    billing = db.query(models.Billing).filter(models.Billing.order_id == order_id,
        models.Billing.centre_id == current_user.centre_id).first()
    if not billing: raise HTTPException(status_code=404, detail="Billing record not found for this order")
    return billing
