from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload
from datetime import datetime

from database import get_session
from models import Patient, PatientVisit, Order, TestDefinition, Package
from routes.helpers import templates, require_permission

router = APIRouter()

@router.get("/patient-status", response_class=HTMLResponse)
def patient_status_page(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "patient_status"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=303)
        
    today_str = datetime.today().strftime("%Y-%m-%d")
    from_date = request.query_params.get("from_date", today_str)
    to_date = request.query_params.get("to_date", today_str)
    name = request.query_params.get("name", "")
    patient_id_q = request.query_params.get("patient_id", "")
    status_q = request.query_params.get("status", "all")
    
    # Visit-centric query (each visit shown separately)
    visit_query = (
        select(PatientVisit)
        .options(
            selectinload(PatientVisit.patient),
            selectinload(PatientVisit.orders).selectinload(Order.test)
        )
        .join(Patient, PatientVisit.patient_id == Patient.id)
        .where(Patient.is_active == True)
    )
    
    if from_date:
        visit_query = visit_query.where(PatientVisit.visit_date >= datetime.strptime(f"{from_date} 00:00:00", "%Y-%m-%d %H:%M:%S"))
    if to_date:
        visit_query = visit_query.where(PatientVisit.visit_date <= datetime.strptime(f"{to_date} 23:59:59", "%Y-%m-%d %H:%M:%S"))
    if name:
        visit_query = visit_query.where(Patient.full_name.ilike(f"%{name}%"))
    if patient_id_q:
        visit_query = visit_query.where(Patient.patient_id.ilike(f"%{patient_id_q}%"))
        
    if status_q != "all":
        visit_query = visit_query.join(Order, Order.visit_id == PatientVisit.id)
        if status_q == "pending":
            visit_query = visit_query.where(Order.status == "ordered")
        elif status_q == "resulted":
            visit_query = visit_query.where(Order.status == "resulted")
        elif status_q == "auth":
            visit_query = visit_query.where(Order.status == "authorized")
        elif status_q == "double_auth":
            visit_query = visit_query.where(Order.status == "double_authorized")

    visits = session.exec(visit_query.distinct().order_by(PatientVisit.visit_date.desc())).all()
    
    patient_data = []
    for visit in visits:
        patient = visit.patient
        if not patient:
            continue
            
        tests_data = []
        packages = {}
        standalones = []
        
        for order in visit.orders:
            if not order.test or order.status == "no_sample":
                continue
                
            if status_q == "pending" and order.status != "ordered": continue
            if status_q == "resulted" and order.status != "resulted": continue
            if status_q == "auth" and order.status != "authorized": continue
            if status_q == "double_auth" and order.status != "double_authorized": continue
            
            # Formulate the human readable status
            readable_status = "Pending"
            badge_color = "bg-red-500 text-white" 
            if order.status == "resulted":
                readable_status = "Resulted"
                badge_color = "bg-blue-500 text-white"
            elif order.status == "authorized":
                readable_status = "Authorize"
                badge_color = "bg-emerald-500 text-white"
            elif order.status == "double_authorized":
                readable_status = "Double Authorized"
                badge_color = "bg-purple-500 text-white" 

            test_obj = {
                "name": order.test.test_name,
                "status": readable_status,
                "color": badge_color
            }
            
            if order.package_name:
                if order.package_name not in packages:
                    packages[order.package_name] = []
                packages[order.package_name].append(test_obj)
            else:
                standalones.append(test_obj)
                
        if not packages and not standalones:
            continue
            
        for pkg_name, pkg_tests in packages.items():
            sub_test_names = ",".join([t["name"] for t in pkg_tests])
            tests_data.append({
                "is_package": True,
                "group_header": f"{pkg_name.upper()},{sub_test_names}",
                "tests": pkg_tests
            })
            
        for t in standalones:
            tests_data.append({
                "is_package": False,
                "test": t
            })
            
        patient_data.append({
            "patient": patient,
            "visit": visit,
            "registration_date": visit.visit_date,
            "tests": tests_data
        })
        
    return templates.TemplateResponse("patient_status.html", {
        "request": request,
        "patient_data": patient_data,
        "filters": {
            "from_date": from_date,
            "to_date": to_date,
            "name": name,
            "patient_id": patient_id_q,
            "status": status_q
        }
    })
