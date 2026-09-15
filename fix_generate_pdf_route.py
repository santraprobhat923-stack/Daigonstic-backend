with open("app/routers/report_ingest.py", "r") as f:
    code = f.read()

import re

new_generate_pdf_job = '''@router.post("/{job_id}/generate-pdf")
def generate_pdf_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    from fastapi.responses import JSONResponse

    job = db.query(models.ReportingIngestionJob).filter(models.ReportingIngestionJob.id == job_id).first()
    if not job or job.centre_id != current_user.centre_id:
        raise HTTPException(status_code=404, detail="Ingestion job not found")

    # Idempotency check for Test 6
    if (job.status in ("FINALIZED", "GENERATED") or getattr(job, "final_report_id", None)) and job.final_report_id:
        return JSONResponse(
            status_code=200,
            content={
                "job_id": job.id,
                "id": job.id,
                "status": "ALREADY_GENERATED",
                "report_id": job.final_report_id,
            }
        )

    # Initial generation via finalize_job
    res = finalize_job(job_id=job_id, db=db, current_user=current_user)
    if isinstance(res, dict):
        res = dict(res)
        res["status"] = "GENERATED"
    return JSONResponse(status_code=201, content=res)
'''

# Replace def generate_pdf_job block
code = re.sub(r"@router\.post\(\"/\{job_id\}/generate-pdf\"[^\n]*\ndef generate_pdf_job.*?(?=\Z|\n@router|\ndef [a-zA-Z_])", new_generate_pdf_job + "\n", code, flags=re.DOTALL)

with open("app/routers/report_ingest.py", "w") as f:
    f.write(code)

print("generate_pdf_job route updated with GENERATED and ALREADY_GENERATED handling.")
