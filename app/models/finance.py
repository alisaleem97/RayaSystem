# app/models/finance.py
# Payment, Expense, and ExpenseType models.

from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship


class Payment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    visit_id: int = Field(foreign_key="patientvisit.id", index=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    amount: float
    payment_method: str = Field(default="cash")
    payment_date: datetime = Field(default_factory=datetime.now)
    note: Optional[str] = None
    recorded_by: int = Field(foreign_key="user.id")
    is_refund: bool = Field(default=False)


class ExpenseType(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    type_name: str = Field(unique=True, index=True)
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None


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
    expense_type: "ExpenseType" = Relationship()
