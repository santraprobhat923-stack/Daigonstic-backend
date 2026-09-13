from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class DemographicField(BaseModel):
    value: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

class NumericDemographicField(BaseModel):
    value: Optional[int] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

class ExtractedPatient(BaseModel):
    patient_code: DemographicField = Field(default_factory=DemographicField)
    patient_name: DemographicField = Field(default_factory=DemographicField)
    age: NumericDemographicField = Field(default_factory=NumericDemographicField)
    gender: DemographicField = Field(default_factory=DemographicField)

class ExtractedParameter(BaseModel):
    name: str = Field(..., min_length=1)
    result: str = Field(...)
    unit: Optional[str] = None
    reference_range: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

class ExtractedPanel(BaseModel):
    panel_name: str
    parameters: List[ExtractedParameter] = Field(default_factory=list)

class ExtractionResult(BaseModel):
    patient: ExtractedPatient = Field(default_factory=ExtractedPatient)
    panels: List[ExtractedPanel] = Field(default_factory=list)
    provider_name: str
    provider_version: str
    raw_text_summary: Optional[str] = None

class ExtractionProcessingError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)

class ExtractionProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    @property
    @abstractmethod
    def provider_version(self) -> str:
        ...

    @abstractmethod
    def extract(self, image_path: Path, context: Dict[str, Any]) -> ExtractionResult:
        ...
