from app.services.audit_service import log_audit_event
from app.models import NotificationJob, Order, Patient
from datetime import datetime
from typing import Tuple, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app import models

class ReleaseService:
    @staticmethod
    def evaluate_release_eligibility(db: Session, report_id: int, centre_id: int) -> Tuple[bool, str, Optional[models.ReportDocument]]:
        report = db.query(models.ReportDocument).filter(
            models.ReportDocument.id == report_id,
            models.ReportDocument.centre_id == centre_id
        ).first()

        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report document not found or tenant mismatch"
            )

        if report.is_released:
            return True, "Report is already released.", report

        # Locate linked billing record via order_id
        if not report.order_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Report is not linked to any order. Cannot verify billing status."
            )

        billing = db.query(models.Billing).filter(
            models.Billing.order_id == report.order_id,
            models.Billing.centre_id == centre_id
        ).first()

        if not billing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Billing record for this order not found"
            )

        # Payment validation: must be paid and pending_amount <= 0
        is_paid = (
            billing.payment_status == models.PaymentStatusEnum.paid
            and billing.pending_amount <= 0.0
        )

        if not is_paid:
            return False, f"Payment pending: status={billing.payment_status.value}, pending_amount={billing.pending_amount}", report

        return True, "Payment cleared. Report is eligible for release.", report

    @classmethod
    def release_report(cls, db: Session, report_id: int, centre_id: int, released_by_user_id: int) -> models.ReportDocument:
        eligible, reason, report = cls.evaluate_release_eligibility(db, report_id, centre_id)

        if report.is_released:
            return report

        if not eligible:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Cannot release report: {reason}"
            )

        # Perform authoritative release
        report.is_released = True
        report.release_status = "RELEASED"
        report.released_at = datetime.utcnow()
        report.released_by = released_by_user_id

        # Milestone 6: Durable Notification Job creation in same transaction
        existing_job = db.query(NotificationJob).filter(
            NotificationJob.centre_id == centre_id,
            NotificationJob.report_id == report.id,
            NotificationJob.notification_type == "REPORT_RELEASED",
            NotificationJob.channel == "SMS"
        ).first()

        if not existing_job:
            order = db.query(Order).filter(Order.id == report.order_id, Order.centre_id == centre_id).first()
            patient = db.query(Patient).filter(Patient.id == order.patient_id).first() if order else None

            # Safe generic privacy payload: zero clinical findings or diagnostic values
            msg_text = "Your diagnostic report is now available. Please use the authorized access portal provided by your diagnostic centre to view your verified report."

            recipient_contact = None
            if patient:
                recipient_contact = getattr(patient, "phone", None) or getattr(patient, "mobile", None) or getattr(patient, "contact_number", None) or getattr(patient, "email", None)

            if not recipient_contact:
                job = NotificationJob(
                    centre_id=centre_id,
                    report_id=report.id,
                    patient_id=order.patient_id if order else 0,
                    notification_type="REPORT_RELEASED",
                    channel="SMS",
                    recipient="UNKNOWN",
                    message_payload=msg_text,
                    status="SKIPPED",
                    last_error="No usable contact information found for patient"
                )
            else:
                job = NotificationJob(
                    centre_id=centre_id,
                    report_id=report.id,
                    patient_id=order.patient_id if order else 0,
                    notification_type="REPORT_RELEASED",
                    channel="SMS",
                    recipient=str(recipient_contact),
                    message_payload=msg_text,
                    status="PENDING"
                )
            db.add(job)

        db.add(report)
        # Milestone 7: Atomic Audit Trail for Report Release
        log_audit_event(
            db=db,
            centre_id=centre_id,
            event_type="REPORT_RELEASED",
            entity_type="REPORT",
            entity_id=report.id,
            actor_user_id=released_by_user_id,
            payload={"order_id": report.order_id, "patient_id": report.patient_id, "release_status": report.release_status}
        )
        db.commit()
        db.refresh(report)
        return report
