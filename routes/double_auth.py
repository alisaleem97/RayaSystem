# routes/double_auth.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload
from datetime import datetime

from database import get_session
from models import Patient, PatientVisit, Order, TestDefinition, Result, ResultDetail
# ✅ NEW: Added log_audit_action to imports
from routes.helpers import templates, get_current_user, log_audit_action

router = APIRouter()

# 1. Double Auth Patients List
@router.get("/double-auth", response_class=HTMLResponse)
def double_auth_patients_page(request: Request, session: Session = Depends(get_session)):
    today_str = datetime.today().strftime("%Y-%m-%d")
    start_date = request.query_params.get("start_date", today_str)
    end_date = request.query_params.get("end_date", today_str)
    name = request.query_params.get("name", "")
    patient_id_q = request.query_params.get("patient_id", "")
    test_q = request.query_params.get("test", "")
    status_q = request.query_params.get("status", "all")
    
    query = select(Patient).where(Patient.is_active == True)
    
    needs_visit_join = bool(start_date or end_date or test_q or status_q != "all")
    if needs_visit_join:
        query = query.join(PatientVisit)
        
    if start_date:
        query = query.where(PatientVisit.visit_date >= f"{start_date} 00:00:00")
    if end_date:
        query = query.where(PatientVisit.visit_date <= f"{end_date} 23:59:59")
        
    if name:
        query = query.where(Patient.full_name.ilike(f"%{name}%"))
    if patient_id_q:
        query = query.where(Patient.patient_id.ilike(f"%{patient_id_q}%"))
        
    if test_q or status_q != "all":
        query = query.join(Order, Order.visit_id == PatientVisit.id).join(TestDefinition, Order.test_id == TestDefinition.id)
        if test_q:
            query = query.where(
                (TestDefinition.test_name.ilike(f"%{test_q}%")) | 
                (TestDefinition.test_short_name.ilike(f"%{test_q}%"))
            )
        if status_q == "pending":
            query = query.where(Order.status == "ordered")
        elif status_q == "received":
            query = query.where(Order.status == "resulted")
        elif status_q == "authorize":
            query = query.where(Order.status == "authorized")
        elif status_q == "double_authorized":
            query = query.where(Order.status == "double_authorized")
        elif status_q == "AD":
            query = query.where(Order.status.in_(["authorized", "double_authorized"]))
            
    if needs_visit_join or not (test_q or status_q != "all"):
        query = query.distinct()
    
    patients_result = session.exec(query.order_by(Patient.created_at.desc())).all()
    
    patient_data = []
    for patient in patients_result:
        visit_query = select(PatientVisit).options(selectinload(PatientVisit.orders).selectinload(Order.test)).where(PatientVisit.patient_id == patient.id)
        if start_date:
            visit_query = visit_query.where(PatientVisit.visit_date >= f"{start_date} 00:00:00")
        if end_date:
            visit_query = visit_query.where(PatientVisit.visit_date <= f"{end_date} 23:59:59")
            
        visit = session.exec(visit_query.order_by(PatientVisit.id.desc())).first()
        visit_date = visit.visit_date if visit else patient.created_at
        
        tests_data = []
        if visit:
            packages = {}
            standalones = []
            
            for order in visit.orders:
                if not order.test or order.status == "no_sample":
                    continue
                # Determine color
                status_color = "red"
                if order.status == "resulted":
                    status_color = "blue"
                elif order.status == "authorized":
                    status_color = "green"
                elif order.status == "double_authorized":
                    status_color = "purple"
                    
                test_info = {
                    "name": order.test.test_name,
                    "color": status_color
                }
                
                if order.package_name:
                    if order.package_name not in packages:
                        packages[order.package_name] = []
                    packages[order.package_name].append(test_info)
                else:
                    standalones.append(test_info)
            
            for pkg_name, pkg_tests in packages.items():
                tests_data.append({
                    "is_package": True,
                    "package_name": pkg_name,
                    "tests": pkg_tests
                })
            for t in standalones:
                tests_data.append({
                    "is_package": False,
                    "test": t
                })
                
        patient_data.append({
            "patient": patient,
            "registration_date": visit_date,
            "tests": tests_data
        })
    
    return templates.TemplateResponse("double_auth_patients.html", {
        "request": request,
        "patient_data": patient_data,
        "filters": {
            "start_date": start_date,
            "end_date": end_date,
            "name": name,
            "patient_id": patient_id_q,
            "test": test_q,
            "status": status_q,
        }
    })

# 2. Double Auth Page
@router.get("/double-auth/{patient_id}", response_class=HTMLResponse)
def double_auth_page(patient_id: str, request: Request, session: Session = Depends(get_session)):
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
            
        result.double_authorized = True
        result.double_authorized_by = current_user.id
        result.double_authorized_at = datetime.utcnow()
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
        return {"success": True, "message": "Test double authorized"}
    except Exception as e:
        session.rollback()
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)

@router.post("/api/double-auth/rerun/{order_id}")
def rerun_order(order_id: int, request: Request, session: Session = Depends(get_session)):
    current_user = get_current_user(request, session)
    if not current_user:
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)
        
    try:
        order = session.get(Order, order_id)
        if not order:
            return JSONResponse({"success": False, "message": "Order not found"}, status_code=404)
            
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
    current_user = get_current_user(request, session)
    if not current_user:
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)
        
    try:
        data = await request.json()
        reason = data.get("reason", "")
        
        order = session.get(Order, order_id)
        if not order:
            return JSONResponse({"success": False, "message": "Order not found"}, status_code=404)
            
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