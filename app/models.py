import enum
from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    Boolean,
    UniqueConstraint,
    Text,
)
from sqlalchemy.orm import synonym

from app.database import Base


# ============================================================
# ENUMS
# ============================================================

class PaymentStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    HELD = "HELD"
    PAID = "PAID"
    RELEASED = "RELEASED"
    REFUNDED = "REFUNDED"

    pending = "PENDING"
    held = "HELD"
    paid = "PAID"
    released = "RELEASED"
    refunded = "REFUNDED"


class ReportStatusEnum(str, enum.Enum):
    PHOTO_UPLOADED = "PHOTO_UPLOADED"
    NEEDS_VERIFICATION = "NEEDS_VERIFICATION"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"

    photo_uploaded = "PHOTO_UPLOADED"
    needs_verification = "NEEDS_VERIFICATION"
    verified = "VERIFIED"
    rejected = "REJECTED"


class TransactionTypeEnum(str, enum.Enum):
    CREDIT_PURCHASE = "CREDIT_PURCHASE"
    REPORT_FEE = "REPORT_FEE"
    PAYOUT = "PAYOUT"
    ADMIN_GRANT = "ADMIN_GRANT"

    credit_purchase = "CREDIT_PURCHASE"
    report_fee = "REPORT_FEE"
    payout = "PAYOUT"
    purchase = "CREDIT_PURCHASE"
    report_upload = "REPORT_FEE"
    admin_grant = "ADMIN_GRANT"


class PurchaseStatusEnum(str, enum.Enum):
    INITIATED = "INITIATED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    APPROVED = "APPROVED"
    PENDING = "PENDING"
    REJECTED = "REJECTED"

    initiated = "INITIATED"
    completed = "COMPLETED"
    failed = "FAILED"
    approved = "APPROVED"
    pending = "PENDING"
    rejected = "REJECTED"


class ReportStorageStatusEnum(str, enum.Enum):
    PENDING_STORAGE = "PENDING_STORAGE"
    STORED = "STORED"

    pending_storage = "PENDING_STORAGE"
    stored = "STORED"


class UserRoleEnum(str, enum.Enum):
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    TECHNICIAN = "technician"

    superadmin = "superadmin"
    admin = "admin"
    technician = "technician"


# ============================================================
# CENTRE / USER
# ============================================================

class Centre(Base):
    __tablename__ = "centres"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    address = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    account_status = Column(String, default="ACTIVE")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)
    role = Column(String, default="technician")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Legacy compatibility
    password = synonym("hashed_password")


# ============================================================
# PATIENT
# ============================================================

class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)
    patient_code = Column(String, index=True, nullable=False)
    name = Column(String, nullable=True)
    age = Column(Integer, nullable=True)
    gender = Column(String, nullable=True)
    status = Column(String, default="PROVISIONAL")
    created_from_ingestion_job_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "centre_id",
            "patient_code",
            name="uq_centre_patient_code",
        ),
    )

    # Legacy schema compatibility
    full_name = synonym("name")


class PatientSession(Base):
    __tablename__ = "patient_sessions"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)


class PatientAccessOTP(Base):
    __tablename__ = "patient_access_otps"

    id = Column(Integer, primary_key=True, index=True)
    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    otp_hash = Column(String, nullable=False)
    identifier_ref = Column(String, nullable=False)
    attempt_count = Column(Integer, nullable=False)
    max_attempts = Column(Integer, nullable=False)
    status = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False)


class PatientReportAccessToken(Base):
    __tablename__ = "patient_report_access_tokens"

    id = Column(Integer, primary_key=True, index=True)
    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    report_id = Column(Integer, ForeignKey("report_documents.id"), nullable=False)
    token_hash = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    used_at = Column(DateTime, nullable=True)
    status = Column(String, default="ACTIVE")
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================
# INGESTION
# ============================================================

class ReportIngestionJob(Base):
    __tablename__ = "report_ingestion_jobs"

    id = Column(Integer, primary_key=True, index=True)
    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)
    technician_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    original_filename = Column(String, nullable=False)
    mime_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)

    source_image_path = Column(String, nullable=False)
    source_image_hash = Column(String, nullable=False)

    status = Column(String, default="PHOTO_UPLOADED")
    created_at = Column(DateTime, default=datetime.utcnow)

    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)

    # SQLite stores these as TEXT-compatible JSON.
    extracted_data = Column(Text, nullable=True)
    verified_data = Column(Text, nullable=True)

    verified_at = Column(DateTime, nullable=True)
    verified_by = Column(Integer, nullable=True)

    final_report_id = Column(
        Integer,
        ForeignKey("report_documents.id"),
        nullable=True,
    )

    attempt_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    last_error = Column(Text, nullable=True)

    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


# ============================================================
# REPORT DOCUMENT
# ============================================================

