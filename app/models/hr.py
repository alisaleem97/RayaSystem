# app/models/hr.py
# Employee and EmployeeAttachment models for HR management.

from typing import Optional, List
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship

class Employee(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    full_name: str = Field(index=True)
    age: Optional[int] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    photo_path: Optional[str] = None
    start_date: datetime = Field(default_factory=datetime.now)
    
    # Store working days as a comma-separated string or JSON string (e.g. "Monday, Tuesday, Wednesday")
    working_days: Optional[str] = None
    
    # Store hours as "09:00" and "17:00" for simplicity
    working_hours_start: Optional[str] = None
    working_hours_end: Optional[str] = None
    
    salary: Optional[float] = None
    username: Optional[str] = None
    is_active: bool = Field(default=True)
    
    created_at: datetime = Field(default_factory=datetime.now)
    
    attachments: List["EmployeeAttachment"] = Relationship(back_populates="employee", cascade_delete=True)

    @property
    def working_life_months(self) -> int:
        if not self.start_date:
            return 0
        now = datetime.now()
        delta = now.year * 12 + now.month - (self.start_date.year * 12 + self.start_date.month)
        return delta if delta > 0 else 0


class EmployeeAttachment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    employee_id: int = Field(foreign_key="employee.id", index=True)
    file_name: str
    file_path: str
    uploaded_at: datetime = Field(default_factory=datetime.now)
    
    employee: Optional["Employee"] = Relationship(back_populates="attachments")
