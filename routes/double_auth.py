# routes/double_auth.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload
from datetime import datetime

from database import get_session
from models import Patient, PatientVisit, Order, TestDefinition, Result, ResultDetail
# ✅ NEW: Added log_audit_action to imports
from routes.helpers import templates, get_current_user, log_audit_action, log_activity_action, require_permission, build_patient_visit_data

router = APIRouter()

# 1. Double Auth Patients List
@router.get("/double-auth", response_class=HTMLResponse)
def double_auth_patients_page(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "double_auth"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=303)
    
    patient_data, filters = build_patient_visit_data(session, request)
    
    return templates.TemplateResponse("double_auth_patients.html", {
        "request": request,
        "patient_data": patient_data,
        "filters": filters
    })

# 2. Double Auth Page
@router.get("/double-auth/{patient_id}", response_class=HTMLResponse)
def double_auth_page(patient_id: str, request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "double_auth"):
        return RedirectResponse(url="/double-auth?error=Permission Denied", status_code=303)
    current_user = get_current_user(request, session)
    patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()
    if not patient:
        return RedirectResponse(url="/double-auth?error=Patient not found", status_code=303)

    visit = session.exec(
        select(PatientVisit)
        .where(PatientVisit.patient_id == patient.id)
        .order_by(PatientVisit.id.desc())
    ).first()

    visit_user_name = None
    if visit and visit.created_by:
        from models import User
        user = session.get(User, visit.created_by)
        if user:
            visit_user_name = user.full_name or user.username

    return templates.TemplateResponse("double_auth.html", {
        "request": request,
        "patient": patient,
        "visit": visit,
        "visit_user_name": visit_user_name,
    })


# 3. Actions API
@router.post("/api/double-auth/authorize/{order_id}")
def double_authorize_order(order_id: int, request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "double_auth", "double_authorize"):
        return JSONResponse({"success": False, "message": "Permission Denied"}, status_code=403)
    current_user = get_current_user(request, session)
    if not current_user:
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)
        
    try:
        order = session.get(Order, order_id)
        if not order:
            return JSONResponse({"success": False, "message": "Order not found"}, status_code=404)
            
        result = session.exec(select(Result).where(Result.order_id == order_id)).first()
        if not result:
            return JSONResponse({"success": False, "message": "Result not found"}, status_code=404)
        
        # Guard: must be authorized first before double-authorizing
        if not result.authorized:
            return JSONResponse({"success": False, "message": "Test must be authorized before double authorization"}, status_code=400)
        
        # Guard: must be in correct status
        if order.status not in ("authorized", "resulted"):
            return JSONResponse({"success": False, "message": f"Cannot double-authorize from status '{order.status}'"}, status_code=400)
        
        result.double_authorized = True
        result.double_authorized_by = current_user.id
        result.double_authorized_at = datetime.now()
        result.unauth_reason = None
        
        order.status = "double_authorized"
        
        session.add(result)
        session.add(order)

        # ---------------------------------------------------------
        # ✅ NEW: INJECT AUDIT LOG HERE (Tracking Double Auth)
        # ---------------------------------------------------------
        log_audit_action(
            session=session,
            table_name="order",
            record_id=order.id,
            action="UPDATE",
            current_user=current_user,
            new_values={
                "action": "Test Double Authorized",
                "status": "double_authorized"
            }
        )
        # ---------------------------------------------------------

        session.commit()

        # Activity Log
        test_name = order.test.test_name if order.test else "Unknown"
        patient = session.get(Patient, order.patient_id) if order.patient_id else None
        patient_name = patient.full_name if patient else "Unknown"
        log_activity_action(session, "DOUBLE_AUTH", f"Double authorized test '{test_name}' for patient {patient_name}", current_user, "patient", order.patient_id)
        session.commit()

        return {"success": True, "message": "Test double authorized"}
    except Exception as e:
        session.rollback()
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)

@router.post("/api/double-auth/rerun/{order_id}")
def rerun_order(order_id: int, request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "double_auth", "rerun"):
        return JSONResponse({"success": False, "message": "Permission Denied"}, status_code=403)
    current_user = get_current_user(request, session)
    if not current_user:
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)
        
    try:
        order = session.get(Order, order_id)
        if not order:
            return JSONResponse({"success": False, "message": "Order not found"}, status_code=404)
        
        # Guard: rerun only allowed from authorized or double_authorized
        if order.status not in ("authorized", "double_authorized"):
            return JSONResponse({"success": False, "message": f"Cannot rerun from status '{order.status}'. Only authorized tests can be rerun."}, status_code=400)
            
        result = session.exec(select(Result).where(Result.order_id == order_id)).first()
        if result:
            # Standalone result value backup
            if result.result_value:
                result.rerun_result = result.result_value
                result.result_value = ""
            
            # Reset authorization
            result.authorized = False
            result.authorized_by = None
            result.authorized_at = None
            result.double_authorized = False
            result.double_authorized_by = None
            result.double_authorized_at = None
            
            # Handle children results (ResultDetail)
            details = session.exec(select(ResultDetail).where(ResultDetail.result_id == result.id)).all()
            for detail in details:
                if detail.result_value:
                    detail.rerun_result = detail.result_value
                    detail.result_value = ""
                session.add(detail)
                
            session.add(result)
            
        order.status = "ordered"  # pending
        session.add(order)

        # ---------------------------------------------------------
        # ✅ NEW: INJECT AUDIT LOG HERE (Tracking ReRun)
        # ---------------------------------------------------------
        log_audit_action(
            session=session,
            table_name="order",
            record_id=order.id,
            action="UPDATE",
            current_user=current_user,
            new_values={
                "action": "Test marked for ReRun",
                "status": "ordered"
            }
        )
        # ---------------------------------------------------------

        session.commit()
        return {"success": True, "message": "Test marked for rerun (pending)"}
    except Exception as e:
        session.rollback()
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)

@router.post("/api/double-auth/unauth/{order_id}")
async def unauth_order(order_id: int, request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "double_auth", "unauthorize"):
        return JSONResponse({"success": False, "message": "Permission Denied"}, status_code=403)
    current_user = get_current_user(request, session)
    if not current_user:
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)
        
    try:
        data = await request.json()
        reason = data.get("reason", "")
        
        order = session.get(Order, order_id)
        if not order:
            return JSONResponse({"success": False, "message": "Order not found"}, status_code=404)
        
        # Guard: unauth only allowed from double_authorized
        if order.status != "double_authorized":
            return JSONResponse({"success": False, "message": f"Cannot unauthorize from status '{order.status}'. Only double-authorized tests can be unauthorized."}, status_code=400)
            
        result = session.exec(select(Result).where(Result.order_id == order_id)).first()
        if not result:
            return JSONResponse({"success": False, "message": "Result not found"}, status_code=404)
            
        result.double_authorized = False
        result.double_authorized_by = None
        result.double_authorized_at = None
        result.unauth_reason = reason
        
        order.status = "authorized"  # Return to auth and rerun buttons
        
        session.add(result)
        session.add(order)

        # ---------------------------------------------------------
        # ✅ NEW: INJECT AUDIT LOG HERE (Tracking Unauthorize)
        # ---------------------------------------------------------
        log_audit_action(
            session=session,
            table_name="order",
            record_id=order.id,
            action="UPDATE",
            current_user=current_user,
            new_values={
                "action": "Test Unauthorized",
                "status": "authorized",
                "reason": reason
            }
        )
        # ---------------------------------------------------------

        session.commit()
        return {"success": True, "message": "Test Unauthorized with reason"}
    except Exception as e:
        session.rollback()
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)