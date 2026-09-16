from pydantic import BaseModel, EmailStr, ConfigDict, Field
from typing import Optional, List
from datetime import datetime
import enum
from app.models import PaymentStatusEnum, ReportStatusEnum, TransactionTypeEnum, PurchaseStatusEnum


# --- Authentication & Users ---
class Token(BaseModel):
    access_token: str
    token_type: str
class TokenData(BaseModel):
    user_id: Optional[int] = None
    centre_id: Optional[int] = None
    role: Optional[str] = None
class UserBase(BaseModel):
    email: EmailStr
    role: Optional[str] = "technician"
class UserCreate(UserBase):
    password: str
    centre_id: int
class UserResponse(UserBase):
    id: int
    centre_id: int
    is_active: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class CentreBase(BaseModel):
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
class CentreCreate(CentreBase):
    pass
class CentreResponse(CentreBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class PatientBase(BaseModel):
    full_name: str
    age: int
    gender: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
class PatientCreate(PatientBase):
    pass
class PatientUpdate(BaseModel):
    full_name: Optional[str] = None
    age: Optional[int] = Field(default=None, ge=0, le=150)
    gender: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    patient_code: Optional[str] = None
class PatientResponse(PatientBase):
    id: int
    centre_id: int
    patient_code: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class TestBase(BaseModel):
    name: str
    code: str
    category: Optional[str] = None
    price: int
    description: Optional[str] = None
class TestCreate(TestBase): pass
class TestResponse(TestBase):
    id: int
    centre_id: int
    model_config = ConfigDict(from_attributes=True)

class OrderItemCreate(BaseModel):
    test_id: int
    quantity: Optional[int] = 1
class OrderItemResponse(BaseModel):
    id: int
    test_id: int
    quantity: int
    unit_price: int
    model_config = ConfigDict(from_attributes=True)
class OrderCreate(BaseModel):
    patient_id: int
    items: List[OrderItemCreate]
    discount: Optional[int] = 0
class OrderResponse(BaseModel):
    id: int
    patient_id: int
    centre_id: int
    status: str
    subtotal: int
    discount: int
    total_amount: int
    created_at: datetime
    items: List[OrderItemResponse] = []
    model_config = ConfigDict(from_attributes=True)

class BillingCreate(BaseModel):
    order_id: int
    payment_status: PaymentStatusEnum
    pending_amount: Optional[int] = 0
class BillingResponse(BaseModel):
    id: int
    order_id: int
    patient_id: int
    centre_id: int
    total_amount: int
    payment_status: PaymentStatusEnum
    pending_amount: int
    bill_file_path: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class SingleReportUploadResult(BaseModel):
    filename: str
    status: str
    detail: str
    report_id: Optional[int] = None
    patient_id: Optional[int] = None
class BulkReportUploadSummary(BaseModel):
    total_files: int
    successful: int
    duplicates: int
    failed: int
    results: List[SingleReportUploadResult]
class BulkReportUploadSummaryExtended(BaseModel):
    total_files: int
    successful: int
    duplicates: int
    failed: int
    credits_consumed: int
    remaining_credits: int
    results: List[SingleReportUploadResult]

class CreditBalanceResponse(BaseModel):
    centre_id: int
    balance: int
    low_credit: bool
    threshold: int
    updated_at: Optional[datetime]
    model_config = ConfigDict(from_attributes=True)
class CreditTransactionResponse(BaseModel):
    id: int
    centre_id: int
    transaction_type: TransactionTypeEnum
    amount: int
    balance_after: int
    reference_type: Optional[str] = None
    reference_id: Optional[int] = None
    description: Optional[str] = None
    created_at: datetime
    created_by: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)
class AdminCreditGrantRequest(BaseModel):
    centre_id: int
    amount: int = Field(..., gt=0, description="Credits to grant must be greater than zero")
    description: Optional[str] = "Admin granted promotional/trial credits"
class CreditRechargeRequest(BaseModel):
    credits: int = Field(..., gt=0, description="Quantity of credits to order")
    payment_method: Optional[str] = "manual_upi"
    payment_reference: Optional[str] = None
class CreditPurchaseResponse(BaseModel):
    id: int
    centre_id: int
    amount_paid: float
    credits: int
    price_per_credit: float
    payment_method: str
    payment_reference: Optional[str] = None
    status: PurchaseStatusEnum
    created_at: datetime
    approved_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)
class RechargeApprovalAction(BaseModel):
    approve: bool
    notes: Optional[str] = None
class CentreDashboardResponse(BaseModel):
    centre_id: int
    centre_name: str
    credit_balance: int
    low_credit: bool
    total_patients: int
    total_orders: int
    total_reports: int
    reports_uploaded_today: int
    reports_uploaded_this_month: int
    pending_payments_count: int
    partially_paid_count: int
    total_pending_amount: float

class VerifiedParameter(BaseModel):
    name: str = Field(..., min_length=1)
    result: str = Field(..., min_length=1)
    unit: Optional[str] = None
    reference_range: Optional[str] = None
class VerifiedPanel(BaseModel):
    panel_name: str = Field(..., min_length=1)
    parameters: List[VerifiedParameter] = Field(..., min_items=1)
class VerificationPayload(BaseModel):
    patient_id: int
    patient_name: Optional[str] = None
    patient_age: Optional[int] = Field(default=None, ge=0, le=150)
    patient_gender: Optional[str] = None
    patient_phone: Optional[str] = None
    patient_email: Optional[EmailStr] = None
    patient_code: Optional[str] = None
    barcode: Optional[str] = None
    panels: List[VerifiedPanel] = Field(..., min_items=1)
    technician_notes: Optional[str] = None
