import json
import os
import hashlib
import uuid
from datetime import datetime

def generate_minimal_pdf(centre_name: str, patient_name: str, patient_code: str, verified_data) -> bytes:
    if isinstance(verified_data, str):
        try:
            verified_data = json.loads(verified_data)
        except Exception:
            verified_data = {}
    elif verified_data is None:
        verified_data = {}
    """
    Generates a valid, standards-compliant PDF/1.4 byte stream without external dependencies.
    """
    lines = [
        f"{centre_name.upper()}",
        "=" * 45,
        f"Patient ID   : {patient_code}",
        f"Patient Name : {patient_name}",
        f"Date         : {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"Status       : Verified & Certified",
        "-" * 45,
        "TEST PARAMETERS & RESULTS",
        "-" * 45,
    ]
    
    panels = verified_data.get("panels", [])
    for panel in panels:
        pname = panel.get("panel_name", "Test Panel")
        lines.append(f"\n[{pname}]")
        for param in panel.get("parameters", []):
            name = param.get("name", "")
            res = param.get("result", "")
            unit = param.get("unit") or ""
            ref = param.get("reference_range") or "N/A"
            lines.append(f"  {name:<22}: {res} {unit} (Ref: {ref})")
            
    notes = verified_data.get("technician_notes")
    if notes:
        lines.append("\nTechnician Notes:")
        lines.append(f"  {notes}")

    lines.append("\n" + "=" * 45)
    lines.append("Electronically Generated & Certified Diagnostic Report")

    # Build PDF Content Stream
    stream_content = "BT\n/F1 10 Tf\n20 TL\n50 750 Td\n"
    for line in lines:
        if line == "":
            stream_content += "T*\n"
        else:
            # Escape PDF parenthesis and backslashes
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream_content += f"({escaped}) '\n"
    stream_content += "ET"

    stream_bytes = stream_content.encode("latin-1", errors="replace")
    stream_len = len(stream_bytes)

    # Object 1: Catalog, 2: Pages, 3: Page, 4: Font, 5: Contents
    obj1 = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    obj2 = b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    obj3 = (
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
    )
    obj4 = b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>\nendobj\n"
    obj5 = f"5 0 obj\n<< /Length {stream_len} >>\nstream\n".encode("ascii") + stream_bytes + b"\nendstream\nendobj\n"

    header = b"%PDF-1.4\n"
    offsets = [0]
    body = bytearray(header)
    
    for obj in [obj1, obj2, obj3, obj4, obj5]:
        offsets.append(len(body))
        body.extend(obj)
        
    xref_offset = len(body)
    xref = f"xref\n0 6\n0000000000 65535 f \n".encode("ascii")
    for off in offsets[1:]:
        xref += f"{off:010d} 00000 n \n".encode("ascii")
        
    trailer = f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    body.extend(xref)
    body.extend(trailer)
    return bytes(body)

def compile_and_save_report(centre_id: int, centre_name: str, patient_name: str, patient_code: str, verified_data: dict):
    pdf_bytes = generate_minimal_pdf(centre_name, patient_name, patient_code, verified_data)
    
    base_dir = os.path.abspath(os.path.join("storage", "reports", str(centre_id)))
    os.makedirs(base_dir, exist_ok=True)
    
    unique_suffix = uuid.uuid4().hex[:8]
    filename = f"{patient_code}_{unique_suffix}.pdf"
    file_path = os.path.join(base_dir, filename)
    
    with open(file_path, "wb") as f:
        f.write(pdf_bytes)
        
    sha256_hash = hashlib.sha256(pdf_bytes).hexdigest()
    file_size = len(pdf_bytes)
    
    return {
        "file_path": file_path,
        "filename": filename,
        "file_size": file_size,
        "file_hash": sha256_hash,
        "pdf_bytes": pdf_bytes
    }
