# routes/results.py
# Result Entry routes — page render, data API, and save API.

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload
from datetime import datetime
import json

from database import get_session
from models import (
    Patient, PatientVisit, Order, TestDefinition, TestParameter,
    TestDevice, TestRange, TestResultType, Result, ResultDetail,
    Parameter, Device, SampleType, Formula
)
from routes.helpers import templates, get_current_user

router = APIRouter()


# ===========================
# RESULT ENTRY PATIENT LIST
# ===========================
@router.get("/result-entry", response_class=HTMLResponse)
def result_entry_patients_page(request: Request, session: Session = Depends(get_session)):
    today_str = datetime.today().strftime("%Y-%m-%d")
    start_date = request.query_params.get("start_date", today_str)
    end_date = request.query_params.get("end_date", today_str)
    name = request.query_params.get("name", "")
    patient_id_q = request.query_params.get("patient_id", "")
    test_q = request.query_params.get("test", "")
    status_q = request.query_params.get("status", "all")
    
    query = select(Patient).where(Patient.is_active == True)
    
    # We join conditionally if we need to filter by visit or orders
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
            
    if needs_visit_join or not (test_q or status_q != "all"):
        query = query.distinct()
    
    # Base query for patients
    patients_result = session.exec(query.order_by(Patient.created_at.desc())).all()
    
    # Process each patient to attach latest visit and test icons
    patient_data = []
    for patient in patients_result:
        # Get latest visit matching the date criteria if applicable
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
                # Determine color based on order status
                status_color = "red"
                if order.status == "resulted":
                    status_color = "blue"
                elif order.status == "authorized":
                    status_color = "green"
                    
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
    
    return templates.TemplateResponse("result_entry_patients.html", {
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

# ===========================
# RESULT ENTRY PAGE
# ===========================
@router.get("/result-entry/{patient_id}", response_class=HTMLResponse)
def result_entry_page(patient_id: str, request: Request, session: Session = Depends(get_session)):
    current_user = get_current_user(request, session)
    patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()
    if not patient:
        return RedirectResponse(url="/patients?error=Patient not found", status_code=303)

    # Get latest visit
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

    return templates.TemplateResponse("result_entry.html", {
        "request": request,
        "patient": patient,
        "visit": visit,
        "visit_user_name": visit_user_name,
    })


# ===========================
# RESULT ENTRY DATA API (JSON)
# ===========================
@router.get("/api/result-entry-data/{patient_id}")
def result_entry_data(patient_id: str, session: Session = Depends(get_session)):
    try:
        patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()
        if not patient:
            return JSONResponse({"error": "Patient not found"}, status_code=404)

        # Get latest visit
        visit = session.exec(
            select(PatientVisit)
            .where(PatientVisit.patient_id == patient.id)
            .order_by(PatientVisit.id.desc())
        ).first()
        if not visit:
            return JSONResponse({"error": "No visit found"}, status_code=404)

        # Get all orders for this visit with eager loading
        orders = session.exec(
            select(Order)
            .options(
                selectinload(Order.test).selectinload(TestDefinition.test_parameters).selectinload(TestParameter.parameter),
                selectinload(Order.test).selectinload(TestDefinition.test_devices).selectinload(TestDevice.device),
                selectinload(Order.result).selectinload(Result.details),
            )
            .where(Order.visit_id == visit.id)
            .order_by(Order.id)
        ).all()

        # Load all ranges and result types in bulk
        test_ids = list(set(o.test_id for o in orders))

        all_ranges = session.exec(
            select(TestRange).where(TestRange.test_id.in_(test_ids), TestRange.is_active == True)
        ).all()

        all_result_types = session.exec(
            select(TestResultType).where(TestResultType.test_id.in_(test_ids), TestResultType.is_active == True)
        ).all()

        # Build range lookup: (test_id, param_id, device_id) -> range data
        ranges_map = {}
        for r in all_ranges:
            key = (r.test_id, r.parameter_id, r.device_id)
            if key not in ranges_map:
                ranges_map[key] = []
            ranges_map[key].append({
                "id": r.id,
                "unit": r.unit or "",
                "gender_type": r.gender_type,
                "age_from": r.age_from,
                "age_to": r.age_to,
                "age_unit": r.age_unit,
                "range_type": r.range_type,
                "normal_from": r.normal_from,
                "normal_to": r.normal_to,
                "low_from": r.low_from,
                "low_to": r.low_to,
                "high_from": r.high_from,
                "high_to": r.high_to,
                "vlow_from": r.vlow_from,
                "vlow_to": r.vlow_to,
                "vhigh_from": r.vhigh_from,
                "vhigh_to": r.vhigh_to,
                "panic_less_than": r.panic_less_than,
                "panic_more_than": r.panic_more_than,
                "text_range": r.text_range,
            })

        # Build result type lookup: (test_id, param_id) -> result_type info
        result_type_map = {}
        for rt in all_result_types:
            key = (rt.test_id, rt.parameter_id)
            result_type_map[key] = {
                "result_type": rt.result_type,
                "selection_options": rt.selection_options,
            }
            
        # Fetch active Formulas for these tests
        all_formulas = session.exec(
            select(Formula).where(Formula.main_test_id.in_(test_ids), Formula.is_active == True)
        ).all()
        
        # Build formula lookup: (test_id, param_id) -> formula expression
        formulas_map = {}
        for f in all_formulas:
            key = (f.main_test_id, f.main_parameter_id)
            formulas_map[key] = f.formula_expression
            key = (rt.test_id, rt.parameter_id)
            result_type_map[key] = {
                "result_type": rt.result_type,
                "selection_options": rt.selection_options,
            }

        # Build existing result details lookup: result_id -> {param_id: detail}
        def build_details_map(result):
            if not result or not result.details:
                return {}
            return {d.parameter_id: {
                "id": d.id,
                "result_value": d.result_value,
                "rerun_result": d.rerun_result,
                "flag": d.flag,
                "device_id": d.device_id,
                "remark": d.remark,
            } for d in result.details}

        if not visit:
            return []

        grid_rows = []
        
        # Exclude no_sample orders
        active_orders = [o for o in orders if o.status != "no_sample"]
        
        for order in active_orders:
            test = order.test
            if not test:
                continue

            # Get devices linked to this test
            devices = []
            primary_device_id = None
            for td in (test.test_devices or []):
                if td.device:
                    devices.append({"id": td.device.id, "name": td.device.device_name})
                    if primary_device_id is None:
                        primary_device_id = td.device.id

            # Get parameters for this test
            params = []
            for tp in (test.test_parameters or []):
                if tp.parameter:
                    params.append({
                        "id": tp.parameter.id,
                        "name": tp.parameter.parameter_name,
                        "short_name": tp.parameter.parameter_short_name,
                        "is_header": tp.parameter.is_header,
                    })

            existing_result = order.result
            details_map = build_details_map(existing_result)

            has_params = len(params) > 0

            def find_range(test_id, param_id, device_id):
                """Find best matching range for patient gender/age."""
                candidates = []
                # Try exact match first (test_id, param_id, device_id)
                for key in [(test_id, param_id, device_id), (test_id, param_id, None), (test_id, None, device_id), (test_id, None, None)]:
                    if key in ranges_map:
                        candidates.extend(ranges_map[key])
                
                if not candidates:
                    return None

                # Filter by gender and age
                best = None
                for c in candidates:
                    gender_ok = c["gender_type"] == "both" or c["gender_type"] == patient.gender
                    age_val = patient.age or 0
                    age_ok = c["age_from"] <= age_val <= c["age_to"]
                    if gender_ok and age_ok:
                        best = c
                        break
                return best if best else candidates[0]

            def get_result_type(test_id, param_id):
                for key in [(test_id, param_id), (test_id, None)]:
                    if key in result_type_map:
                        return result_type_map[key]
                return {"result_type": "number", "selection_options": None}

            if has_params:
                # Parent row (read-only, no input)
                parent_dev_id = (existing_result.device_id if existing_result else None) or primary_device_id
                grid_rows.append({
                    "type": "parent",
                    "order_id": order.id,
                    "order_number": order.order_number,
                    "test_id": test.id,
                    "test_name": test.test_name,
                    "devices": devices,
                    "selected_device_id": parent_dev_id,
                    "result_id": existing_result.id if existing_result else None,
                    "authorized": existing_result.authorized if existing_result else False,
                    "double_authorized": existing_result.double_authorized if existing_result else False,
                    "unauth_reason": existing_result.unauth_reason if existing_result else "",
                    "status": order.status,
                    "note": existing_result.note if existing_result else "",
                })
                # Child rows (one per parameter)
                for p in params:
                    detail = details_map.get(p["id"], {})
                    dev_id = parent_dev_id
                    rng = find_range(test.id, p["id"], dev_id)
                    rt = get_result_type(test.id, p["id"])
                    grid_rows.append({
                        "type": "child",
                        "order_id": order.id,
                        "test_id": test.id,
                        "test_name": test.test_name,
                        "parameter_id": p["id"],
                        "parameter_name": p["name"],
                        "parameter_short_name": p["short_name"],
                        "is_header": p["is_header"],
                        "devices": devices,
                        "selected_device_id": dev_id,
                        "range": rng,
                        "result_type": rt["result_type"],
                        "selection_options": rt["selection_options"],
                        "formula_expression": formulas_map.get((test.id, p["id"]), ""),
                        "result_value": detail.get("result_value", ""),
                        "rerun_result": detail.get("rerun_result", ""),
                        "flag": detail.get("flag", ""),
                        "remark": detail.get("remark", ""),
                        "detail_id": detail.get("id"),
                        "authorized": existing_result.authorized if existing_result else False,
                        "double_authorized": existing_result.double_authorized if existing_result else False,
                        "unauth_reason": existing_result.unauth_reason if existing_result else "",
                    })
            else:
                # Standalone test (no sub-parameters)
                dev_id = (existing_result.device_id if existing_result else None) or primary_device_id
                rng = find_range(test.id, None, dev_id)
                rt = get_result_type(test.id, None)
                grid_rows.append({
                    "type": "standalone",
                    "order_id": order.id,
                    "order_number": order.order_number,
                    "test_id": test.id,
                    "test_name": test.test_name,
                    "devices": devices,
                    "selected_device_id": dev_id,
                    "range": rng,
                    "result_type": rt["result_type"],
                    "selection_options": rt["selection_options"],
                    "formula_expression": formulas_map.get((test.id, None), ""),
                    "result_id": existing_result.id if existing_result else None,
                    "result_value": existing_result.result_value if existing_result else "",
                    "rerun_result": existing_result.rerun_result if existing_result else "",
                    "flag": existing_result.flag if existing_result else "",
                    "note": existing_result.note if existing_result else "",
                    "authorized": existing_result.authorized if existing_result else False,
                    "double_authorized": existing_result.double_authorized if existing_result else False,
                    "unauth_reason": existing_result.unauth_reason if existing_result else "",
                    "status": order.status,
                })

        # Also provide the full ranges_map as flat list for client-side device-change lookups
        all_ranges_flat = []
        for r in all_ranges:
            all_ranges_flat.append({
                "test_id": r.test_id,
                "parameter_id": r.parameter_id,
                "device_id": r.device_id,
                "unit": r.unit or "",
                "gender_type": r.gender_type,
                "age_from": r.age_from,
                "age_to": r.age_to,
                "age_unit": r.age_unit,
                "range_type": r.range_type,
                "normal_from": r.normal_from,
                "normal_to": r.normal_to,
                "low_from": r.low_from,
                "low_to": r.low_to,
                "high_from": r.high_from,
                "high_to": r.high_to,
                "vlow_from": r.vlow_from,
                "vlow_to": r.vlow_to,
                "vhigh_from": r.vhigh_from,
                "vhigh_to": r.vhigh_to,
                "panic_less_than": r.panic_less_than,
                "panic_more_than": r.panic_more_than,
                "text_range": r.text_range,
            })

        return {
            "success": True,
            "patient": {
                "id": patient.id,
                "patient_id": patient.patient_id,
                "full_name": patient.full_name,
                "gender": patient.gender,
                "age": patient.age,
                "age_unit": patient.age_unit,
            },
            "visit_id": visit.visit_id if visit else None,
            "grid_rows": grid_rows,
            "all_ranges": all_ranges_flat,
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


# ===========================
# SAVE RESULTS API
# ===========================
@router.post("/api/result-entry/save")
async def save_results(request: Request, session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        body = await request.json()
        rows = body.get("rows", [])
        now = datetime.utcnow()
        user_id = current_user.id if current_user else 1

        for row in rows:
            order_id = row.get("order_id")
            if not order_id:
                continue

            order = session.get(Order, order_id)
            if not order:
                continue

            row_type = row.get("type")
            authorized = row.get("authorized", False)

            if row_type == "standalone":
                # Upsert Result for standalone test
                result = session.exec(
                    select(Result).where(Result.order_id == order_id)
                ).first()
                if not result:
                    result = Result(
                        order_id=order_id,
                        entered_by=user_id,
                        entered_at=now,
                    )
                    session.add(result)

                result.result_value = row.get("result_value", "")
                result.rerun_result = row.get("rerun_result", "")
                result.flag = row.get("flag", "")
                result.note = row.get("remark", "")
                result.device_id = row.get("device_id")
                result.authorized = authorized
                if authorized:
                    result.authorized_by = user_id
                    result.authorized_at = now
                else:
                    result.authorized_by = None
                    result.authorized_at = None

                # Update order status
                if result.result_value:
                    order.status = "authorized" if authorized else "resulted"
                else:
                    order.status = "ordered"

                session.add(result)
                session.add(order)

            elif row_type == "parent":
                # Upsert Result for parent (container for details)
                result = session.exec(
                    select(Result).where(Result.order_id == order_id)
                ).first()
                if not result:
                    result = Result(
                        order_id=order_id,
                        result_value="",
                        rerun_result="",
                        flag="",
                        note="",
                        entered_by=user_id,
                        entered_at=now,
                    )
                    session.add(result)
                    session.flush()  # Need result.id for details

                result.authorized = authorized
                if authorized:
                    result.authorized_by = user_id
                    result.authorized_at = now
                else:
                    result.authorized_by = None
                    result.authorized_at = None

                if "device_id" in row:
                    result.device_id = row.get("device_id")
                
                if "note" in row:
                    result.note = row.get("note")

                # Process child parameter details
                children = row.get("children", [])
                has_any_value = False
                for child in children:
                    param_id = child.get("parameter_id")
                    if not param_id:
                        continue

                    detail = session.exec(
                        select(ResultDetail).where(
                            ResultDetail.result_id == result.id,
                            ResultDetail.parameter_id == param_id
                        )
                    ).first()
                    if not detail:
                        detail = ResultDetail(
                            result_id=result.id,
                            parameter_id=param_id,
                        )
                        session.add(detail)

                    detail.result_value = child.get("result_value", "")
                    detail.rerun_result = child.get("rerun_result", "")
                    detail.flag = child.get("flag", "")
                    detail.device_id = child.get("device_id")
                    detail.remark = child.get("remark", "")
                    session.add(detail)

                    if detail.result_value:
                        has_any_value = True

                if has_any_value:
                    order.status = "authorized" if authorized else "resulted"
                else:
                    order.status = "ordered"

                session.add(result)
                session.add(order)

        session.commit()
        return {"success": True, "message": "Results saved successfully!"}

    except Exception as e:
        session.rollback()
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


# ===========================
# GET RANGE FOR DEVICE CHANGE (Real-time)
# ===========================
@router.get("/api/range-for-device")
def get_range_for_device(
    test_id: int, device_id: int,
    parameter_id: int = None,
    gender: str = "both", age: int = 0,
    session: Session = Depends(get_session)
):
    """Return the best matching range when user changes device."""
    query = select(TestRange).where(
        TestRange.test_id == test_id,
        TestRange.is_active == True,
    )
    if parameter_id:
        query = query.where(TestRange.parameter_id == parameter_id)
    
    # Try device-specific first, then fallback
    ranges = session.exec(query.where(TestRange.device_id == device_id)).all()
    if not ranges:
        ranges = session.exec(query.where(TestRange.device_id == None)).all()
    if not ranges:
        ranges = session.exec(query).all()

    best = None
    for r in ranges:
        gender_ok = r.gender_type == "both" or r.gender_type == gender
        age_ok = r.age_from <= age <= r.age_to
        if gender_ok and age_ok:
            best = r
            break
    if not best and ranges:
        best = ranges[0]

    if best:
        return {
            "unit": best.unit or "",
            "range_type": best.range_type,
            "normal_from": best.normal_from,
            "normal_to": best.normal_to,
            "low_from": best.low_from,
            "low_to": best.low_to,
            "high_from": best.high_from,
            "high_to": best.high_to,
            "text_range": best.text_range,
        }
    return {"unit": "", "range_type": "number", "normal_from": None, "normal_to": None}

# ===========================
# NO SAMPLE ACTIONS & PAGE
# ===========================
@router.post("/api/result-entry/no-sample/{order_id}")
async def mark_no_sample(order_id: int, request: Request, session: Session = Depends(get_session)):
    current_user = get_current_user(request, session)
    if not current_user:
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)
        
    try:
        data = await request.json()
        reason = data.get("reason", "")
        
        order = session.get(Order, order_id)
        if not order:
            return JSONResponse({"success": False, "message": "Order not found"}, status_code=404)
            
        order.status = "no_sample"
        order.no_sample_reason = reason
        session.add(order)
        session.commit()
        return {"success": True, "message": "Test moved to No Sample"}
    except Exception as e:
        session.rollback()
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)

@router.post("/api/no-sample/receive/{order_id}")
def receive_no_sample(order_id: int, request: Request, session: Session = Depends(get_session)):
    current_user = get_current_user(request, session)
    if not current_user:
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)
        
    try:
        order = session.get(Order, order_id)
        if not order:
            return JSONResponse({"success": False, "message": "Order not found"}, status_code=404)
            
        order.status = "ordered"
        session.add(order)
        session.commit()
        return {"success": True, "message": "Sample Received successfully. Test returned to pending."}
    except Exception as e:
        session.rollback()
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)

@router.get("/no-sample", response_class=HTMLResponse)
def no_sample_page(request: Request, session: Session = Depends(get_session)):
    query = select(Order).options(selectinload(Order.patient), selectinload(Order.test), selectinload(Order.visit)).where(Order.status == "no_sample").order_by(Order.order_date.desc())
    no_sample_orders = session.exec(query).all()
    
    return templates.TemplateResponse("no_sample.html", {
        "request": request,
        "orders": no_sample_orders
    })
