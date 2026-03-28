# routes/patients.py
# Patient registration, management, editing, soft-delete/restore, and deleted patients view.

from fastapi import APIRouter, Depends, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload
from datetime import datetime
from typing import Optional
import json
from database import get_session
from models import (
    Patient, PatientVisit, Order, TestDefinition, Package, PackageTest,
    Province, Region, Partner, SampleType, LabInfo,
)
from routes.helpers import templates, get_current_user, create_audit_log, model_to_dict, generate_barcode_base64

router = APIRouter()

# ===========================
# PATIENT REGISTRATION PAGE
# ===========================
@router.get("/patient-registration", response_class=HTMLResponse)
def patient_registration_page(request: Request, session: Session = Depends(get_session)):
    provinces = session.exec(select(Province).where(Province.is_active == True)).all()
    partners = session.exec(select(Partner).where(Partner.is_active == True)).all()
    tests = session.exec(select(TestDefinition).where(TestDefinition.is_available == True)).all()
    packages = session.exec(select(Package).where(Package.is_active == True)).all()
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    last_patient_id = request.query_params.get("patient_id")
    return templates.TemplateResponse("patient_registration.html", {
        "request": request, "provinces": provinces, "partners": partners,
        "tests": tests, "packages": packages,
        "message_success": success, "message_error": error,
        "last_patient_id": last_patient_id
    })

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
    session: Session = Depends(get_session)
):
    try:
        current_user = get_current_user(request, session)
        items = json.loads(selected_items)
        
        total_price = sum(float(item.get('price', 0)) for item in items)
        
        final_total = total_price
        discount_amt = float(discount_amount) if discount_amount else 0.0
        if discount_percentage:
            final_total = total_price * (1 - discount_percentage / 100)
            discount_amt = total_price - final_total
        elif discount_amount:
            final_total = total_price - float(discount_amount)
        
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
            remaining_amount=remaining
        )
        session.add(new_visit)
        session.commit()
        session.refresh(new_visit)
        
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
        # ---------------------------------------------------------
        
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
    search = request.query_params.get("search", "")
    province_filter = request.query_params.get("province", "")
    gender_filter = request.query_params.get("gender", "")
    
    query = select(Patient).where(Patient.is_active == True)
    
    if search:
        query = query.where(
            (Patient.full_name.ilike(f"%{search}%")) |
            (Patient.patient_id.ilike(f"%{search}%")) |
            (Patient.phone_number.ilike(f"%{search}%"))
        )
    
    if province_filter:
        query = query.where(Patient.province_id == int(province_filter))
    
    if gender_filter:
        query = query.where(Patient.gender == gender_filter)
    
    patients = session.exec(query.order_by(Patient.created_at.desc())).all()
    provinces = session.exec(select(Province).where(Province.is_active == True)).all()
    
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    
    return templates.TemplateResponse("patients.html", {
        "request": request,
        "patients": patients,
        "provinces": provinces,
        "search": search,
        "province_filter": province_filter,
        "gender_filter": gender_filter,
        "message_success": success,
        "message_error": error
    })

@router.get("/patients/edit/{patient_id}", response_class=HTMLResponse)
def patient_edit_page(request: Request, patient_id: str, session: Session = Depends(get_session)):
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
                    "package_name": order.package_name
                })
        
        orders_json_str = json.dumps(orders_json if orders_json else [])
        
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
# PATIENT UPDATE
# ===========================
@router.post("/patients/update/{patient_id}")
async def update_patient(
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
    discount_percentage: Optional[float] = Form(None),
    discount_amount: Optional[float] = Form(None),
    discount_note: Optional[str] = Form(None),
    received_amount: Optional[float] = Form(None),
    session: Session = Depends(get_session)
):
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
        patient.edited_at = datetime.utcnow()

        session.add(patient)
        session.commit()

        # Update orders: remove old orders for latest visit, recreate from selected_items
        items = json.loads(selected_items) if selected_items else []

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

        # Delete old orders for this visit
        old_orders = session.exec(select(Order).where(Order.visit_id == latest_visit.id)).all()
        for old_order in old_orders:
            session.delete(old_order)
        session.commit()

        # Calculate totals
        total_price = sum(float(item.get('price', 0)) for item in items)
        discount_amt = float(discount_amount) if discount_amount else 0.0
        final_total = total_price

        if discount_percentage:
            final_total = total_price * (1 - discount_percentage / 100)
            discount_amt = total_price - final_total
        elif discount_amount:
            final_total = total_price - float(discount_amount)

        received = float(received_amount) if received_amount else 0.0
        remaining = max(0, final_total - received)

        # Update visit payment info
        disc_pct = float(discount_percentage) if discount_percentage else 0.0
        latest_visit.received_amount = received
        latest_visit.discount_amount = round(discount_amt, 2)
        latest_visit.discount_percentage = disc_pct
        latest_visit.discount_note = discount_note
        latest_visit.remaining_amount = remaining
        latest_visit.edited_by = current_user.id if current_user else None
        latest_visit.edited_at = datetime.utcnow()
        session.add(latest_visit)

        # Recreate orders with price snapshots
        discount_ratio = discount_amt / total_price if total_price > 0 else 0

        for item in items:
            if item.get('type') == 'test':
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
    try:
        current_user = get_current_user(request, session)
        patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()

        if patient:
            old_values = model_to_dict(patient)
            patient.is_active = False
            patient.deleted_by = current_user.id if current_user else None
            patient.deleted_at = datetime.utcnow()
            patient.deleted_reason = deleted_reason
            session.add(patient)
            session.commit()

            # ---------------------------------------------------------
            # ✅ FIXED: LOG AND COMMIT DELETE
            # ---------------------------------------------------------
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
    search = request.query_params.get("search", "")
    
    query = select(Patient).where(Patient.is_active == False)
    
    if search:
        query = query.where(
            (Patient.full_name.ilike(f"%{search}%")) |
            (Patient.patient_id.ilike(f"%{search}%")) |
            (Patient.phone_number.ilike(f"%{search}%"))
        )
    
    patients = session.exec(query.order_by(Patient.deleted_at.desc())).all()
    
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    
    return templates.TemplateResponse("deleted_patients.html", {
        "request": request,
        "patients": patients,
        "search": search,
        "message_success": success,
        "message_error": error
    })

@router.get("/patients/view-deleted/{patient_id}", response_class=HTMLResponse)
def view_deleted_patient(request: Request, patient_id: str, session: Session = Depends(get_session)):
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
    try:
        current_user = get_current_user(request, session)
        patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()
        
        if patient:
            old_values = model_to_dict(patient)
            patient.is_active = True
            patient.deleted_by = None
            patient.deleted_at = None
            patient.edited_by = current_user.id if current_user else None
            patient.edited_at = datetime.utcnow()
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