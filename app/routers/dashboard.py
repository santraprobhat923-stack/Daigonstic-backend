from datetime import datetime, date
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app import models, schemas, oauth2
from app.database import get_db
from app.services import credit_service

router = APIRouter(prefix="/dashboard", tags=["Centre Dashboard"])

@router.get("", response_model=schemas.CentreDashboardResponse)
def get_centre_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    centre_id = current_user.centre_id
    centre = db.query(models.Centre).filter(models.Centre.id == centre_id).first()
    credit_account = credit_service.get_or_create_account(db, centre_id)

    total_patients = db.query(func.count(models.Patient.id)).filter(models.Patient.centre_id == centre_id).scalar() or 0
    total_orders = db.query(func.count(models.Order.id)).filter(models.Order.centre_id == centre_id).scalar() or 0
    total_reports = db.query(func.count(models.ReportDocument.id)).filter(models.ReportDocument.centre_id == centre_id).scalar() or 0

    today_start = datetime.combine(date.today(), datetime.min.time())
    reports_today = db.query(func.count(models.ReportDocument.id)).filter(
        models.ReportDocument.centre_id == centre_id,
        models.ReportDocument.created_at >= today_start
    ).scalar() or 0

    month_start = datetime(date.today().year, date.today().month, 1)
    reports_month = db.query(func.count(models.ReportDocument.id)).filter(
        models.ReportDocument.centre_id == centre_id,
        models.ReportDocument.created_at >= month_start
    ).scalar() or 0

    pending_payments_count = db.query(func.count(models.Billing.id)).filter(
        models.Billing.centre_id == centre_id,
        models.Billing.payment_status == models.PaymentStatusEnum.pending
    ).scalar() or 0

    # Keep compatibility with the current enum while still exposing the dashboard field.
    partially_paid_count = db.query(func.count(models.Billing.id)).filter(
        models.Billing.centre_id == centre_id,
        models.Billing.payment_status == "PARTIALLY_PAID"
    ).scalar() or 0

    total_pending_amount = db.query(func.sum(models.Billing.pending_amount)).filter(
        models.Billing.centre_id == centre_id
    ).scalar() or 0.0

    return schemas.CentreDashboardResponse(
        centre_id=centre_id,
        centre_name=centre.name if centre else "Unknown",
        credit_balance=credit_account.balance,
        low_credit=credit_account.balance < credit_service.LOW_CREDIT_THRESHOLD,
        total_patients=total_patients,
        total_orders=total_orders,
        total_reports=total_reports,
        reports_uploaded_today=reports_today,
        reports_uploaded_this_month=reports_month,
        pending_payments_count=pending_payments_count,
        partially_paid_count=partially_paid_count,
        total_pending_amount=float(total_pending_amount)
    )
