import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional
from sqlalchemy.orm import Session

from app.models import PatientReportAccessToken, ReportDocument, Billing
from app.services.audit_service import log_audit_event


def hash_token(raw_token: str) -> str:
    """Computes SHA-256 hash of a bearer token."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class PatientAccessService:
    @staticmethod
    def issue_token(
        db: Session,
        centre_id: int,
        patient_id: int,
        report_id: int,
        expiry_hours: int = 24,
    ) -> str:
        report = (
            db.query(ReportDocument)
            .filter(
                ReportDocument.id == report_id,
                ReportDocument.centre_id == centre_id,
                ReportDocument.patient_id == patient_id,
            )
            .first()
        )
        if not report:
            raise ValueError("Report not found or patient/tenant mismatch.")

        if not report.is_released or report.release_status != "RELEASED":
            raise ValueError("Report is not released for patient access.")

        raw_token = secrets.token_urlsafe(32)
        thash = hash_token(raw_token)
        now_utc = datetime.now(timezone.utc)
        expires_at = now_utc + timedelta(hours=expiry_hours)

        token_record = PatientReportAccessToken(
            centre_id=centre_id,
            patient_id=patient_id,
            report_id=report_id,
            token_hash=thash,
            issued_at=now_utc,
            expires_at=expires_at,
            access_count=0,
            failed_attempts=0,
        )
        db.add(token_record)

        log_audit_event(
            db=db,
            centre_id=centre_id,
            event_type="REPORT_ACCESS_TOKEN_ISSUED",
            entity_type="REPORT",
            entity_id=report_id,
            actor_user_id=None,
            payload={
                "patient_id": patient_id,
                "token_id_prefix": thash[:8],
                "expires_at": expires_at.isoformat(),
            },
        )
        db.commit()
        return raw_token

    @staticmethod
    def validate_token_and_authorize(
        db: Session,
        raw_token: str,
        expected_report_id: Optional[int] = None,
    ) -> Tuple[bool, Optional[str], Optional[ReportDocument], Optional[PatientReportAccessToken]]:
        thash = hash_token(raw_token)
        token_record = (
            db.query(PatientReportAccessToken)
            .filter(PatientReportAccessToken.token_hash == thash)
            .first()
        )

        if not token_record:
            return False, "INVALID_TOKEN", None, None

        if token_record.revoked_at is not None:
            return False, "TOKEN_REVOKED", None, token_record

        # Ensure datetime comparison compatibility
        exp = token_record.expires_at
        now = datetime.now(timezone.utc) if exp.tzinfo is not None else datetime.utcnow()
        if now > exp:
            return False, "TOKEN_EXPIRED", None, token_record

        if expected_report_id is not None and token_record.report_id != expected_report_id:
            return False, "REPORT_MISMATCH", None, token_record

        report = (
            db.query(ReportDocument)
            .filter(
                ReportDocument.id == token_record.report_id,
                ReportDocument.centre_id == token_record.centre_id,
            )
            .first()
        )
        if not report:
            return False, "REPORT_NOT_FOUND", None, token_record

        if not report.is_released or report.release_status != "RELEASED":
            return False, "REPORT_NOT_RELEASED", None, token_record

        billing = (
            db.query(Billing)
            .filter(
                Billing.order_id == report.order_id,
                Billing.centre_id == token_record.centre_id,
            )
            .first()
        )
        if billing:
            if billing.payment_status != "paid" or billing.pending_amount > 0.0:
                return False, "PAYMENT_PENDING", None, token_record

        return True, None, report, token_record

    @staticmethod
    def record_access_success(
        db: Session,
        token_record: PatientReportAccessToken,
        report: ReportDocument,
    ):
        token_record.used_at = datetime.utcnow()
        token_record.access_count += 1
        log_audit_event(
            db=db,
            centre_id=token_record.centre_id,
            event_type="REPORT_DOWNLOAD_SUCCEEDED",
            entity_type="REPORT",
            entity_id=report.id,
            actor_user_id=None,
            payload={
                "patient_id": token_record.patient_id,
                "access_count": token_record.access_count,
            },
        )
        db.commit()

    @staticmethod
    def record_access_failure(
        db: Session,
        raw_token: str,
        reason: str,
        centre_id: Optional[int] = None,
        report_id: Optional[int] = None,
    ):
        thash = hash_token(raw_token)
        log_audit_event(
            db=db,
            centre_id=centre_id if centre_id else 1,
            event_type="REPORT_DOWNLOAD_FAILED",
            entity_type="REPORT" if report_id else "SECURITY",
            entity_id=report_id if report_id else 0,
            actor_user_id=None,
            payload={"reason": reason, "token_prefix": thash[:8]},
        )
        db.commit()
