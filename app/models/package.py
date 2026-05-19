# app/models/package.py
# Package, PackageTest, and Partner models.

from typing import Optional, List
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship


class Partner(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    partner_name: str = Field(unique=True, index=True)
    partner_note: Optional[str] = None
    partner_contact: Optional[str] = None
    partner_weight: Optional[float] = Field(default=None)
    is_active: bool = Field(default=True)

    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None
    deleted_by: Optional[int] = Field(default=None, foreign_key="user.id")
    deleted_at: Optional[datetime] = None


class Package(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    package_name: str = Field(unique=True, index=True)
    package_short_name: str
    price: float
    package_note: Optional[str] = None
    is_active: bool = Field(default=True)

    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None
    deleted_by: Optional[int] = Field(default=None, foreign_key="user.id")
    deleted_at: Optional[datetime] = None

    package_tests: List["PackageTest"] = Relationship(back_populates="package")


class PackageTest(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    package_id: int = Field(foreign_key="package.id")
    test_id: int = Field(foreign_key="testdefinition.id")

    package: Package = Relationship(back_populates="package_tests")
    test: "TestDefinition" = Relationship()
