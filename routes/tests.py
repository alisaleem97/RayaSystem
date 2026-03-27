# routes/tests.py
# CRUD routes for: Test Definitions, Formulas, Test Ranges, Test Result Types, Packages.
# Includes N+1 fixes with selectinload.

from fastapi import APIRouter, Depends, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload
from datetime import datetime
from typing import Optional
from database import get_session
from models import (
    TestDefinition, TestDevice, TestParameter, Department, SampleType, ReportNote,
    Device, Parameter, Formula, FormulaItem, TestRange, TestResultType,
    Package, PackageTest,
)
from routes.helpers import templates, get_current_user, create_audit_log, model_to_dict

router = APIRouter()

# ===========================
# TEST DEFINITION ROUTES (N+1 FIX: selectinload)
# ===========================
@router.get("/tests", response_class=HTMLResponse)
def tests_page(request: Request, session: Session = Depends(get_session)):
    # ✅ N+1 FIX: eager-load test_devices and test_parameters in one query
    tests = session.exec(
        select(TestDefinition)
        .options(selectinload(TestDefinition.test_devices), selectinload(TestDefinition.test_parameters))
        .order_by(TestDefinition.id.asc())
    ).all()
    tests_json = []
    for test in tests:
        test_dict = model_to_dict(test)
        device_ids = [int(td.device_id) for td in test.test_devices]
        parameter_ids = [int(tp.parameter_id) for tp in test.test_parameters]
        test_dict['device_ids'] = device_ids
        test_dict['parameter_ids'] = parameter_ids
        tests_json.append(test_dict)
    departments = session.exec(select(Department).where(Department.is_active == True)).all()
    sample_types = session.exec(select(SampleType).where(SampleType.is_active == True)).all()
    report_notes = session.exec(select(ReportNote).where(ReportNote.is_active == True)).all()
    devices = session.exec(select(Device).where(Device.is_active == True)).all()
    parameters = session.exec(select(Parameter)).all()
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse("tests.html", {
        "request": request, "tests": tests, "tests_json": tests_json,
        "departments": departments, "sample_types": sample_types, "report_notes": report_notes,
        "devices": devices, "parameters": parameters,
        "message_success": success, "message_error": error
    })

