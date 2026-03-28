# routes/auth.py
# Authentication and dashboard routes.

from fastapi import APIRouter, Depends, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from database import get_session
from models import User, Patient
# ✅ NEW: Imported create_audit_log and get_current_user
from routes.helpers import templates, create_audit_log, get_current_user

router = APIRouter()

# ===========================
# DASHBOARD & AUTH
# ===========================
@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session)):
    patients = session.exec(select(Patient).order_by(Patient.created_at.desc())).all()
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "patients": patients, "message_success": success, "message_error": error}
    )

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...), session: Session = Depends(get_session)):
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    user = session.exec(select(User).where(User.username == username)).first()
    
    if user and pwd_context.verify(password, user.hashed_password) and user.is_active:
        # ---------------------------------------------------------
        # ✅ NEW: INJECT AUDIT LOG HERE (Tracking Successful Login)
        # ---------------------------------------------------------
        create_audit_log(
            session, 
            "user", 
            user.id, 
            "LOGIN", 
            user, # The user who just authenticated
            new_values={"action": "Successful login"}
        )
        session.commit()
        # ---------------------------------------------------------
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    else:
        # ---------------------------------------------------------
        # ✅ NEW: INJECT AUDIT LOG HERE (Tracking Failed Login)
        # ---------------------------------------------------------
        if user: 
            # We only log if the username actually exists in the system
            create_audit_log(
                session, 
                "user", 
                user.id, 
                "LOGIN_FAILED", 
                user, 
                new_values={"action": "Failed login attempt (bad password or inactive account)"}
            )
            session.commit()
        # ---------------------------------------------------------
        return templates.TemplateResponse("login.html", {"request": request, "message_error": "Invalid username or password"})

# ✅ NEW: Added request and session dependencies to logout so we can track WHO is logging out
@router.get("/logout")
def logout(request: Request, session: Session = Depends(get_session)):
    current_user = get_current_user(request, session)
    
    # ---------------------------------------------------------
    # ✅ NEW: INJECT AUDIT LOG HERE (Tracking Logout)
    # ---------------------------------------------------------
    if current_user:
        create_audit_log(
            session, 
            "user", 
            current_user.id, 
            "LOGOUT", 
            current_user, 
            new_values={"action": "User logged out"}
        )
        session.commit()
    # ---------------------------------------------------------
    
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)