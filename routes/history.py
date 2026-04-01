from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from sqlalchemy import or_, and_
from sqlalchemy.orm import selectinload
from datetime import datetime
import json

from database import get_session
from models import Patient, PatientVisit, Order, TestDefinition, AuditLog, ActivityLog # ✅ Added ActivityLog
from routes.helpers import templates, require_permission, build_patient_list_query

router = APIRouter()

# ===========================
# 1. PATIENT HISTORY SEARCH PAGE
# ===========================
@router.get("/patient-history", response_class=HTMLResponse)
def patient_history_search(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "patient_history"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=303)
    
    query, filters = build_patient_list_query(request)
    patients = session.exec(query).all()
    
    return templates.TemplateResponse("patient_history_list.html", {
        "request": request,
        "patients": patients,
        "filters": filters
    })

# ===========================
# 2. PATIENT HISTORY DETAIL PAGE
# ===========================
@router.get("/patient-history/{patient_id}", response_class=HTMLResponse)
def patient_history_detail(patient_id: str, request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "patient_history"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=303)
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

    # 4. Smart Formatting for the UI
    formatted_logs = []
    for log in audit_logs:
        # Normalize text to avoid case-sensitivity bugs
        safe_action = str(log.action).upper() if log.action else ""
        safe_table = str(log.table_name).lower() if log.table_name else ""

        # Default Fallbacks
        action_type = f"{safe_action} - {safe_table.upper()}"
        action_detail = f"System action on {safe_table} record."

        # Parse the JSON payload we injected during saves
        if log.new_values:
            try:
                new_vals = json.loads(log.new_values)
                explicit_action = new_vals.get("action")
                test_name = new_vals.get("test_name")

                # --- TRANSLATE ACTION TYPE ---
                if safe_action == "PRINT":
                    action_type = "Document Printed"
                elif safe_action == "DISPATCH":
                    action_type = "Communication"
                elif safe_action == "CREATE" and safe_table == "patient":
                    action_type = "Registration"
                elif safe_action == "UPDATE" and safe_table == "patient":
                    action_type = "Profile Update"
                elif safe_table == "order":
                    if explicit_action:
                        if "Double" in explicit_action:
                            action_type = "Double Auth"
                        elif "Authorized" in explicit_action:
                            action_type = "Authorization"
                        elif "No Sample" in explicit_action:
                            action_type = "Sample Issue"
                        elif "ReRun" in explicit_action:
                            action_type = "ReRun Request"
                        else:
                            action_type = "Result Update"
                    else:
                        action_type = "Test Update"
                elif safe_table == "patientvisit":
                    action_type = "Visit Update"

                # --- TRANSLATE ACTION DETAIL ---
                if explicit_action:
                    action_detail = explicit_action
                    
                    if test_name:
                        action_detail += f": {test_name}"
                    if "reason" in new_vals and new_vals["reason"]:
                        action_detail += f" (Reason: {new_vals['reason']})"
                    if "phone" in new_vals:
                        action_detail += f" to {new_vals['phone']}"
                    if "total_tests_ordered" in new_vals:
                        action_detail += f" with {new_vals['total_tests_ordered']} tests"
                else:
                    if "status" in new_vals:
                        friendly_status = str(new_vals['status']).replace('_', ' ').title()
                        action_detail = f"Status changed to: {friendly_status}"

            except Exception:
                pass # Silently fallback to raw data if JSON parsing fails

        formatted_logs.append({
            "date": log.created_at,
            "action_type": action_type,
            "username": log.username or "System",
            "detail": action_detail
        })

    return templates.TemplateResponse("patient_history_detail.html", {
        "request": request,
        "patient": patient,
        "logs": formatted_logs
    })

# ===========================
# 3. GLOBAL ACTIVITY LOGS PAGE
# ===========================
@router.get("/activity-logs", response_class=HTMLResponse)
def global_activity_logs(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "activity_logs", "view"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=303)

    # Filters
    filter_user = request.query_params.get("user", "")
    filter_action = request.query_params.get("action", "")

    query = select(ActivityLog)

    if filter_user:
        query = query.where(ActivityLog.username == filter_user)
    if filter_action:
        query = query.where(ActivityLog.action_type == filter_action)

    query = query.order_by(ActivityLog.created_at.desc()).limit(500)
    activities = session.exec(query).all()

    # Get distinct usernames and action types for the filter dropdowns
    all_users = session.exec(select(ActivityLog.username).distinct()).all()
    all_actions = session.exec(select(ActivityLog.action_type).distinct()).all()

    return templates.TemplateResponse("activity_logs.html", {
        "request": request,
        "activities": activities,
        "all_users": sorted([u for u in all_users if u]),
        "all_actions": sorted([a for a in all_actions if a]),
        "filter_user": filter_user,
        "filter_action": filter_action
    })