import re
import os
from typing import Optional, Dict, Any

try:
    from pypdf import PdfReader
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

class PatientIdentityResult:
    def __init__(
        self,
        patient_code: Optional[str] = None,
        patient_name: Optional[str] = None,
        phone: Optional[str] = None,
        gender: Optional[str] = None,
        dob: Optional[str] = None,
        method: str = "none",
        is_ambiguous: bool = False,
        failure_reason: Optional[str] = None
    ):
        self.patient_code = patient_code
        self.patient_name = patient_name
        self.phone = phone
        self.gender = gender
        self.dob = dob
        self.method = method
        self.is_ambiguous = is_ambiguous
        self.failure_reason = failure_reason

def extract_from_filename(filename: str, centre_pattern: Optional[str] = None) -> Optional[str]:
    clean_name = os.path.basename(filename)

    # 1. Centre-configured custom pattern if provided
    if centre_pattern:
        try:
            m = re.search(centre_pattern, clean_name, re.IGNORECASE)
            if m:
                return m.group(0).upper()
        except Exception:
            pass

    # 2. Match standard medical patterns: PAT-10452, LAB-88301, PID-12345, or PAT10452
    m = re.search(r'(PAT|LAB|PID)[-_]?([0-9A-Za-z]+)', clean_name, re.IGNORECASE)
    if m:
        prefix = m.group(1).upper()
        code = m.group(2).upper()
        return f"{prefix}-{code}"

    return None

def extract_from_pdf_text(file_path: str) -> Dict[str, Any]:
    data = {"candidate_ids": [], "name": None, "phone": None, "gender": None}
    if not HAS_PYPDF or not os.path.exists(file_path):
        return data

    try:
        reader = PdfReader(file_path)
        extracted = ""
        for page in reader.pages[:2]:
            extracted += "\n" + (page.extract_text() or "")

        if not extracted.strip():
            return data

        # Extract labeled Patient ID from text stream
        ids = re.findall(r'(?:Patient\s*ID|PID|Reg\.?\s*No|UHID)\s*[:#-]?\s*([A-Za-z0-9\-_/]+)', extracted, re.IGNORECASE)
        unique_ids = list(dict.fromkeys([i.strip().upper() for i in ids if len(i.strip()) >= 3]))
        data["candidate_ids"] = unique_ids

        # Optional metadata
        m_name = re.search(r'(?:Patient\s*Name|Name)\s*[:#-]?\s*([A-Za-z\s\.]+)(?:\n|\r|Age|Sex|Gender|$)', extracted, re.IGNORECASE)
        if m_name:
            c_name = m_name.group(1).strip()
            if 2 < len(c_name) < 50:
                data["name"] = c_name
    except Exception:
        pass

    return data

def resolve_patient_identity(
    filename: str,
    temp_file_path: Optional[str] = None,
    centre_pattern: Optional[str] = None,
    explicit_code: Optional[str] = None
) -> PatientIdentityResult:
    # Tier 1: Explicit parameter (ignore swagger dummy strings)
    if explicit_code and str(explicit_code).strip().lower() not in ["string", "none", "null", ""]:
        return PatientIdentityResult(
            patient_code=str(explicit_code).strip().upper(),
            method="explicit"
        )

    # Tier 2: Filename pattern matching
    code_from_name = extract_from_filename(filename, centre_pattern)
    if code_from_name:
        return PatientIdentityResult(
            patient_code=code_from_name,
            method="filename_pattern"
        )

    # Tier 3: Machine-Readable PDF Text
    if temp_file_path and temp_file_path.lower().endswith(".pdf"):
        pdf_info = extract_from_pdf_text(temp_file_path)
        candidates = pdf_info.get("candidate_ids", [])
        if len(candidates) == 1:
            return PatientIdentityResult(
                patient_code=candidates[0],
                patient_name=pdf_info.get("name"),
                method="pdf_text_extraction"
            )
        elif len(candidates) > 1:
            return PatientIdentityResult(
                is_ambiguous=True,
                failure_reason=f"AMBIGUOUS_PATIENT_ID: Multiple IDs found in text: {candidates}"
            )

    # Tier 4: Reject
    return PatientIdentityResult(
        is_ambiguous=True,
        failure_reason="AMBIGUOUS_PATIENT_ID: Filename does not match pattern and no singular ID found in document."
    )
