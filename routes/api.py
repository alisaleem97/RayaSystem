# routes/api.py
# JSON API endpoints — patient data, orders, barcode, lab info, general listings.
# Includes N+1 fixes with selectinload.

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload
from database import get_session
from models import (
    Patient, PatientVisit, Order, TestDefinition, SampleType,
    Region, PackageTest, Parameter, Department, Device,
    ReportNote, Formula, LabInfo, AuditLog, ActivityLog,
)
from routes.helpers import generate_barcode_base64, get_current_user
from fastapi.responses import JSONResponse

router = APIRouter()

# ===========================
# REGION API
# ===========================
@router.get("/api/regions")
def get_regions_by_province(province_id: int, session: Session = Depends(get_session)):
    regions = session.exec(select(Region).where(Region.province_id == province_id)).all()
    return [{"id": r.id, "region_name": r.region_name} for r in regions]

@router.get("/api/package-tests/{package_id}")
def get_package_tests(package_id: int, session: Session = Depends(get_session)):
    package_tests = session.exec(select(PackageTest).where(PackageTest.package_id == package_id)).all()
    return {"test_ids": [pt.test_id for pt in package_tests]}

@router.get("/api/generate-patient-id")
def generate_patient_id_api(session: Session = Depends(get_session)):
    try:
        labId = 1
        baseNumber = 100000
        last_patient = session.exec(select(Patient).order_by(Patient.id.desc()).limit(1)).first()
        if last_patient and last_patient.patient_id:
            try:
                last_number = int(last_patient.patient_id[1:])
                next_number = last_number + 1
            except Exception:
                next_number = baseNumber
        else:
            next_number = baseNumber
        patient_id = str(labId) + str(next_number).zfill(6)
        return {"patient_id": patient_id}
    except Exception as e:
        return {"error": str(e)}

# ===========================
# PATIENT ORDERS API (WITH PRICE SNAPSHOT + N+1 FIX)
# ===========================
@router.get("/api/patient-orders/{patient_id}")
def get_patient_orders_api(patient_id: str, session: Session = Depends(get_session)):
    try:
        patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()
        if not patient:
            return {"success": False, "error": "Patient not found"}
        
        # ✅ N+1 FIX: eager-load test relationship
        orders = session.exec(
            select(Order)
            .options(selectinload(Order.test))
            .where(Order.patient_id == patient.id)
        ).all()
        
        orders_data = []
        for order in orders:
            test = order.test
            orders_data.append({
                "order_id": order.id,
                "order_number": order.order_number,
                "test_id": order.test_id,
                "test_name": test.test_name if test else 'Unknown',
                "package_name": order.package_name or None,
                "unit_price": order.unit_price or (test.price if test else 0),
                "discount_amount": order.discount_amount or 0,
                "final_price": order.final_price or (order.unit_price or 0),
                "status": order.status,
                "order_date": order.order_date.isoformat() if order.order_date else None
            })
        
        return {"success": True, "orders": orders_data}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ===========================
# LAB INFO API
# ===========================
@router.get("/api/lab-info")
def get_lab_info_api(session: Session = Depends(get_session)):
    lab_info = session.exec(select(LabInfo).limit(1)).first()
    if lab_info:
        return {
            "success": True,
            "lab_info": {
                "lab_name": lab_info.lab_name or "NexLab Medical Center",
                "lab_title": lab_info.lab_title or "Medical Laboratory",
                "lab_address": lab_info.lab_address or "",
                "lab_phone_1": lab_info.lab_phone_1 or "",
                "lab_phone_2": lab_info.lab_phone_2 or "",
                "lab_email": lab_info.lab_email or "",
                "lab_website": lab_info.lab_website or "",
                "tax_percentage": lab_info.tax_percentage if lab_info.tax_percentage is not None else 0.0,
                "lab_currency": lab_info.lab_currency or "$",
                "first_doctor_name": lab_info.first_doctor_name or "",
                "second_doctor_name": lab_info.second_doctor_name or "",
                "lab_note_1": lab_info.lab_note_1 or "",
                "lab_note_2": lab_info.lab_note_2 or "",
                "lab_logo": lab_info.lab_logo or "",
                "lab_qr_1": lab_info.lab_qr_1 or "",
                "lab_qr_2": lab_info.lab_qr_2 or "",
                "lab_stamp_1": lab_info.lab_stamp_1 or "",
                "lab_stamp_2": lab_info.lab_stamp_2 or "",
                "lab_signature_1": lab_info.lab_signature_1 or "",
                "lab_signature_2": lab_info.lab_signature_2 or "",
            }
        }
    return {
        "success": True,
        "lab_info": {
            "lab_name": "NexLab Medical Center", "lab_title": "Medical Laboratory",
            "lab_address": "", "lab_phone_1": "", "lab_phone_2": "",
            "lab_email": "", "lab_website": "", "lab_currency": "$", "tax_percentage": 0.0,
            "first_doctor_name": "", "second_doctor_name": "",
            "lab_note_1": "", "lab_note_2": "",
            "lab_logo": "", "lab_qr_1": "", "lab_qr_2": "",
            "lab_stamp_1": "", "lab_stamp_2": "",
            "lab_signature_1": "", "lab_signature_2": "",
        }
    }

