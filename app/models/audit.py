# app/models/audit.py
# Audit logging, activity tracking, and archival models.

from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field


class AuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    table_name: str
    record_id: int
    action: str
    user_id: int = Field(foreign_key="user.id")
    username: str
    old_values: Optional[str] = None
    new_values: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


class ActivityLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    action_type: str = Field(index=True)
    description: str
    target_type: Optional[str] = None
    target_id: Optional[int] = None
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    username: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


class DeletedRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    source_table: str = Field(index=True)
    record_id: int
    record_data: str  # Full JSON snapshot
    deleted_reason: Optional[str] = None
    deleted_by: int = Field(foreign_key="user.id")
    deleted_at: datetime = Field(default_factory=datetime.now)
