# app/models/inventory.py
# Supply, Inventory, and CalControl models.

from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship


class Supply(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    note: Optional[str] = None
    is_active: bool = Field(default=True)
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None


class Inventory(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    material_type: str = Field(index=True)
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


class CalControl(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    test_id: int = Field(foreign_key="testdefinition.id", index=True)
    device_id: int = Field(foreign_key="device.id", index=True)
    process_type: str = Field(index=True)
    quantity: float
    note: Optional[str] = None
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    test: "TestDefinition" = Relationship()
    device: "Device" = Relationship()