class ReportDocument(Base):
    __tablename__ = "report_documents"

    id = Column(Integer, primary_key=True, index=True)

    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)

    patient_code = Column(String(64), nullable=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)

    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)

    # Original/source document compatibility
    file_path = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    stored_filename = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    file_hash = Column(String(64), nullable=False)
    file_checksum = Column(String(64), nullable=True)

    identification_method = Column(String(32), nullable=True)
    storage_status = Column(String, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Authoritative generated PDF
    release_status = Column(String, default="HELD_PAYMENT")
    is_released = Column(Boolean, default=False)
    released_at = Column(DateTime, nullable=True)
    released_by = Column(Integer, nullable=True)

    pdf_path = Column(String, nullable=True)
    pdf_filename = Column(String, nullable=True)
    pdf_hash = Column(String, nullable=True)
    pdf_size = Column(Integer, nullable=True)

    ingestion_job_id = Column(
        Integer,
        ForeignKey("report_ingestion_jobs.id"),
        nullable=True,
    )

    verified_at = Column(DateTime, nullable=True)
    verified_by = Column(Integer, nullable=True)


# ============================================================
# TESTS
# ============================================================

class Test(Base):
    __tablename__ = "tests"

    id = Column(Integer, primary_key=True, index=True)
    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)
    patient_code = Column(String(64), nullable=True)

    code = Column(String, nullable=False)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    description = Column(String, nullable=True)
    category = Column(String, nullable=True)


# ============================================================
# ORDERS
# ============================================================

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)

    patient_code = Column(String(64), nullable=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)

    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    status = Column(String, nullable=True)

    subtotal = Column(Float, nullable=True)
    discount = Column(Float, nullable=True)
    total = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Existing routers use total_amount.
    total_amount = synonym("total")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    test_id = Column(Integer, ForeignKey("tests.id"), nullable=False)

    price_at_order = Column(Float, nullable=False)
    quantity = Column(Integer, default=1)

    # Existing router compatibility.
    unit_price = synonym("price_at_order")


# ============================================================
# BILLING
# ============================================================

class Billing(Base):
    __tablename__ = "billing"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)

    patient_code = Column(String(64), nullable=True)
    patient_id = Column(Integer, nullable=True)

    total_amount = Column(Float, nullable=False)
    paid_amount = Column(Float, default=0)
    pending_amount = Column(Float, default=0)

    payment_status = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    bill_file_path = Column(String, nullable=True)


# ============================================================
# CREDITS
# ============================================================

class CentreCreditAccount(Base):
    __tablename__ = "centre_credit_accounts"

    id = Column(Integer, primary_key=True, index=True)
    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)
    balance = Column(Integer, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id = Column(Integer, primary_key=True, index=True)
    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    amount = Column(Integer, nullable=False)
    balance_after = Column(Integer, nullable=False)

    transaction_type = Column(String, nullable=False)

    reference_type = Column(String, nullable=True)
    reference_id = Column(Integer, nullable=True)

    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CreditPurchase(Base):
    __tablename__ = "credit_purchases"

    id = Column(Integer, primary_key=True, index=True)
    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)

    patient_code = Column(String(64), nullable=True)

    amount_paid = Column(Float, nullable=False)
    credits = Column(Integer, nullable=False)
    price_per_credit = Column(Float, nullable=False)

    payment_method = Column(String, nullable=True)
    payment_reference = Column(String, nullable=True)

    status = Column(String, nullable=True)

    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================
# NOTIFICATION WORKER
# ============================================================

class NotificationJob(Base):
    __tablename__ = "notification_jobs"

    id = Column(Integer, primary_key=True, index=True)

    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)
    report_id = Column(Integer, nullable=True)
    patient_id = Column(Integer, nullable=True)

    notification_type = Column(String, nullable=False)
    channel = Column(String, nullable=False)
    recipient = Column(String, nullable=True)

    message_payload = Column(Text, nullable=True)

    status = Column(String, default="PENDING")

    attempt_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)

    last_error = Column(Text, nullable=True)
    next_attempt_at = Column(DateTime, nullable=True)

    locked_at = Column(DateTime, nullable=True)
    locked_by = Column(String, nullable=True)

    started_at = Column(DateTime, nullable=True)
    last_attempt_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    dead_lettered_at = Column(DateTime, nullable=True)

    original_filename = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    source_image_hash = Column(String, nullable=True)
    source_image_path = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================
# AUDIT
# ============================================================

class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, index=True)

    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)

    event_type = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(Integer, nullable=True)

    payload = Column(Text, nullable=True)

    schema_version = Column(Integer, default=1)

    canonical_payload = Column(Text, nullable=True)
    previous_event_hash = Column(String, nullable=True)
    event_hash = Column(String, nullable=True)

    is_chained = Column(Boolean, default=True)
    sequence_id = Column(Integer, nullable=True)

    timestamp = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================
# CENTRE ACTIVATION
# ============================================================

class CentreActivationKey(Base):
    __tablename__ = "centre_activation_keys"

    id = Column(Integer, primary_key=True, index=True)

    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)

    key_hash = Column(String, nullable=False)
    status = Column(String, default="ACTIVE")

    created_at = Column(DateTime, default=datetime.utcnow)
    used_at = Column(DateTime, nullable=True)
    activated_at = Column(DateTime, nullable=True)
