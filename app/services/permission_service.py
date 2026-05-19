# app/services/permission_service.py
# Permission checking for page/button access control.

from fastapi import Request
from sqlmodel import Session, select
import json

from app.services.auth_service import get_current_user
from app.models import UserPermission


def require_permission(request: Request, session: Session, page_key: str, button_key: str = None) -> bool:
    """Verifies if the current user has the specified page/button permission."""
    user = get_current_user(request, session)
    if not user:
        return False

    # Admins always have all permissions
    if user.role == 'admin' or user.username == 'admin':
        return True

    # Check page permission
    perms = session.exec(
        select(UserPermission).where(
            UserPermission.user_id == user.id,
            UserPermission.page_key == page_key
        )
    ).first()

    if not perms:
        return False

    # Check specific button permission if requested
    if button_key:
        if not perms.allowed_buttons:
            return False
        try:
            buttons = json.loads(perms.allowed_buttons)
            if button_key not in buttons:
                return False
        except Exception:
            return False

    return True
