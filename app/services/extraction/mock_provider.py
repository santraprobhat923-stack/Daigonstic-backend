from pathlib import Path
from typing import Dict, Any
from app.services.extraction.base import (
    ExtractionProvider,
    ExtractionResult,
    ExtractedPatient,
    ExtractedPanel,
    ExtractedParameter,
    DemographicField,
    NumericDemographicField,
    ExtractionProcessingError
)

class MockExtractionProvider(ExtractionProvider):
    @property
    def provider_name(self) -> str:
        return "deterministic-mock-v1"

    @property
    def provider_version(self) -> str:
        return "1.0.0"

    def extract(self, image_path: Path, context: Dict[str, Any]) -> ExtractionResult:
        if not image_path.is_file():
            raise ExtractionProcessingError(
                code="FILE_NOT_FOUND",
                message="Source analyzer image does not exist on storage."
            )

        filename = context.get("original_filename", "").lower()

        # Failure Trigger Scenario
        if "fail" in filename or "corrupt" in filename:
            raise ExtractionProcessingError(
                code="UNREADABLE_SCAN",
                message="The uploaded document image was unreadable or out of focus."
            )

        # Scenario B: Partial / Missing Demographics
        if "partial" in filename or "lipid" in filename:
            return ExtractionResult(
                patient=ExtractedPatient(
                    patient_code=DemographicField(value="P-PARTIAL-01", confidence=0.95),
                    patient_name=DemographicField(value=None, confidence=None),
                    age=NumericDemographicField(value=None, confidence=None),
                    gender=DemographicField(value=None, confidence=None)
                ),
                panels=[
                    ExtractedPanel(
                        panel_name="Lipid Profile",
                        parameters=[
                            ExtractedParameter(
                                name="Total Cholesterol",
                                result="210",
                                unit="mg/dL",
                                reference_range="< 200",
                                confidence=0.94
                            ),
                            ExtractedParameter(
                                name="Triglycerides",
                                result="160",
                                unit="mg/dL",
                                reference_range="< 150",
                                confidence=0.91
                            )
                        ]
                    )
                ],
                provider_name=self.provider_name,
                provider_version=self.provider_version,
                raw_text_summary="SYNTHETIC MOCK EXTRACTION: PARTIAL DEMOGRAPHICS"
            )

        # Scenario A: Standard Complete CBC Panel (Default)
        return ExtractionResult(
            patient=ExtractedPatient(
                patient_code=DemographicField(value="P-101", confidence=0.96),
                patient_name=DemographicField(value="Patient A (C1)", confidence=0.92),
                age=NumericDemographicField(value=30, confidence=0.90),
                gender=DemographicField(value="Male", confidence=0.95)
            ),
            panels=[
                ExtractedPanel(
                    panel_name="Complete Blood Count",
                    parameters=[
                        ExtractedParameter(
                            name="Hemoglobin",
                            result="14.2",
                            unit="g/dL",
                            reference_range="13.0-17.0",
                            confidence=0.97
                        ),
                        ExtractedParameter(
                            name="Total Leukocyte Count",
                            result="7800",
                            unit="/cumm",
                            reference_range="4000-11000",
                            confidence=0.94
                        ),
                        ExtractedParameter(
                            name="Platelet Count",
                            result="250000",
                            unit="/cumm",
                            reference_range="150000-450000",
                            confidence=0.92
                        )
                    ]
                )
            ],
            provider_name=self.provider_name,
            provider_version=self.provider_version,
            raw_text_summary="SYNTHETIC MOCK EXTRACTION: COMPLETE CBC"
        )
