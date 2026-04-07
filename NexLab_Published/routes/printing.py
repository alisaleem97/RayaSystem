# routes/printing.py
# Print barcode/receipt, designer pages, and print template API.

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload
from datetime import datetime
from database import get_session
from models import (
    Patient, PatientVisit, Order, LabInfo, PrintTemplate, 
    Result, ResultDetail, Parameter, TestRange, TestDefinition, TestParameter
)
from fastapi.encoders import jsonable_encoder
from fastapi import File, UploadFile
import os
import uuid
from routes.helpers import templates, get_current_user, generate_barcode_base64, calculate_age, log_audit_action, log_activity_action, require_permission
from fastapi.responses import RedirectResponse

router = APIRouter()

# ===========================
# PRINT DESIGNER ROUTES
# ===========================
@router.get("/print-barcode-designer", response_class=HTMLResponse)
def print_barcode_designer(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "barcode_designer"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=303)
    return templates.TemplateResponse("print_barcode_designer.html", {"request": request})

@router.get("/print-receipt-designer", response_class=HTMLResponse)
def print_receipt_designer(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "receipt_designer"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=303)
    return templates.TemplateResponse("print_receipt_designer.html", {"request": request})

@router.get("/print-result-designer", response_class=HTMLResponse)
def print_result_designer(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "result_designer"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=303)
    return templates.TemplateResponse("print_result_designer.html", {"request": request})

@router.get("/print-results", response_class=HTMLResponse)
def print_results_page(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "print_results"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=303)
    today_str = datetime.today().strftime("%Y-%m-%d")
    start_date = request.query_params.get("start_date", today_str)
    end_date = request.query_params.get("end_date", today_str)
    name = request.query_params.get("name", "")
    patient_id_q = request.query_params.get("patient_id", "")
    test_q = request.query_params.get("test", "")
    status_q = request.query_params.get("status", "double_authorized") # Default to double_authorized for printing
    
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
        
    return templates.TemplateResponse("print_results.html", {
        "request": request,
        "patient_data": patient_data,
        "filters": {
            "start_date": start_date,
            "end_date": end_date,
            "name": name,
            "patient_id": patient_id_q,
            "test": test_q,
            "status": status_q
        }
    })

# ===========================
# MEDICAL REPORT PRINTING (Now Audited)
# ===========================
@router.get("/print-report/{patient_id}", response_class=HTMLResponse)
def print_report(patient_id: str, request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "print_results", "print"):
        return RedirectResponse(url="/print-results?error=Permission Denied", status_code=303)
    patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()
    if not patient:
         return HTMLResponse(content="Patient not found", status_code=404)
         
    current_user = get_current_user(request, session)
    if current_user:
        log_activity_action(session, "PRINT_REPORT", f"Printed medical report for patient {patient.full_name}", current_user, "patient", patient.id)
        session.commit()
         
    visit = session.exec(
        select(PatientVisit)
        .where(PatientVisit.patient_id == patient.id)
        .order_by(PatientVisit.id.desc())
    ).first()
    
    lab_info = session.exec(select(LabInfo).limit(1)).first()
    template = session.exec(select(PrintTemplate).where(PrintTemplate.template_name == "result_report")).first()
    barcode_data = generate_barcode_base64(patient_id)
    
    # Use jsonable_encoder but specifically ensure all dates are strings
    encoded_patient = jsonable_encoder(patient)
    encoded_visit = jsonable_encoder(visit) if visit else None
    encoded_lab_info = jsonable_encoder(lab_info) if lab_info else None
    
    encoded_template = jsonable_encoder(template) if template else {}
    
    # ---------------------------------------------------------
    # ✅ NEW: INJECT AUDIT LOG HERE (Tracking the print action)
    # ---------------------------------------------------------
    current_user = get_current_user(request, session)
    if visit:
        log_audit_action(
            session=session,
            table_name="patientvisit",
            record_id=visit.id,
            action="PRINT",
            current_user=current_user,
            new_values={"action": "Generated Medical Report PDF"}
        )
        session.commit() # We must commit here because GET routes normally don't save
    # ---------------------------------------------------------

    return templates.TemplateResponse("print_report.html", {
        "request": request,
        "patient": encoded_patient,
        "visit": encoded_visit,
        "lab_info": encoded_lab_info,
        "template": encoded_template,
        "barcode_data": barcode_data
    })

