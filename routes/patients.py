# routes/patients.py
# Patient registration, management, editing, soft-delete/restore, and deleted patients view.

from fastapi import APIRouter, Depends, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlmodel import Session, select
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
    
    return templates.TemplateResponse("patient_registration.html", {
        "request": request, "provinces": provinces, "partners": partners,
        "tests": tests, "packages": packages,
        "message_success": success, "message_error": error,
        "last_patient_id": last_patient_id,
        "print_token": print_token,
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
    except:
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
        session.commit()
        session.refresh(new_patient)
        
        visits = session.exec(select(PatientVisit).where(PatientVisit.patient_id == new_patient.id)).all()
        visit_count = len(visits)
        visit_id = patient_id + str(visit_count).zfill(3)
        
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
        session.commit()
        session.refresh(new_visit)
        
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
            session.commit()
        
        discount_ratio = discount_amt / total_price if total_price > 0 else 0
        
        for item in items:
            if item['type'] == 'test':
                test = session.get(TestDefinition, item['id'])
                unit_price = test.price if test else 0.0
                order_discount = unit_price * discount_ratio
                final_price = unit_price - order_discount
                
                order = Order(
                    order_number=f"ORD-{visit_id}-{item['id']}",
                    patient_id=new_patient.id,
                    test_id=item['id'],
                    visit_id=new_visit.id,
                    ordered_by=current_user.id if current_user else None,
                    unit_price=unit_price,
                    discount_amount=order_discount,
                    final_price=final_price
                )
                session.add(order)
                
            elif item['type'] == 'package':
                package = session.get(Package, item['id'])
                package_name = package.package_name if package else ''
                package_price = package.price if package else 0.0
                package_tests = session.exec(
                    select(PackageTest).where(PackageTest.package_id == item['id'])
                ).all()
                num_tests = len(package_tests)
                price_per_test = package_price / num_tests if num_tests > 0 else 0.0
                for pt in package_tests:
                    unit_price = price_per_test
                    order_discount = unit_price * discount_ratio
                    final_price = unit_price - order_discount
                    
                    order = Order(
                        order_number=f"ORD-{visit_id}-{pt.test_id}",
                        patient_id=new_patient.id,
                        test_id=pt.test_id,
                        visit_id=new_visit.id,
                        ordered_by=current_user.id if current_user else None,
                        unit_price=unit_price,
                        discount_amount=order_discount,
                        final_price=final_price,
                        package_name=package_name
                    )
                    session.add(order)
        
        session.commit()
        
        # ---------------------------------------------------------
        # ✅ FIXED: LOG AND COMMIT REGISTRATION
        # ---------------------------------------------------------
        create_audit_log(
            session, 
            "patient", 
            new_patient.id, 
            "create", 
            current_user, 
            new_values={"action": "Patient Registered", "total_tests_ordered": len(items), "visit_id": visit_id}
        )
        session.commit()
        
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
            session.commit()
        # ---------------------------------------------------------
        
        # Activity Log: Patient Registration
        log_activity_action(session, "REGISTER_PATIENT", f"Registered patient {new_patient.full_name} (ID: {new_patient.patient_id})", current_user, "patient", new_patient.id)
        session.commit()
        
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
@router.get("/patients", response_class=HTMLResponse)
def patients_page(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "patients"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    search = request.query_params.get("search", "")
    today_str = datetime.now().strftime('%Y-%m-%d')
    from_date = request.query_params.get("from_date", today_str)
    to_date = request.query_params.get("to_date", today_str)
    test_filter = request.query_params.get("test_filter", "")
    
    query = select(Patient).where(Patient.is_active == True)
    
    if search:
        query = query.where(
            (Patient.full_name.ilike(f"%{search}%")) |
            (Patient.patient_id.ilike(f"%{search}%")) |
            (Patient.phone_number.ilike(f"%{search}%"))
        )
    
    if from_date:
        try:
            fd = datetime.strptime(from_date, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
            query = query.where(Patient.created_at >= fd)
        except Exception:
            pass
            
    if to_date:
        try:
            td = datetime.strptime(to_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            query = query.where(Patient.created_at <= td)
        except Exception:
            pass
            
    if test_filter:
        try:
            query = query.join(Order, Patient.id == Order.patient_id).where(Order.test_id == int(test_filter)).distinct()
        except Exception:
            pass
    
    patients = session.exec(query.order_by(Patient.created_at.desc())).all()
    tests = session.exec(select(TestDefinition).where(TestDefinition.is_available == True)).all()
    
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    
    return templates.TemplateResponse("patients.html", {
        "request": request,
        "patients": patients,
        "tests": tests,
        "search": search,
        "from_date": from_date,
        "to_date": to_date,
        "test_filter": test_filter,
        "message_success": success,
        "message_error": error
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
        
        visits = session.exec(
            select(PatientVisit)
            .where(PatientVisit.patient_id == patient.id)
            .order_by(PatientVisit.visit_date.desc())
        ).all()
        latest_visit = visits[0] if visits else None
        
        # ✅ N+1 FIX: eager-load test relationship for orders
        orders_json = []
        if latest_visit:
            orders = session.exec(
                select(Order)
                .options(selectinload(Order.test))
                .where(Order.visit_id == latest_visit.id)
            ).all()
            for order in orders:
                test = order.test
                orders_json.append({
                    "id": order.test_id,
                    "name": test.test_name if test else 'Unknown Test',
                    "type": 'test',
                    "price": float(order.unit_price) if order.unit_price else (float(test.price) if test else 0.0),
                    "package_name": order.package_name,
                    "status": order.status
                })
        
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
        
        # Get latest visit
        latest_visit = session.exec(
            select(PatientVisit)
            .where(PatientVisit.patient_id == patient.id)
            .order_by(PatientVisit.visit_date.desc())
        ).first()
        if not latest_visit:
            return JSONResponse({"success": False, "error": "No visit found"}, status_code=404)
        
        # Parse query params since this is called from JS
        test_id = int(request.query_params.get("test_id", 0))
        reason = request.query_params.get("reason", "Removed from patient edit")
        
        if not test_id:
            return JSONResponse({"success": False, "error": "test_id is required"}, status_code=400)
        
        # Find matching order(s)
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
        
        session.commit()
        
        # Log activity
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
        with open("update_debug.log", "a") as f:
            f.write(f"DEBUG update patient {patient_id}\n")
            f.write(f"selected_items: {selected_items}\n")
            f.write(f"deleted_items: {deleted_items}\n")

        # Get or create the latest visit
        visits = session.exec(
            select(PatientVisit)
            .where(PatientVisit.patient_id == patient.id)
            .order_by(PatientVisit.visit_date.desc())
        ).all()
        latest_visit = visits[0] if visits else None

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
            from models import LabInfo
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

        for item in items:
            if item.get('type') == 'test':
                if int(item['id']) in active_old_order_test_ids:
                    continue  # Keep existing order to preserve results and IDs
                test = session.get(TestDefinition, item['id'])
                unit_price = test.price if test else 0.0
                order_discount = unit_price * discount_ratio
                final_price = unit_price - order_discount

                order = Order(
                    order_number=f"ORD-{latest_visit.visit_id}-{item['id']}",
                    patient_id=patient.id,
                    test_id=item['id'],
                    visit_id=latest_visit.id,
                    ordered_by=current_user.id if current_user else None,
                    unit_price=unit_price,
                    discount_amount=order_discount,
                    final_price=final_price
                )
                session.add(order)

                # Log newly added test
                test_name = test.test_name if test else f"Test #{item['id']}"
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
                package = session.get(Package, item['id'])
                package_name = package.package_name if package else ''
                package_price = package.price if package else 0.0
                package_tests = session.exec(
                    select(PackageTest).where(PackageTest.package_id == item['id'])
                ).all()
                num_tests = len(package_tests)
                price_per_test = package_price / num_tests if num_tests > 0 else 0.0
                for pt in package_tests:
                    if pt.test_id in active_old_order_test_ids:
                        continue  # Keep existing order to preserve results and IDs
                    unit_price = price_per_test
                    order_discount = unit_price * discount_ratio
                    final_price = unit_price - order_discount

                    order = Order(
                        order_number=f"ORD-{latest_visit.visit_id}-{pt.test_id}",
                        patient_id=patient.id,
                        test_id=pt.test_id,
                        visit_id=latest_visit.id,
                        ordered_by=current_user.id if current_user else None,
                        unit_price=unit_price,
                        discount_amount=order_discount,
                        final_price=final_price,
                        package_name=package_name
                    )
                    session.add(order)

                    # Log newly added test from package
                    test_def = session.get(TestDefinition, pt.test_id)
                    test_name = test_def.test_name if test_def else f"Test #{pt.test_id}"
                    create_audit_log(
                        session,
                        "patient",
                        patient.id,
                        "update",
                        current_user,
                        old_values={},
                        new_values={"action": "Test Added", "test_name": test_name}
                    )

        session.commit()
        
        # ---------------------------------------------------------
        # ✅ FIXED: LOG AND COMMIT UPDATE
        # ---------------------------------------------------------
        create_audit_log(
            session, 
            "patient", 
            patient.id, 
            "update", 
            current_user, 
            old_values=old_values, 
            new_values={"action": "Patient Profile Updated"}
        )
        session.commit()
        # ---------------------------------------------------------

        # Activity Log: Patient Edit
        log_activity_action(session, "EDIT_PATIENT", f"Updated patient {patient.full_name} (ID: {patient_id})", current_user, "patient", patient.id)
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
            session.commit()

            # ---------------------------------------------------------
            # ✅ FIXED: LOG AND COMMIT DELETE
            # ---------------------------------------------------------
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
            session.commit()
            # ---------------------------------------------------------

            # Activity Log: Patient Delete
            log_activity_action(session, "DELETE_PATIENT", f"Deleted patient {patient.full_name} (ID: {patient_id}). Reason: {deleted_reason}", current_user, "patient", patient.id)
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
    
    patients = session.exec(query.order_by(Patient.deleted_at.desc())).all()
    
    # Fetch all users for dropdown and dictionary
    users = session.exec(select(User)).all()
    user_dict = {u.id: u.full_name for u in users}
    
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    
    return templates.TemplateResponse("deleted_patients.html", {
        "request": request,
        "patients": patients,
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
            patient.edited_by = current_user.id if current_user else None
            patient.edited_at = datetime.now()
            session.add(patient)
            session.commit()
            
            # ---------------------------------------------------------
            # ✅ FIXED: LOG AND COMMIT RESTORE
            # ---------------------------------------------------------
            create_audit_log(
                session, 
                "patient", 
                patient.id, 
                "restore", 
                current_user, 
                old_values=old_values,
                new_values={"action": "Patient Restored from Deleted Status"}
            )
            session.commit()
            # ---------------------------------------------------------
            
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
        except:
            data = {}
            
        patient_id = data.get("patient_id")
        test_id = data.get("test_id")
        
        patient = session.get(Patient, patient_id) if patient_id else None
        test = session.get(TestDefinition, test_id) if test_id else None
        
        report_data.append({
            "no": idx,
            "deleted_at": rec.deleted_at.strftime("%d-%m-%Y %H:%M"),
            "deleted_by_name": user_map.get(rec.deleted_by, "System"),
            "patient_code": patient.patient_id if patient else "N/A",
            "patient_name": patient.full_name if patient else "Unknown",
            "age_gender": f"{patient.age} {patient.age_unit} - {patient.gender}" if patient else "N/A",
            "test_name": test.test_name if test else "Unknown Test",
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