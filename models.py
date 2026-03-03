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
    created_at: datetime = Field(default_factory=datetime.utcnow)

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
    created_at: datetime = Field(default_factory=datetime.utcnow)

# ===========================
# 2. PATIENT
# ===========================
class Patient(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: str = Field(unique=True, index=True)
    full_name: str
    date_of_birth: datetime
    gender: str
    phone: str
    email: Optional[str] = None
    address: Optional[str] = None
    
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None
    deleted_by: Optional[int] = Field(default=None, foreign_key="user.id")
    deleted_at: Optional[datetime] = None
    
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
    created_at: datetime = Field(default_factory=datetime.utcnow)
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
    created_at: datetime = Field(default_factory=datetime.utcnow)
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
    created_at: datetime = Field(default_factory=datetime.utcnow)
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
    created_at: datetime = Field(default_factory=datetime.utcnow)
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
    created_at: datetime = Field(default_factory=datetime.utcnow)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None
    deleted_by: Optional[int] = Field(default=None, foreign_key="user.id")
    deleted_at: Optional[datetime] = None

# ===========================
# 8. TEST DEFINITION (FIXED - No Unique on report_note_id)
# ===========================
class TestDefinition(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    test_name: str = Field(unique=True, index=True)
    test_short_name: str
    department_id: int = Field(foreign_key="department.id")
    sample_type_id: int = Field(foreign_key="sampletype.id")
    
    # ✅ FIX: Changed from optional unique to regular foreign key
    # This allows MULTIPLE tests to use the SAME report note
    report_note_id: Optional[int] = Field(default=None, foreign_key="reportnote.id")
    
    price: float
    test_note: Optional[str] = None
    test_condition: Optional[str] = None
    is_available: bool = Field(default=True)
    
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
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
# 11. TEST CATALOG (Legacy - keep for compatibility)
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
# 12. ORDER
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
    order_date: datetime = Field(default_factory=datetime.utcnow)
    collection_date: Optional[datetime] = None
    verified_date: Optional[datetime] = None
    patient: Patient = Relationship(back_populates="orders")
    test: TestDefinition = Relationship()
    result: Optional["Result"] = Relationship(back_populates="order")

# ===========================
# 13. RESULT
# ===========================
class Result(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id", unique=True)
    result_value: str
    flag: Optional[str] = None
    note: Optional[str] = None
    entered_by: int = Field(foreign_key="user.id")
    entered_at: datetime = Field(default_factory=datetime.utcnow)
    order: Order = Relationship(back_populates="result")