# ===========================
# PATIENT API (WITH ACCOUNTING DATA + N+1 FIX)
# ===========================
@router.get("/api/patient/{patient_id}")
def get_patient_api(patient_id: str, session: Session = Depends(get_session)):
    try:
        patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()
        if not patient:
            return {"error": "Patient not found"}
        
        # ✅ N+1 FIX: eager-load test + sample_type relationships
        orders = session.exec(
            select(Order)
            .options(
                selectinload(Order.test).selectinload(TestDefinition.sample_type)
            )
            .where(Order.patient_id == patient.id)
        ).all()
        
        test_names = [order.test.test_name if order.test else 'Unknown' for order in orders]
        test_short_names = [order.test.test_short_name if order.test and order.test.test_short_name else (order.test.test_name if order.test else 'Unknown') for order in orders]
        
        tests_by_sample_type = {}
        for order in orders:
            if order.test:
                sample_type_name = order.test.sample_type.sample_name if order.test.sample_type else "Unknown"
                if sample_type_name not in tests_by_sample_type:
                    tests_by_sample_type[sample_type_name] = []
                tests_by_sample_type[sample_type_name].append(
                    order.test.test_short_name if order.test.test_short_name else order.test.test_name
                )
        
        visits = session.exec(select(PatientVisit).where(PatientVisit.patient_id == patient.id)).all()
        visit_id = visits[0].visit_id if visits else patient.patient_id + '000'
        
        received_amount = visits[0].received_amount if visits else 0.0
        discount_amount = visits[0].discount_amount if visits else 0.0
        tax_amount = visits[0].tax_amount if visits and visits[0].tax_amount else 0.0
        remaining_amount = visits[0].remaining_amount if visits else 0.0
        
        total_amount = sum([float(order.final_price) if order.final_price else 0 for order in orders])
        
        total_after_tax = total_amount - discount_amount + tax_amount
        
        return {
            "patient_id": patient.patient_id,
            "full_name": patient.full_name,
            "gender": patient.gender,
            "age": patient.age,
            "age_unit": patient.age_unit,
            "phone_key": patient.phone_key,
            "phone_number": patient.phone_number,
            "tests": test_names,
            "tests_by_sample_type": tests_by_sample_type,
            "visit_id": visit_id,
            "visit_date": visits[0].visit_date.isoformat() if visits and visits[0].visit_date else None,
            "total_amount": round(total_amount, 2),
            "discount_amount": round(discount_amount, 2),
            "tax_amount": round(tax_amount, 2),
            "total_after_tax": round(total_after_tax, 2),
            "paid_amount": round(received_amount, 2),
            "remain_amount": round(remaining_amount, 2)
        }
    except Exception as e:
        print(f"❌ Error in get_patient_api: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

# ===========================
# BARCODE API
# ===========================
@router.get("/api/barcode/{patient_id}")
def get_barcode_api(patient_id: str, session: Session = Depends(get_session)):
    barcode_data = generate_barcode_base64(patient_id)
    return {"barcode_data": barcode_data}

# ===========================
# CHECK DUPLICATE PATIENT BY PHONE
# ===========================
@router.get("/api/check-patient-phone")
def check_patient_phone(phone_key: str, phone_number: str, session: Session = Depends(get_session)):
    try:
        patient = session.exec(select(Patient).where(
            Patient.phone_key == phone_key,
            Patient.phone_number == phone_number,
            Patient.is_active == True
        )).first()
        
        if patient:
            return {
                "exists": True,
                "patient": {
                    "id": patient.id,
                    "patient_id": patient.patient_id,
                    "full_name": patient.full_name,
                    "phone_key": patient.phone_key,
                    "phone_number": patient.phone_number,
                    "gender": patient.gender,
                    "age": patient.age,
                    "province_id": patient.province_id,
                    "region_id": patient.region_id,
                    "email": patient.email,
                    "note": patient.note
                }
            }
        return {"exists": False}
    except Exception as e:
        return {"exists": False, "error": str(e)}

# ===========================
# GENERAL LIST ENDPOINTS (Login Required)
# ===========================
def _require_login(request: Request, session: Session):
    """Quick login check for data APIs. Returns user or None."""
    user = get_current_user(request, session)
    if not user:
        return None
    return user

@router.get("/api/patients")
def list_patients_api(request: Request, session: Session = Depends(get_session)):
    if not _require_login(request, session):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return session.exec(select(Patient)).all()

@router.get("/api/parameters")
def list_parameters_api(request: Request, session: Session = Depends(get_session)):
    if not _require_login(request, session):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return session.exec(select(Parameter)).all()

@router.get("/api/departments")
def list_departments_api(request: Request, session: Session = Depends(get_session)):
    if not _require_login(request, session):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return session.exec(select(Department)).all()

@router.get("/api/devices")
def list_devices_api(request: Request, session: Session = Depends(get_session)):
    if not _require_login(request, session):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return session.exec(select(Device)).all()

@router.get("/api/sample-types")
def list_sample_types_api(request: Request, session: Session = Depends(get_session)):
    if not _require_login(request, session):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return session.exec(select(SampleType)).all()

@router.get("/api/report-notes")
def list_report_notes_api(request: Request, session: Session = Depends(get_session)):
    if not _require_login(request, session):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return session.exec(select(ReportNote)).all()

@router.get("/api/tests")
def list_tests_api(request: Request, session: Session = Depends(get_session)):
    if not _require_login(request, session):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return session.exec(select(TestDefinition)).all()

@router.get("/api/formulas")
def list_formulas_api(request: Request, session: Session = Depends(get_session)):
    if not _require_login(request, session):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return session.exec(select(Formula)).all()

@router.get("/api/audit-logs")
def list_audit_logs_api(request: Request, session: Session = Depends(get_session)):
    if not _require_login(request, session):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return session.exec(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(500)).all()

# ===========================
# AUDIT LOG CLEANUP (Admin Only)
# ===========================
@router.delete("/api/audit-logs/cleanup")
def cleanup_old_logs(request: Request, session: Session = Depends(get_session)):
    """
    Delete audit and activity logs older than 6 months.
    Admin-only endpoint to prevent unbounded table growth.
    Accepts optional ?months=N query param (default: 6).
    """
    from routes.helpers import require_permission
    if not require_permission(request, session, "settings"):
        return JSONResponse({"error": "Admin access required"}, status_code=403)
    
    try:
        months = int(request.query_params.get("months", 6))
    except (ValueError, TypeError):
        months = 6
    
    from datetime import datetime, timedelta
    cutoff_date = datetime.now() - timedelta(days=months * 30)
    
    # Count before deletion
    audit_count = len(session.exec(
        select(AuditLog).where(AuditLog.created_at < cutoff_date)
    ).all())
    activity_count = len(session.exec(
        select(ActivityLog).where(ActivityLog.created_at < cutoff_date)
    ).all())
    
    # Delete old records
    from sqlalchemy import delete
    session.exec(delete(AuditLog).where(AuditLog.created_at < cutoff_date))
    session.exec(delete(ActivityLog).where(ActivityLog.created_at < cutoff_date))
    session.commit()
    
    return {
        "success": True,
        "message": f"Cleaned up logs older than {months} months",
        "deleted": {
            "audit_logs": audit_count,
            "activity_logs": activity_count
        },
        "cutoff_date": cutoff_date.isoformat()
    }
