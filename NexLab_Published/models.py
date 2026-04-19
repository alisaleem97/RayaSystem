# models.py
from typing import Optional, List
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship

# ===========================
# 1. USER (Staff Login)
# ===========================
class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    full_name: str
    role: str = Field(default="receptionist")
    hashed_password: str
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.now)
    last_seen: Optional[datetime] = None
    is_online: bool = Field(default=False)

# ===========================
# 1b. USER PERMISSION (Granular Page+Button Access)
# ===========================
class UserPermission(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    page_key: str = Field(index=True)
    allowed_buttons: Optional[str] = Field(default=None)  # JSON array of button keys

# ===========================
# AUDIT LOG (Track all actions)
# ===========================
class AuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    table_name: str
    record_id: int
    action: str
    user_id: int = Field(foreign_key="user.id")
    username: str
    old_values: Optional[str] = None
    new_values: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)

# ===========================
# 2. PATIENT
# ===========================
class Patient(SQLModel, table=True):
    __tablename__ = "patient"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: str = Field(unique=True, index=True)
    full_name: str = Field()
    gender: str = Field()
    age: Optional[int] = Field(default=None)
    age_unit: Optional[str] = Field(default="year")
    date_of_birth: Optional[datetime] = None
    phone_key: str = Field()
    phone_number: str = Field()
    weight: Optional[float] = Field(default=None)
    height: Optional[float] = Field(default=None)
    province_id: Optional[int] = Field(default=None, foreign_key="province.id")
    region_id: Optional[int] = Field(default=None, foreign_key="region.id")
    note: Optional[str] = Field(default=None)
    email: Optional[str] = Field(default=None)
    diagnosis: Optional[str] = Field(default=None)
    symptoms: Optional[str] = Field(default=None)
    therapy: Optional[str] = Field(default=None)
    partner_id: Optional[int] = Field(default=None, foreign_key="partner.id")
    doctor: Optional[str] = Field(default=None)
    skin_colour: Optional[str] = Field(default=None)
    agent_name: Optional[str] = Field(default=None)
    is_outlab: bool = Field(default=False)
    is_active: bool = Field(default=True)
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None
    deleted_by: Optional[int] = Field(default=None, foreign_key="user.id")
    deleted_at: Optional[datetime] = None
    deleted_reason: Optional[str] = Field(default=None)
    
    # Relationships
    visits: List["PatientVisit"] = Relationship(back_populates="patient", cascade_delete=True)
    orders: List["Order"] = Relationship(back_populates="patient")

