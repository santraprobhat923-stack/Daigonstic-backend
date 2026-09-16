from pathlib import Path
from typing import Any, Dict
import re

from PIL import Image, ImageOps
import pytesseract

from app.services.extraction.base import (
    DemographicField,
    NumericDemographicField,
    ExtractedPatient,
    ExtractedParameter,
    ExtractedPanel,
    ExtractionProcessingError,
    ExtractionProvider,
    ExtractionResult,
)


class TesseractExtractionProvider(ExtractionProvider):
    """
    REAL OCR PROVIDER

    Pipeline:
    image -> Tesseract OCR -> deterministic structured parsing

    Medical values are never invented. Only values explicitly present
    in the OCR text are structured.
    """

    @property
    def provider_name(self) -> str:
        return "TESSERACT_OCR"

    @property
    def provider_version(self) -> str:
        try:
            return str(pytesseract.get_tesseract_version())
        except Exception:
            return "UNKNOWN"

    def _parse_patient(self, text: str) -> ExtractedPatient:
        patient_code = None
        patient_name = None
        age = None
        gender = None

        # Patient ID: supports clean and legacy OCR variants such as:
        # "Patient ID: P-101"
        # "PatientID: P-102 Name: Prya Das"
        # "PatientI[: P-101 Name: ahul Sharma"
        id_match = re.search(
            r"Patient\s*I[Dd\[\:]*\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9._/-]*)",
            text,
            re.IGNORECASE,
        )
        if id_match:
            patient_code = id_match.group(1).strip(" .,:;")

        # Patient name can appear on the same line as the ID,
        # e.g. "PatientID: P-102 Name: Prya Das" or
        # "PatientI[: P-101 Name: ahul Sharma".
        # Parse the explicit Name: token independently of the corrupted ID text.
        name_match = re.search(
            r"\bName\s*[:\-]\s*(.+?)(?=\s+(?:Age|#ge|Gender|Ref|Test|TESTNAME)\b|$)",
            text,
            re.IGNORECASE,
        )

        if name_match:
            patient_name = name_match.group(1).strip(" .:-")

        # Clean format:
        # "Age/Sex: 29 Y / Female"
        age_sex_match = re.search(
            r"Age\s*/\s*Sex\s*[:\-]\s*(\d{1,3})\s*Y?\s*/\s*([A-Za-z]+)",
            text,
            re.IGNORECASE,
        )
        if age_sex_match:
            age = int(age_sex_match.group(1))
            gender = self._normalize_gender(age_sex_match.group(2))

        # Legacy OCR:
        # "#ge:28 Gender F"
        # "#ge: 40 Gender M"
        if age is None:
            legacy_age_match = re.search(
                r"#ge\s*[:\-]?\s*(\d{1,3})",
                text,
                re.IGNORECASE,
            )
            if legacy_age_match:
                age = int(legacy_age_match.group(1))

        gender_match = re.search(
            r"Gender\s*[:\-]?\s*([MF])(?:\b|[^A-Za-z])",
            text,
            re.IGNORECASE,
        )
        if gender_match:
            gender = self._normalize_gender(gender_match.group(1))

        # Final fallback for a clean standalone Age field.
        if age is None:
            age_match = re.search(
                r"\bAge\s*[:\-]?\s*(\d{1,3})",
                text,
                re.IGNORECASE,
            )
            if age_match:
                age = int(age_match.group(1))

        return ExtractedPatient(
            patient_code=DemographicField(
                value=patient_code,
                confidence=0.90 if patient_code else None,
            ),
            patient_name=DemographicField(
                value=patient_name,
                confidence=0.90 if patient_name else None,
            ),
            age=NumericDemographicField(
                value=age,
                confidence=0.85 if age is not None else None,
            ),
            gender=DemographicField(
                value=gender,
                confidence=0.90 if gender else None,
            ),
        )

    @staticmethod
    def _normalize_gender(value: str) -> str:
        value = value.strip().lower()
        if value in {"m", "male"}:
            return "Male"
        if value in {"f", "female"}:
            return "Female"
        return value

    def _parse_panel(self, text: str) -> ExtractedPanel:
        lines = [
            re.sub(r"\s+", " ", line).strip()
            for line in text.splitlines()
            if line.strip()
        ]

        panel_name = "Unclassified Panel"

        # Preferred structured report format:
        # Test: Complete Blood Count (CBC)
        for line in lines:
            match = re.match(r"Test\s*:\s*(.+)$", line, re.IGNORECASE)
            if match:
                panel_name = match.group(1).strip()
                break

        aliases = {
            "hemogobin": "Hemoglobin",
            "hemoglobin": "Hemoglobin",
            "weccount": "WBC Count",
            "wbc count": "WBC Count",
            "plteletcount": "Platelet Count",
            "plateletcount": "Platelet Count",
            "rccount": "RBC Count",
            "rbccount": "RBC Count",
            "reccount": "RBC Count",
            "bilrubin tolal": "Bilirubin Total",
            "bilirubin tolal": "Bilirubin Total",
            "bilirubin ol": "Bilirubin Total",
            "sgot(ast": "SGOT / AST",
            "sgot ast": "SGOT / AST",
            "scotisn": "SGOT / AST",
            "siptalt": "SGPT/ALT",
            "sptalt": "SGPT/ALT",
            "alkaline phesphatase": "Alkaline Phosphatase",
            "alkaline phosphatass": "Alkaline Phosphatase",
            "sumtsh": "Serum TSH",
            "serumtsh": "Serum TSH",
            "freetd": "Free T4",
            "freo t4": "Free T4",
        }

        parameters: List[ExtractedParameter] = []

        # Parse one parameter per line.
        for line in lines:
            if re.search(r"TESTNAME\s+RESULT\s+UNIT", line, re.IGNORECASE):
                continue

            if re.search(
                r"^(?:Status|Sttus|Date|Patient|Name|Age|Gender|Ref)\b",
                line,
                re.IGNORECASE,
            ):
                continue

            # Legacy demographic/reference metadata can appear on one line:
            # "#ge:28 Gender F Ref LFT-2028:02"
            if re.search(r"#ge\s*[:\-]?\s*\d+", line, re.IGNORECASE):
                continue

            if re.search(r"\bGender\s*[:\-]?\s*[MF]\b", line, re.IGNORECASE):
                continue

            if re.search(r"\bRef\s+[A-Za-z0-9._/-]+", line, re.IGNORECASE):
                continue

            # Clean format:
            # "TSH: 2.45 ulU/mL (Ref: 0.27 - 4.20)"
            match = re.match(
                r"^(.+?)\s*:\s*"
                r"([+-]?\d+(?:\.\d+)?)\s*"
                r"([A-Za-zµμ/%^0-9._-]+)?"
                r"(?:\s*\(Ref:\s*(.*?)\))?$",
                line,
                re.IGNORECASE,
            )

            if not match:
                # Legacy/table format:
                # "Hemogobin 145 gL"
                # "WECCount 7800 cellsmeL."
                # "RECCount 51 milloniul"
                match = re.match(
                    r"^(.+?)\s+"
                    r"([+-]?\d+(?:\.\d+)?)\s+"
                    r"([A-Za-zµμ/%^0-9._-]+)\s*$",
                    line,
                    re.IGNORECASE,
                )

            if not match:
                continue

            raw_name = match.group(1).strip()
            result = match.group(2).strip()
            unit = match.group(3).strip() if match.group(3) else None
            reference_range = match.group(4).strip() if len(match.groups()) >= 4 and match.group(4) else None

            normalized_key = re.sub(r"\s+", " ", raw_name).strip().lower()
            normalized_name = aliases.get(normalized_key, raw_name)

            # Avoid accidentally treating metadata as a lab parameter.
            if normalized_name.lower() in {
                "patient id",
                "patient name",
                "age",
                "gender",
                "test",
                "status",
            }:
                continue

            parameters.append(
                ExtractedParameter(
                    name=normalized_name,
                    result=result,
                    unit=unit,
                    reference_range=reference_range,
                    confidence=0.85,
                )
            )

        return ExtractedPanel(
            panel_name=panel_name,
            parameters=parameters,
        )

    def extract(
        self,
        image_path: Path,
        context: Dict[str, Any],
    ) -> ExtractionResult:
        image_path = Path(image_path)

        if not image_path.exists():
            raise ExtractionProcessingError(
                "IMAGE_NOT_FOUND",
                f"OCR source image does not exist: {image_path}",
            )

        try:
            image = Image.open(image_path)
            image.load()
        except Exception as exc:
            raise ExtractionProcessingError(
                "IMAGE_OPEN_FAILED",
                f"Unable to open OCR source image: {exc}",
            ) from exc

        try:
            image = ImageOps.grayscale(image)

            raw_text = pytesseract.image_to_string(
                image,
                config="--psm 6",
            )
        except Exception as exc:
            raise ExtractionProcessingError(
                "OCR_FAILED",
                f"Tesseract OCR failed: {exc}",
            ) from exc

        raw_text = raw_text.strip()

        if not raw_text:
            raise ExtractionProcessingError(
                "OCR_EMPTY",
                "Tesseract returned no readable text from the image.",
            )

        patient = self._parse_patient(raw_text)
        panels = [self._parse_panel(raw_text)]

        return ExtractionResult(
            patient=patient,
            panels=panels,
            provider_name=self.provider_name,
            provider_version=self.provider_version,
            raw_text_summary=raw_text,
        )
