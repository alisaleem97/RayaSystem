# app/models/lab.py
# LabInfo and PrintTemplate models.

from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field


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
    welcome_message: Optional[str] = Field(default=None)
    welcome_template_name: Optional[str] = Field(default=None)
    province_id: Optional[int] = Field(default=None, foreign_key="province.id")
    lab_currency: str = Field(default="$")
    tax_percentage: float = Field(default=0.0)
    phone_country_code: str = Field(default="964")

    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None


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