@router.get("/view-results/{patient_id}", response_class=HTMLResponse)
def view_results(patient_id: str, request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "print_results"):
        return RedirectResponse(url="/print-results?error=Permission Denied", status_code=303)
    patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()
    if not patient:
         return HTMLResponse(content="Patient not found", status_code=404)
         
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
            
    return templates.TemplateResponse("view_results.html", {
        "request": request,
        "patient": patient,
        "visit": visit,
        "visit_user_name": visit_user_name
    })



# ===========================
# PRINT TEMPLATE API ROUTES
# ===========================
@router.post("/api/print-template/save")
async def save_print_template(request: Request, session: Session = Depends(get_session)):
    try:
        data = await request.json()
        template_name = data.get("template_name", "")
        
        # Check permissions based on template_name
        req_page = "result_designer"
        if template_name == "barcode_label":
            req_page = "barcode_designer"
        elif template_name == "receipt":
            req_page = "receipt_designer"
            
        if not require_permission(request, session, req_page, "save"):
            return JSONResponse({"success": False, "message": "Permission Denied"}, status_code=403)
            
        current_user = get_current_user(request, session)
        existing = session.exec(select(PrintTemplate).where(PrintTemplate.template_name == data['template_name'])).first()
        if existing:
            existing.paper_width = data['paper_width']
            existing.paper_height = data['paper_height']
            existing.margin = data['margin']
            existing.elements = data['elements']
            existing.edited_by = current_user.id if current_user else None
            existing.edited_at = datetime.now()
            session.add(existing)
            session.commit()
            session.refresh(existing)
            return {"success": True, "template_id": existing.id}
        else:
            new_template = PrintTemplate(
                template_name=data['template_name'], template_type=data['template_type'],
                paper_width=data['paper_width'], paper_height=data['paper_height'],
                margin=data['margin'], elements=data['elements'],
                created_by=current_user.id if current_user else None
            )
            session.add(new_template)
            session.commit()
            session.refresh(new_template)
            return {"success": True, "template_id": new_template.id}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/api/print-template/load/{template_name}")
def load_print_template(template_name: str, session: Session = Depends(get_session)):
    try:
        template = session.exec(select(PrintTemplate).where(PrintTemplate.template_name == template_name)).first()
        if template:
            return {
                "success": True,
                "template": {
                    "id": template.id, "template_name": template.template_name,
                    "paper_width": template.paper_width, "paper_height": template.paper_height,
                    "margin": template.margin, "elements": template.elements
                }
            }
        return {"success": False, "error": "Template not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/api/double-authorized-tests/{patient_id}")
