import os

target = "/storage/emulated/0/diagnostic_backend/app/routers/reports.py"

# Read in lines, dropping any byte sequence that contains nulls
with open(target, "rb") as f:
    raw_lines = f.readlines()

clean_lines = []
for line in raw_lines:
    if b"def sanitize_content_disposition_filename" in line:
        break
    if b"@router.get(\"/{report_id}\"" in line or b"@router.get('/{report_id}'" in line:
        break
    # Strip null bytes strictly
    filtered = line.replace(b"\x00", b"")
    clean_lines.append(filtered)

code_base = b"".join(clean_lines).rstrip()

phase4a_code = b'''

import os
import re
import unicodedata
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi import Query

def sanitize_content_disposition_filename(filename: str) -> str:
    if not filename:
        return "report.pdf"
    clean = re.sub(r'[\r\n\x00]', '', filename)
    clean = os.path.basename(clean)
    clean = unicodedata.normalize('NFKD', clean).encode('ascii', 'ignore').decode('ascii')
    ascii_clean = re.sub(r'[^a-zA-Z0-9_.-]', '_', clean)
    return ascii_clean or "report.pdf"

@router.get("/{report_id}")
def get_report_metadata(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    report = db.query(models.Report).filter(
        models.Report.id == report_id,
        models.Report.centre_id == current_user.centre_id
    ).first()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    patient = db.query(models.Patient).filter(
        models.Patient.id == report.patient_id,
        models.Patient.centre_id == current_user.centre_id
    ).first()

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
        "uploaded_at": getattr(report, "created_at", getattr(report, "uploaded_at", None)),
        "file_size_bytes": file_size,
        "is_available": os.path.exists(report.file_path) if report.file_path else False
    }

@router.get("/{report_id}/download")
def download_report(
    report_id: int,
    inline: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    report = db.query(models.Report).filter(
        models.Report.id == report_id,
        models.Report.centre_id == current_user.centre_id
    ).first()

    if not report or not report.file_path:
        raise HTTPException(status_code=404, detail="Report not found or access denied")

    tenant_storage_root = Path(f"/storage/emulated/0/diagnostic_backend/storage/reports/{current_user.centre_id}").resolve()
    target_path = Path(report.file_path).resolve()

    try:
        target_path.relative_to(tenant_storage_root)
    except ValueError:
        raise HTTPException(status_code=403, detail="Storage security violation: File path escapes tenant scope")

    if not target_path.is_file():
        raise HTTPException(status_code=404, detail="Report document file missing on storage")

    ext = target_path.suffix.lower()
    media_map = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg"
    }
    media_type = media_map.get(ext, "application/octet-stream")

    safe_name = sanitize_content_disposition_filename(report.filename or target_path.name)
    disp = "inline" if inline else "attachment"

    return FileResponse(
        path=str(target_path),
        media_type=media_type,
        headers={
            "Content-Disposition": f'{disp}; filename="{safe_name}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-cache, no-store, must-revalidate"
        }
    )
'''

full_payload = code_base + b"\n\n" + phase4a_code

# Remove file completely first so Android filesystem inode doesn't retain old size
if os.path.exists(target):
    os.remove(target)

with open(target, "wb") as f:
    f.write(full_payload)
    f.flush()
    os.fsync(f.fileno())

print("Clean write completed without null bytes.")
