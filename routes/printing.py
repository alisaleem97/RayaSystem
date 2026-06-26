# routes/printing.py
# Print barcode/receipt, designer pages, and print template API.

from fastapi import APIRouter, Depends, Request, status, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload
from datetime import datetime
from database import get_session
from models import (
    Patient, PatientVisit, Order, LabInfo, PrintTemplate, 
    Result, ResultDetail, Parameter, TestRange, TestDefinition, TestParameter,
    TestResultType
)
from fastapi.encoders import jsonable_encoder
from fastapi import File, UploadFile
import os
import uuid
import logging
from routes.helpers import templates, get_current_user, generate_barcode_base64, calculate_age, log_audit_action, log_activity_action, require_permission, age_to_days, build_patient_visit_data
from fastapi.responses import RedirectResponse
from routes.generate_pdf import generate_native_barcode_pdf
from io import BytesIO

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
    
    # Default status to double_authorized for printing
    default_status = request.query_params.get("status", "double_authorized")
    patient_data, filters, page, total_pages, total_count = build_patient_visit_data(session, request, status_filter=default_status)
    
    return templates.TemplateResponse("print_results.html", {
        "request": request,
        "patient_data": patient_data,
        "filters": filters,
        "page": page,
        "total_pages": total_pages,
        "total_count": total_count,
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
         
    # Support visit_id query param to select a specific visit
    visit_id_param = request.query_params.get("visit_id")
    if visit_id_param:
        visit = session.exec(
            select(PatientVisit)
            .where(PatientVisit.visit_id == visit_id_param, PatientVisit.patient_id == patient.id)
        ).first()
    else:
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
         
    # Support visit_id query param to select a specific visit
    visit_id_param = request.query_params.get("visit_id")
    if visit_id_param:
        visit = session.exec(
            select(PatientVisit)
            .where(PatientVisit.visit_id == visit_id_param, PatientVisit.patient_id == patient.id)
        ).first()
    else:
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
            
    # Fetch all visits for the "Previous Results" bar
    all_visits = session.exec(
        select(PatientVisit)
        .where(PatientVisit.patient_id == patient.id)
        .order_by(PatientVisit.visit_date.asc())
    ).all()
            
    return templates.TemplateResponse("view_results.html", {
        "request": request,
        "patient": patient,
        "visit": visit,
        "visit_user_name": visit_user_name,
        "all_visits": all_visits
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
        if template_name in ("barcode", "barcode_label"):
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
def load_print_template(template_name: str, request: Request, session: Session = Depends(get_session)):
    current_user = get_current_user(request, session)
    if not current_user:
        return {"success": False, "error": "Authentication required"}
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
            
        # Support visit_id query param to select a specific visit
        visit_id_param = request.query_params.get("visit_id")
        if visit_id_param:
            visit = session.exec(
                select(PatientVisit)
                .where(PatientVisit.visit_id == visit_id_param, PatientVisit.patient_id == patient.id)
            ).first()
        else:
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

        test_ids = [order.test_id for order in orders if order.test_id]
        all_result_types = session.exec(
            select(TestResultType).where(TestResultType.test_id.in_(test_ids), TestResultType.is_active == True)
        ).all()
        result_type_map = {}
        for rt in all_result_types:
            result_type_map[(rt.test_id, rt.parameter_id)] = rt.result_type

        def get_result_type(test_id, param_id=None):
            return result_type_map.get((test_id, param_id), "number")
            
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
                patient_days = age_to_days(patient.age, patient.age_unit)
                for r in ranges:
                    if r.parameter_id == param_id:
                        gender_ok = r.gender_type == "both" or r.gender_type == patient.gender
                        range_from_days = age_to_days(r.age_from, r.age_from_unit or "year")
                        range_to_days = age_to_days(r.age_to, r.age_to_unit or "year")
                        age_ok = range_from_days <= patient_days <= range_to_days
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
                    "status": order.status,
                    "print_separately": test.print_separately,
                    "note": res.note if res else ""
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
                        "result_type": get_result_type(test.id, param.id),
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
                    "result_type": get_result_type(test.id, None),
                    "range": rng.text_range if rng and rng.range_type == "text" else (f"{rng.normal_from} - {rng.normal_to}" if rng and rng.normal_from is not None else ""),
                    "unit": rng.unit if rng else "",
                    "flag": res.flag if res else "",
                    "remark": res.note if res else "",
                    "note": res.note if res else "",
                    "print_separately": test.print_separately
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

@router.get("/api/all-visit-tests/{visit_id}")
def get_all_visit_tests(visit_id: str, request: Request, session: Session = Depends(get_session)):
    """Returns ALL orders for a visit with their current status for the call centre view."""
    try:
        visit = session.exec(
            select(PatientVisit)
            .options(selectinload(PatientVisit.patient))
            .where(PatientVisit.visit_id == visit_id)
        ).first()

        if not visit:
            return {"success": False, "error": "Visit not found"}

        patient = visit.patient

        orders = session.exec(
            select(Order).options(
                selectinload(Order.test).selectinload(TestDefinition.test_parameters).selectinload(TestParameter.parameter),
                selectinload(Order.result).selectinload(Result.details).selectinload(ResultDetail.parameter)
            ).where(Order.visit_id == visit.id, Order.status != "no_sample")
        ).all()

        test_ids = [order.test_id for order in orders if order.test_id]
        all_result_types = session.exec(
            select(TestResultType).where(TestResultType.test_id.in_(test_ids), TestResultType.is_active == True)
        ).all()
        result_type_map = {}
        for rt in all_result_types:
            result_type_map[(rt.test_id, rt.parameter_id)] = rt.result_type

        def get_result_type(test_id, param_id=None):
            return result_type_map.get((test_id, param_id), "number")

        grid_rows = []
        for order in orders:
            test = order.test
            res = order.result
            if not test:
                continue

            # Determine display status
            if order.status == "double_authorized":
                display_status = "Double AUTH"
            elif order.status == "authorized":
                display_status = "AUTH"
            elif order.status == "resulted":
                display_status = "Resulted"
            else:
                display_status = "Pending"

            # Fetch ranges for this test/patient
            ranges = session.exec(
                select(TestRange).where(TestRange.test_id == test.id, TestRange.is_active == True)
            ).all()

            def find_range(param_id=None):
                best = None
                patient_days = age_to_days(patient.age, patient.age_unit)
                for r in ranges:
                    if r.parameter_id == param_id:
                        gender_ok = r.gender_type == "both" or r.gender_type == patient.gender
                        range_from_days = age_to_days(r.age_from, r.age_from_unit or "year")
                        range_to_days = age_to_days(r.age_to, r.age_to_unit or "year")
                        age_ok = range_from_days <= patient_days <= range_to_days
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
                    "status": order.status,
                    "display_status": display_status,
                    "print_separately": test.print_separately,
                    "note": res.note if res else ""
                })
                # Child rows
                for tp in test.test_parameters:
                    param = tp.parameter
                    detail = next((d for d in res.details if d.parameter_id == param.id), None) if res else None
                    rng = find_range(param.id)
                    grid_rows.append({
                        "type": "child",
                        "parameter_name": param.parameter_name,
                        "result_value": detail.result_value if detail else "",
                        "result_type": get_result_type(test.id, param.id),
                        "range": rng.text_range if rng and rng.range_type == "text" else (f"{rng.normal_from} - {rng.normal_to}" if rng and rng.normal_from is not None else ""),
                        "range_type": rng.range_type if rng else None,
                        "unit": rng.unit if rng else "",
                        "flag": detail.flag if detail else "",
                        "remark": detail.remark if detail else "",
                        "display_status": display_status
                    })
            else:
                # Standalone
                rng = find_range(None)
                grid_rows.append({
                    "type": "standalone",
                    "test_name": test.test_name,
                    "order_id": order.id,
                    "status": order.status,
                    "display_status": display_status,
                    "result_value": res.result_value if res else "",
                    "result_type": get_result_type(test.id, None),
                    "range": rng.text_range if rng and rng.range_type == "text" else (f"{rng.normal_from} - {rng.normal_to}" if rng and rng.normal_from is not None else ""),
                    "range_type": rng.range_type if rng else None,
                    "unit": rng.unit if rng else "",
                    "flag": res.flag if res else "",
                    "remark": res.note if res else "",
                    "note": res.note if res else "",
                    "print_separately": test.print_separately
                })

        return {
            "success": True,
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
    
    # Load saved barcode template design
    template = session.exec(select(PrintTemplate).where(PrintTemplate.template_name == "barcode")).first()
    template_data = None
    if template:
        template_data = {
            "paper_width": template.paper_width,
            "paper_height": template.paper_height,
            "margin": template.margin,
            "elements": template.elements
        }
    
    # Load visit data
    visit_id_param = request.query_params.get("visit_id") if request else None
    if visit_id_param:
        visit = session.exec(select(PatientVisit).where(PatientVisit.visit_id == visit_id_param, PatientVisit.patient_id == patient.id)).first()
    else:
        visit = session.exec(select(PatientVisit).where(PatientVisit.patient_id == patient.id).order_by(PatientVisit.id.desc())).first()
        
    visit_id = visit.visit_id if visit else ""
    visit_date = visit.visit_date.strftime('%Y-%m-%d %H:%M') if visit and visit.visit_date else ""

    # Get orders with test + sample_type eagerly loaded
    orders = session.exec(
        select(Order).options(
            selectinload(Order.test).selectinload(TestDefinition.sample_type)
        ).where(Order.visit_id == visit.id)
    ).all() if visit else []
    
    # Build tests_by_sample_type using test_short_name
    tests_by_sample_type = {}
    for order in orders:
        if order.test:
            sample_type_name = order.test.sample_type.sample_name if order.test.sample_type else "Unknown"
            if sample_type_name not in tests_by_sample_type:
                tests_by_sample_type[sample_type_name] = []
            test_display = order.test.test_short_name if order.test.test_short_name else order.test.test_name
            tests_by_sample_type[sample_type_name].append(test_display)
    
    # If no tests, still have at least one barcode
    if not tests_by_sample_type:
        tests_by_sample_type = {"Unknown": []}
    
    lab_info = session.exec(select(LabInfo).limit(1)).first()
        
    # Generate print_token for API image access
    import hashlib
    from app.config import SECRET_KEY
    print_token = hashlib.sha256(SECRET_KEY.encode()).hexdigest()[:16]
    
    return templates.TemplateResponse("print_barcode.html", {
        "request": request,
        "patient": patient,
        "lab_info": lab_info,
        "template_data": template_data,
        "tests_by_sample_type": tests_by_sample_type,
        "visit_id": visit_id,
        "visit_date": visit_date,
        "print_token": print_token
    })

@router.get("/api/print-barcode-pdf/{patient_id}")
def api_print_barcode_pdf(patient_id: str, request: Request, session: Session = Depends(get_session)):
    """
    Returns a mathematically perfect, native PDF generation of the barcode label using ReportLab.
     Bypasses all client-side browser/HTML rendering for optimal thermal printer compatibility.
    """
    patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
        
    barcode_template = session.exec(select(PrintTemplate).where(PrintTemplate.template_name == "barcode")).first()
    if not barcode_template:
        raise HTTPException(status_code=404, detail="No barcode template configured in the database")

    # Support visit_id query param to select a specific visit
    visit_id_param = request.query_params.get("visit_id") if request else None
    if visit_id_param:
        visit = session.exec(select(PatientVisit).where(PatientVisit.visit_id == visit_id_param, PatientVisit.patient_id == patient.id)).first()
    else:
        visit = session.exec(select(PatientVisit).where(PatientVisit.patient_id == patient.id).order_by(PatientVisit.id.desc())).first()
    v_id = visit.visit_id if visit else ''
    v_date = visit.visit_date.strftime('%Y-%m-%d %H:%M') if visit and visit.visit_date else ''
    
    # Get orders with test + sample_type eagerly loaded
    orders = session.exec(
        select(Order).options(
            selectinload(Order.test).selectinload(TestDefinition.sample_type)
        ).where(Order.visit_id == visit.id)
    ).all() if visit else []
    
    tests_by_sample_type = {}
    for order in orders:
        if order.test:
            sample_type_name = order.test.sample_type.sample_name if order.test.sample_type else "Unknown"
            if sample_type_name not in tests_by_sample_type:
                tests_by_sample_type[sample_type_name] = []
            test_display = order.test.test_short_name if order.test.test_short_name else order.test.test_name
            tests_by_sample_type[sample_type_name].append(test_display)
        
    try:
        pdf_buffer = generate_native_barcode_pdf(patient, tests_by_sample_type, barcode_template, visit_id=v_id, visit_date=v_date)
        response = StreamingResponse(pdf_buffer, media_type="application/pdf")
        response.headers["Content-Disposition"] = f"attachment; filename=barcode_{patient_id}.pdf"
        return response
    except Exception as e:
        import traceback
        logging.error(f"Failed to generate native barcode PDF: {e}\n{traceback.format_exc()}")
        print(f"❌ Barcode PDF Error for {patient_id}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/print-barcode-image/{patient_id}")
def api_print_barcode_image(patient_id: str, page: int = 0, request: Request = None, session: Session = Depends(get_session)):
    """
    Returns a high-DPI PNG image of the barcode label (rendered server-side with Pillow).
    One page per sample type. Use ?page=N to get a specific page.
    Response header X-Page-Count contains total number of pages.
    """
    from app.services.barcode_image_service import generate_barcode_label_image

    patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    barcode_template = session.exec(select(PrintTemplate).where(PrintTemplate.template_name == "barcode")).first()
    if not barcode_template:
        raise HTTPException(status_code=404, detail="No barcode template configured")

    # Support visit_id query param to select a specific visit
    visit_id_param = request.query_params.get("visit_id") if request else None
    if visit_id_param:
        visit = session.exec(select(PatientVisit).where(PatientVisit.visit_id == visit_id_param, PatientVisit.patient_id == patient.id)).first()
    else:
        visit = session.exec(select(PatientVisit).where(PatientVisit.patient_id == patient.id).order_by(PatientVisit.id.desc())).first()
    v_id = visit.visit_id if visit else ''
    v_date = visit.visit_date.strftime('%Y-%m-%d %H:%M') if visit and visit.visit_date else ''
    
    orders = session.exec(
        select(Order).options(
            selectinload(Order.test).selectinload(TestDefinition.sample_type)
        ).where(Order.visit_id == visit.id)
    ).all() if visit else []

    tests_by_sample_type = {}
    for order in orders:
        if order.test:
            sample_type_name = order.test.sample_type.sample_name if order.test.sample_type else "Unknown"
            if sample_type_name not in tests_by_sample_type:
                tests_by_sample_type[sample_type_name] = []
            test_display = order.test.test_short_name if order.test.test_short_name else order.test.test_name
            tests_by_sample_type[sample_type_name].append(test_display)

    try:
        pages = generate_barcode_label_image(patient, tests_by_sample_type, barcode_template, visit_id=v_id, visit_date=v_date)
        if not pages:
            raise HTTPException(status_code=500, detail="No barcode pages generated")
        total = len(pages)
        idx = max(0, min(page, total - 1))
        return StreamingResponse(pages[idx], media_type="image/png",
            headers={
                "Content-Disposition": f"inline; filename=barcode_{patient_id}_p{idx}.png",
                "X-Page-Count": str(total),
            })
    except Exception as e:
        import traceback
        logging.error(f"Barcode image generation failed: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/print-receipt/{patient_id}", response_class=HTMLResponse)
def print_receipt(patient_id: str, request: Request, session: Session = Depends(get_session)):
    patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()
    if not patient:
        return HTMLResponse(content="Patient not found", status_code=404)
        
    current_user = get_current_user(request, session)
    if current_user:
        log_activity_action(session, "PRINT_RECEIPT", f"Printed receipt for patient {patient.full_name}", current_user, "patient", patient.id)
        session.commit()
    
    # Load saved receipt template design
    template = session.exec(select(PrintTemplate).where(PrintTemplate.template_name == "receipt")).first()
    template_data = None
    if template:
        template_data = {
            "paper_width": template.paper_width,
            "paper_height": template.paper_height,
            "margin": template.margin,
            "elements": template.elements
        }
    
    # Load lab info
    lab_info = session.exec(select(LabInfo).limit(1)).first()
    
    # Load visit data + accounting
    visit_id_param = request.query_params.get("visit_id")
    if visit_id_param:
        visit = session.exec(
            select(PatientVisit)
            .where(PatientVisit.visit_id == visit_id_param, PatientVisit.patient_id == patient.id)
        ).first()
    else:
        visit = session.exec(
            select(PatientVisit)
            .where(PatientVisit.patient_id == patient.id)
            .order_by(PatientVisit.id.desc())
        ).first()
        
    visit_id = visit.visit_id if visit else ""
    visit_date = visit.visit_date.strftime('%d/%m/%Y %H:%M') if visit and visit.visit_date else ""
    
    received_amount = visit.received_amount if visit else 0.0
    discount_amount = visit.discount_amount if visit else 0.0
    tax_amount = visit.tax_amount if visit and visit.tax_amount else 0.0
    remaining_amount = visit.remaining_amount if visit else 0.0
    
    # Load orders with test relationship
    orders = session.exec(
        select(Order).options(
            selectinload(Order.test)
        ).where(Order.visit_id == visit.id)
    ).all() if visit else []
    
    # Build orders data for template
    orders_data = []
    for order in orders:
        test = order.test
        orders_data.append({
            "test_name": test.test_name if test else 'Unknown',
            "test_short_name": test.test_short_name if test and test.test_short_name else (test.test_name if test else 'Unknown'),
            "package_name": order.package_name or None,
            "unit_price": order.unit_price or (test.price if test else 0),
            "final_price": order.final_price or (order.unit_price or 0),
            "test_id": order.test_id
        })
        
    # Calculate accounting totals (same logic as /api/patient/)
    total_amount = sum([float(o["final_price"]) if o["final_price"] else 0 for o in orders_data])
    total_after_tax = total_amount - discount_amount + tax_amount
    
    # --- Compute page_size as a clean CSS string (MUST be done in Python, not Jinja inside CSS!) ---
    def normalize_dim(val, default_unit='mm'):
        """Ensure a CSS dimension string always has a unit (e.g., '210' -> '210mm')."""
        if not val or str(val).strip() in ('auto', ''):
            return None
        val = str(val).strip()
        import re
        if re.match(r'^[\d\.]+$', val):  # pure number, no unit
            return val + default_unit
        return val

    if template_data:
        pw = normalize_dim(template_data.get("paper_width")) or "80mm"
        ph = normalize_dim(template_data.get("paper_height"))
        if ph:
            page_size = f"{pw} {ph}"
        else:
            page_size = f"{pw} 210mm"
    else:
        page_size = "80mm 210mm"

    return templates.TemplateResponse("print_receipt_page.html", {
        "request": request,
        "patient": patient,
        "lab_info": lab_info,
        "template_data": template_data,
        "orders": orders_data,
        "visit_id": visit_id,
        "visit_date": visit_date,
        "total_amount": total_amount,
        "discount_amount": discount_amount,
        "tax_amount": tax_amount,
        "total_after_tax": total_after_tax,
        "paid_amount": received_amount,
        "remain_amount": remaining_amount,
        "page_size": page_size,
    })