@router.post("/tests/create")
def create_test(test_name: str = Form(...), test_short_name: str = Form(...),
                department_id: int = Form(...), sample_type_id: int = Form(...),
                report_note_id: Optional[int] = Form(None), price: float = Form(...),
                test_note: Optional[str] = Form(None), test_condition: Optional[str] = Form(None),
                is_available: str = Form(None), device_ids: Optional[str] = Form(""),
                parameter_ids: Optional[str] = Form(""), request: Request = None,
                session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        is_available_bool = True if is_available == "on" else False
        new_test = TestDefinition(
            test_name=test_name, test_short_name=test_short_name.upper(),
            department_id=department_id, sample_type_id=sample_type_id,
            report_note_id=report_note_id if report_note_id and report_note_id != "" else None,
            price=price, test_note=test_note, test_condition=test_condition,
            is_available=is_available_bool, created_by=current_user.id if current_user else None
        )
        session.add(new_test)
        session.commit()
        session.refresh(new_test)
        if device_ids and device_ids.strip():
            device_id_list = [int(d.strip()) for d in device_ids.split(',') if d.strip().isdigit()]
            for device_id in device_id_list:
                link = TestDevice(test_id=new_test.id, device_id=device_id)
                session.add(link)
        if parameter_ids and parameter_ids.strip():
            parameter_id_list = [int(p.strip()) for p in parameter_ids.split(',') if p.strip().isdigit()]
            for parameter_id in parameter_id_list:
                link = TestParameter(test_id=new_test.id, parameter_id=parameter_id)
                session.add(link)
        session.commit()
        create_audit_log(session, "testdefinition", new_test.id, "create", current_user, new_values=model_to_dict(new_test))
        return RedirectResponse(url="/tests?success=Test saved successfully!", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/tests?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/tests/update/{test_id}")
def update_test(test_id: int, test_name: str = Form(...), test_short_name: str = Form(...),
                department_id: int = Form(...), sample_type_id: int = Form(...),
                report_note_id: Optional[int] = Form(None), price: float = Form(...),
                test_note: Optional[str] = Form(None), test_condition: Optional[str] = Form(None),
                is_available: str = Form(None), device_ids: Optional[str] = Form(""),
                parameter_ids: Optional[str] = Form(""), request: Request = None,
                session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        test = session.get(TestDefinition, test_id)
        if test:
            old_values = model_to_dict(test)
            test.test_name = test_name
            test.test_short_name = test_short_name.upper()
            test.department_id = department_id
            test.sample_type_id = sample_type_id
            test.report_note_id = report_note_id if report_note_id and report_note_id != "" else None
            test.price = price
            test.test_note = test_note
            test.test_condition = test_condition
            test.is_available = True if is_available == "on" else False
            test.edited_by = current_user.id if current_user else None
            test.edited_at = datetime.utcnow()
            existing_device_links = session.exec(select(TestDevice).where(TestDevice.test_id == test_id)).all()
            for link in existing_device_links:
                session.delete(link)
            if device_ids and device_ids.strip():
                device_id_list = [int(d.strip()) for d in device_ids.split(',') if d.strip().isdigit()]
                for device_id in device_id_list:
                    link = TestDevice(test_id=test.id, device_id=device_id)
                    session.add(link)
            existing_parameter_links = session.exec(select(TestParameter).where(TestParameter.test_id == test_id)).all()
            for link in existing_parameter_links:
                session.delete(link)
            if parameter_ids and parameter_ids.strip():
                parameter_id_list = [int(p.strip()) for p in parameter_ids.split(',') if p.strip().isdigit()]
                for parameter_id in parameter_id_list:
                    link = TestParameter(test_id=test.id, parameter_id=parameter_id)
                    session.add(link)
            session.add(test)
            session.commit()
            session.refresh(test)
            create_audit_log(session, "testdefinition", test.id, "update", current_user, old_values=old_values, new_values=model_to_dict(test))
            return RedirectResponse(url="/tests?success=Test updated successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/tests?error=Test not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/tests?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/tests/delete/{test_id}")
def delete_test(test_id: int, request: Request, session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        test = session.get(TestDefinition, test_id)
        if test:
            old_values = model_to_dict(test)
            existing_device_links = session.exec(select(TestDevice).where(TestDevice.test_id == test_id)).all()
            for link in existing_device_links:
                session.delete(link)
            existing_parameter_links = session.exec(select(TestParameter).where(TestParameter.test_id == test_id)).all()
            for link in existing_parameter_links:
                session.delete(link)
            session.delete(test)
            session.commit()
            create_audit_log(session, "testdefinition", test.id, "delete", current_user, old_values=old_values)
            return RedirectResponse(url="/tests?success=Test deleted successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/tests?error=Test not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/tests?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

# ===========================
# FORMULA ROUTES
# ===========================
@router.get("/formulas", response_class=HTMLResponse)
def formulas_page(request: Request, session: Session = Depends(get_session)):
    formulas = session.exec(select(Formula).order_by(Formula.id.asc())).all()
    formulas_json = [model_to_dict(f) for f in formulas]
    tests = session.exec(select(TestDefinition).where(TestDefinition.is_available == True)).all()
    parameters = session.exec(select(Parameter)).all()
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse("formulas.html", {
        "request": request, "formulas": formulas, "formulas_json": formulas_json,
        "tests": tests, "parameters": parameters,
        "message_success": success, "message_error": error
    })

@router.post("/formulas/create")
def create_formula(formula_name: str = Form(...), main_test_id: int = Form(...),
                   main_parameter_id: Optional[int] = Form(None), gender_type: str = Form(...),
                   formula_expression: str = Form(""), formula_description: Optional[str] = Form(None),
                   request: Request = None, session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        new_formula = Formula(
            formula_name=formula_name, main_test_id=main_test_id,
            main_parameter_id=main_parameter_id if main_parameter_id else None,
            gender_type=gender_type, formula_expression=formula_expression,
            formula_description=formula_description, is_active=True,
            created_by=current_user.id if current_user else None
        )
        session.add(new_formula)
        session.commit()
        session.refresh(new_formula)
        create_audit_log(session, "formula", new_formula.id, "create", current_user, new_values=model_to_dict(new_formula))
        return RedirectResponse(url="/formulas?success=Formula saved successfully!", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/formulas?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/formulas/update/{formula_id}")
def update_formula(formula_id: int, formula_name: str = Form(...), main_test_id: int = Form(...),
                   main_parameter_id: Optional[int] = Form(None), gender_type: str = Form(...),
                   formula_expression: str = Form(""), formula_description: Optional[str] = Form(None),
                   request: Request = None, session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        formula = session.get(Formula, formula_id)
        if formula:
            old_values = model_to_dict(formula)
            formula.formula_name = formula_name
            formula.main_test_id = main_test_id
            formula.main_parameter_id = main_parameter_id if main_parameter_id else None
            formula.gender_type = gender_type
            formula.formula_expression = formula_expression
            formula.formula_description = formula_description
            formula.edited_by = current_user.id if current_user else None
            formula.edited_at = datetime.utcnow()
            session.add(formula)
            session.commit()
            session.refresh(formula)
            create_audit_log(session, "formula", formula.id, "update", current_user, old_values=old_values, new_values=model_to_dict(formula))
            return RedirectResponse(url="/formulas?success=Formula updated successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/formulas?error=Formula not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/formulas?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/formulas/delete/{formula_id}")
def delete_formula(formula_id: int, request: Request, session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        formula = session.get(Formula, formula_id)
        if formula:
            old_values = model_to_dict(formula)
            session.delete(formula)
            session.commit()
            create_audit_log(session, "formula", formula.id, "delete", current_user, old_values=old_values)
            return RedirectResponse(url="/formulas?success=Formula deleted successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/formulas?error=Formula not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/formulas?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

# ===========================
# TEST RANGE ROUTES
# ===========================
@router.get("/test-ranges", response_class=HTMLResponse)
def test_ranges_page(request: Request, session: Session = Depends(get_session)):
    ranges = session.exec(select(TestRange).order_by(TestRange.id.asc())).all()
    ranges_json = [model_to_dict(r) for r in ranges]
    tests = session.exec(select(TestDefinition).where(TestDefinition.is_available == True)).all()
    parameters = session.exec(select(Parameter)).all()
    devices = session.exec(select(Device).where(Device.is_active == True)).all()
    departments = session.exec(select(Department).where(Department.is_active == True)).all()
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse("test_ranges.html", {
        "request": request, "ranges": ranges, "ranges_json": ranges_json,
        "tests": tests, "parameters": parameters, "devices": devices, "departments": departments,
        "message_success": success, "message_error": error
    })

@router.post("/test-ranges/create")
def create_test_range(test_id: int = Form(...), parameter_id: Optional[int] = Form(None),
                      device_id: Optional[int] = Form(None), unit: str = Form(...),
                      gender_type: str = Form(...), age_from: int = Form(...),
                      age_to: int = Form(...), age_unit: str = Form(...),
                      fasting_required: str = Form("false"), range_type: str = Form(...),
                      normal_from: Optional[float] = Form(None), normal_to: Optional[float] = Form(None),
                      vlow_from: Optional[float] = Form(None), vlow_to: Optional[float] = Form(None),
                      low_from: Optional[float] = Form(None), low_to: Optional[float] = Form(None),
                      midlow_from: Optional[float] = Form(None), midlow_to: Optional[float] = Form(None),
                      midhigh_from: Optional[float] = Form(None), midhigh_to: Optional[float] = Form(None),
                      high_from: Optional[float] = Form(None), high_to: Optional[float] = Form(None),
                      vhigh_from: Optional[float] = Form(None), vhigh_to: Optional[float] = Form(None),
                      panic_less_than: Optional[float] = Form(None), panic_more_than: Optional[float] = Form(None),
                      text_range: Optional[str] = Form(None), request: Request = None,
                      session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        fasting_bool = fasting_required.lower() == "true"
        new_range = TestRange(
            test_id=test_id, parameter_id=parameter_id if parameter_id else None,
            device_id=device_id if device_id else None, unit=unit, gender_type=gender_type,
            age_from=age_from, age_to=age_to, age_unit=age_unit, fasting_required=fasting_bool,
            range_type=range_type, normal_from=normal_from, normal_to=normal_to,
            vlow_from=vlow_from, vlow_to=vlow_to, low_from=low_from, low_to=low_to,
            midlow_from=midlow_from, midlow_to=midlow_to, midhigh_from=midhigh_from,
            midhigh_to=midhigh_to, high_from=high_from, high_to=high_to,
            vhigh_from=vhigh_from, vhigh_to=vhigh_to, panic_less_than=panic_less_than,
            panic_more_than=panic_more_than, text_range=text_range if range_type == "text" else None,
            is_active=True, created_by=current_user.id if current_user else None
        )
        session.add(new_range)
        session.commit()
        session.refresh(new_range)
        create_audit_log(session, "testrange", new_range.id, "create", current_user, new_values=model_to_dict(new_range))
        return RedirectResponse(url="/test-ranges?success=Test range saved successfully!", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/test-ranges?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/test-ranges/update/{range_id}")
def update_test_range(range_id: int, test_id: int = Form(...), parameter_id: Optional[int] = Form(None),
                      device_id: Optional[int] = Form(None), unit: str = Form(...),
                      gender_type: str = Form(...), age_from: int = Form(...),
                      age_to: int = Form(...), age_unit: str = Form(...),
                      fasting_required: str = Form("false"), range_type: str = Form(...),
                      normal_from: Optional[float] = Form(None), normal_to: Optional[float] = Form(None),
                      vlow_from: Optional[float] = Form(None), vlow_to: Optional[float] = Form(None),
                      low_from: Optional[float] = Form(None), low_to: Optional[float] = Form(None),
                      midlow_from: Optional[float] = Form(None), midlow_to: Optional[float] = Form(None),
                      midhigh_from: Optional[float] = Form(None), midhigh_to: Optional[float] = Form(None),
                      high_from: Optional[float] = Form(None), high_to: Optional[float] = Form(None),
                      vhigh_from: Optional[float] = Form(None), vhigh_to: Optional[float] = Form(None),
                      panic_less_than: Optional[float] = Form(None), panic_more_than: Optional[float] = Form(None),
                      text_range: Optional[str] = Form(None), request: Request = None,
                      session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        range_item = session.get(TestRange, range_id)
        if range_item:
            old_values = model_to_dict(range_item)
            fasting_bool = fasting_required.lower() == "true"
            range_item.test_id = test_id
            range_item.parameter_id = parameter_id if parameter_id else None
            range_item.device_id = device_id if device_id else None
            range_item.unit = unit
            range_item.gender_type = gender_type
            range_item.age_from = age_from
            range_item.age_to = age_to
            range_item.age_unit = age_unit
            range_item.fasting_required = fasting_bool
            range_item.range_type = range_type
            range_item.normal_from = normal_from
            range_item.normal_to = normal_to
            range_item.vlow_from = vlow_from
            range_item.vlow_to = vlow_to
            range_item.low_from = low_from
            range_item.low_to = low_to
            range_item.midlow_from = midlow_from
            range_item.midlow_to = midlow_to
            range_item.midhigh_from = midhigh_from
            range_item.midhigh_to = midhigh_to
            range_item.high_from = high_from
            range_item.high_to = high_to
            range_item.vhigh_from = vhigh_from
            range_item.vhigh_to = vhigh_to
            range_item.panic_less_than = panic_less_than
            range_item.panic_more_than = panic_more_than
            range_item.text_range = text_range if range_type == "text" else None
            range_item.edited_by = current_user.id if current_user else None
            range_item.edited_at = datetime.utcnow()
            session.add(range_item)
            session.commit()
            session.refresh(range_item)
            create_audit_log(session, "testrange", range_item.id, "update", current_user, old_values=old_values, new_values=model_to_dict(range_item))
            return RedirectResponse(url="/test-ranges?success=Test range updated successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/test-ranges?error=Test range not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/test-ranges?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/test-ranges/delete/{range_id}")
def delete_test_range(range_id: int, request: Request, session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        range_item = session.get(TestRange, range_id)
        if range_item:
            old_values = model_to_dict(range_item)
            session.delete(range_item)
            session.commit()
            create_audit_log(session, "testrange", range_item.id, "delete", current_user, old_values=old_values)
            return RedirectResponse(url="/test-ranges?success=Test range deleted successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/test-ranges?error=Test range not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/test-ranges?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

# ===========================
# TEST RESULT TYPE ROUTES
# ===========================
@router.get("/test-result-types", response_class=HTMLResponse)
def test_result_types_page(request: Request, session: Session = Depends(get_session)):
    result_types = session.exec(select(TestResultType).order_by(TestResultType.id.asc())).all()
    result_types_json = [model_to_dict(rt) for rt in result_types]
    tests = session.exec(select(TestDefinition).where(TestDefinition.is_available == True)).all()
    parameters = session.exec(select(Parameter)).all()
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse("test_result_types.html", {
        "request": request, "result_types": result_types, "result_types_json": result_types_json,
        "tests": tests, "parameters": parameters,
        "message_success": success, "message_error": error
    })

@router.post("/test-result-types/create")
def create_test_result_type(test_id: int = Form(...), parameter_id: Optional[int] = Form(None),
                            result_type: str = Form(...), selection_options: Optional[str] = Form(None),
                            request: Request = None, session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        new_result_type = TestResultType(
            test_id=test_id, parameter_id=parameter_id if parameter_id else None,
            result_type=result_type, selection_options=selection_options if result_type == "selection" else None,
            is_active=True, created_by=current_user.id if current_user else None
        )
        session.add(new_result_type)
        session.commit()
        session.refresh(new_result_type)
        create_audit_log(session, "testresulttype", new_result_type.id, "create", current_user, new_values=model_to_dict(new_result_type))
        return RedirectResponse(url="/test-result-types?success=Result type saved successfully!", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/test-result-types?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/test-result-types/update/{result_type_id}")
def update_test_result_type(result_type_id: int, test_id: int = Form(...),
                            parameter_id: Optional[int] = Form(None), result_type: str = Form(...),
                            selection_options: Optional[str] = Form(None), request: Request = None,
                            session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        rt = session.get(TestResultType, result_type_id)
        if rt:
            old_values = model_to_dict(rt)
            rt.test_id = test_id
            rt.parameter_id = parameter_id if parameter_id else None
            rt.result_type = result_type
            rt.selection_options = selection_options if result_type == "selection" else None
            rt.edited_by = current_user.id if current_user else None
            rt.edited_at = datetime.utcnow()
            session.add(rt)
            session.commit()
            session.refresh(rt)
            create_audit_log(session, "testresulttype", rt.id, "update", current_user, old_values=old_values, new_values=model_to_dict(rt))
            return RedirectResponse(url="/test-result-types?success=Result type updated successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/test-result-types?error=Result type not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/test-result-types?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/test-result-types/delete/{result_type_id}")
def delete_test_result_type(result_type_id: int, request: Request, session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        rt = session.get(TestResultType, result_type_id)
        if rt:
            old_values = model_to_dict(rt)
            session.delete(rt)
            session.commit()
            create_audit_log(session, "testresulttype", rt.id, "delete", current_user, old_values=old_values)
            return RedirectResponse(url="/test-result-types?success=Result type deleted successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/test-result-types?error=Result type not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/test-result-types?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

# ===========================
# PACKAGE ROUTES (N+1 FIX: selectinload)
# ===========================
@router.get("/packages", response_class=HTMLResponse)
def packages_page(request: Request, session: Session = Depends(get_session)):
    # ✅ N+1 FIX: eager-load package_tests in one query
    packages = session.exec(
        select(Package)
        .options(selectinload(Package.package_tests))
        .order_by(Package.id.asc())
    ).all()
    packages_json = []
    for pkg in packages:
        pkg_dict = model_to_dict(pkg)
        test_ids = [pt.test_id for pt in pkg.package_tests]
        pkg_dict['test_ids'] = test_ids
        packages_json.append(pkg_dict)
    tests = session.exec(select(TestDefinition).where(TestDefinition.is_available == True)).all()
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse("packages.html", {
        "request": request, "packages": packages, "packages_json": packages_json,
        "tests": tests, "message_success": success, "message_error": error
    })

@router.post("/packages/create")
def create_package(package_name: str = Form(...), package_short_name: str = Form(...),
                   price: float = Form(...), package_note: Optional[str] = Form(None),
                   test_ids: Optional[str] = Form(""), request: Request = None,
                   session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        new_package = Package(
            package_name=package_name, package_short_name=package_short_name.upper(),
            price=price, package_note=package_note, is_active=True,
            created_by=current_user.id if current_user else None
        )
        session.add(new_package)
        session.commit()
        session.refresh(new_package)
        if test_ids and test_ids.strip():
            test_id_list = [int(t.strip()) for t in test_ids.split(',') if t.strip().isdigit()]
            for test_id in test_id_list:
                link = PackageTest(package_id=new_package.id, test_id=test_id)
                session.add(link)
        session.commit()
        create_audit_log(session, "package", new_package.id, "create", current_user, new_values=model_to_dict(new_package))
        return RedirectResponse(url="/packages?success=Package saved successfully!", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/packages?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/packages/update/{package_id}")
def update_package(package_id: int, package_name: str = Form(...), package_short_name: str = Form(...),
                   price: float = Form(...), package_note: Optional[str] = Form(None),
                   test_ids: Optional[str] = Form(""), request: Request = None,
                   session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        pkg = session.get(Package, package_id)
        if pkg:
            old_values = model_to_dict(pkg)
            pkg.package_name = package_name
            pkg.package_short_name = package_short_name.upper()
            pkg.price = price
            pkg.package_note = package_note
            pkg.edited_by = current_user.id if current_user else None
            pkg.edited_at = datetime.utcnow()
            existing_links = session.exec(select(PackageTest).where(PackageTest.package_id == package_id)).all()
            for link in existing_links:
                session.delete(link)
            if test_ids and test_ids.strip():
                test_id_list = [int(t.strip()) for t in test_ids.split(',') if t.strip().isdigit()]
                for test_id in test_id_list:
                    link = PackageTest(package_id=pkg.id, test_id=test_id)
                    session.add(link)
            session.add(pkg)
            session.commit()
            session.refresh(pkg)
            create_audit_log(session, "package", pkg.id, "update", current_user, old_values=old_values, new_values=model_to_dict(pkg))
            return RedirectResponse(url="/packages?success=Package updated successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/packages?error=Package not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/packages?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/packages/delete/{package_id}")
def delete_package(package_id: int, request: Request, session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        pkg = session.get(Package, package_id)
        if pkg:
            old_values = model_to_dict(pkg)
            existing_links = session.exec(select(PackageTest).where(PackageTest.package_id == package_id)).all()
            for link in existing_links:
                session.delete(link)
            session.delete(pkg)
            session.commit()
            create_audit_log(session, "package", pkg.id, "delete", current_user, old_values=old_values)
            return RedirectResponse(url="/packages?success=Package deleted successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/packages?error=Package not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/packages?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)
