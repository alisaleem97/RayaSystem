# app/models/patient.py
# Patient, PatientVisit, and Attachment models.

from typing import Optional, List
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship


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


class Attachment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    visit_id: Optional[int] = Field(default=None, foreign_key="patientvisit.id", index=True)
    file_name: str
    file_path: str
    file_type: str
    description: Optional[str] = None
    uploaded_by: int = Field(foreign_key="user.id")
    uploaded_at: datetime = Field(default_factory=datetime.now)
