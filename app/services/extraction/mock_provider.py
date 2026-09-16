from pathlib import Path
from typing import Any, Dict

from app.services.extraction.base import (
    DemographicField,
    NumericDemographicField,
    ExtractedPatient,
    ExtractedParameter,
    ExtractedPanel,
    ExtractionProvider,
    ExtractionResult,
)


class MockExtractionProvider(ExtractionProvider):
    """
    MOCK EXTRACTION — STAGING ONLY

    Deterministic fixture for automated/staging tests.
    This provider intentionally does NOT inspect image pixels.

    It must conform to the same ExtractionProvider contract
    used by the real OCR provider.
    """

    @property
    def provider_name(self) -> str:
        return "MOCK_EXTRACTION_STAGING_ONLY"

    @property
    def provider_version(self) -> str:
        return "2.2.0"

    def extract(
        self,
        image_path: Path,
        context: Dict[str, Any],
    ) -> ExtractionResult:

        return ExtractionResult(
            patient=ExtractedPatient(
                patient_code=DemographicField(
                    value="P-101",
                    confidence=0.96,
                ),
                patient_name=DemographicField(
                    value="Patient A",
                    confidence=0.92,
                ),
                age=NumericDemographicField(
                    value=30,
                    confidence=0.90,
                ),
                gender=DemographicField(
                    value="Male",
                    confidence=0.95,
                ),
            ),
            panels=[
                ExtractedPanel(
                    panel_name="Complete Blood Count",
                    parameters=[
                        ExtractedParameter(
                            name="WBC",
                            result="7200",
                            unit="cells/mcL",
                            confidence=0.98,
                        ),
                        ExtractedParameter(
                            name="Hemoglobin",
                            result="14.2",
                            unit="g/dL",
                            confidence=0.95,
                        ),
                        ExtractedParameter(
                            name="Platelets",
                            result="250000",
                            unit="/uL",
                            confidence=0.94,
                        ),
                    ],
                )
            ],
            provider_name=self.provider_name,
            provider_version=self.provider_version,
            raw_text_summary="STAGING MOCK RESULT — NO LIVE OCR",
        )
