from app.services.extraction.base import ExtractionProvider
from app.services.extraction.tesseract_provider import TesseractExtractionProvider


def get_extraction_provider() -> ExtractionProvider:
    """
    Return the currently configured extraction provider.

    Tesseract is the local/staging OCR provider.
    Structured parsing is intentionally handled separately.
    """
    return TesseractExtractionProvider()
