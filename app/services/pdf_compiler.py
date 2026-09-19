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

    lines = [
        f"{centre_name.upper()}",
        "=" * 45,
        f"Patient ID   : {patient_code}",
        f"Patient Name : {patient_name}",
        f"Date         : {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "Status       : Verified & Certified",
        "-" * 45,
        "TEST PARAMETERS & RESULTS",
        "-" * 45,
    ]
    for panel in verified_data.get("panels", []):
        lines.append(f"\n[{panel.get('panel_name', 'Test Panel')}]")
        for param in panel.get("parameters", []):
            lines.append(
                f"  {param.get('name', ''):<22}: "
                f"{param.get('result', '')} {param.get('unit') or ''} "
                f"(Ref: {param.get('reference_range') or 'N/A'})"
            )

    notes = verified_data.get("technician_notes")
    if notes:
        lines.extend(["\nTechnician Notes:", f"  {notes}"])
    lines.extend(["\n" + "=" * 45, "Electronically Generated & Certified Diagnostic Report"])

    stream_content = "BT\n/F1 10 Tf\n20 TL\n50 750 Td\n"
    for line in lines:
        if not line:
            stream_content += "T*\n"
        else:
            escaped = (
                str(line)
                .replace("\\", "\\\\")
                .replace("(", "\\(")
                .replace(")", "\\)")
            )
            stream_content += f"({escaped}) '\n"
    stream_content += "ET"
    stream_bytes = stream_content.encode("latin-1", errors="replace")

    objs = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>\nendobj\n",
        f"5 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode("ascii")
        + stream_bytes
        + b"\nendstream\nendobj\n",
    ]
    body = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objs:
        offsets.append(len(body))
        body.extend(obj)
    xref_offset = len(body)
    body.extend(b"xref\n0 6\n0000000000 65535 f \n")
    for off in offsets[1:]:
        body.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    body.extend(
        f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(body)


def _safe_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _flatten_verified_fields(patient_name: str, patient_code: str, verified_data: dict):
    """Return the verified values that are allowed to reach the final PDF."""
    fields = {
        "patient_name": _safe_text(verified_data.get("patient_name")) or _safe_text(patient_name),
        "patient_id": _safe_text(verified_data.get("patient_code")) or _safe_text(patient_code),
        "patient_code": _safe_text(verified_data.get("patient_code")) or _safe_text(patient_code),
        "age_gender": " / ".join(
            x for x in [
                _safe_text(verified_data.get("patient_age")),
                _safe_text(verified_data.get("patient_gender")),
            ] if x
        ),
        "age": _safe_text(verified_data.get("patient_age")),
        "gender": _safe_text(verified_data.get("patient_gender")),
        "phone": _safe_text(verified_data.get("patient_phone")),
        "email": _safe_text(verified_data.get("patient_email")),
        "date": datetime.utcnow().strftime("%d-%m-%Y"),
        "status": "Verified & Certified",
    }

    panels = verified_data.get("panels") or []
    tests = []
    for panel in panels:
        panel_name = _safe_text(panel.get("panel_name")) or "Test Panel"
        for param in panel.get("parameters") or []:
            name = _safe_text(param.get("name"))
            result = _safe_text(param.get("result"))
            unit = _safe_text(param.get("unit"))
            reference = _safe_text(param.get("reference_range"))
            if not name:
                continue
            tests.append({
                "panel": panel_name,
                "name": name,
                "result": result,
                "unit": unit,
                "reference": reference,
            })

    return fields, tests, _safe_text(verified_data.get("technician_notes"))


def _field_key(label: str) -> str:
    key = "".join(ch.lower() if ch.isalnum() else "_" for ch in label).strip("_")
    aliases = {
        "patient_name": "patient_name",
        "patient_full_name": "patient_name",
        "name": "patient_name",
        "patient_id": "patient_id",
        "patient_code": "patient_id",
        "patient_no": "patient_id",
        "patient_number": "patient_id",
        "uhid": "patient_id",
        "date": "date",
        "report_date": "date",
        "age_gender": "age_gender",
        "age": "age",
        "gender": "gender",
        "phone": "phone",
        "mobile": "phone",
        "phone_number": "phone",
        "email": "email",
        "status": "status",
    }
    return aliases.get(key, key)


def _fill_acroform(template_reader, fields, tests):
    """Fill real PDF form fields when a centre template contains AcroForm fields."""
    try:
        acro = template_reader.trailer["/Root"].get("/AcroForm")
        if not acro:
            return False
        form = acro.get_object()
        names = []
        for field in form.get("/Fields", []):
            obj = field.get_object()
            name = obj.get("/T")
            if name:
                names.append(str(name))

        values = dict(fields)
        for index, test in enumerate(tests, start=1):
            values[f"test_{index}_name"] = test["name"]
            values[f"test_{index}_result"] = test["result"]
            values[f"test_{index}_unit"] = test["unit"]
            values[f"test_{index}_reference"] = test["reference"]

        filled = False
        for field_name in names:
            key = _field_key(field_name)
            value = values.get(field_name)
            if value is None:
                value = values.get(key)
            if value is None:
                for index, test in enumerate(tests, start=1):
                    if key in {
                        f"test_{index}_name",
                        f"test_{index}_result",
                        f"test_{index}_unit",
                        f"test_{index}_reference",
                    }:
                        value = values.get(key)
                        break
            if value is not None:
                for page in template_reader.pages:
                    try:
                        from pypdf import PdfReader
                        PdfReader  # keep import local and explicit for minimal dependency assumptions
                        page_fields = page.get("/Annots") or []
                        for annot in page_fields:
                            a = annot.get_object()
                            if str(a.get("/T") or "") == field_name:
                                a.update({"/V": str(value)})
                                filled = True
                    except Exception:
                        continue
        return filled
    except Exception:
        return False


def _extract_label_positions(page):
    """Find labels and the actual blank/value coordinate on the same PDF row."""
    tokens = []

    def visitor_text(text, cm, tm, font_dict, font_size):
        clean = " ".join(str(text or "").split()).strip()
        if not clean:
            return
        tokens.append({"text": clean, "x": float(tm[4]), "y": float(tm[5])})

    try:
        page.extract_text(visitor_text=visitor_text)
    except Exception:
        return {}

    positions = {}
    for token in tokens:
        raw = token["text"]
        label = raw.rstrip(":").strip()
        key = _field_key(label)
        if not key or key in {
            "patient_details", "test_results", "test", "result",
            "unit", "reference_range"
        }:
            continue

        # Use the template's real underscore/value column rather than
        # estimating a position from the label width.
        candidates = [
            t for t in tokens
            if t["x"] > token["x"] + 2
            and abs(t["y"] - token["y"]) <= 2
            and set(t["text"].replace(" ", "")) <= {"_"}
            and len(t["text"].replace(" ", "")) >= 3
        ]
        value_x = (
            candidates[0]["x"]
            if candidates
            else token["x"] + max(20, len(label) * 4.5)
        )
        positions.setdefault(key, (value_x, token["y"], label))

    return positions

def _pdf_text_overlay(page_width, page_height, fields, tests, label_positions, notes):
    """Create a transparent PDF page that writes verified values onto the centre template."""
    from io import BytesIO

    entries = []

    def add_text(x, y, text, size=9):
        text = _safe_text(text)
        if text:
            entries.append((max(8, float(x)), max(8, float(y)), text, size))

    # Put values beside labels when the uploaded template contains searchable labels.
    for key, value in fields.items():
        if not value:
            continue
        pos = label_positions.get(key)
        if pos:
            add_text(pos[0], pos[1], value, 9)

    # Test rows: first use matching searchable test labels. This makes common
    # centre templates work without hard-coded coordinates.
    unmatched = []
    for test in tests:
        key = _field_key(test["name"])
        pos = label_positions.get(key)
        if pos:
            result = " ".join(x for x in [test["result"], test["unit"]] if x)
            if test["reference"]:
                result += f"  ({test['reference']})"
            add_text(pos[0], pos[1], result, 9)
        else:
            unmatched.append(test)

    # Never draw a second report block over a centre's template.
    # Unmatched custom fields remain untouched until the centre maps them.

    if notes:
        add_text(40, 32, f"Technician Notes: {notes}", 8)

    if not entries:
        return None

    # Build a one-page transparent PDF using the same page size as the template.
    commands = [
        "q",
        "BT",
        "/F1 9 Tf",
        "0 g",
    ]
    for x, y, text, size in entries:
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands.append(f"/F1 {size:g} Tf")
        commands.append(f"1 0 0 1 {x:.2f} {y:.2f} Tm")
        commands.append(f"({escaped}) Tj")
    commands.extend(["ET", "Q"])
    stream = "\n".join(commands).encode("latin-1", errors="replace")

    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        (
            f"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width:g} {page_height:g}] "
            f"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
        ).encode("ascii"),
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        (
            f"5 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"\nendstream\nendobj\n"
        ),
    ]
    body = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(body))
        body.extend(obj)
    xref = len(body)
    body.extend(b"xref\n0 6\n0000000000 65535 f \n")
    for off in offsets[1:]:
        body.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    body.extend(
        f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    return bytes(body)


def _apply_template(template_path: str, generated_bytes: bytes, patient_name: str, patient_code: str, verified_data: dict) -> bytes:
    """Render verified data onto the uploaded centre template.

    Priority:
    1. PDF form fields, when present.
    2. Searchable labels in the template, placing values beside the labels.
    3. A compact fallback result block while preserving the uploaded template.
    """
    try:
        from io import BytesIO
        from pypdf import PdfReader, PdfWriter

        template_reader = PdfReader(template_path)
        if not template_reader.pages:
            return generated_bytes

        fields, tests, notes = _flatten_verified_fields(patient_name, patient_code, verified_data)
        writer = PdfWriter()

        # Work on a cloned reader so the stored centre template is never modified.
        # IMPORTANT: a template may contain patient labels but no mapped test-result
        # fields. In that case the old code returned the template alone, silently
        # dropping the verified test results. For safety, fall back to the generated
        # authoritative report unless at least one test can actually be rendered.
        form_filled = _fill_acroform(template_reader, fields, tests)

        first_page = template_reader.pages[0]
        labels = _extract_label_positions(first_page)

        matched_test_count = 0
        for test in tests:
            key = _field_key(test["name"])
            if key in labels:
                matched_test_count += 1

        acro_test_mapped = False
        try:
            root = template_reader.trailer["/Root"].get_object()
            acro = root.get("/AcroForm")
            if acro:
                form = acro.get_object()
                for field in form.get("/Fields", []):
                    name = str(field.get_object().get("/T") or "")
                    if name.startswith("test_"):
                        acro_test_mapped = True
                        break
        except Exception:
            acro_test_mapped = False

        if tests and not matched_test_count and not acro_test_mapped:
            # Do not produce a PDF that looks valid but contains no test results.
            return generated_bytes

        for page_index, template_page in enumerate(template_reader.pages):
            width = float(template_page.mediabox.width)
            height = float(template_page.mediabox.height)

            if page_index == 0 and not form_filled:
                overlay = _pdf_text_overlay(width, height, fields, tests, labels, notes)
                if overlay:
                    overlay_page = PdfReader(BytesIO(overlay)).pages[0]
                    template_page.merge_page(overlay_page, over=True)

            writer.add_page(template_page)

        out = BytesIO()
        writer.write(out)
        return out.getvalue()
    except Exception:
        # A bad template must never destroy the verified report. Fall back to
        # the authoritative generated PDF rather than returning a broken file.
        return generated_bytes


def compile_and_save_report(
    centre_id: int,
    centre_name: str,
    patient_name: str,
    patient_code: str,
    verified_data: dict,
    template_path: str = None,
):
    pdf_bytes = generate_minimal_pdf(centre_name, patient_name, patient_code, verified_data)

    # A centre uploads its template once. Every subsequent report automatically
    # resolves the template from its own tenant directory.
    if not template_path:
        template_path = os.path.join("storage", "templates", str(centre_id), "template.pdf")

    if template_path and os.path.isfile(template_path):
        pdf_bytes = _apply_template(
            template_path,
            pdf_bytes,
            patient_name=patient_name,
            patient_code=patient_code,
            verified_data=verified_data,
        )

    base_dir = os.path.abspath(os.path.join("storage", "reports", str(centre_id)))
    os.makedirs(base_dir, exist_ok=True)
    filename = f"{patient_code}_{uuid.uuid4().hex[:8]}.pdf"
    file_path = os.path.join(base_dir, filename)
    with open(file_path, "wb") as f:
        f.write(pdf_bytes)

    return {
        "file_path": file_path,
        "filename": filename,
        "file_size": len(pdf_bytes),
        "file_hash": hashlib.sha256(pdf_bytes).hexdigest(),
        "pdf_bytes": pdf_bytes,
    }
