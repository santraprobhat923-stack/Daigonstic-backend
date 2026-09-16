from app.services.extraction.base import ExtractionProvider
from app.services.extraction.enhanced_tesseract_provider import EnhancedTesseractExtractionProvider


def get_extraction_provider() -> ExtractionProvider:
    """Return the local Tesseract OCR provider with enhanced patient-header parsing."""
    return EnhancedTesseractExtractionProvider()
