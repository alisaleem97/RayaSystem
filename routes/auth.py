# routes/auth.py
# Authentication and dashboard routes.

from fastapi import APIRouter, Depends, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from database import get_session
from models import User, Patient
from routes.helpers import templates

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
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    else:
        return templates.TemplateResponse("login.html", {"request": request, "message_error": "Invalid username or password"})

@router.get("/logout")
def logout():
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
