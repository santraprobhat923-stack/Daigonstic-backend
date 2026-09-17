import json
import os
import hashlib
import uuid
from datetime import datetime


def generate_minimal_pdf(centre_name: str, patient_name: str, patient_code: str, verified_data) -> bytes:
    if isinstance(verified_data, str):
        try: verified_data = json.loads(verified_data)
        except Exception: verified_data = {}
    elif verified_data is None: verified_data = {}
    lines = [f"{centre_name.upper()}", "=" * 45, f"Patient ID   : {patient_code}",
             f"Patient Name : {patient_name}", f"Date         : {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
             "Status       : Verified & Certified", "-" * 45, "TEST PARAMETERS & RESULTS", "-" * 45]
    for panel in verified_data.get("panels", []):
        lines.append(f"\n[{panel.get('panel_name', 'Test Panel')}]")
        for param in panel.get("parameters", []):
            lines.append(f"  {param.get('name',''):<22}: {param.get('result','')} {param.get('unit') or ''} (Ref: {param.get('reference_range') or 'N/A'})")
    notes = verified_data.get("technician_notes")
    if notes: lines.extend(["\nTechnician Notes:", f"  {notes}"])
    lines.extend(["\n" + "=" * 45, "Electronically Generated & Certified Diagnostic Report"])
    stream_content = "BT\n/F1 10 Tf\n20 TL\n50 750 Td\n"
    for line in lines:
        if not line: stream_content += "T*\n"
        else:
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream_content += f"({escaped}) '\n"
    stream_bytes = (stream_content + "ET").encode("latin-1", errors="replace")
    objs = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>\nendobj\n",
        f"5 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode("ascii") + stream_bytes + b"\nendstream\nendobj\n",
    ]
    body = bytearray(b"%PDF-1.4\n"); offsets = [0]
    for obj in objs: offsets.append(len(body)); body.extend(obj)
    xref_offset = len(body); body.extend(b"xref\n0 6\n0000000000 65535 f \n")
    for off in offsets[1:]: body.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    body.extend(f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
    return bytes(body)


def _apply_template(template_path: str, generated_bytes: bytes) -> bytes:
    try:
        from io import BytesIO
        from pypdf import PdfReader, PdfWriter
        template_reader = PdfReader(template_path); generated_reader = PdfReader(BytesIO(generated_bytes))
        if not template_reader.pages or not generated_reader.pages: return generated_bytes
        writer = PdfWriter(); first = template_reader.pages[0]
        first.merge_page(generated_reader.pages[0], over=True); writer.add_page(first)
        for page in template_reader.pages[1:]: writer.add_page(page)
        out = BytesIO(); writer.write(out); return out.getvalue()
    except Exception:
        return generated_bytes


def compile_and_save_report(centre_id: int, centre_name: str, patient_name: str, patient_code: str,
                            verified_data: dict, template_path: str = None):
    pdf_bytes = generate_minimal_pdf(centre_name, patient_name, patient_code, verified_data)
    # If the centre uploaded a template, use it automatically for every report.
    if not template_path:
        template_path = os.path.join("storage", "templates", str(centre_id), "template.pdf")
    if template_path and os.path.isfile(template_path): pdf_bytes = _apply_template(template_path, pdf_bytes)
    base_dir = os.path.abspath(os.path.join("storage", "reports", str(centre_id))); os.makedirs(base_dir, exist_ok=True)
    filename = f"{patient_code}_{uuid.uuid4().hex[:8]}.pdf"; file_path = os.path.join(base_dir, filename)
    with open(file_path, "wb") as f: f.write(pdf_bytes)
    return {"file_path": file_path, "filename": filename, "file_size": len(pdf_bytes),
            "file_hash": hashlib.sha256(pdf_bytes).hexdigest(), "pdf_bytes": pdf_bytes}
