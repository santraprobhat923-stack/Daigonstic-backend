from pathlib import Path
from typing import Any, Dict

from PIL import Image, ImageOps
import pytesseract

from app.services.extraction.base import (
    DemographicField,
    ExtractedPatient,
    ExtractedPanel,
    ExtractionProcessingError,
    ExtractionProvider,
    ExtractionResult,
)


class TesseractExtractionProvider(ExtractionProvider):
    """
    REAL OCR PROVIDER

    Responsibilities:
    - Open the supplied image.
    - Perform lightweight image preprocessing.
    - Run Tesseract OCR.
    - Preserve the raw OCR text.

    This provider does NOT interpret or invent medical results.
    Structured medical parsing is a separate layer.
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
            # Convert to grayscale for more stable OCR.
            image = ImageOps.grayscale(image)

            # Keep OCR configuration conservative for analyzer printouts.
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

        # At this stage we intentionally do NOT parse medical values.
        # The raw OCR text is preserved for the next extraction layer.
        return ExtractionResult(
            patient=ExtractedPatient(),
            panels=[],
            provider_name=self.provider_name,
            provider_version=self.provider_version,
            raw_text_summary=raw_text,
        )
