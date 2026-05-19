# app/models/test.py
# Test definition, test-device/parameter links, ranges, and result types.

from typing import Optional, List
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship

from app.models.department import Department, SampleType, ReportNote, Device, Parameter


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
    print_separately: bool = Field(default=False)

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


class TestDevice(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    test_id: int = Field(foreign_key="testdefinition.id")
    device_id: int = Field(foreign_key="device.id")

    test: TestDefinition = Relationship(back_populates="test_devices")
    device: Device = Relationship()


class TestParameter(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    test_id: int = Field(foreign_key="testdefinition.id")
    parameter_id: int = Field(foreign_key="parameter.id")

    test: TestDefinition = Relationship(back_populates="test_parameters")
    parameter: Parameter = Relationship()


class TestRange(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    test_id: int = Field(foreign_key="testdefinition.id")
    parameter_id: Optional[int] = Field(default=None, foreign_key="parameter.id")
    device_id: Optional[int] = Field(default=None, foreign_key="device.id")
    unit: str = Field(default="")
    gender_type: str = Field(default="both")
    age_from: int = Field(default=0)
    age_from_unit: str = Field(default="year")
    age_to: int = Field(default=999)
    age_to_unit: str = Field(default="year")
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
