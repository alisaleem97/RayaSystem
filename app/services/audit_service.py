# app/services/audit_service.py
# Audit logging, activity logging, and archival services.

from datetime import datetime
import json
from sqlmodel import Session

from app.models import AuditLog, DeletedRecord, ActivityLog


def log_audit_action(session: Session, table_name: str, record_id: int, action: str,
                     current_user, old_values: dict = None, new_values: dict = None):
    """Universal Audit Logger. Safely wraps in try/except to never crash the caller."""
    try:
        username = "System"
        user_id = None
        if current_user:
            user_id = current_user.id
            username = getattr(current_user, 'full_name', current_user.username)

        log_entry = AuditLog(
            table_name=table_name.lower(),
            record_id=record_id,
            action=action.upper(),
            user_id=user_id,
            username=username,
            old_values=json.dumps(old_values) if old_values else None,
            new_values=json.dumps(new_values) if new_values else None,
            created_at=datetime.now()
        )
        session.add(log_entry)
    except Exception as e:
        print(f"Warning: Audit Log Failure: {str(e)}")


# Backwards-compatible alias
create_audit_log = log_audit_action


def archive_deleted_record(session: Session, source_table: str, record_id: int,
                           record_data: dict, current_user, deleted_reason: str = None):
    """Saves a JSON snapshot of a record before soft or hard deletion."""
    try:
        user_id = current_user.id if hasattr(current_user, 'id') else 0
        archive = DeletedRecord(
            source_table=source_table,
            record_id=record_id,
            record_data=json.dumps(record_data),
            deleted_by=user_id,
            deleted_reason=deleted_reason
        )
        session.add(archive)
    except Exception as e:
        print(f"Warning: Failed to archive deleted record: {str(e)}")


def log_activity_action(session: Session, action_type: str, description: str,
                        current_user, target_type: str = None, target_id: int = None):
    """Logs non-data operational events (logins, printing, etc.)."""
    try:
        user_id = current_user.id if hasattr(current_user, 'id') else None
        username = getattr(current_user, 'full_name', getattr(current_user, 'username', "System"))

        activity = ActivityLog(
            action_type=action_type.upper(),
            description=description,
            user_id=user_id,
            username=username,
            target_type=target_type,
            target_id=target_id
        )
        session.add(activity)
    except Exception as e:
        print(f"Warning: Activity Log Failure: {str(e)}")
