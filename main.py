from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.routers import (
    centres, users, auth, patients, tests, orders, billing, credits, dashboard,
    report_ingest, reports_final, workflow, public_reports
)

app = FastAPI(
    title="Diagnostic Centre Automated Ingestion Backend",
    version="3.2.0",
    description="Centre-scoped analyzer image ingestion, technician verification, PDF generation, payment and optional WhatsApp workflow."
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(auth.router)
app.include_router(centres.router)
app.include_router(users.router)
app.include_router(patients.router)
app.include_router(tests.router)
app.include_router(orders.router)
app.include_router(billing.router)
app.include_router(credits.router)
app.include_router(dashboard.router)
app.include_router(report_ingest.router)
app.include_router(reports_final.router)
app.include_router(workflow.router)
app.include_router(public_reports.router)

@app.get("/")
def read_root():
    return {"status": "online", "system": "Diagnostic Centre Automated Ingestion Pipeline", "version": "3.2.0",
            "workflow": "photo -> OCR -> technician verification -> PDF credit -> payment -> optional WhatsApp", "docs": "/docs"}
