import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Enum as SQLEnum, CheckConstraint, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database import Base

class UserRoleEnum(str, enum.Enum):
    superadmin = "superadmin"
    admin = "admin"
    technician = "technician"

class PaymentStatusEnum(str, enum.Enum):
    paid = "paid"
    partially_paid = "partially_paid"
    pending = "pending"

class TransactionTypeEnum(str, enum.Enum):
    admin_grant = "admin_grant"
    purchase = "purchase"
    report_upload = "report_upload"
    refund = "refund"

class PurchaseStatusEnum(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"

class ReportStorageStatusEnum(str, enum.Enum):
    pending_storage = "pending_storage"
    stored = "stored"
    failed = "failed"
ReportStatusEnum = ReportStorageStatusEnum

class Centre(Base):
    __tablename__ = "centres"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    address = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    users = relationship("User", back_populates="centre")
    patients = relationship("Patient", back_populates="centre")
    tests = relationship("Test", back_populates="centre")
    orders = relationship("Order", back_populates="centre")
    reports = relationship("ReportDocument", back_populates="centre")
    credit_account = relationship("CentreCreditAccount", back_populates="centre", uselist=False)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(SQLEnum(UserRoleEnum), default=UserRoleEnum.technician, nullable=False)
    is_active = Column(Boolean, default=True)
    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)

    centre = relationship("Centre", back_populates="users")

class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (UniqueConstraint("centre_id", "patient_code", name="uq_centre_patient_code"),)
    id = Column(Integer, primary_key=True, index=True)
    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)
    patient_code = Column(String(64), index=True, nullable=True)
    full_name = Column(String, nullable=False)
    age = Column(Integer, nullable=True, default=0)
    gender = Column(String, nullable=True)
    dob = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    centre = relationship("Centre", back_populates="patients")
    orders = relationship("Order", back_populates="patient")
    reports = relationship("ReportDocument", back_populates="patient")

class Test(Base):
    __tablename__ = "tests"
    id = Column(Integer, primary_key=True, index=True)
    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)
    patient_code = Column(String(64), index=True, nullable=True)
    code = Column(String, nullable=False)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    description = Column(String, nullable=True)

    centre = relationship("Centre", back_populates="tests")

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)
    patient_code = Column(String(64), index=True, nullable=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    status = Column(String, default="pending")
    subtotal = Column(Float, default=0.0)
    discount = Column(Float, default=0.0)
    total = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    centre = relationship("Centre", back_populates="orders")
    patient = relationship("Patient", back_populates="orders")
    items = relationship("OrderItem", back_populates="order")
    billing = relationship("Billing", back_populates="order", uselist=False)
    reports = relationship("ReportDocument", back_populates="order")

class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    test_id = Column(Integer, ForeignKey("tests.id"), nullable=False)
    price_at_order = Column(Float, nullable=False)

    order = relationship("Order", back_populates="items")
    test = relationship("Test")

class Billing(Base):
    __tablename__ = "billing"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)
    patient_code = Column(String(64), index=True, nullable=True)
    total_amount = Column(Float, nullable=False)
    paid_amount = Column(Float, default=0.0)
    pending_amount = Column(Float, default=0.0)
    payment_status = Column(SQLEnum(PaymentStatusEnum), default=PaymentStatusEnum.pending)
    created_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("Order", back_populates="billing")

class ReportDocument(Base):
    __tablename__ = "report_documents"
    __table_args__ = (
        UniqueConstraint("centre_id", "file_hash", name="uq_centre_file_hash"),
    )
    id = Column(Integer, primary_key=True, index=True)
    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)
    patient_code = Column(String(64), index=True, nullable=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    file_path = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    stored_filename = Column(String, nullable=True)
    file_size = Column(Integer, default=0, nullable=True)
    file_hash = Column(String(64), nullable=False)
    file_checksum = Column(String(64), nullable=True)
    identification_method = Column(String(32), default="manual", nullable=True)
    storage_status = Column(
        SQLEnum(ReportStorageStatusEnum),
        default=ReportStorageStatusEnum.pending_storage,
        nullable=False
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    centre = relationship("Centre", back_populates="reports")
    patient = relationship("Patient", back_populates="reports")
    order = relationship("Order", back_populates="reports")

class CentreCreditAccount(Base):
    __tablename__ = "centre_credit_accounts"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="check_credit_balance_non_negative"),
    )
    id = Column(Integer, primary_key=True, index=True)
    centre_id = Column(Integer, ForeignKey("centres.id"), unique=True, nullable=False)
    balance = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)

    centre = relationship("Centre", back_populates="credit_account")

class CreditTransaction(Base):
    __tablename__ = "credit_transactions"
    id = Column(Integer, primary_key=True, index=True)
    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    amount = Column(Integer, nullable=False)
    balance_after = Column(Integer, nullable=False)
    transaction_type = Column(SQLEnum(TransactionTypeEnum), nullable=False)
    reference_type = Column(String, nullable=True)
    reference_id = Column(Integer, nullable=True)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class CreditPurchase(Base):
    __tablename__ = "credit_purchases"
    id = Column(Integer, primary_key=True, index=True)
    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)
    patient_code = Column(String(64), index=True, nullable=True)
    amount_paid = Column(Float, nullable=False)
    credits = Column(Integer, nullable=False)
    price_per_credit = Column(Float, nullable=False)
    payment_method = Column(String, default="manual")
    payment_reference = Column(String, nullable=True)
    status = Column(SQLEnum(PurchaseStatusEnum), default=PurchaseStatusEnum.pending)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PatientAccessOTP(Base):
    __tablename__ = "patient_access_otps"

    id = Column(Integer, primary_key=True, index=True)
    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    otp_hash = Column(String, nullable=False)
    identifier_ref = Column(String, nullable=False)
    attempt_count = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)
    status = Column(String, default="PENDING", nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class PatientSession(Base):
    __tablename__ = "patient_sessions"

    id = Column(Integer, primary_key=True, index=True)
    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    token_hash = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)


class ReportIngestionJob(Base):
    __tablename__ = "report_ingestion_jobs"

    id = Column(Integer, primary_key=True, index=True)
    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)
    source_image_path = Column(String, nullable=False)
    source_image_hash = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String, nullable=False)
    status = Column(String, default="PHOTO_UPLOADED", nullable=False)
    extracted_data = Column(String, nullable=True)
    verified_data = Column(String, nullable=True)
    technician_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    verified_at = Column(DateTime, nullable=True)
    final_report_id = Column(Integer, ForeignKey("report_documents.id"), nullable=True)
    error_code = Column(String, nullable=True)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
