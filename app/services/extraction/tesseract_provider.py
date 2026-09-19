from pathlib import Path
from typing import Any, Dict, List
import re

from PIL import Image, ImageOps, ImageFilter
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
    """REAL OCR provider with deterministic technician-verifiable parsing."""

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

        id_match = re.search(r"Patient\s*I[Dd\[\:]*\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9._/-]*)", text, re.IGNORECASE)
        if id_match:
            patient_code = id_match.group(1).strip(" .,:;")

        name_match = re.search(r"\bName\s*[:\-]\s*(.+?)(?=\s+(?:Age|#ge|Gender|Sex|Ref|Test|TESTNAME)\b|$)", text, re.IGNORECASE)
        if name_match:
            patient_name = name_match.group(1).strip(" .:-")

        age_sex_match = re.search(r"Age\s*/\s*Sex\s*[:\-]\s*(\d{1,3})\s*Y?\s*/\s*([A-Za-z]+)", text, re.IGNORECASE)
        if age_sex_match:
            age = int(age_sex_match.group(1))
            gender = self._normalize_gender(age_sex_match.group(2))

        if age is None:
            legacy_age_match = re.search(r"#ge\s*[:\-]?\s*(\d{1,3})", text, re.IGNORECASE)
            if legacy_age_match:
                age = int(legacy_age_match.group(1))

        gender_match = re.search(r"Gender\s*[:\-]?\s*([MF])(?:\b|[^A-Za-z])", text, re.IGNORECASE)
        if gender_match:
            gender = self._normalize_gender(gender_match.group(1))

        if age is None:
            age_match = re.search(r"\bAge\s*[:\-]?\s*(\d{1,3})", text, re.IGNORECASE)
            if age_match:
                age = int(age_match.group(1))

        return ExtractedPatient(
            patient_code=DemographicField(value=patient_code, confidence=0.90 if patient_code else None),
            patient_name=DemographicField(value=patient_name, confidence=0.90 if patient_name else None),
            age=NumericDemographicField(value=age, confidence=0.85 if age is not None else None),
            gender=DemographicField(value=gender, confidence=0.90 if gender else None),
        )

    @staticmethod
    def _normalize_gender(value: str) -> str:
        value = value.strip().lower()
        if value in {"m", "male"}:
            return "Male"
        if value in {"f", "female"}:
            return "Female"
        return value

    @staticmethod
    def _ocr_score(text: str) -> int:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return -10000
        score = min(len(lines), 40)
        for line in lines:
            if re.search(r"\b(?:Test|TESTNAME|RESULT|UNIT|Age|Gender|Sex|Name|Patient)\b", line, re.IGNORECASE):
                score += 3
            if re.search(r"[A-Za-z][A-Za-z /_()\-]{2,}\s*:?\s*[+-]?\d+(?:[.,]\d+)?", line):
                score += 5
            if re.search(r"[+-]?\d+(?:[.,]\d+)?\s+[A-Za-zµμ/%^0-9._-]+", line):
                score += 2
        return score

    def _run_ocr_passes(self, image: Image.Image) -> str:
        """Run several OCR passes for cross-checking, without duplicating conflicting rows."""
        max_dimension = 2400
        if max(image.size) > max_dimension:
            scale = max_dimension / max(image.size)
            image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))))

        gray = ImageOps.grayscale(image)
        enhanced = ImageOps.autocontrast(gray)
        variants = [
            gray,
            enhanced,
            enhanced.filter(ImageFilter.SHARPEN),
            ImageOps.autocontrast(gray.resize((gray.width * 2, gray.height * 2))),
        ]

        candidates: List[str] = []
        for variant in variants:
            for psm in (6, 11):
                try:
                    text = pytesseract.image_to_string(variant, config=f"--psm {psm}").strip()
                except Exception:
                    continue
                if text:
                    candidates.append(text)

        if not candidates:
            raise ExtractionProcessingError("OCR_EMPTY", "Tesseract returned no readable text from the image.")

        # Do NOT concatenate all OCR passes. Different preprocessing/PSM passes
        # can read the same number differently (for example 88 -> 8 or 8.8).
        # Instead, select one strong candidate and let _parse_panel deduplicate
        # rows within that candidate. Keeping the passes separate prevents one
        # physical result from becoming multiple database rows.
        ranked = sorted(candidates, key=self._ocr_score, reverse=True)
        best = ranked[0]
        best_count = len(self._parse_panel(best).parameters)

        for candidate in ranked[1:]:
            count = len(self._parse_panel(candidate).parameters)
            if count > best_count:
                best = candidate
                best_count = count

        return best

    def _parse_panel(self, text: str) -> ExtractedPanel:
        lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
        panel_name = "Unclassified Panel"
        for line in lines:
            match = re.match(r"Test\s*:\s*(.+)$", line, re.IGNORECASE)
            if match:
                panel_name = match.group(1).strip()
                break

        aliases = {
            "hemogobin": "Hemoglobin", "hemoglobin": "Hemoglobin",
            "weccount": "WBC Count", "wbc count": "WBC Count", "wbc": "WBC Count",
            "plteletcount": "Platelet Count", "plateletcount": "Platelet Count", "platelets": "Platelet Count",
            "rccount": "RBC Count", "rbccount": "RBC Count", "reccount": "RBC Count", "rbc": "RBC Count",
            "bilrubin tolal": "Bilirubin Total", "bilirubin tolal": "Bilirubin Total", "bilirubin ol": "Bilirubin Total",
            "sgot(ast": "SGOT / AST", "sgot ast": "SGOT / AST", "scotisn": "SGOT / AST",
            "siptalt": "SGPT/ALT", "sptalt": "SGPT/ALT",
            "alkaline phesphatase": "Alkaline Phosphatase", "alkaline phosphatass": "Alkaline Phosphatase",
            "sumtsh": "Serum TSH", "serumtsh": "Serum TSH", "freetd": "Free T4", "freo t4": "Free T4",
        }

        parameters: List[ExtractedParameter] = []
        for line in lines:
            if re.search(r"TESTNAME\s+RESULT\s+UNIT", line, re.IGNORECASE):
                continue
            if re.search(r"^(?:Status|Sttus|Date|Patient|Name|Age|Gender|Sex|Ref)\b", line, re.IGNORECASE):
                continue
            if re.search(r"#ge\s*[:\-]?\s*\d+", line, re.IGNORECASE):
                continue
            if re.search(r"\b(?:Gender|Sex)\s*[:\-]?\s*[MF]\b", line, re.IGNORECASE):
                continue
            if re.search(r"\bRef\s+[A-Za-z0-9._/-]+", line, re.IGNORECASE):
                continue

            match = re.match(
                r"^(.+?)\s*:\s*([+-]?\d+(?:[.,]\d+)?)\s*([A-Za-zµμ/%^0-9._-]+)?(?:\s*\(Ref:\s*(.*?)\))?$",
                line, re.IGNORECASE,
            )
            if not match:
                match = re.match(
                    r"^(.+?)\s+([+-]?\d+(?:[.,]\d+)?)\s+([A-Za-zµμ/%^0-9._-]+)\s*$",
                    line, re.IGNORECASE,
                )
            if not match:
                match = re.match(
                    r"^([A-Za-z][A-Za-z0-9 /_()\-]{2,}?)\s*[:\-]?\s*([+-]?\d+(?:[.,]\d+)?)\s*$",
                    line, re.IGNORECASE,
                )
            if not match:
                continue

            raw_name = match.group(1).strip(" .:-")
            result = match.group(2).strip().replace(",", ".")
            unit = match.group(3).strip() if match.group(3) else None
            reference_range = match.group(4).strip() if len(match.groups()) >= 4 and match.group(4) else None
            normalized_key = re.sub(r"\s+", " ", raw_name).strip().lower()
            normalized_name = aliases.get(normalized_key, raw_name)

            if normalized_name.lower() in {"patient id", "patient name", "age", "gender", "sex", "test", "status"}:
                continue

            parameters.append(ExtractedParameter(name=normalized_name, result=result, unit=unit, reference_range=reference_range, confidence=0.85))

        return ExtractedPanel(panel_name=panel_name, parameters=parameters)

    def extract(self, image_path: Path, context: Dict[str, Any]) -> ExtractionResult:
        image_path = Path(image_path)
        if not image_path.exists():
            raise ExtractionProcessingError("IMAGE_NOT_FOUND", f"OCR source image does not exist: {image_path}")
        try:
            image = Image.open(image_path)
            image.load()
        except Exception as exc:
            raise ExtractionProcessingError("IMAGE_OPEN_FAILED", f"Unable to open OCR source image: {exc}") from exc

        raw_text = self._run_ocr_passes(image).strip()
        if not raw_text:
            raise ExtractionProcessingError("OCR_EMPTY", "Tesseract returned no readable text from the image.")

        patient = self._parse_patient(raw_text)
        panels = [self._parse_panel(raw_text)]
        return ExtractionResult(
            patient=patient,
            panels=panels,
            provider_name=self.provider_name,
            provider_version=self.provider_version,
            raw_text_summary=raw_text,
        )
