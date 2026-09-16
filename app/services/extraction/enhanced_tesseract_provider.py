import re

from app.services.extraction.tesseract_provider import TesseractExtractionProvider
from app.services.extraction.base import DemographicField, NumericDemographicField, ExtractedPatient


class EnhancedTesseractExtractionProvider(TesseractExtractionProvider):
    """Tesseract provider with broader patient-header parsing."""

    def _parse_patient(self, text: str) -> ExtractedPatient:
        patient_code = None
        patient_name = None
        age = None
        gender = None
        phone = None
        email = None

        # Common OCR variants for patient/sample ID.
        id_patterns = [
            r"(?:Patient\s*(?:ID|I[Dd]|No|Number)|PatientI[Dd]?|UHID|MRN|Reg(?:istration)?\s*(?:No|ID))\s*[:#\-]?\s*([A-Za-z0-9][A-Za-z0-9._/-]*)",
            r"\bID\s*[:#\-]\s*([A-Za-z0-9][A-Za-z0-9._/-]*)",
        ]
        for pattern in id_patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                patient_code = m.group(1).strip(" .,:;")
                break

        # Explicit name labels are preferred because they are much safer than
        # guessing from arbitrary header text.
        name_patterns = [
            r"\b(?:Patient\s*)?Name\s*[:\-]\s*(.+?)(?=\s+(?:Age|DOB|Date\s*of\s*Birth|Gender|Sex|Phone|Mobile|Contact|Email|E-mail|Patient\s*ID|ID|UHID|MRN)\s*[:#\-]?|$)",
            r"\bPt\.?\s*Name\s*[:\-]\s*(.+?)(?=\s+(?:Age|Gender|Sex|Phone|Mobile|ID|UHID|MRN)\b|$)",
        ]
        for pattern in name_patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                candidate = re.sub(r"\s+", " ", m.group(1)).strip(" .:-")
                if candidate:
                    patient_name = candidate
                    break

        # Age/Sex or Age/Gender combined headers.
        combined = re.search(
            r"(?:Age\s*/\s*(?:Sex|Gender)|(?:Sex|Gender)\s*/\s*Age)\s*[:\-]?\s*(\d{1,3})\s*(?:Y|YR|YRS|YEARS)?\s*/\s*([A-Za-z]+)",
            text,
            re.IGNORECASE,
        )
        if combined:
            age = int(combined.group(1))
            gender = self._normalize_gender(combined.group(2))

        if age is None:
            age_patterns = [
                r"\bAge\s*[:#\-]?\s*(\d{1,3})\s*(?:Y|YR|YRS|YEARS)?\b",
                r"#ge\s*[:#\-]?\s*(\d{1,3})\b",
            ]
            for pattern in age_patterns:
                m = re.search(pattern, text, re.IGNORECASE)
                if m:
                    age = int(m.group(1))
                    break

        gender_match = re.search(
            r"(?:Gender|Sex)\s*[:#\-]?\s*(Male|Female|M|F)\b",
            text,
            re.IGNORECASE,
        )
        if gender_match:
            gender = self._normalize_gender(gender_match.group(1))

        phone_match = re.search(
            r"(?:Phone|Mobile|Mob|Contact|Tel)\s*(?:No|Number)?\s*[:#\-]?\s*(\+?\d[\d\s().-]{7,}\d)",
            text,
            re.IGNORECASE,
        )
        if phone_match:
            phone = re.sub(r"[^0-9+]", "", phone_match.group(1))

        email_match = re.search(
            r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
            text,
            re.IGNORECASE,
        )
        if email_match:
            email = email_match.group(0).strip()

        return ExtractedPatient(
            patient_code=DemographicField(value=patient_code, confidence=0.90 if patient_code else None),
            patient_name=DemographicField(value=patient_name, confidence=0.90 if patient_name else None),
            age=NumericDemographicField(value=age, confidence=0.85 if age is not None else None),
            gender=DemographicField(value=gender, confidence=0.90 if gender else None),
            phone=DemographicField(value=phone, confidence=0.85 if phone else None),
            email=DemographicField(value=email, confidence=0.90 if email else None),
        )
