from typing import Dict, Any

class MockExtractionProvider:
    """
    MOCK EXTRACTION — STAGING ONLY
    This is a deterministic test fixture for staging demonstrations. 
    It does not perform live OCR on image pixels.
    """
    def extract(self, image_path: str) -> Dict[str, Any]:
        return {
            "provider_metadata": {
                "engine": "MOCK_EXTRACTION_STAGING_ONLY",
                "version": "2.1.0"
            },
            "patient": {
                "patient_code": {"value": "P-101", "confidence": 0.96},
                "patient_name": {"value": "Patient A", "confidence": 0.92},
                "age": {"value": 30, "confidence": 0.90},
                "gender": {"value": "Male", "confidence": 0.95}
            },
            "panels": [
                {
                    "panel_name": "Complete Blood Count",
                    "tests": [
                        {"test_name": "WBC", "raw_extracted_value": "7200", "unit": "cells/mcL", "confidence": 0.98},
                        {"test_name": "Hemoglobin", "raw_extracted_value": "14.2", "unit": "g/dL", "confidence": 0.95},
                        {"test_name": "Platelets", "raw_extracted_value": "250000", "unit": "/uL", "confidence": 0.94}
                    ]
                }
            ]
        }
