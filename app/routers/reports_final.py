import os
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, oauth2
from app.services.release_service import ReleaseService

router = APIRouter(prefix="/reports", tags=["Reports Release & Generation"])


def _report_or_404(db: Session, report_id: int, centre_id: int):
    report = db.query(models.ReportDocument).filter(
        models.ReportDocument.id == report_id,
        models.ReportDocument.centre_id == centre_id
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report document not found")
    return report


@router.get("/final/{report_id}/status")
def get_report_release_status(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    if getattr(current_user, "role", None) not in ["technician", "centre_admin", "admin", "receptionist"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    eligible, reason, report = ReleaseService.evaluate_release_eligibility(db, report_id, current_user.centre_id)
    return {
        "report_id": report.id,
        "order_id": report.order_id,
        "is_released": report.is_released,
        "release_status": report.release_status,
        "released_at": report.released_at,
        "released_by": report.released_by,
        "is_eligible_for_release": eligible,
        "eligibility_reason": reason
    }


@router.get("/final/{report_id}/payment-context")
def get_report_payment_context(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    """Return tenant-scoped orders for the report patient and the linked billing state."""
    report = _report_or_404(db, report_id, current_user.centre_id)
    patient = db.query(models.Patient).filter(
        models.Patient.id == report.patient_id,
        models.Patient.centre_id == current_user.centre_id
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Report patient not found")

    orders = db.query(models.Order).filter(
        models.Order.patient_id == patient.id,
        models.Order.centre_id == current_user.centre_id
    ).order_by(models.Order.id.desc()).all()

    billing_by_order = {
        b.order_id: b for b in db.query(models.Billing).filter(
            models.Billing.centre_id == current_user.centre_id,
            models.Billing.order_id.in_([o.id for o in orders]) if orders else False
        ).all()
    }

    return {
        "report_id": report.id,
        "patient_id": patient.id,
        "patient_name": patient.name,
        "order_id": report.order_id,
        "orders": [
            {
                "id": order.id,
                "status": order.status,
                "total_amount": order.total_amount,
                "created_at": order.created_at,
                "billing": (
                    {
                        "id": billing_by_order[order.id].id,
                        "payment_status": billing_by_order[order.id].payment_status,
                        "total_amount": billing_by_order[order.id].total_amount,
                        "paid_amount": billing_by_order[order.id].paid_amount,
                        "pending_amount": billing_by_order[order.id].pending_amount,
                    }
                    if order.id in billing_by_order else None
                )
            }
            for order in orders
        ]
    }


@router.post("/final/{report_id}/link-order/{order_id}")
def link_report_to_order(
    report_id: int,
    order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.require_technician)
):
    report = _report_or_404(db, report_id, current_user.centre_id)
    order = db.query(models.Order).filter(
        models.Order.id == order_id,
        models.Order.centre_id == current_user.centre_id,
        models.Order.patient_id == report.patient_id
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found for this report's patient")
    if report.is_released:
        raise HTTPException(status_code=400, detail="Released report cannot be re-linked to another order")
    report.order_id = order.id
    db.commit()
    db.refresh(report)
    return {"report_id": report.id, "order_id": report.order_id, "message": "Order linked to report"}


@router.post("/final/{report_id}/release")
def release_final_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    if getattr(current_user, "role", None) not in ["technician", "centre_admin", "admin"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    released_report = ReleaseService.release_report(
        db, report_id=report_id, centre_id=current_user.centre_id,
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
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    report = _report_or_404(db, report_id, current_user.centre_id)
    if not report.is_released:
        raise HTTPException(status_code=402, detail="Report is not released. Payment pending or release sign-off required.")
    if not os.path.exists(report.file_path):
        raise HTTPException(status_code=404, detail="Physical report file not found")
    return FileResponse(report.file_path, media_type="application/pdf", filename=f"report_{report.id}.pdf")
