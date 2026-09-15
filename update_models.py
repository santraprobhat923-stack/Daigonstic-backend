with open("app/models.py", "r") as f:
    code = f.read()

new_job_model = """class ReportIngestionJob(Base):
    __tablename__ = "report_ingestion_jobs"
    id = Column(Integer, primary_key=True, index=True)
    centre_id = Column(Integer, nullable=False, index=True)
    technician_id = Column(Integer, nullable=True, index=True)
    file_path = Column(String, nullable=False)
    source_image_path = Column(String, nullable=True)
    status = Column(String, default="PENDING")
    created_at = Column(DateTime, default=datetime.utcnow)"""

if "class ReportIngestionJob" in code:
    import re
    # Find and replace the existing ReportIngestionJob definition cleanly
    code = re.sub(r"class ReportIngestionJob\(Base\):.*?(?=(\nclass |\Z))", new_job_model, code, flags=re.DOTALL)
else:
    code += "\n\n" + new_job_model

with open("app/models.py", "w") as f:
    f.write(code)

print("ReportIngestionJob successfully updated!")
