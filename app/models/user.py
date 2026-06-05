# app/models/user.py
# User authentication and permission models.

from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    full_name: str
    role: str = Field(default="receptionist")
    hashed_password: str
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.now)
    last_seen: Optional[datetime] = None
    is_online: bool = Field(default=False)

    # Security & Session Fields
    failed_login_attempts: int = Field(default=0)
    locked_until: Optional[datetime] = None
    session_token: Optional[str] = None

    # Profile Fields
    date_of_birth: Optional[datetime] = None
    phone_number: Optional[str] = None
    address: Optional[str] = None

    # Audit Fields
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None


class UserPermission(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    page_key: str = Field(index=True)
    allowed_buttons: Optional[str] = Field(default=None)  # JSON array of button keys
