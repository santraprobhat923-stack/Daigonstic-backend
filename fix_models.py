import re

with open("app/models.py", "r") as f:
    code = f.read()

# If ReportIngestionJob lacks technician_id, let us replace its definition
if "class ReportIngestionJob" in code and "technician_id" not in code:
    old_def = """class ReportIngestionJob(Base):
    __tablename__ = "report_ingestion_jobs"
    id = Column(Integer, primary_key=True, index=True)
    centre_id = Column(Integer, nullable=False, index=True)
    file_path = Column(String, nullable=False)
    status = Column(String, default="PENDING")
    created_at = Column(DateTime, default=datetime.utcnow)"""

    new_def = """class ReportIngestionJob(Base):
    __tablename__ = "report_ingestion_jobs"
    id = Column(Integer, primary_key=True, index=True)
    centre_id = Column(Integer, nullable=False, index=True)
    technician_id = Column(Integer, nullable=True, index=True)
    file_path = Column(String, nullable=False)
    status = Column(String, default="PENDING")
    created_at = Column(DateTime, default=datetime.utcnow)"""

    code = code.replace(old_def, new_def)
    with open("app/models.py", "w") as f:
        f.write(code)
    print("Updated ReportIngestionJob definition with technician_id.")
else:
    print("ReportIngestionJob already has technician_id or needs manual check.")
