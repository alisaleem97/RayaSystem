# app/models/order.py
# Order, Result, and ResultDetail models.

from typing import Optional, List
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship

from app.models.department import Parameter


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
    package_name: Optional[str] = Field(default=None)
    # Price snapshot at order time
    unit_price: float = Field(default=0.0)
    discount_amount: float = Field(default=0.0)
    final_price: float = Field(default=0.0)
    no_sample_reason: Optional[str] = Field(default=None)

    # Relationships — use string references for cross-module models
    patient: "Patient" = Relationship(back_populates="orders")
    test: "TestDefinition" = Relationship()
    result: Optional["Result"] = Relationship(back_populates="order")
    visit: Optional["PatientVisit"] = Relationship(back_populates="orders")


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
    details: List["ResultDetail"] = Relationship(back_populates="result", cascade_delete=True)


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
