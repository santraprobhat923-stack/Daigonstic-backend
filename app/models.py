from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, UniqueConstraint, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Centre(Base):
    __tablename__ = "centres"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    address = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)
    role = Column(String, default="technician")
    is_active = Column(Boolean, default=True)

class Patient(Base):
    __tablename__ = "patients"
    id = Column(Integer, primary_key=True, index=True)
    centre_id = Column(Integer, ForeignKey("centres.id"), nullable=False)
    patient_code = Column(String, index=True, nullable=False)
    name = Column(String, nullable=True)
    age = Column(Integer, nullable=True)
    gender = Column(String, nullable=True)
    status = Column(String, default="PROVISIONAL") # PROVISIONAL, VERIFIED, ARCHIVED
    created_from_ingestion_job_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('centre_id', 'patient_code', name='uq_centre_patient_code'),
    )

class PatientSession(Base):
    __tablename__ = "patient_sessions"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)

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
    status = Column(String, default="PHOTO_UPLOADED") # PHOTO_UPLOADED, NEEDS_VERIFICATION, VERIFIED, REJECTED
    created_at = Column(DateTime, default=datetime.utcnow)
