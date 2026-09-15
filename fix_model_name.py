with open("app/routers/report_ingest.py", "r") as f:
    code = f.read()

code = code.replace("models.ReportingIngestionJob", "models.ReportIngestionJob")

with open("app/routers/report_ingest.py", "w") as f:
    f.write(code)

print("Fixed ReportIngestionJob class name.")
