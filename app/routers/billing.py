import os
import shutil
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session

from app import models, schemas, oauth2
from app.database import get_db

router = APIRouter(
    prefix="/billing",
    tags=["Billing & Payments"]
)

BILL_STORAGE_DIR = "storage/bills"
os.makedirs(BILL_STORAGE_DIR, exist_ok=True)


@router.post("/", response_model=schemas.BillingResponse, status_code=status.HTTP_201_CREATED)
def record_billing(
    order_id: int = Form(...),
    payment_status: models.PaymentStatusEnum = Form(...),
    pending_amount: int = Form(0),
    bill_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.require_technician)
):
    # Enforce payment status validation rules
    if payment_status == models.PaymentStatusEnum.paid and pending_amount != 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="When payment status is 'paid', pending_amount must be 0."
        )
    if payment_status in [models.PaymentStatusEnum.partially_paid, models.PaymentStatusEnum.pending] and pending_amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"When payment status is '{payment_status.value}', pending_amount must be > 0."
        )

    # Tenant check: Order must belong to current centre
    order = db.query(models.Order).filter(
        models.Order.id == order_id,
        models.Order.centre_id == current_user.centre_id
    ).first()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id} not found in this centre."
        )

    # Check for existing billing
    if db.query(models.Billing).filter(models.Billing.order_id == order_id).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Billing record already exists for order {order_id}."
        )

    # Optional Bill Document handling
    saved_file_path = None
    if bill_file and bill_file.filename:
        tenant_dir = os.path.join(BILL_STORAGE_DIR, str(current_user.centre_id))
        os.makedirs(tenant_dir, exist_ok=True)
        safe_filename = f"bill_order_{order_id}_{bill_file.filename}"
        saved_file_path = os.path.join(tenant_dir, safe_filename)
        with open(saved_file_path, "wb") as buffer:
            shutil.copyfileobj(bill_file.file, buffer)

    billing = models.Billing(
        order_id=order.id,
        patient_id=order.patient_id,
        centre_id=current_user.centre_id,
        total_amount=order.total_amount,
        payment_status=payment_status,
        pending_amount=pending_amount,
        bill_file_path=saved_file_path
    )
    db.add(billing)
    db.commit()
    db.refresh(billing)
    return billing
