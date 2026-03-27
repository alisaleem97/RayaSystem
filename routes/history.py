from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select
from sqlalchemy import or_, and_
from sqlalchemy.orm import selectinload
from datetime import datetime
import json

from database import get_session
from models import Patient, PatientVisit, Order, TestDefinition, AuditLog
from routes.helpers import templates, get_current_user

router = APIRouter()

# ===========================
# 1. PATIENT HISTORY SEARCH PAGE
# ===========================
@router.get("/patient-history", response_class=HTMLResponse)
def patient_history_search(request: Request, session: Session = Depends(get_session)):
    today_str = datetime.today().strftime("%Y-%m-%d")
    start_date = request.query_params.get("start_date", today_str)
    end_date = request.query_params.get("end_date", today_str)
    name = request.query_params.get("name", "")
    patient_id_q = request.query_params.get("patient_id", "")
    test_q = request.query_params.get("test", "")
    
    query = select(Patient).where(Patient.is_active == True)
    
    needs_visit_join = bool(start_date or end_date or test_q)
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
        
    if test_q:
        query = query.join(Order, Order.visit_id == PatientVisit.id).join(TestDefinition, Order.test_id == TestDefinition.id)
        query = query.where(
            (TestDefinition.test_name.ilike(f"%{test_q}%")) | 
            (TestDefinition.test_short_name.ilike(f"%{test_q}%"))
        )
            
    if needs_visit_join:
        query = query.distinct()
    
    patients = session.exec(query.order_by(Patient.created_at.desc())).all()
    
    return templates.TemplateResponse("patient_history_list.html", {
        "request": request,
        "patients": patients,
        "filters": {
            "start_date": start_date,
            "end_date": end_date,
            "name": name,
            "patient_id": patient_id_q,
            "test": test_q,
        }
    })

# ===========================
# 2. PATIENT HISTORY DETAIL PAGE
# ===========================
@router.get("/patient-history/{patient_id}", response_class=HTMLResponse)
def patient_history_detail(patient_id: str, request: Request, session: Session = Depends(get_session)):
    # 1. Get the Core Patient
    patient = session.exec(
        select(Patient)
        .options(selectinload(Patient.visits), selectinload(Patient.orders))
        .where(Patient.patient_id == patient_id)
    ).first()
    
    if not patient:
        return templates.TemplateResponse("error.html", {"request": request, "message": "Patient not found"})

    # 2. Gather all related IDs to build the Polymorphic Query
    visit_ids = [v.id for v in patient.visits] if patient.visits else []
    order_ids = [o.id for o in patient.orders] if patient.orders else []
    
    # We must also find the result IDs linked to these orders
    result_ids = []
    if order_ids:
        from models import Result
        results = session.exec(select(Result.id).where(Result.order_id.in_(order_ids))).all()
        result_ids = [r for r in results]

    # 3. Build the OR condition for the AuditLog
    conditions = [
        and_(AuditLog.table_name == 'patient', AuditLog.record_id == patient.id)
    ]
    if visit_ids:
        conditions.append(and_(AuditLog.table_name == 'patientvisit', AuditLog.record_id.in_(visit_ids)))
    if order_ids:
        conditions.append(and_(AuditLog.table_name == 'order', AuditLog.record_id.in_(order_ids)))
    if result_ids:
        conditions.append(and_(AuditLog.table_name == 'result', AuditLog.record_id.in_(result_ids)))
        
    logs_query = select(AuditLog).where(or_(*conditions)).order_by(AuditLog.created_at.desc())
    audit_logs = session.exec(logs_query).all()

    # 4. Format the output for the UI
    formatted_logs = []
    for log in audit_logs:
        # Create a human-readable action string
        action_detail = f"Action on {log.table_name.capitalize()} record."
        
        # If there are JSON updates, we can extract them to show what changed
        if log.new_values:
            try:
                new_val_dict = json.loads(log.new_values)
                if "status" in new_val_dict:
                    action_detail = f"Status changed to: {new_val_dict['status']}"
                elif "result_value" in new_val_dict:
                    action_detail = f"Result entered/updated."
                elif "authorized" in new_val_dict or "double_authorized" in new_val_dict:
                    action_detail = "Authorization state changed."
            except:
                pass # Fallback to default if not JSON

        formatted_logs.append({
            "date": log.created_at,
            "action_type": f"{log.action.upper()} - {log.table_name.upper()}",
            "username": log.username or "System",
            "detail": action_detail
        })

    return templates.TemplateResponse("patient_history_detail.html", {
        "request": request,
        "patient": patient,
        "logs": formatted_logs
    })