# routes/auth.py
# Authentication and dashboard routes.

from fastapi import APIRouter, Depends, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from database import get_session
from models import User, Patient
# ✅ Centralized imports
from routes.helpers import templates, create_audit_log, log_activity_action, get_current_user, SECRET_KEY, pwd_context

router = APIRouter()

# ===========================
# DASHBOARD & AUTH
# ===========================
@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session)):
    # Check login
    current_user = get_current_user(request, session)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    
    patients = session.exec(select(Patient).order_by(Patient.created_at.desc())).all()
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "patients": patients, "message_success": success, "message_error": error, "current_user": current_user}
    )

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, session: Session = Depends(get_session)):
    # If already logged in, redirect to dashboard
    current_user = get_current_user(request, session)
    if current_user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...), session: Session = Depends(get_session)):
    from itsdangerous import URLSafeSerializer
    s = URLSafeSerializer(SECRET_KEY)
    user = session.exec(select(User).where(User.username == username)).first()
    
    if user and pwd_context.verify(password, user.hashed_password) and user.is_active:
        # Create session cookie
        cookie_value = s.dumps({"user_id": user.id, "username": user.username})
        
        log_activity_action(
            session=session,
            action_type="LOGIN",
            description="Successful password login via portal",
            current_user=user,
            target_type="system"
        )
        session.commit()
        
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(
            key="nexlab_session",
            value=cookie_value,
            httponly=True,
            max_age=60 * 60 * 24 * 7,  # 7 days
            samesite="lax"
        )
        return response
    else:
        if user: 
            log_activity_action(
                session=session,
                action_type="LOGIN_FAILED",
                description="Failed login attempt (bad password or inactive)",
                current_user=user,
                target_type="system"
            )
            session.commit()
        return templates.TemplateResponse("login.html", {"request": request, "message_error": "Invalid username or password"})

@router.get("/logout")
def logout(request: Request, session: Session = Depends(get_session)):
    current_user = get_current_user(request, session)
    
    if current_user:
        log_activity_action(
            session=session,
            action_type="LOGOUT",
            description="User logged out manually",
            current_user=current_user,
            target_type="system"
        )
        session.commit()
    
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("nexlab_session")
    return response