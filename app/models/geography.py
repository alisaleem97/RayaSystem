# app/models/geography.py
# Province and Region models.

from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship


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
