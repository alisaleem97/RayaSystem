# routes/patients.py
# Patient registration, management, editing, soft-delete/restore, and deleted patients view.

from fastapi import APIRouter, Depends, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlmodel import Session, select
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from datetime import datetime
from typing import Optional
import json
from pydantic import BaseModel
from database import get_session
from models import (
    Patient, PatientVisit, Order, TestDefinition, Package, PackageTest,
    Province, Region, Partner, SampleType, LabInfo, Payment, Attachment, User, DeletedRecord, Result, ResultDetail
)
from routes.helpers import templates, get_current_user, create_audit_log, model_to_dict, generate_barcode_base64, require_permission, archive_deleted_record, log_activity_action

router = APIRouter()

# ===========================
# PATIENT REGISTRATION PAGE
# ===========================
@router.get("/patient-registration", response_class=HTMLResponse)
def patient_registration_page(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "patient_registration"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    provinces = session.exec(select(Province).where(Province.is_active == True)).all()
    partners = session.exec(select(Partner).where(Partner.is_active == True)).all()
    tests = session.exec(select(TestDefinition).where(TestDefinition.is_available == True)).all()
    packages = session.exec(select(Package).where(Package.is_active == True)).all()
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    last_patient_id = request.query_params.get("patient_id")
    import hashlib
    from routes.helpers import SECRET_KEY
    print_token = hashlib.sha256(SECRET_KEY.encode()).hexdigest()[:16]
    
    from models import PrintTemplate
    barcode_template = session.exec(select(PrintTemplate).where(PrintTemplate.template_name == "barcode")).first()
    receipt_template = session.exec(select(PrintTemplate).where(PrintTemplate.template_name == "receipt")).first()
    
    lab_info = session.exec(select(LabInfo)).first()
    default_province_id = lab_info.province_id if lab_info else None
    
    return templates.TemplateResponse("patient_registration.html", {
        "request": request, "provinces": provinces, "partners": partners,
        "tests": tests, "packages": packages,
        "message_success": success, "message_error": error,
        "last_patient_id": last_patient_id,
        "print_token": print_token,
        "default_province_id": default_province_id,
        "barcode_width": barcode_template.paper_width if barcode_template else '4in',
        "barcode_height": barcode_template.paper_height if barcode_template else '2in',
        "receipt_width": receipt_template.paper_width if receipt_template else '80mm',
        "receipt_height": receipt_template.paper_height if receipt_template else 'auto'
    })

class CheckDuplicateRequest(BaseModel):
    full_name: str
    selected_items: str

@router.post("/api/check-duplicate-registration")
def check_duplicate_registration(request_data: CheckDuplicateRequest, session: Session = Depends(get_session)):
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 1. Parse requested tests
    try:
        items = json.loads(request_data.selected_items)
    except Exception:
        items = []
        
    requested_test_ids = set()
    for item in items:
        if item.get('type') == 'test':
            requested_test_ids.add(int(item['id']))
        elif item.get('type') == 'package':
            pts = session.exec(select(PackageTest).where(PackageTest.package_id == int(item['id']))).all()
            for pt in pts:
                requested_test_ids.add(pt.test_id)
                
    if not requested_test_ids:
        return JSONResponse({"duplicate": False})
        
    # 2. Find visits today for patients with same name
    visits_today = session.exec(
        select(PatientVisit)
        .join(Patient)
        .where(
            Patient.full_name.ilike(request_data.full_name),
            PatientVisit.created_at >= today_start
        )
    ).all()
    
    for visit in visits_today:
        orders = session.exec(select(Order).where(Order.visit_id == visit.id)).all()
        visit_test_ids = {o.test_id for o in orders}
        if requested_test_ids.issubset(visit_test_ids) and len(requested_test_ids) > 0:
            # We have a duplicate
            return JSONResponse({
                "duplicate": True,
                "message": "This patient has already been registered today with all of the selected tests."
            })
            
    return JSONResponse({"duplicate": False})

# ===========================
# PATIENT REGISTRATION CREATE (WITH PRICE SNAPSHOT)
# ===========================
@router.post("/patient-registration/create")
async def create_patient_registration(
    request: Request,
    patient_id: str = Form(...),
    full_name: str = Form(...),
    gender: str = Form(...),
    date_of_birth: Optional[str] = Form(None),
    age: Optional[int] = Form(None),
    age_unit: Optional[str] = Form(None),
    phone_key: str = Form(...),
    phone_number: str = Form(...),
    weight: float = Form(...),
    height: float = Form(...),
    province_id: int = Form(...),
    region_id: int = Form(...),
    fasting_time: Optional[int] = Form(None),
    note: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    diagnosis: Optional[str] = Form(None),
    symptoms: Optional[str] = Form(None),
    therapy: Optional[str] = Form(None),
    partner_id: Optional[int] = Form(None),
    doctor: Optional[str] = Form(None),
    skin_colour: Optional[str] = Form(None),
    agent_name: Optional[str] = Form(None),
    is_outlab: str = Form("false"),
    selected_items: str = Form(...),
    discount_percentage: Optional[float] = Form(None),
    discount_amount: Optional[float] = Form(None),
    discount_note: Optional[str] = Form(None),
    received_amount: Optional[float] = Form(None),
    apply_tax_toggle: Optional[str] = Form(None),
    force_duplicate: Optional[str] = Form("false"),
    existing_patient_db_id: Optional[int] = Form(None),
    session: Session = Depends(get_session)
):
    if not require_permission(request, session, "patient_registration", "save_registration"):
        return RedirectResponse(url="/patient-registration?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        items = json.loads(selected_items)
        
        total_price = sum(float(item.get('price', 0)) for item in items)
        
        # --- Check Discount Permissions ---
        has_discount_perm = require_permission(request, session, "patient_registration", "discount")
                        
        if not has_discount_perm:
            discount_percentage = None
            discount_amount = None
        # ----------------------------------
        
        final_total = total_price
        discount_amt = float(discount_amount) if discount_amount else 0.0
        if discount_percentage:
            final_total = total_price * (1 - discount_percentage / 100)
            discount_amt = total_price - final_total
        elif discount_amount:
            final_total = total_price - float(discount_amount)
        
        # --- NEW TAX LOGIC ---
        is_tax_applied = apply_tax_toggle == "on"
        tax_amount = 0.0
        if is_tax_applied:
            from models import LabInfo
            lab_info = session.exec(select(LabInfo)).first()
            tax_percentage = lab_info.tax_percentage if lab_info else 0.0
            tax_amount = (tax_percentage / 100) * final_total
            final_total += tax_amount
        # ---------------------
        
        received = float(received_amount) if received_amount else 0.0
        remaining = max(0, final_total - received)
        
        # --- Returning patient vs new patient ---
        is_returning = False
        if existing_patient_db_id:
            existing = session.get(Patient, existing_patient_db_id)
            if existing and existing.is_active:
                new_patient = existing
                patient_id = existing.patient_id  # Reuse the same Patient ID
                new_patient.fasting_time = fasting_time  # Update for the new visit
                is_returning = True
            else:
                existing_patient_db_id = None  # Fallback to new patient

        if not existing_patient_db_id:
            new_patient = Patient(
                patient_id=patient_id,
                full_name=full_name,
                gender=gender,
                date_of_birth=datetime.strptime(date_of_birth, "%Y-%m-%d") if date_of_birth else None,
                age=age,
                age_unit=age_unit,
                phone_key=phone_key,
                phone_number=phone_number,
                weight=weight,
                height=height,
                province_id=province_id,
                region_id=region_id,
                fasting_time=fasting_time,
                note=note,
                email=email,
                diagnosis=diagnosis,
                symptoms=symptoms,
                therapy=therapy,
                partner_id=partner_id if partner_id else None,
                doctor=doctor,
                skin_colour=skin_colour,
                agent_name=agent_name,
                is_outlab=is_outlab.lower() == "true",
                created_by=current_user.id if current_user else None
            )
            session.add(new_patient)
            session.flush()  # Get new_patient.id without committing
        
        # Generate visit_id using timestamp to avoid race conditions with concurrent registrations
        import time
        ts_suffix = str(int(time.time() * 1000))[-6:]  # Last 6 digits of ms timestamp
        visit_id = f"{patient_id}{ts_suffix}"
        
        disc_pct = float(discount_percentage) if discount_percentage else 0.0
        new_visit = PatientVisit(
            visit_id=visit_id,
            patient_id=new_patient.id,
            created_by=current_user.id if current_user else None,
            received_amount=received,
            discount_amount=round(discount_amt, 2),
            discount_percentage=disc_pct,
            discount_note=discount_note,
            tax_applied=is_tax_applied,
            tax_amount=round(tax_amount, 2),
            remaining_amount=remaining
        )
        session.add(new_visit)
        session.flush()  # Get new_visit.id without committing
        
        # [NEW] Add initial payment record if amount > 0
        if received > 0:
            payment = Payment(
                visit_id=new_visit.id,
                patient_id=new_patient.id,
                amount=received,
                payment_method="cash",
                recorded_by=current_user.id if current_user else 0
            )
            session.add(payment)
        
        discount_ratio = discount_amt / total_price if total_price > 0 else 0
        
        created_orders = {}

        for item in items:
            if item['type'] == 'test':
                test_id = int(item['id'])
                test = session.get(TestDefinition, test_id)
                unit_price = test.price if test else 0.0
                order_discount = unit_price * discount_ratio
                final_price = unit_price - order_discount
                
                if test_id in created_orders:
                    existing_order = created_orders[test_id]
                    existing_order.unit_price += unit_price
                    existing_order.discount_amount += order_discount
                    existing_order.final_price += final_price
                else:
                    order = Order(
                        order_number=f"ORD-{visit_id}-{test_id}",
                        patient_id=new_patient.id,
                        test_id=test_id,
                        visit_id=new_visit.id,
                        ordered_by=current_user.id if current_user else None,
                        unit_price=unit_price,
                        discount_amount=order_discount,
                        final_price=final_price
                    )
                    created_orders[test_id] = order
                    session.add(order)
                
            elif item['type'] == 'package':
                package_id = int(item['id'])
                package = session.get(Package, package_id)
                package_name = package.package_name if package else ''
                package_price = package.price if package else 0.0
                package_tests = session.exec(
                    select(PackageTest).where(PackageTest.package_id == package_id)
                ).all()
                num_tests = len(package_tests)
                price_per_test = package_price / num_tests if num_tests > 0 else 0.0
                for pt in package_tests:
                    test_id = pt.test_id
                    unit_price = price_per_test
                    order_discount = unit_price * discount_ratio
                    final_price = unit_price - order_discount
                    
                    if test_id in created_orders:
                        existing_order = created_orders[test_id]
                        existing_order.unit_price += unit_price
                        existing_order.discount_amount += order_discount
                        existing_order.final_price += final_price
                        if existing_order.package_name:
                            if package_name and package_name not in existing_order.package_name:
                                existing_order.package_name += f", {package_name}"
                        else:
                            existing_order.package_name = package_name
                    else:
                        order = Order(
                            order_number=f"ORD-{visit_id}-{test_id}",
                            patient_id=new_patient.id,
                            test_id=test_id,
                            visit_id=new_visit.id,
                            ordered_by=current_user.id if current_user else None,
                            unit_price=unit_price,
                            discount_amount=order_discount,
                            final_price=final_price,
                            package_name=package_name
                        )
                        created_orders[test_id] = order
                        session.add(order)
        
        # Audit & Activity Logs (all part of the same transaction)
        audit_action = "New Visit (Returning Patient)" if is_returning else "Patient Registered"
        create_audit_log(
            session, 
            "patient", 
            new_patient.id, 
            "create" if not is_returning else "update", 
            current_user, 
            new_values={"action": audit_action, "total_tests_ordered": len(items), "visit_id": visit_id}
        )
        
        if force_duplicate.lower() == "true":
            create_audit_log(
                session, 
                "patient", 
                new_patient.id, 
                "update", 
                current_user, 
                old_values={},
                new_values={"action": "Duplicate Registration Confirmed", "note": "User explicitly confirmed bypassing duplicate check."}
            )
        
        activity_msg = f"New visit for returning patient {new_patient.full_name} (ID: {new_patient.patient_id})" if is_returning else f"Registered patient {new_patient.full_name} (ID: {new_patient.patient_id})"
        log_activity_action(session, "REGISTER_PATIENT", activity_msg, current_user, "patient", new_patient.id)
        
        # Single atomic commit — all or nothing
        session.commit()
        
        # --- Send Welcome WhatsApp Message (background thread — non-blocking) ---
        try:
            lab_info = session.exec(select(LabInfo)).first()
            if lab_info and lab_info.welcome_message and phone_number:
                from fastapi.encoders import jsonable_encoder
                import threading
                
                to_phone = phone_number.strip().replace(" ", "")
                country_code = getattr(lab_info, 'phone_country_code', '964') or '964'
                if not to_phone.startswith('+'):
                    to_phone = "+" + (to_phone if to_phone.startswith(country_code) else country_code + to_phone.lstrip('0'))
                
                lab_info_data = jsonable_encoder(lab_info)
                welcome_msg = lab_info.welcome_message
                
                def _send_welcome():
                    try:
                        from routes.whatsapp_utils import send_wati_text
                        send_wati_text(to_phone, welcome_msg, lab_info_data)
                    except Exception as e:
                        import logging
                        logging.getLogger("nexlab.whatsapp").warning(f"Welcome message failed: {e}")
                
                threading.Thread(target=_send_welcome, daemon=True).start()
        except Exception as wa_err:
            import logging
            logging.getLogger("nexlab.whatsapp").warning(f"Welcome message setup failed: {wa_err}")
        # -------------------------------------------------------
        
        return RedirectResponse(
            url=f"/patient-registration?success=Patient registered successfully!&patient_id={new_patient.patient_id}",
            status_code=status.HTTP_303_SEE_OTHER
        )
    except Exception as e:
        session.rollback()
        print(f"❌ Error creating patient: {str(e)}")
        import traceback
        traceback.print_exc()
        return RedirectResponse(
            url=f"/patient-registration?error={str(e).replace(' ', '%20')}",
            status_code=status.HTTP_303_SEE_OTHER
        )

# ===========================
# PATIENT MANAGEMENT ROUTES
# ===========================
PAGE_SIZE = 50  # Patients per page

@router.get("/patients", response_class=HTMLResponse)
def patients_page(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "patients"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    search = request.query_params.get("search", "")
    today_str = datetime.now().strftime('%Y-%m-%d')
    from_date = request.query_params.get("from_date", today_str)
    to_date = request.query_params.get("to_date", today_str)
    test_filter = request.query_params.get("test_filter", "")
    
    # Pagination
    try:
        page = max(1, int(request.query_params.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    
    query = select(PatientVisit).join(Patient).where(Patient.is_active == True)
    count_query = select(func.count(PatientVisit.id)).join(Patient).where(Patient.is_active == True)
    
    if search:
        search_filter = (
            (Patient.full_name.ilike(f"%{search}%")) |
            (Patient.patient_id.ilike(f"%{search}%")) |
            (Patient.phone_number.ilike(f"%{search}%"))
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)
    
    if from_date:
        try:
            fd = datetime.strptime(from_date, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
            query = query.where(PatientVisit.visit_date >= fd)
            count_query = count_query.where(PatientVisit.visit_date >= fd)
        except Exception:
            pass
            
    if to_date:
        try:
            td = datetime.strptime(to_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            query = query.where(PatientVisit.visit_date <= td)
            count_query = count_query.where(PatientVisit.visit_date <= td)
        except Exception:
            pass
            
    if test_filter:
        try:
            query = query.join(Order, PatientVisit.id == Order.visit_id).where(Order.test_id == int(test_filter)).distinct()
            count_query = count_query.join(Order, PatientVisit.id == Order.visit_id).where(Order.test_id == int(test_filter))
        except Exception:
            pass
    
    # Get total count for pagination
    total_count = session.exec(count_query).one()
    total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, total_pages)
    offset = (page - 1) * PAGE_SIZE
    
    # Use selectinload to eagerly load the related Patient so it's accessible in the template
    query = query.options(selectinload(PatientVisit.patient))
    patient_visits = session.exec(query.order_by(PatientVisit.visit_date.desc()).offset(offset).limit(PAGE_SIZE)).all()
    tests = session.exec(select(TestDefinition).where(TestDefinition.is_available == True)).all()
    
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    
    return templates.TemplateResponse("patients.html", {
        "request": request,
        "patient_visits": patient_visits,
        "tests": tests,
        "search": search,
        "from_date": from_date,
        "to_date": to_date,
        "test_filter": test_filter,
        "message_success": success,
        "message_error": error,
        "page": page,
        "total_pages": total_pages,
        "total_count": total_count,
    })
@router.get("/api/patients/{patient_id}/has-resulted-tests")
def check_has_resulted_tests(patient_id: str, session: Session = Depends(get_session)):
    patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()
    if not patient:
        return JSONResponse({"success": False, "error": "Patient not found"})
        
    orders = session.exec(select(Order).where(Order.patient_id == patient.id)).all()
    has_results = any(o.status in ['resulted', 'received', 'authorized', 'double_authorized'] for o in orders)
    
    return JSONResponse({"success": True, "has_results": has_results})

@router.get("/patients/edit/{patient_id}", response_class=HTMLResponse)
def patient_edit_page(request: Request, patient_id: str, session: Session = Depends(get_session)):
    if not require_permission(request, session, "patient_edit"):
        return RedirectResponse(url="/patients?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()
        
        if not patient:
            return RedirectResponse(url="/patients?error=Patient not found", status_code=status.HTTP_303_SEE_OTHER)
        
        provinces = session.exec(select(Province).where(Province.is_active == True)).all()
        regions = session.exec(select(Region).where(Region.province_id == patient.province_id)).all() if patient.province_id else []
        partners = session.exec(select(Partner).where(Partner.is_active == True)).all()
        tests = session.exec(select(TestDefinition).where(TestDefinition.is_available == True)).all()
        packages = session.exec(select(Package).where(Package.is_active == True)).all()
        
        visit_id_param = request.query_params.get("visit_id")
        visits = session.exec(
            select(PatientVisit)
            .where(PatientVisit.patient_id == patient.id)
            .order_by(PatientVisit.visit_date.desc())
        ).all()
        latest_visit = None
        if visit_id_param:
            for v in visits:
                if v.visit_id == visit_id_param:
                    latest_visit = v
                    break
        if not latest_visit and visits:
            latest_visit = visits[0]
        
        # ✅ N+1 FIX: eager-load test relationship for orders
        orders_json = []
        if latest_visit:
            orders = session.exec(
                select(Order)
                .options(selectinload(Order.test))
                .where(Order.visit_id == latest_visit.id)
            ).all()
            
            packages_map = {p.package_name: p for p in packages}
            processed_packages = {}
            
            for order in orders:
                test = order.test
                is_in_package = False
                
                if order.package_name:
                    pkg_names = [n.strip() for n in order.package_name.split(",") if n.strip()]
                    for p_name in pkg_names:
                        if p_name in packages_map:
                            is_in_package = True
                            if p_name not in processed_packages:
                                p = packages_map[p_name]
                                processed_packages[p_name] = {
                                    "id": p.id,
                                    "name": p.package_name,
                                    "type": 'package',
                                    "price": float(p.price),
                                    "package_name": p.package_name,
                                    "status": order.status
                                }
                            else:
                                if order.status in ['resulted', 'received', 'authorized', 'double_authorized']:
                                    processed_packages[p_name]["status"] = order.status
                
                if not is_in_package:
                    orders_json.append({
                        "id": order.test_id,
                        "name": test.test_name if test else 'Unknown Test',
                        "type": 'test',
                        "price": float(order.unit_price) if order.unit_price else (float(test.price) if test else 0.0),
                        "package_name": order.package_name,
                        "status": order.status
                    })
            
            orders_json.extend(processed_packages.values())
        
        orders_json_str = json.dumps(orders_json if orders_json else [])
        
        # [NEW] Fetch payments for the latest visit
        payments = []
        if latest_visit:
            payments = session.exec(
                select(Payment)
                .where(Payment.visit_id == latest_visit.id)
                .order_by(Payment.payment_date.desc())
            ).all()
        
        # Fetch attachments for the patient
        attachments = session.exec(
            select(Attachment)
            .where(Attachment.patient_id == patient.id)
            .order_by(Attachment.uploaded_at.desc())
        ).all()
        
        success = request.query_params.get("success")
        error = request.query_params.get("error")
        
        return templates.TemplateResponse("patient_edit.html", {
            "request": request,
            "patient": patient,
            "provinces": provinces,
            "regions": regions,
            "partners": partners,
            "tests": tests,
            "packages": packages,
            "visits": visits,
            "latest_visit": latest_visit,
            "payments": payments,
            "attachments": attachments,
            "orders_json": orders_json_str,
            "message_success": success,
            "message_error": error
        })
    except Exception as e:
        print(f"❌ ERROR in patient_edit_page: {str(e)}")
        import traceback
        traceback.print_exc()
        return HTMLResponse(content=f"<h1>Error Loading Page</h1><p>{str(e)}</p>", status_code=500)

# ===========================
# IMMEDIATE TEST REMOVAL API (AJAX)
# ===========================
@router.post("/api/patients/{patient_id}/remove-test")
def api_remove_test(patient_id: str, request: Request, session: Session = Depends(get_session)):
    """Immediately delete a specific test order from the patient's latest visit."""
    if not require_permission(request, session, "patient_edit", "save"):
        return JSONResponse({"success": False, "error": "Permission Denied"}, status_code=403)
    try:
        current_user = get_current_user(request, session)
        patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()
        if not patient:
            return JSONResponse({"success": False, "error": "Patient not found"}, status_code=404)
        
        visit_id_param = request.query_params.get("visit_id")
        
        # Get target visit
        if visit_id_param:
            latest_visit = session.exec(
                select(PatientVisit)
                .where(PatientVisit.patient_id == patient.id, PatientVisit.visit_id == visit_id_param)
            ).first()
        else:
            latest_visit = session.exec(
                select(PatientVisit)
                .where(PatientVisit.patient_id == patient.id)
                .order_by(PatientVisit.visit_date.desc())
            ).first()
            
        if not latest_visit:
            return JSONResponse({"success": False, "error": "No visit found"}, status_code=404)
        
        # Parse query params since this is called from JS
        test_id = int(request.query_params.get("test_id", 0))
        item_type = request.query_params.get("item_type", "test")
        reason = request.query_params.get("reason", "Removed from patient edit")
        
        if not test_id:
            return JSONResponse({"success": False, "error": "test_id is required"}, status_code=400)
        
        # Find matching order(s)
        if item_type == "package":
            package_id = test_id
            package = session.get(Package, package_id)
            if not package:
                return JSONResponse({"success": False, "error": "Package not found"}, status_code=404)
            package_test_ids = [pt.test_id for pt in session.exec(select(PackageTest).where(PackageTest.package_id == package_id)).all()]
            
            orders_to_delete = session.exec(
                select(Order)
                .options(selectinload(Order.result).selectinload(Result.details))
                .where(Order.visit_id == latest_visit.id, Order.test_id.in_(package_test_ids))
            ).all()
        else:
            orders_to_delete = session.exec(
                select(Order)
                .options(selectinload(Order.result).selectinload(Result.details))
                .where(Order.visit_id == latest_visit.id, Order.test_id == test_id)
            ).all()
        
        if not orders_to_delete:
            return JSONResponse({"success": False, "error": "Order not found"}, status_code=404)
        
        deleted_test_names = []
        for order in orders_to_delete:
            # Resolve test name for logging
            test_def = session.get(TestDefinition, order.test_id)
            test_name = test_def.test_name if test_def else f"Test #{order.test_id}"
            deleted_test_names.append(test_name)
            
            # Archive before deletion
            archive_deleted_record(session, "order", order.id, model_to_dict(order), current_user, reason)
            
            # ✅ Audit Log — log against PATIENT so it appears in Patient History
            #    (logging against the order would orphan the entry since the order gets deleted)
            create_audit_log(
                session,
                "patient",
                patient.id,
                "delete",
                current_user,
                old_values=model_to_dict(order),
                new_values={"action": "Test Removed", "test_name": test_name, "reason": reason}
            )
            
            # Delete result and details if they exist
            if order.result:
                for det in order.result.details:
                    session.delete(det)
                session.delete(order.result)
            session.delete(order)
        
        # Recalculate visit financial totals from remaining orders
        remaining_orders = session.exec(
            select(Order).where(Order.visit_id == latest_visit.id)
        ).all()
        new_total_price = sum((o.unit_price or 0.0) for o in remaining_orders)
        
        # Recalculate discount proportionally
        disc_pct = latest_visit.discount_percentage or 0.0
        new_discount = round(new_total_price * disc_pct / 100, 2) if disc_pct > 0 else 0.0
        
        # Recalculate tax
        new_tax = round((new_total_price - new_discount) * 0.0, 2)  # Preserve existing tax logic
        if latest_visit.tax_applied and latest_visit.tax_amount:
            # Keep tax ratio consistent
            old_total = sum((o.unit_price or 0.0) for o in remaining_orders) + sum((o.unit_price or 0.0) for _ in [])
            new_tax = latest_visit.tax_amount  # Tax amount set by user, preserved
        
        final_total = new_total_price - new_discount + (latest_visit.tax_amount or 0.0)
        latest_visit.discount_amount = new_discount
        latest_visit.remaining_amount = max(0, final_total - (latest_visit.received_amount or 0.0))
        session.add(latest_visit)
        
        # Log activity (same transaction)
        log_activity_action(session, "REMOVE_TEST", f"Removed {', '.join(deleted_test_names)} from patient {patient.full_name} (ID: {patient_id}). Reason: {reason}", current_user, "order", test_id)
        
        session.commit()
        
        print(f"✅ API: Removed test_id={test_id} from patient {patient_id}, reason: {reason}")
        return JSONResponse({"success": True, "message": "Test removed successfully"})
    
    except Exception as e:
        session.rollback()
        print(f"❌ API Error removing test: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

# ===========================
# PATIENT UPDATE
# ===========================
@router.post("/patients/update/{patient_id}")
def update_patient(
    patient_id: str,
    request: Request,
    full_name: str = Form(...),
    gender: str = Form(...),
    date_of_birth: Optional[str] = Form(None),
    age: Optional[int] = Form(None),
    age_unit: Optional[str] = Form(None),
    phone_key: str = Form(...),
    phone_number: str = Form(...),
    weight: float = Form(...),
    height: float = Form(...),
    province_id: int = Form(...),
    region_id: int = Form(...),
    fasting_time: Optional[int] = Form(None),
    note: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    diagnosis: Optional[str] = Form(None),
    symptoms: Optional[str] = Form(None),
    therapy: Optional[str] = Form(None),
    partner_id: Optional[int] = Form(None),
    doctor: Optional[str] = Form(None),
    skin_colour: Optional[str] = Form(None),
    agent_name: Optional[str] = Form(None),
    is_outlab: str = Form("false"),
    selected_items: str = Form("[]"),
    deleted_items: str = Form("[]"),
    discount_percentage: Optional[float] = Form(None),
    discount_amount: Optional[float] = Form(None),
    discount_note: Optional[str] = Form(None),
    received_amount: Optional[float] = Form(None),
    apply_tax_toggle: Optional[str] = Form(None),
    session: Session = Depends(get_session)
):
    if not require_permission(request, session, "patient_edit", "save"):
        return RedirectResponse(url="/patients?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()

        if not patient:
            return RedirectResponse(url="/patients?error=Patient not found", status_code=status.HTTP_303_SEE_OTHER)

        old_values = model_to_dict(patient)

        # Update patient fields
        patient.full_name = full_name
        patient.gender = gender
        patient.date_of_birth = datetime.strptime(date_of_birth, "%Y-%m-%d") if date_of_birth else None
        patient.age = age
        patient.age_unit = age_unit
        patient.phone_key = phone_key
        patient.phone_number = phone_number
        patient.weight = weight
        patient.height = height
        patient.province_id = province_id
        patient.region_id = region_id
        patient.fasting_time = fasting_time
        patient.note = note
        patient.email = email
        patient.diagnosis = diagnosis
        patient.symptoms = symptoms
        patient.therapy = therapy
        patient.partner_id = partner_id if partner_id else None
        patient.doctor = doctor
        patient.skin_colour = skin_colour
        patient.agent_name = agent_name
        patient.is_outlab = is_outlab.lower() == "true"
        patient.edited_by = current_user.id if current_user else None
        patient.edited_at = datetime.now()

        session.add(patient)
        session.commit()

        # Update orders: remove old orders for latest visit, recreate from selected_items
        items = json.loads(selected_items) if selected_items else []
        import logging
        logger = logging.getLogger("nexlab.patients")
        logger.debug(f"Update patient {patient_id} | selected_items: {selected_items} | deleted_items: {deleted_items}")

        visit_id_param = request.query_params.get("visit_id")
        
        # Get or create the latest visit
        visits = session.exec(
            select(PatientVisit)
            .where(PatientVisit.patient_id == patient.id)
            .order_by(PatientVisit.visit_date.desc())
        ).all()
        
        latest_visit = None
        if visit_id_param:
            for v in visits:
                if v.visit_id == visit_id_param:
                    latest_visit = v
                    break
        if not latest_visit and visits:
            latest_visit = visits[0]

        if not latest_visit:
            visit_count = 0
            visit_id = patient_id + str(visit_count).zfill(3)
            latest_visit = PatientVisit(
                visit_id=visit_id,
                patient_id=patient.id,
                created_by=current_user.id if current_user else None
            )
            session.add(latest_visit)
            session.commit()
            session.refresh(latest_visit)

        # Safely handle deleted orders and preserve unmodified ones
        deleted_tests_json = json.loads(deleted_items) if deleted_items else []
        final_test_ids = []
        for item in items:
            if item.get('type') == 'test':
                final_test_ids.append(int(item['id']))
            elif item.get('type') == 'package':
                pts = session.exec(select(PackageTest).where(PackageTest.package_id == int(item['id']))).all()
                final_test_ids.extend([pt.test_id for pt in pts])

        print(f"🔍 PATIENT UPDATE DEBUG [{patient_id}]:")
        print(f"   selected_items count: {len(items)}")
        print(f"   deleted_items count: {len(deleted_tests_json)}")
        print(f"   final_test_ids (should remain): {final_test_ids}")
        print(f"   deleted_tests_json: {deleted_tests_json}")

        old_orders = session.exec(
            select(Order)
            .options(selectinload(Order.result).selectinload(Result.details))
            .where(Order.visit_id == latest_visit.id)
        ).all()
        active_old_order_test_ids = []
        
        print(f"   old_orders test_ids: {[o.test_id for o in old_orders]}")
        
        for old_order in old_orders:
            if old_order.test_id not in final_test_ids:
                reason = "Deleted test from patient visit"
                for dt in deleted_tests_json:
                    if dt.get('type') == 'test' and int(dt['id']) == old_order.test_id:
                        reason = dt.get('reason', reason)
                
                print(f"   ❌ DELETING order id={old_order.id}, test_id={old_order.test_id}, reason={reason}")
                
                # Resolve test name for logging
                test_def = session.get(TestDefinition, old_order.test_id)
                test_name = test_def.test_name if test_def else f"Test #{old_order.test_id}"

                archive_deleted_record(session, "order", old_order.id, model_to_dict(old_order), current_user, reason)
                
                # ✅ Audit Log — log against PATIENT so it appears in Patient History
                create_audit_log(
                    session,
                    "patient",
                    patient.id,
                    "delete",
                    current_user,
                    old_values=model_to_dict(old_order),
                    new_values={"action": "Test Removed", "test_name": test_name, "reason": reason}
                )
                if old_order.result:
                    for det in old_order.result.details:
                        session.delete(det)
                    session.delete(old_order.result)
                session.delete(old_order)
            else:
                print(f"   ✅ KEEPING order id={old_order.id}, test_id={old_order.test_id}")
                active_old_order_test_ids.append(old_order.test_id)
        session.commit()
        print(f"   ✅ Deletion commit successful")

        # Calculate totals
        total_price = sum(float(item.get('price', 0)) for item in items)
        
        # --- Check Discount Permissions ---
        has_discount_perm = require_permission(request, session, "patient_edit", "discount")
                        
        if not has_discount_perm:
            discount_percentage = None
            discount_amount = None
        # ----------------------------------
        
        discount_amt = float(discount_amount) if discount_amount else 0.0
        final_total = total_price
        
        if discount_percentage:
            final_total = total_price * (1 - discount_percentage / 100)
            discount_amt = total_price - final_total
        elif discount_amount:
            final_total = total_price - float(discount_amount)

        # --- NEW TAX LOGIC ---
        is_tax_applied = apply_tax_toggle == "on"
        tax_amount = 0.0
        if is_tax_applied:
            lab_info = session.exec(select(LabInfo)).first()
            tax_percentage = lab_info.tax_percentage if lab_info else 0.0
            tax_amount = (tax_percentage / 100) * final_total
            final_total += tax_amount
        # ---------------------

        received = float(received_amount) if received_amount else 0.0
        remaining = max(0, final_total - received)

        # [NEW] Record payment difference as a new Payment record
        print(f"DEBUG Update Patient: {patient_id}")
        print(f"DEBUG selected_items received: {selected_items}")
        print(f"DEBUG deleted_items received: {deleted_items}")
        payment_diff = received - (latest_visit.received_amount if latest_visit.received_amount else 0.0)
        if payment_diff != 0:
            payment_record = Payment(
                visit_id=latest_visit.id,
                patient_id=patient.id,
                amount=abs(payment_diff),
                payment_method="cash",
                recorded_by=current_user.id if current_user else 0,
                is_refund=(payment_diff < 0),
                note="Updated via EDIT form"
            )
            session.add(payment_record)

        # Update visit payment info
        disc_pct = float(discount_percentage) if discount_percentage else 0.0
        latest_visit.received_amount = received
        latest_visit.discount_amount = round(discount_amt, 2)
        latest_visit.discount_percentage = disc_pct
        latest_visit.discount_note = discount_note
        latest_visit.tax_applied = is_tax_applied
        latest_visit.tax_amount = round(tax_amount, 2)
        latest_visit.remaining_amount = remaining
        latest_visit.edited_by = current_user.id if current_user else None
        latest_visit.edited_at = datetime.now()
        session.add(latest_visit)

        # Recreate orders with price snapshots
        discount_ratio = discount_amt / total_price if total_price > 0 else 0
        
        # map old active orders
        active_orders_map = {o.test_id: o for o in old_orders if o.test_id in active_old_order_test_ids}
        
        # Reset their prices to 0 so we can recalculate them from the current items list
        for o in active_orders_map.values():
            o.unit_price = 0.0
            o.discount_amount = 0.0
            o.final_price = 0.0

        created_orders = {}

        for item in items:
            if item.get('type') == 'test':
                test_id = int(item['id'])
                test = session.get(TestDefinition, test_id)
                unit_price = test.price if test else 0.0
                order_discount = unit_price * discount_ratio
                final_price = unit_price - order_discount
                
                if test_id in active_orders_map:
                    order = active_orders_map[test_id]
                    order.unit_price += unit_price
                    order.discount_amount += order_discount
                    order.final_price += final_price
                elif test_id in created_orders:
                    order = created_orders[test_id]
                    order.unit_price += unit_price
                    order.discount_amount += order_discount
                    order.final_price += final_price
                else:
                    order = Order(
                        order_number=f"ORD-{latest_visit.visit_id}-{test_id}",
                        patient_id=patient.id,
                        test_id=test_id,
                        visit_id=latest_visit.id,
                        ordered_by=current_user.id if current_user else None,
                        unit_price=unit_price,
                        discount_amount=order_discount,
                        final_price=final_price
                    )
                    created_orders[test_id] = order
                    session.add(order)

                    # Log newly added test
                    test_name = test.test_name if test else f"Test #{test_id}"
                    create_audit_log(
                        session,
                        "patient",
                        patient.id,
                        "update",
                        current_user,
                        old_values={},
                        new_values={"action": "Test Added", "test_name": test_name}
                    )

            elif item.get('type') == 'package':
                package_id = int(item['id'])
                package = session.get(Package, package_id)
                package_name = package.package_name if package else ''
                package_price = package.price if package else 0.0
                package_tests = session.exec(
                    select(PackageTest).where(PackageTest.package_id == package_id)
                ).all()
                num_tests = len(package_tests)
                price_per_test = package_price / num_tests if num_tests > 0 else 0.0
                for pt in package_tests:
                    test_id = pt.test_id
                    unit_price = price_per_test
                    order_discount = unit_price * discount_ratio
                    final_price = unit_price - order_discount

                    if test_id in active_orders_map:
                        order = active_orders_map[test_id]
                        order.unit_price += unit_price
                        order.discount_amount += order_discount
                        order.final_price += final_price
                        if not order.package_name:
                            order.package_name = package_name
                        elif package_name and package_name not in order.package_name:
                            order.package_name += f", {package_name}"
                    elif test_id in created_orders:
                        order = created_orders[test_id]
                        order.unit_price += unit_price
                        order.discount_amount += order_discount
                        order.final_price += final_price
                        if not order.package_name:
                            order.package_name = package_name
                        elif package_name and package_name not in order.package_name:
                            order.package_name += f", {package_name}"
                    else:
                        order = Order(
                            order_number=f"ORD-{latest_visit.visit_id}-{test_id}",
                            patient_id=patient.id,
                            test_id=test_id,
                            visit_id=latest_visit.id,
                            ordered_by=current_user.id if current_user else None,
                            unit_price=unit_price,
                            discount_amount=order_discount,
                            final_price=final_price,
                            package_name=package_name
                        )
                        created_orders[test_id] = order
                        session.add(order)

                        # Log newly added test
                        test_def = session.get(TestDefinition, test_id)
                        test_name = test_def.test_name if test_def else f"Test #{test_id}"
                        create_audit_log(
                            session,
                            "patient",
                            patient.id,
                            "update",
                            current_user,
                            old_values={},
                            new_values={"action": "Test Added", "test_name": test_name}
                        )

        # Audit & Activity Logs (same transaction as data changes)
        create_audit_log(
            session, 
            "patient", 
            patient.id, 
            "update", 
            current_user, 
            old_values=old_values, 
            new_values={"action": "Patient Profile Updated"}
        )
        log_activity_action(session, "EDIT_PATIENT", f"Updated patient {patient.full_name} (ID: {patient_id})", current_user, "patient", patient.id)
        
        # Single atomic commit
        session.commit()

        return RedirectResponse(
            url=f"/patients/edit/{patient_id}?success=Patient updated successfully!",
            status_code=status.HTTP_303_SEE_OTHER
        )
    except Exception as e:
        session.rollback()
        print(f"❌ Error updating patient: {str(e)}")
        import traceback
        traceback.print_exc()
        return RedirectResponse(
            url=f"/patients/edit/{patient_id}?error={str(e).replace(' ', '%20')}",
            status_code=status.HTTP_303_SEE_OTHER
        )

# ===========================
# DELETE VISIT (and all child records)
# ===========================
@router.post("/patients/{patient_id}/delete-visit/{visit_id}")
def delete_patient_visit(
    patient_id: str,
    visit_id: str,
    request: Request,
    deleted_reason: str = Form(...),
    session: Session = Depends(get_session)
):
    """Delete a specific visit and all its child records: orders, results, result details, payments, attachments."""
    if not require_permission(request, session, "patients", "delete"):
        return RedirectResponse(url=f"/patients/edit/{patient_id}?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()
        if not patient:
            return RedirectResponse(url="/patients?error=Patient not found", status_code=status.HTTP_303_SEE_OTHER)

        visit = session.exec(
            select(PatientVisit).where(
                PatientVisit.patient_id == patient.id,
                PatientVisit.visit_id == visit_id
            )
        ).first()
        if not visit:
            return RedirectResponse(url=f"/patients/edit/{patient_id}?error=Visit not found", status_code=status.HTTP_303_SEE_OTHER)

        # Archive the visit before deletion
        archive_deleted_record(session, "patientvisit", visit.id, model_to_dict(visit), current_user, deleted_reason)

        # 1. Delete all orders (and their results + result details)
        orders = session.exec(
            select(Order)
            .options(selectinload(Order.result).selectinload(Result.details))
            .where(Order.visit_id == visit.id)
        ).all()

        deleted_test_names = []
        for order in orders:
            test_def = session.get(TestDefinition, order.test_id)
            test_name = test_def.test_name if test_def else f"Test #{order.test_id}"
            deleted_test_names.append(test_name)

            archive_deleted_record(session, "order", order.id, model_to_dict(order), current_user, deleted_reason)

            # Delete result details → result
            if order.result:
                for det in order.result.details:
                    session.delete(det)
                session.delete(order.result)
            session.delete(order)

        # 2. Delete all payment records for this visit
        payments = session.exec(select(Payment).where(Payment.visit_id == visit.id)).all()
        for payment in payments:
            archive_deleted_record(session, "payment", payment.id, model_to_dict(payment), current_user, deleted_reason)
            session.delete(payment)

        # 3. Delete all attachments for this visit
        attachments = session.exec(select(Attachment).where(Attachment.visit_id == visit.id)).all()
        for att in attachments:
            archive_deleted_record(session, "attachment", att.id, model_to_dict(att), current_user, deleted_reason)
            # Delete physical file
            import os
            if att.file_path and os.path.exists(att.file_path):
                try:
                    os.remove(att.file_path)
                except Exception:
                    pass
            session.delete(att)

        # 4. Delete the visit itself
        session.delete(visit)

        # Audit log & activity
        create_audit_log(
            session,
            "patient",
            patient.id,
            "delete",
            current_user,
            old_values=model_to_dict(visit),
            new_values={
                "action": f"Visit Deleted (ID: {visit_id}). Tests: {', '.join(deleted_test_names)}. Reason: {deleted_reason}",
                "deleted_tests": deleted_test_names,
                "deleted_payments_count": len(payments),
                "deleted_attachments_count": len(attachments)
            }
        )
        log_activity_action(
            session,
            "DELETE_VISIT",
            f"Deleted visit {visit_id} from patient {patient.full_name} (ID: {patient_id}). "
            f"Tests: {', '.join(deleted_test_names)}. Payments: {len(payments)}. Reason: {deleted_reason}",
            current_user,
            "patientvisit",
            visit.id
        )

        session.commit()

        print(f"✅ Deleted visit {visit_id} from patient {patient_id}: "
              f"{len(orders)} orders, {len(payments)} payments, {len(attachments)} attachments")

        return RedirectResponse(
            url=f"/patients/edit/{patient_id}?success=Visit deleted successfully!",
            status_code=status.HTTP_303_SEE_OTHER
        )

    except Exception as e:
        session.rollback()
        print(f"❌ Error deleting visit: {str(e)}")
        import traceback
        traceback.print_exc()
        return RedirectResponse(
            url=f"/patients/edit/{patient_id}?error={str(e).replace(' ', '%20')}",
            status_code=status.HTTP_303_SEE_OTHER
        )

# ===========================
# PATIENT SOFT DELETE
# ===========================
@router.post("/patients/delete/{patient_id}")
def delete_patient(patient_id: str, request: Request, deleted_reason: str = Form(...), session: Session = Depends(get_session)):
    if not require_permission(request, session, "patients", "delete"):
        return RedirectResponse(url="/patients?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()

        if patient:
            old_values = model_to_dict(patient)
            patient.is_active = False
            patient.deleted_by = current_user.id if current_user else None
            patient.deleted_at = datetime.now()
            patient.deleted_reason = deleted_reason
            session.add(patient)

            archive_deleted_record(session, "patient", patient.id, old_values, current_user, deleted_reason)
            
            create_audit_log(
                session, 
                "patient", 
                patient.id, 
                "soft_delete", 
                current_user, 
                old_values=old_values,
                new_values={"action": f"Patient Soft Deleted. Reason: {deleted_reason}"}
            )
            log_activity_action(session, "DELETE_PATIENT", f"Deleted patient {patient.full_name} (ID: {patient_id}). Reason: {deleted_reason}", current_user, "patient", patient.id)
            
            # Single atomic commit
            session.commit()
            
            return RedirectResponse(url="/patients?success=Patient deleted successfully!", status_code=status.HTTP_303_SEE_OTHER)

        return RedirectResponse(url="/patients?error=Patient not found", status_code=status.HTTP_303_SEE_OTHER)

    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/patients?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

# ===========================
# DELETED PATIENTS
# ===========================
@router.get("/patients/deleted", response_class=HTMLResponse)
def deleted_patients_page(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "deleted_patients"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    
    search = request.query_params.get("search", "")
    start_date_str = request.query_params.get("start_date")
    end_date_str = request.query_params.get("end_date")
    user_filter = request.query_params.get("user_id", "all")
    
    if not start_date_str:
        start_date_str = datetime.now().strftime("%d-%m-%Y")
    if not end_date_str:
        end_date_str = start_date_str
    
    query = select(Patient).where(Patient.is_active == False)
    
    if search:
        query = query.where(
            (Patient.full_name.ilike(f"%{search}%")) |
            (Patient.patient_id.ilike(f"%{search}%")) |
            (Patient.phone_number.ilike(f"%{search}%"))
        )
        
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%d-%m-%Y").replace(hour=0, minute=0, second=0)
            query = query.where(Patient.deleted_at >= start_date)
        except ValueError:
            pass
            
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, "%d-%m-%Y").replace(hour=23, minute=59, second=59)
            query = query.where(Patient.deleted_at <= end_date)
        except ValueError:
            pass
            
    if user_filter and user_filter != "all":
        query = query.where(Patient.deleted_by == int(user_filter))
    
    query = query.options(selectinload(Patient.visits).selectinload(PatientVisit.orders))
    patients = session.exec(query.order_by(Patient.deleted_at.desc())).all()
    
    # Fetch all users for dropdown and dictionary
    users = session.exec(select(User)).all()
    user_dict = {u.id: u.full_name for u in users}
    
    patient_totals = {}
    for p in patients:
        total = 0.0
        # Get the latest visit for this patient
        if p.visits:
            latest_visit = sorted(p.visits, key=lambda v: v.visit_date, reverse=True)[0]
            total = sum((o.unit_price or 0.0) for o in latest_visit.orders) - (latest_visit.discount_amount or 0.0) + (latest_visit.tax_amount or 0.0)
        patient_totals[p.id] = total
    
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    
    return templates.TemplateResponse("deleted_patients.html", {
        "request": request,
        "patients": patients,
        "patient_totals": patient_totals,
        "search": search,
        "start_date": start_date_str,
        "end_date": end_date_str,
        "user_filter": user_filter,
        "users": users,
        "user_dict": user_dict,
        "message_success": success,
        "message_error": error
    })

@router.get("/patients/view-deleted/{patient_id}", response_class=HTMLResponse)
def view_deleted_patient(request: Request, patient_id: str, session: Session = Depends(get_session)):
    if not require_permission(request, session, "deleted_patients"):
        return RedirectResponse(url="/patients/deleted?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()
    
    if not patient or patient.is_active:
        return RedirectResponse(url="/patients/deleted?error=Patient not found", status_code=status.HTTP_303_SEE_OTHER)
    
    provinces = session.exec(select(Province).where(Province.is_active == True)).all()
    regions = session.exec(select(Region).where(Region.province_id == patient.province_id)).all() if patient.province_id else []
    partners = session.exec(select(Partner).where(Partner.is_active == True)).all()
    
    visits = session.exec(select(PatientVisit).where(PatientVisit.patient_id == patient.id).order_by(PatientVisit.visit_date.desc())).all()
    orders = session.exec(select(Order).where(Order.patient_id == patient.id).order_by(Order.order_date.desc())).all()
    
    return templates.TemplateResponse("view_deleted_patient.html", {
        "request": request,
        "patient": patient,
        "provinces": provinces,
        "regions": regions,
        "partners": partners,
        "visits": visits,
        "orders": orders
    })

@router.get("/patients/restore/{patient_id}")
def restore_patient(patient_id: str, request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "deleted_patients", "restore"):
        return RedirectResponse(url="/patients/deleted?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()
        
        if patient:
            old_values = model_to_dict(patient)
            patient.is_active = True
            patient.deleted_by = None
            patient.deleted_at = None
            patient.deleted_reason = None
            patient.edited_by = current_user.id if current_user else None
            patient.edited_at = datetime.now()
            session.add(patient)
            
            create_audit_log(
                session, 
                "patient", 
                patient.id, 
                "restore", 
                current_user, 
                old_values=old_values,
                new_values={"action": "Patient Restored from Deleted Status"}
            )
            
            # Single atomic commit
            session.commit()
            
            return RedirectResponse(url="/patients/deleted?success=Patient restored successfully!", status_code=status.HTTP_303_SEE_OTHER)
        
        return RedirectResponse(url="/patients/deleted?error=Patient not found", status_code=status.HTTP_303_SEE_OTHER)
        
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/patients/deleted?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)


# ===========================
# ADD NEW PAYMENT (AJAX or Form)
# ===========================
@router.post("/patient/{patient_id}/payment")
def add_patient_payment(
    patient_id: str,
    request: Request,
    visit_id: int = Form(...),
    amount: float = Form(...),
    payment_method: str = Form("cash"),
    note: Optional[str] = Form(None),
    is_refund: bool = Form(False),
    session: Session = Depends(get_session)
):
    current_user = get_current_user(request, session)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        
    try:
        visit = session.get(PatientVisit, visit_id)
        patient_record = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()
        
        if not visit or not patient_record or visit.patient_id != patient_record.id:
            return RedirectResponse(url=f"/patient/edit/{patient_id}?error=Invalid visit", status_code=status.HTTP_303_SEE_OTHER)
        
        # 1. Create the payment record
        payment = Payment(
            visit_id=visit.id,
            patient_id=patient_record.id,
            amount=amount,
            payment_method=payment_method,
            note=note,
            is_refund=is_refund,
            recorded_by=current_user.id
        )
        session.add(payment)
        
        # 2. Update the visit's total received amount
        all_payments = session.exec(select(Payment).where(Payment.visit_id == visit.id)).all()
        
        total_received = sum([p.amount if not p.is_refund else -p.amount for p in all_payments])
        if is_refund:
            total_received -= amount
        else:
            total_received += amount
            
        visit.received_amount = max(0, total_received)
        
        # Recalculate remaining
        total_price = sum([(o.unit_price or 0.0) for o in visit.orders])
        discount_amt = visit.discount_amount or 0.0
        tax_amt = visit.tax_amount or 0.0
        final_total = total_price - discount_amt + tax_amt
        visit.remaining_amount = max(0, final_total - visit.received_amount)
        
        session.add(visit)
        session.commit()
        
        msg = "Refund recorded" if is_refund else "Payment recorded"
        return RedirectResponse(url=f"/patient/edit/{patient_id}?success={msg} successfully", status_code=status.HTTP_303_SEE_OTHER)
        
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/patient/edit/{patient_id}?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

# ===========================
# DELETED TESTS
# ===========================
@router.get("/deleted_tests_page", response_class=HTMLResponse)
def deleted_tests_page(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "deleted_tests"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    
    start_date_str = request.query_params.get("start_date")
    end_date_str = request.query_params.get("end_date")
    user_filter = request.query_params.get("user_id", "all")
    
    if not start_date_str:
        start_date_str = datetime.now().strftime("%d-%m-%Y")
    if not end_date_str:
        end_date_str = start_date_str
        
    query = select(DeletedRecord).where(DeletedRecord.source_table == "order")
    
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%d-%m-%Y").replace(hour=0, minute=0, second=0)
            query = query.where(DeletedRecord.deleted_at >= start_date)
        except ValueError:
            pass
            
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, "%d-%m-%Y").replace(hour=23, minute=59, second=59)
            query = query.where(DeletedRecord.deleted_at <= end_date)
        except ValueError:
            pass
            
    if user_filter and user_filter != "all":
        query = query.where(DeletedRecord.deleted_by == int(user_filter))
        
    deleted_records = session.exec(query.order_by(DeletedRecord.deleted_at.desc())).all()
    
    users = session.exec(select(User)).all()
    user_map = {u.id: u.full_name for u in users}
    
    report_data = []
    for idx, rec in enumerate(deleted_records, 1):
        try:
            data = json.loads(rec.record_data)
        except Exception:
            data = {}
            
        patient_id = data.get("patient_id")
        test_id = data.get("test_id")
        
        patient = session.get(Patient, patient_id) if patient_id else None
        test = session.get(TestDefinition, test_id) if test_id else None
        
        # Safely determine price
        try:
            if "unit_price" in data and data["unit_price"] is not None:
                p_val = float(data["unit_price"])
            elif "final_price" in data and data["final_price"] is not None:
                p_val = float(data["final_price"])
            else:
                p_val = float(test.price) if test and test.price is not None else 0.0
        except (ValueError, TypeError):
            p_val = 0.0

        report_data.append({
            "no": idx,
            "deleted_at": rec.deleted_at.strftime("%d-%m-%Y %H:%M"),
            "deleted_by_name": user_map.get(rec.deleted_by, "System"),
            "patient_code": patient.patient_id if patient else "N/A",
            "patient_name": patient.full_name if patient else "Unknown",
            "age_gender": f"{patient.age} {patient.age_unit} - {patient.gender}" if patient else "N/A",
            "test_name": test.test_name if test else "Unknown Test",
            "price": p_val,
            "reason": rec.deleted_reason or "No reason provided"
        })
        
    return templates.TemplateResponse("deleted_tests.html", {
        "request": request,
        "report_data": report_data,
        "users": users,
        "start_date": start_date_str,
        "end_date": end_date_str,
        "user_filter": user_filter
    })