# ===========================
# 3. PARAMETER
# ===========================
class Parameter(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    parameter_name: str = Field(unique=True, index=True)
    parameter_short_name: str
    is_header: bool = Field(default=False)
    
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None
    deleted_by: Optional[int] = Field(default=None, foreign_key="user.id")
    deleted_at: Optional[datetime] = None

# ===========================
# 4. DEPARTMENT
# ===========================
class Department(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    department_name: str = Field(unique=True, index=True)
    department_note: Optional[str] = None
    is_active: bool = Field(default=True)
    
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None
    deleted_by: Optional[int] = Field(default=None, foreign_key="user.id")
    deleted_at: Optional[datetime] = None
    activated_by: Optional[int] = Field(default=None, foreign_key="user.id")
    activated_at: Optional[datetime] = None
    deactivated_by: Optional[int] = Field(default=None, foreign_key="user.id")
    deactivated_at: Optional[datetime] = None

# ===========================
# 5. DEVICE
# ===========================
class Device(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    device_name: str = Field(unique=True, index=True)
    serial_number: str
    install_date: datetime
    installer_name: str
    installer_phone: str
    note: Optional[str] = None
    is_active: bool = Field(default=True)
    
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None
    deleted_by: Optional[int] = Field(default=None, foreign_key="user.id")
    deleted_at: Optional[datetime] = None
    activated_by: Optional[int] = Field(default=None, foreign_key="user.id")
    activated_at: Optional[datetime] = None
    deactivated_by: Optional[int] = Field(default=None, foreign_key="user.id")
    deactivated_at: Optional[datetime] = None

# ===========================
# 6. SAMPLE TYPE
# ===========================
class SampleType(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    sample_name: str = Field(unique=True, index=True)
    sample_note: Optional[str] = None
    is_active: bool = Field(default=True)
    
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None
    deleted_by: Optional[int] = Field(default=None, foreign_key="user.id")
    deleted_at: Optional[datetime] = None
    activated_by: Optional[int] = Field(default=None, foreign_key="user.id")
    activated_at: Optional[datetime] = None
    deactivated_by: Optional[int] = Field(default=None, foreign_key="user.id")
    deactivated_at: Optional[datetime] = None

# ===========================
# 7. REPORT NOTE
# ===========================
class ReportNote(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    note_name: str = Field(unique=True, index=True)
    note_content: str
    is_active: bool = Field(default=True)
    
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None
    deleted_by: Optional[int] = Field(default=None, foreign_key="user.id")
    deleted_at: Optional[datetime] = None

# ===========================
# 8. TEST DEFINITION
# ===========================
class TestDefinition(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    test_name: str = Field(unique=True, index=True)
    test_short_name: str
    department_id: int = Field(foreign_key="department.id")
    sample_type_id: int = Field(foreign_key="sampletype.id")
    report_note_id: Optional[int] = Field(default=None, foreign_key="reportnote.id")
    price: float
    test_note: Optional[str] = None
    test_condition: Optional[str] = None
    is_available: bool = Field(default=True)
    
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None
    deleted_by: Optional[int] = Field(default=None, foreign_key="user.id")
    deleted_at: Optional[datetime] = None
    
    # Relationships
    department: Department = Relationship()
    sample_type: SampleType = Relationship()
    report_note: Optional[ReportNote] = Relationship()
    test_devices: List["TestDevice"] = Relationship(back_populates="test")
    test_parameters: List["TestParameter"] = Relationship(back_populates="test")

# ===========================
# 9. TEST-DEVICE LINK (Many-to-Many)
# ===========================
class TestDevice(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    test_id: int = Field(foreign_key="testdefinition.id")
    device_id: int = Field(foreign_key="device.id")
    
    test: TestDefinition = Relationship(back_populates="test_devices")
    device: Device = Relationship()

# ===========================
# 10. TEST-PARAMETER LINK (Many-to-Many)
# ===========================
class TestParameter(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    test_id: int = Field(foreign_key="testdefinition.id")
    parameter_id: int = Field(foreign_key="parameter.id")
    
    test: TestDefinition = Relationship(back_populates="test_parameters")
    parameter: Parameter = Relationship()

# ===========================
# 11. FORMULA
# ===========================
class Formula(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    formula_name: str
    main_test_id: int = Field(foreign_key="testdefinition.id")
    main_parameter_id: Optional[int] = Field(default=None, foreign_key="parameter.id")
    gender_type: str = Field(default="both")
    formula_expression: str = Field(default="")
    formula_description: Optional[str] = None
    is_active: bool = Field(default=True)
    
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None
    deleted_by: Optional[int] = Field(default=None, foreign_key="user.id")
    deleted_at: Optional[datetime] = None
    
    main_test: TestDefinition = Relationship()
    main_parameter: Optional[Parameter] = Relationship()
    items: List["FormulaItem"] = Relationship(back_populates="formula")

# ===========================
# 12. FORMULA ITEM
# ===========================
class FormulaItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    formula_id: int = Field(foreign_key="formula.id")
    operation: str = Field(default="+")
    source_type: str = Field(default="parameter")
    source_test_id: Optional[int] = Field(default=None, foreign_key="testdefinition.id")
    source_parameter_id: Optional[int] = Field(default=None, foreign_key="parameter.id")
    weight_value: float = Field(default=1.0)
    order_index: int = Field(default=0)
    
    formula: Formula = Relationship(back_populates="items")

# ===========================
# 13. TEST CATALOG (Legacy)
# ===========================
class TestCatalog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    test_code: str = Field(unique=True, index=True)
    test_name: str
    sample_type: str
    unit: str
    reference_min: float
    reference_max: float
    price: float
    is_active: bool = Field(default=True)

# ===========================
# 14. ORDER (UPDATED - Price Snapshot for Audit Compliance)
# ===========================
class Order(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_number: str = Field(unique=True, index=True)
    patient_id: int = Field(foreign_key="patient.id")
    test_id: int = Field(foreign_key="testdefinition.id")
    status: str = Field(default="ordered")
    ordered_by: int = Field(foreign_key="user.id")
    collected_by: Optional[int] = Field(default=None, foreign_key="user.id")
    verified_by: Optional[int] = Field(default=None, foreign_key="user.id")
    order_date: datetime = Field(default_factory=datetime.now)
    collection_date: Optional[datetime] = None
    verified_date: Optional[datetime] = None
    visit_id: Optional[int] = Field(default=None, foreign_key="patientvisit.id")
    package_name: Optional[str] = Field(default=None)  # Store package name if order is from a package
    # ✅ AUDIT COMPLIANCE: Price snapshot at order time
    unit_price: float = Field(default=0.0)
    discount_amount: float = Field(default=0.0)
    final_price: float = Field(default=0.0)
    no_sample_reason: Optional[str] = Field(default=None)
    
    # Relationships
    patient: Patient = Relationship(back_populates="orders")
    test: TestDefinition = Relationship()
    result: Optional["Result"] = Relationship(back_populates="order")
    visit: Optional["PatientVisit"] = Relationship(back_populates="orders")

# ===========================
# 15. RESULT
# ===========================
class Result(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id", unique=True)
    result_value: Optional[str] = Field(default=None)
    rerun_result: Optional[str] = Field(default=None)
    flag: Optional[str] = None
    note: Optional[str] = None
    device_id: Optional[int] = Field(default=None, foreign_key="device.id")
    entered_by: int = Field(foreign_key="user.id")
    entered_at: datetime = Field(default_factory=datetime.now)
    authorized: bool = Field(default=False)
    authorized_by: Optional[int] = Field(default=None, foreign_key="user.id")
    authorized_at: Optional[datetime] = None
    double_authorized: bool = Field(default=False)
    double_authorized_by: Optional[int] = Field(default=None, foreign_key="user.id")
    double_authorized_at: Optional[datetime] = None
    unauth_reason: Optional[str] = Field(default=None)
    
    order: Order = Relationship(back_populates="result")
    details: List["ResultDetail"] = Relationship(back_populates="result")

# ===========================
# 15b. RESULT DETAIL (Per-Parameter Results)
# ===========================
class ResultDetail(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    result_id: int = Field(foreign_key="result.id")
    parameter_id: int = Field(foreign_key="parameter.id")
    result_value: Optional[str] = Field(default=None)
    rerun_result: Optional[str] = Field(default=None)
    flag: Optional[str] = None
    device_id: Optional[int] = Field(default=None, foreign_key="device.id")
    remark: Optional[str] = Field(default=None)
    
    result: Result = Relationship(back_populates="details")
    parameter: Parameter = Relationship()

# ===========================
# 16. TEST RANGE
# ===========================
class TestRange(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    test_id: int = Field(foreign_key="testdefinition.id")
    parameter_id: Optional[int] = Field(default=None, foreign_key="parameter.id")
    device_id: Optional[int] = Field(default=None, foreign_key="device.id")
    unit: str = Field(default="")
    gender_type: str = Field(default="both")
    age_from: int = Field(default=0)
    age_to: int = Field(default=999)
    age_unit: str = Field(default="year")
    fasting_required: bool = Field(default=False)
    range_type: str = Field(default="number")
    
    normal_from: Optional[float] = Field(default=None)
    normal_to: Optional[float] = Field(default=None)
    vlow_from: Optional[float] = Field(default=None)
    vlow_to: Optional[float] = Field(default=None)
    low_from: Optional[float] = Field(default=None)
    low_to: Optional[float] = Field(default=None)
    midlow_from: Optional[float] = Field(default=None)
    midlow_to: Optional[float] = Field(default=None)
    midhigh_from: Optional[float] = Field(default=None)
    midhigh_to: Optional[float] = Field(default=None)
    high_from: Optional[float] = Field(default=None)
    high_to: Optional[float] = Field(default=None)
    vhigh_from: Optional[float] = Field(default=None)
    vhigh_to: Optional[float] = Field(default=None)
    panic_less_than: Optional[float] = Field(default=None)
    panic_more_than: Optional[float] = Field(default=None)
    
    text_range: Optional[str] = Field(default=None)
    
    is_active: bool = Field(default=True)
    
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None
    deleted_by: Optional[int] = Field(default=None, foreign_key="user.id")
    deleted_at: Optional[datetime] = None
    
    test: TestDefinition = Relationship()
    parameter: Optional[Parameter] = Relationship()
    device: Optional[Device] = Relationship()

# ===========================
# 17. TEST RESULT TYPE
# ===========================
class TestResultType(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    test_id: int = Field(foreign_key="testdefinition.id")
    parameter_id: Optional[int] = Field(default=None, foreign_key="parameter.id")
    result_type: str = Field(default="number")
    selection_options: Optional[str] = Field(default=None)
    is_active: bool = Field(default=True)
    
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None
    deleted_by: Optional[int] = Field(default=None, foreign_key="user.id")
    deleted_at: Optional[datetime] = None
    
    test: TestDefinition = Relationship()
    parameter: Optional[Parameter] = Relationship()

# ===========================
# 18. PACKAGE
# ===========================
class Package(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    package_name: str = Field(unique=True, index=True)
    package_short_name: str
    price: float
    package_note: Optional[str] = None
    is_active: bool = Field(default=True)
    
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None
    deleted_by: Optional[int] = Field(default=None, foreign_key="user.id")
    deleted_at: Optional[datetime] = None
    
    package_tests: List["PackageTest"] = Relationship(back_populates="package")

# ===========================
# 19. PACKAGE-TEST LINK
# ===========================
class PackageTest(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    package_id: int = Field(foreign_key="package.id")
    test_id: int = Field(foreign_key="testdefinition.id")
    
    package: Package = Relationship(back_populates="package_tests")
    test: TestDefinition = Relationship()

# ===========================
# 20. PARTNER
# ===========================
class Partner(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    partner_name: str = Field(unique=True, index=True)
    partner_note: Optional[str] = None
    partner_contact: Optional[str] = None
    partner_weight: Optional[float] = Field(default=None)
    is_active: bool = Field(default=True)
    
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None
    deleted_by: Optional[int] = Field(default=None, foreign_key="user.id")
    deleted_at: Optional[datetime] = None

# ===========================
# 21. PROVINCE
# ===========================
class Province(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    province_name: str = Field(unique=True, index=True)
    is_active: bool = Field(default=True)
    
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None
    deleted_by: Optional[int] = Field(default=None, foreign_key="user.id")
    deleted_at: Optional[datetime] = None

# ===========================
# 22. REGION
# ===========================
class Region(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    region_name: str = Field(unique=True, index=True)
    province_id: int = Field(foreign_key="province.id")
    is_active: bool = Field(default=True)
    
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None
    deleted_by: Optional[int] = Field(default=None, foreign_key="user.id")
    deleted_at: Optional[datetime] = None
    
    province: Province = Relationship()

# ===========================
# 23. LAB INFO (UPDATED - Added lab_currency field)
# ===========================
class LabInfo(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    lab_name: str = Field(default="")
    lab_title: Optional[str] = Field(default=None)
    first_doctor_name: Optional[str] = Field(default=None)
    second_doctor_name: Optional[str] = Field(default=None)
    lab_address: Optional[str] = Field(default=None)
    lab_phone_1: str = Field(default="")
    lab_phone_2: Optional[str] = Field(default=None)
    whatsapp_api: Optional[str] = Field(default=None)
    whatsapp_token: Optional[str] = Field(default=None)
    telegram_api: Optional[str] = Field(default=None)
    telegram_token: Optional[str] = Field(default=None)
    lab_qr_1: Optional[str] = Field(default=None)
    lab_qr_2: Optional[str] = Field(default=None)
    lab_stamp_1: Optional[str] = Field(default=None)
    lab_stamp_2: Optional[str] = Field(default=None)
    lab_logo: Optional[str] = Field(default=None)
    lab_signature_1: Optional[str] = Field(default=None)
    lab_signature_2: Optional[str] = Field(default=None)
    lab_image_1: Optional[str] = Field(default=None)
    lab_image_2: Optional[str] = Field(default=None)
    lab_email: Optional[str] = Field(default=None)
    lab_note_1: Optional[str] = Field(default=None)
    lab_note_2: Optional[str] = Field(default=None)
    lab_website: Optional[str] = Field(default=None)
    lab_currency: str = Field(default="$")  # ✅ NEW FIELD
    tax_percentage: float = Field(default=0.0)  # ✅ Tax Percentage
    
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None

# ===========================
# 24. PATIENT VISIT
# ===========================
class PatientVisit(SQLModel, table=True):
    __tablename__ = "patientvisit"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    visit_id: str = Field(index=True)
    patient_id: int = Field(foreign_key="patient.id")
    visit_date: datetime = Field(default_factory=datetime.now)
    is_active: bool = Field(default=True)
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None
    deleted_by: Optional[int] = Field(default=None, foreign_key="user.id")
    deleted_at: Optional[datetime] = None
    
    # Payment fields
    received_amount: float = Field(default=0.0)
    discount_amount: float = Field(default=0.0)
    discount_percentage: float = Field(default=0.0)
    discount_note: Optional[str] = Field(default=None)
    tax_applied: bool = Field(default=True)
    tax_amount: float = Field(default=0.0)
    remaining_amount: float = Field(default=0.0)
    
    # Call Centre fields
    is_called: bool = Field(default=False)
    is_whatsapp_sent: bool = Field(default=False)
    is_printed: bool = Field(default=False)
    
    # Relationships
    patient: Optional["Patient"] = Relationship(back_populates="visits")
    orders: List["Order"] = Relationship(back_populates="visit")

# ===========================
# 25. PRINT TEMPLATE
# ===========================
class PrintTemplate(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    template_name: str = Field(unique=True, index=True)
    template_type: str = Field(default="receipt")
    paper_width: str = Field(default="80mm")
    paper_height: str = Field(default="auto")
    margin: str = Field(default="0")
    elements: str = Field(default="")
    is_active: bool = Field(default=True)
    
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None


# ===========================
# 26. PAYMENT (New - Partial Payments / History)
# ===========================
class Payment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    visit_id: int = Field(foreign_key="patientvisit.id", index=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    amount: float
    payment_method: str = Field(default="cash") # cash, card, transfer
    payment_date: datetime = Field(default_factory=datetime.now)
    note: Optional[str] = None
    
    recorded_by: int = Field(foreign_key="user.id")
    is_refund: bool = Field(default=False)

# ===========================
# 27. DELETED RECORD (New - Archival Snapshot)
# ===========================
class DeletedRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    source_table: str = Field(index=True)      # e.g., "patient", "order", "patientvisit"
    record_id: int                             # Original ID
    record_data: str                           # Full JSON snapshot
    deleted_reason: Optional[str] = None
    
    deleted_by: int = Field(foreign_key="user.id")
    deleted_at: datetime = Field(default_factory=datetime.now)

# ===========================
# 28. ATTACHMENT (New - External Documents)
# ===========================
class Attachment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    visit_id: Optional[int] = Field(default=None, foreign_key="patientvisit.id", index=True)
    file_name: str
    file_path: str
    file_type: str                             # "image", "pdf", etc.
    description: Optional[str] = None
    
    uploaded_by: int = Field(foreign_key="user.id")
    uploaded_at: datetime = Field(default_factory=datetime.now)

# ===========================
# 29. ACTIVITY LOG (New - Operational Monitoring)
# ===========================
class ActivityLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    action_type: str = Field(index=True)      # e.g., "LOGIN", "PRINT_RECEIPT", "SEND_WHATSAPP"
    description: str
    target_type: Optional[str] = None         # e.g., "patient", "visit"
    target_id: Optional[int] = None
    
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    username: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)

# ===========================
# 30. EXPENSE TYPE (New - Financial Setup)
# ===========================
class ExpenseType(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    type_name: str = Field(unique=True, index=True)
    
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None

# ===========================
# 31. EXPENSE (New - Financial Entry)
# ===========================
class Expense(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    type_id: int = Field(foreign_key="expensetype.id", index=True)
    expense_date: datetime = Field(default_factory=datetime.now)
    amount: float = Field(default=0.0)
    note: Optional[str] = None
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    
    created_by: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None
    
    # Relationships
    expense_type: "ExpenseType" = Relationship()

# ===========================
# 32. CHAT (New - Messages Feature)
# ===========================
class Chat(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    is_group: bool = Field(default=False)
    name: Optional[str] = None
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_at: Optional[datetime] = None
    
# ===========================
# 33. CHAT MEMBER (New - Messages Feature)
# ===========================
class ChatMember(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    chat_id: int = Field(foreign_key="chat.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    joined_at: datetime = Field(default_factory=datetime.now)
    is_admin: bool = Field(default=False)
    # Allows tracing if user has pending unread messages
    last_read_message_id: Optional[int] = None

# ===========================
# 34. MESSAGE (New - Messages Feature)
# ===========================
class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    chat_id: int = Field(foreign_key="chat.id", index=True)
    sender_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)  # System messages might have None
    text: Optional[str] = None
    attachment_path: Optional[str] = None
    attachment_name: Optional[str] = None
    attachment_type: Optional[str] = None
    voice_note_path: Optional[str] = None
    voice_note_duration: Optional[int] = None
    reply_to_id: Optional[int] = Field(default=None, foreign_key="message.id")
    created_at: datetime = Field(default_factory=datetime.now)
    is_deleted: bool = Field(default=False)
    is_call: bool = Field(default=False)
    call_type: Optional[str] = None
    call_status: Optional[str] = None
    call_duration: Optional[int] = None

# ===========================
# 35. MESSAGE RECEIPT (New - Messages Feature)
# ===========================
class MessageReceipt(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    message_id: int = Field(foreign_key="message.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    chat_id: int = Field(foreign_key="chat.id", index=True)
    status: str = Field(default="delivered")  # delivered, read
    updated_at: datetime = Field(default_factory=datetime.now)

# ===========================
# 36. SUPPLY (New - Inventory Management)
# ===========================
class Supply(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    note: Optional[str] = None
    is_active: bool = Field(default=True)
    
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None

# ===========================
# 37. INVENTORY (New - Inventory Management)
# ===========================
class Inventory(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    material_type: str = Field(index=True)  # "Test" or "Supply"
    
    test_id: Optional[int] = Field(default=None, foreign_key="testdefinition.id")
    supply_id: Optional[int] = Field(default=None, foreign_key="supply.id")
    
    test: Optional["TestDefinition"] = Relationship()
    supply: Optional["Supply"] = Relationship()
    
    quantity: float = Field(default=0.0)
    unit: str = Field(default="Test")
    expiration_date: datetime
    note: Optional[str] = None
    is_active: bool = Field(default=True)
    
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None
