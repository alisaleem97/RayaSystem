# app/services/auth_service.py
# Authentication helpers: session validation, user lookup, inactivity timeout.

from fastapi import Request
from sqlmodel import Session
from datetime import datetime, timedelta
from typing import Optional

from app.config import SECRET_KEY


def get_current_user(request: Request, session: Session) -> Optional["User"]:
    """Get current logged-in user from session cookie."""
    try:
        from itsdangerous import URLSafeSerializer
        from app.models import User

        s = URLSafeSerializer(SECRET_KEY)
        cookie = request.cookies.get("nexlab_session")
        if not cookie:
            return None
        data = s.loads(cookie)
        user_id = data.get("user_id")
        session_token = data.get("session_token")

        if user_id and session_token:
            user = session.get(User, user_id)
            if user and user.session_token == session_token:
                # Check inactivity timeout (2 hours)
                if user.last_seen and (datetime.now() - user.last_seen) > timedelta(hours=2):
                    user.session_token = None
                    session.commit()
                    return None

                # Update last_seen if > 5 mins to avoid spamming DB
                if not user.last_seen or (datetime.now() - user.last_seen) > timedelta(minutes=5):
                    user.last_seen = datetime.now()
                    session.commit()

                return user
    except Exception:
        pass
    return None


def login_required(request: Request, session: Session) -> Optional["User"]:
    """Check if user is logged in, return user or None."""
    return get_current_user(request, session)
