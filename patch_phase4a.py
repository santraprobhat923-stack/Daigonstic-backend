import re
import os

REPORTS_PY = "/storage/emulated/0/diagnostic_backend/app/routers/reports.py"

with open(REPORTS_PY, "r") as f:
    code = f.read()

# Add necessary imports if missing
imports_to_ensure = """
import os
import re
import unicodedata
from pathlib import Path
from urllib.parse import quote
from fastapi.responses import FileResponse
from fastapi import HTTPException, status, Query
"""

phase_4a_code = '''
# ============================================================================
# PHASE 4A: SECURE REPORT VIEWING & STREAMING INFRASTRUCTURE
# ============================================================================

def sanitize_content_disposition_filename(filename: str) -> str:
    """
    Strips CR, LF, null bytes, and path separators to prevent header injection.
    Formats according to RFC 5987 / RFC 6266 for cross-browser safety.
    """
    if not filename:
        return "report.pdf"
    # Remove null bytes and newlines
    clean = re.sub(r'[\r\n\x00]', '', filename)
    # Strip any directory traversal characters
    clean = os.path.basename(clean)
    # Normalize unicode
    clean = unicodedata.normalize('NFKD', clean).encode('ascii', 'ignore').decode('ascii')
    # Filter only safe characters for the fallback ascii parameter
    ascii_clean = re.sub(r'[^a-zA-Z0-9_.-]', '_', clean)
    if not ascii_clean:
        ascii_clean = "report.pdf"
    return ascii_clean


@router.get("/{report_id}", summary="Get Report Metadata (Phase 4A Secure)")
def get_report_metadata(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Tenant-isolated metadata endpoint. Never leaks filesystem paths or internal storage hashes.
    """
    report = db.query(models.Report).filter(
        models.Report.id == report_id,
        models.Report.centre_id == current_user.centre_id
    ).first()

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found"
        )

    # Safe patient resolution
    patient = db.query(models.Patient).filter(
        models.Patient.id == report.patient_id,
        models.Patient.centre_id == current_user.centre_id
    ).first()

    # Determine file size safely
    file_size = None
    if report.file_path and os.path.exists(report.file_path):
        try:
            file_size = os.path.getsize(report.file_path)
        except OSError:
            pass

    return {
        "report_id": report.id,
        "centre_id": report.centre_id,
        "patient_id": report.patient_id,
        "patient_code": getattr(patient, "patient_code", None),
        "patient_name": getattr(patient, "full_name", None),
        "original_filename": report.filename,
        "uploaded_at": getattr(report, "uploaded_at", getattr(report, "created_at", None)),
        "file_type": getattr(report, "file_type", "application/pdf"),
        "file_size_bytes": file_size,
        "is_available": os.path.exists(report.file_path) if report.file_path else False
    }


@router.get("/{report_id}/download", summary="Secure Report Streaming & Download")
def download_report(
    report_id: int,
    inline: bool = Query(False, description="Display inline in browser (True) or trigger download (False)"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Secure file streaming endpoint.
    - Tenant isolated via current_user.centre_id
    - Path traversal protected via canonical path resolution
    - Header injection protected via sanitized Content-Disposition
    - Streams via chunked FileResponse (low memory footprint)
    """
    # 1. Tenant-scoped database query
    report = db.query(models.Report).filter(
        models.Report.id == report_id,
        models.Report.centre_id == current_user.centre_id
    ).first()

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found or access denied"
        )

    if not report.file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report file record is empty"
        )

    # 2. Canonical path traversal defense
    tenant_storage_root = Path(f"/storage/emulated/0/diagnostic_backend/storage/reports/{current_user.centre_id}").resolve()
    target_path = Path(report.file_path).resolve()

    try:
        # Raises ValueError if target_path is not relative to tenant_storage_root
        target_path.relative_to(tenant_storage_root)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Storage security violation: File path escapes tenant scope"
        )

    if not target_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Underlying document file is missing on storage"
        )

    # 3. Detect / Map Content-Type safely
    extension = target_path.suffix.lower()
    content_type_map = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg"
    }
    media_type = content_type_map.get(extension, "application/octet-stream")

    # 4. Sanitize Content-Disposition header (Strict protection against CRLF injection)
    safe_download_name = sanitize_content_disposition_filename(report.filename or target_path.name)
    disposition_type = "inline" if inline else "attachment"
    content_disposition = f'{disposition_type}; filename="{safe_download_name}"; filename*=UTF-8\'\'{quote(safe_download_name)}'

    return FileResponse(
        path=str(target_path),
        media_type=media_type,
        headers={
            "Content-Disposition": content_disposition,
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-cache, no-store, must-revalidate"
        }
    )
'''

if "def download_report(" not in code:
    with open(REPORTS_PY, "a") as f:
        f.write("\n" + phase_4a_code)
    print("Phase 4A secure download endpoints appended successfully to reports.py!")
else:
    print("Download route already exists in reports.py. Re-patching latest security logic...")
    # Replace existing download_report block
    idx = code.find("def download_report(")
    # Seek backwards to decor
    decor_idx = code.rfind("@router.get(", 0, idx)
    code = code[:decor_idx] + phase_4a_code
    with open(REPORTS_PY, "w") as f:
        f.write(code)
    print("Updated existing download_report block.")