def get_double_authorized_tests(patient_id: str, request: Request, session: Session = Depends(get_session)):
    try:
        order_ids_str = request.query_params.get("order_ids")
        order_ids = []
        if order_ids_str:
            order_ids = [int(x) for x in order_ids_str.split(",") if x.strip()]

        patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()

        if not patient:
            return {"success": False, "error": "Patient not found"}
            
        visit = session.exec(
            select(PatientVisit)
            .where(PatientVisit.patient_id == patient.id)
            .order_by(PatientVisit.id.desc())
        ).first()
        
        if not visit:
            return {"success": False, "error": "No visit found"}
            
        # Get double authorized orders
        query = select(Order).options(
                selectinload(Order.test).selectinload(TestDefinition.test_parameters).selectinload(TestParameter.parameter),
                selectinload(Order.result).selectinload(Result.details).selectinload(ResultDetail.parameter)
            ).where(Order.visit_id == visit.id, Order.status == "double_authorized")
        
        if order_ids:
            query = query.where(Order.id.in_(order_ids))
            
        orders = session.exec(query).all()

        
        grid_rows = []
        for order in orders:
            test = order.test
            res = order.result
            
            # Fetch ranges for this test/patient
            ranges = session.exec(
                select(TestRange).where(TestRange.test_id == test.id, TestRange.is_active == True)
            ).all()
            
            def find_range(param_id=None):
                best = None
                for r in ranges:
                    if r.parameter_id == param_id:
                        gender_ok = r.gender_type == "both" or r.gender_type == patient.gender
                        age_ok = r.age_from <= (patient.age or 0) <= r.age_to
                        if gender_ok and age_ok:
                            best = r
                            break
                if not best and ranges:
                    for r in ranges:
                        if r.parameter_id == param_id:
                            return r
                return best

            if test.test_parameters:
                # Parent row
                grid_rows.append({
                    "type": "parent",
                    "test_name": test.test_name,
                    "order_id": order.id,
                    "status": order.status
                })

                # Child rows
                for tp in test.test_parameters:
                    param = tp.parameter
                    detail = next((d for d in res.details if d.parameter_id == param.id), None)
                    rng = find_range(param.id)
                    grid_rows.append({
                        "type": "child",
                        "parameter_name": param.parameter_name,
                        "result_value": detail.result_value if detail else "",
                        "range": rng.text_range if rng and rng.range_type == "text" else (f"{rng.normal_from} - {rng.normal_to}" if rng and rng.normal_from is not None else ""),
                        "unit": rng.unit if rng else "",
                        "flag": detail.flag if detail else "",
                        "remark": detail.remark if detail else ""
                    })
            else:
                # Standalone
                rng = find_range(None)
                grid_rows.append({
                    "type": "standalone",
                    "test_name": test.test_name,
                    "order_id": order.id,
                    "result_value": res.result_value if res else "",

                    "range": rng.text_range if rng and rng.range_type == "text" else (f"{rng.normal_from} - {rng.normal_to}" if rng and rng.normal_from is not None else ""),
                    "unit": rng.unit if rng else "",
                    "flag": res.flag if res else "",
                    "remark": res.note if res else ""
                })
                
        return {
            "success": True,
            "patient": {
                "full_name": patient.full_name,
                "patient_id": patient.patient_id,
                "age": patient.age,
                "age_unit": patient.age_unit,
                "gender": patient.gender,
                "doctor": patient.doctor,
                "agent_name": patient.agent_name
            },
            "visit": {
                "visit_id": visit.visit_id,
                "visit_date": visit.visit_date.strftime("%Y-%m-%d %H:%M")
            },
            "results": grid_rows
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

@router.post("/api/upload-watermark")
async def upload_watermark(file: UploadFile = File(...)):
    try:
        os.makedirs("uploads", exist_ok=True)
        ext = os.path.splitext(file.filename)[1]
        filename = f"watermark_{uuid.uuid4().hex}{ext}"
        filepath = os.path.join("uploads", filename)
        with open(filepath, "wb") as f:
            f.write(await file.read())
        return {"success": True, "filename": filename}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ===========================
# PRINT ROUTES (WITH LOCAL BARCODE)
# ===========================
@router.get("/print-barcode/{patient_id}", response_class=HTMLResponse)
def print_barcode(patient_id: str, request: Request, session: Session = Depends(get_session)):
    patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()
    if not patient:
        return HTMLResponse(content="Patient not found", status_code=404)
        
    current_user = get_current_user(request, session)
    if current_user:
        log_activity_action(session, "PRINT_BARCODE", f"Printed barcode for patient {patient.full_name}", current_user, "patient", patient.id)
        session.commit()
        
    lab_info = session.exec(select(LabInfo).limit(1)).first()
    barcode_data = generate_barcode_base64(patient_id)
    return templates.TemplateResponse("print_barcode.html", {
        "request": request, "patient": patient, "lab_info": lab_info, "barcode_data": barcode_data
    })

@router.get("/print-receipt/{patient_id}", response_class=HTMLResponse)
def print_receipt(patient_id: str, request: Request, session: Session = Depends(get_session)):
    patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()
    if not patient:
        return HTMLResponse(content="Patient not found", status_code=404)
        
    current_user = get_current_user(request, session)
    if current_user:
        log_activity_action(session, "PRINT_RECEIPT", f"Printed receipt for patient {patient.full_name}", current_user, "patient", patient.id)
        session.commit()
        
    visits = session.exec(select(PatientVisit).where(PatientVisit.patient_id == patient.id)).all()
    orders = session.exec(select(Order).where(Order.patient_id == patient.id)).all()
    lab_info = session.exec(select(LabInfo).limit(1)).first()
    barcode_data = generate_barcode_base64(patient_id)
    return templates.TemplateResponse("print_receipt.html", {
        "request": request, "patient": patient, "visits": visits, "orders": orders,
        "lab_info": lab_info, "barcode_data": barcode_data
    })