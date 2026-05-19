# app/models/department.py
# Department, SampleType, Device, Parameter, and ReportNote models.

from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field


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
