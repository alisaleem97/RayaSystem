# routes/auth.py
# Authentication and dashboard routes.

from fastapi import APIRouter, Depends, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select, func, or_, and_
from database import get_session
from models import User, Patient, Order, Result, PatientVisit, DeletedRecord, ResultDetail, TestDefinition, Parameter
# ✅ Centralized imports
from routes.helpers import templates, create_audit_log, log_activity_action, get_current_user, SECRET_KEY, pwd_context
from datetime import datetime, date, time

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
    
    # 1. Total Patients (Today)
    today_start = datetime.combine(date.today(), time.min)
    today_end = datetime.combine(date.today(), time.max)
    today_patients_count = session.exec(select(func.count(Patient.id)).where(Patient.created_at >= today_start, Patient.created_at <= today_end)).one()
    
    # Orders and Results logic for Pending, Done, Waiting
    stmt_has_orders = select(Order.patient_id).distinct()
    has_orders_ids = set(session.exec(stmt_has_orders).all())
    
    # Pending: at least one order has NO result OR result is NOT authorized.
    stmt_pending = select(Order.patient_id).outerjoin(Result, Order.id == Result.order_id).where(or_(Result.id == None, Result.authorized == False)).distinct()
    pending_ids = set(session.exec(stmt_pending).all())
    pending_patients_count = len(pending_ids)
    
    # Done: ALL tests are double authorized.
    # Means: Patient has orders AND Patient is NOT in the "not double authorized" list.
    stmt_not_done = select(Order.patient_id).outerjoin(Result, Order.id == Result.order_id).where(or_(Result.id == None, Result.double_authorized == False)).distinct()
    not_done_ids = set(session.exec(stmt_not_done).all())
    
    done_ids = has_orders_ids - not_done_ids
    done_patients_count = len(done_ids)
    
    # Waiting: ALL tests are AUTH, but at least one NOT Double AUTH.
    # This means: NOT Pending AND NOT Done.
    waiting_ids = has_orders_ids - pending_ids - done_ids
    waiting_patients_count = len(waiting_ids)
    
    # Deleted patients
    deleted_patients_count = session.exec(select(func.count(DeletedRecord.id)).where(DeletedRecord.source_table == "patient")).one()
    
    # Call Centre
    call_centre_total = done_patients_count
    done_ids_list = list(done_ids) if done_ids else [-1]
    sent_count = session.exec(select(func.count(func.distinct(PatientVisit.patient_id))).where(PatientVisit.patient_id.in_(done_ids_list), PatientVisit.is_called == True)).one()
    not_sent_count = call_centre_total - sent_count
    
    # Critical Value Alerts (Last 10 PANIC results)
    stmt_critical = select(ResultDetail, Order, Patient, Parameter, Result).join(Result, Result.id == ResultDetail.result_id).join(Order, Order.id == Result.order_id).join(Patient, Patient.id == Order.patient_id).join(Parameter, Parameter.id == ResultDetail.parameter_id).where(ResultDetail.flag == "⚠ PANIC").order_by(Result.entered_at.desc()).limit(10)
    critical_data = session.exec(stmt_critical).all()
    critical_alerts = []
    for cd, order, pat, param, res in critical_data:
        critical_alerts.append({
            "patient_name": pat.full_name,
            "patient_id": pat.patient_id,
            "test_name": param.parameter_name,
            "value": cd.result_value,
            "date": res.entered_at.strftime('%Y-%m-%d %H:%M') if res.entered_at else ""
        })
    # Also standalone test panics
    stmt_critical_main = select(Result, Order, Patient, TestDefinition).join(Order, Order.id == Result.order_id).join(Patient, Patient.id == Order.patient_id).join(TestDefinition, TestDefinition.id == Order.test_id).where(Result.flag == "⚠ PANIC").order_by(Result.entered_at.desc()).limit(10)
    critical_main_data = session.exec(stmt_critical_main).all()
    for cm, order, pat, test in critical_main_data:
        critical_alerts.append({
            "patient_name": pat.full_name,
            "patient_id": pat.patient_id,
            "test_name": test.test_name,
            "value": cm.result_value,
            "date": cm.entered_at.strftime('%Y-%m-%d %H:%M') if cm.entered_at else ""
        })
    critical_alerts.sort(key=lambda x: x["date"], reverse=True)
    critical_alerts = critical_alerts[:10]

    # Demographics
    males = session.exec(select(func.count(Patient.id)).where(func.lower(Patient.gender) == "male")).one()
    females = session.exec(select(func.count(Patient.id)).where(func.lower(Patient.gender) == "female")).one()
    
    # Top Requested Tests
    top_tests_stmt = select(TestDefinition.test_name, func.count(Order.id).label("count")).join(Order, Order.test_id == TestDefinition.id).group_by(TestDefinition.test_name).order_by(func.count(Order.id).desc()).limit(5)
    top_tests = session.exec(top_tests_stmt).all()
    
    dashboard_data = {
        "today_patients": today_patients_count,
        "pending_patients": pending_patients_count,
        "waiting_patients": waiting_patients_count,
        "done_patients": done_patients_count,
        "deleted_patients": deleted_patients_count,
        "call_center_total": call_centre_total,
        "call_center_sent": sent_count,
        "call_center_not_sent": not_sent_count,
        "critical_alerts": critical_alerts,
        "males": males,
        "females": females,
        "top_tests": [{"name": t[0], "count": t[1]} for t in top_tests]
    }
    
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "message_success": success, "message_error": error, "current_user": current_user, "dash": dashboard_data}
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