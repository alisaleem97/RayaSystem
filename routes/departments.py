# routes/departments.py
# CRUD routes for: Departments, Sample Types, Devices, Parameters, Report Notes.

from fastapi import APIRouter, Depends, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from datetime import datetime
from typing import Optional
from database import get_session
from models import Department, SampleType, Device, Parameter, ReportNote
from routes.helpers import templates, get_current_user, create_audit_log, model_to_dict, require_permission

router = APIRouter()

# ===========================
# DEPARTMENTS ROUTES
# ===========================
@router.get("/departments", response_class=HTMLResponse)
def departments_page(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "departments"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    departments = session.exec(select(Department).order_by(Department.id.asc())).all()
    departments_dict = [model_to_dict(d) for d in departments]
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse("departments.html", {
        "request": request, "departments": departments,
        "departments_json": departments_dict, "message_success": success, "message_error": error
    })

@router.post("/departments/create")
def create_department(department_name: str = Form(...), department_note: Optional[str] = Form(None),
                      request: Request = None, session: Session = Depends(get_session)):
    if not require_permission(request, session, "departments", "create"):
        return RedirectResponse(url="/departments?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        new_department = Department(department_name=department_name, department_note=department_note, is_active=True,
                                    created_by=current_user.id if current_user else None)
        session.add(new_department)
        session.commit()
        session.refresh(new_department)
        create_audit_log(session, "department", new_department.id, "create", current_user, new_values=model_to_dict(new_department))
        return RedirectResponse(url="/departments?success=Department saved successfully!", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/departments?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/departments/update/{dept_id}")
def update_department(dept_id: int, department_name: str = Form(...), department_note: Optional[str] = Form(None),
                      request: Request = None, session: Session = Depends(get_session)):
    if not require_permission(request, session, "departments", "edit"):
        return RedirectResponse(url="/departments?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        dept = session.get(Department, dept_id)
        if dept:
            old_values = model_to_dict(dept)
            dept.department_name = department_name
            dept.department_note = department_note
            dept.edited_by = current_user.id if current_user else None
            dept.edited_at = datetime.now()
            session.add(dept)
            session.commit()
            session.refresh(dept)
            create_audit_log(session, "department", dept.id, "update", current_user, old_values=old_values, new_values=model_to_dict(dept))
            return RedirectResponse(url="/departments?success=Department updated successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/departments?error=Department not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/departments?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/departments/delete/{dept_id}")
def delete_department(dept_id: int, request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "departments", "delete"):
        return RedirectResponse(url="/departments?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        dept = session.get(Department, dept_id)
        if dept:
            old_values = model_to_dict(dept)
            create_audit_log(session, "department", dept.id, "delete", current_user, old_values=old_values)
            session.delete(dept)
            session.commit()
            return RedirectResponse(url="/departments?success=Department deleted successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/departments?error=Department not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/departments?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

# ===========================
# SAMPLE TYPES ROUTES
# ===========================
@router.get("/sample-types", response_class=HTMLResponse)
def sample_types_page(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "sample_types"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    sample_types = session.exec(select(SampleType).order_by(SampleType.id.asc())).all()
    sample_types_dict = [model_to_dict(s) for s in sample_types]
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse("sample_types.html", {
        "request": request, "sample_types": sample_types,
        "sample_types_json": sample_types_dict, "message_success": success, "message_error": error
    })

@router.post("/sample-types/create")
def create_sample_type(sample_name: str = Form(...), sample_note: Optional[str] = Form(None),
                       request: Request = None, session: Session = Depends(get_session)):
    if not require_permission(request, session, "sample_types", "create"):
        return RedirectResponse(url="/sample-types?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        new_sample_type = SampleType(sample_name=sample_name, sample_note=sample_note, is_active=True,
                                     created_by=current_user.id if current_user else None)
        session.add(new_sample_type)
        session.commit()
        session.refresh(new_sample_type)
        create_audit_log(session, "sampletype", new_sample_type.id, "create", current_user, new_values=model_to_dict(new_sample_type))
        return RedirectResponse(url="/sample-types?success=Sample type saved successfully!", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/sample-types?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/sample-types/update/{sample_id}")
def update_sample_type(sample_id: int, sample_name: str = Form(...), sample_note: Optional[str] = Form(None),
                       request: Request = None, session: Session = Depends(get_session)):
    if not require_permission(request, session, "sample_types", "edit"):
        return RedirectResponse(url="/sample-types?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        sample = session.get(SampleType, sample_id)
        if sample:
            old_values = model_to_dict(sample)
            sample.sample_name = sample_name
            sample.sample_note = sample_note
            sample.edited_by = current_user.id if current_user else None
            sample.edited_at = datetime.now()
            session.add(sample)
            session.commit()
            session.refresh(sample)
            create_audit_log(session, "sampletype", sample.id, "update", current_user, old_values=old_values, new_values=model_to_dict(sample))
            return RedirectResponse(url="/sample-types?success=Sample type updated successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/sample-types?error=Sample type not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/sample-types?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/sample-types/delete/{sample_id}")
def delete_sample_type(sample_id: int, request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "sample_types", "delete"):
        return RedirectResponse(url="/sample-types?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        sample = session.get(SampleType, sample_id)
        if sample:
            old_values = model_to_dict(sample)
            create_audit_log(session, "sampletype", sample.id, "delete", current_user, old_values=old_values)
            session.delete(sample)
            session.commit()
            return RedirectResponse(url="/sample-types?success=Sample type deleted successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/sample-types?error=Sample type not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/sample-types?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

# ===========================
# DEVICES ROUTES
# ===========================
@router.get("/devices", response_class=HTMLResponse)
def devices_page(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "devices"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    devices = session.exec(select(Device).order_by(Device.id.asc())).all()
    devices_dict = [model_to_dict(d) for d in devices]
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse("devices.html", {
        "request": request, "devices": devices,
        "devices_json": devices_dict, "message_success": success, "message_error": error
    })

@router.post("/devices/create")
def create_device(device_name: str = Form(...), serial_number: str = Form(...), install_date: str = Form(...),
                  installer_name: str = Form(...), installer_phone: str = Form(...), note: Optional[str] = Form(None),
                  request: Request = None, session: Session = Depends(get_session)):
    if not require_permission(request, session, "devices", "create"):
        return RedirectResponse(url="/devices?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        install_dt = datetime.strptime(install_date, "%Y-%m-%d")
        new_device = Device(device_name=device_name, serial_number=serial_number, install_date=install_dt,
                           installer_name=installer_name, installer_phone=installer_phone, note=note, is_active=True,
                           created_by=current_user.id if current_user else None)
        session.add(new_device)
        session.commit()
        session.refresh(new_device)
        create_audit_log(session, "device", new_device.id, "create", current_user, new_values=model_to_dict(new_device))
        return RedirectResponse(url="/devices?success=Device saved successfully!", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/devices?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/devices/update/{device_id}")
def update_device(device_id: int, device_name: str = Form(...), serial_number: str = Form(...), install_date: str = Form(...),
                  installer_name: str = Form(...), installer_phone: str = Form(...), note: Optional[str] = Form(None),
                  request: Request = None, session: Session = Depends(get_session)):
    if not require_permission(request, session, "devices", "edit"):
        return RedirectResponse(url="/devices?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        device = session.get(Device, device_id)
        if device:
            old_values = model_to_dict(device)
            device.device_name = device_name
            device.serial_number = serial_number
            device.install_date = datetime.strptime(install_date, "%Y-%m-%d")
            device.installer_name = installer_name
            device.installer_phone = installer_phone
            device.note = note
            device.edited_by = current_user.id if current_user else None
            device.edited_at = datetime.now()
            session.add(device)
            session.commit()
            session.refresh(device)
            create_audit_log(session, "device", device.id, "update", current_user, old_values=old_values, new_values=model_to_dict(device))
            return RedirectResponse(url="/devices?success=Device updated successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/devices?error=Device not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/devices?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/devices/delete/{device_id}")
def delete_device(device_id: int, request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "devices", "delete"):
        return RedirectResponse(url="/devices?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        device = session.get(Device, device_id)
        if device:
            old_values = model_to_dict(device)
            create_audit_log(session, "device", device.id, "delete", current_user, old_values=old_values)
            session.delete(device)
            session.commit()
            return RedirectResponse(url="/devices?success=Device deleted successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/devices?error=Device not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/devices?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

# ===========================
# PARAMETERS ROUTES
# ===========================
@router.get("/parameters", response_class=HTMLResponse)
def parameters_page(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "parameters"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    parameters = session.exec(select(Parameter).order_by(Parameter.id.asc())).all()
    parameters_dict = [model_to_dict(p) for p in parameters]
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse("parameters.html", {
        "request": request, "parameters": parameters,
        "parameters_json": parameters_dict, "message_success": success, "message_error": error
    })

@router.post("/parameters/create")
def create_parameter(parameter_name: str = Form(...), parameter_short_name: str = Form(...),
                     is_header: str = Form(None), request: Request = None, session: Session = Depends(get_session)):
    if not require_permission(request, session, "parameters", "create"):
        return RedirectResponse(url="/parameters?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        # Check for duplicate name before inserting
        existing = session.exec(select(Parameter).where(Parameter.parameter_name == parameter_name)).first()
        if existing:
            return RedirectResponse(url=f"/parameters?error=Parameter '{parameter_name}' already exists!", status_code=status.HTTP_303_SEE_OTHER)
        is_header_bool = True if is_header == "on" else False
        new_parameter = Parameter(parameter_name=parameter_name, parameter_short_name=parameter_short_name.upper(),
                                 is_header=is_header_bool, created_by=current_user.id if current_user else None)
        session.add(new_parameter)
        session.commit()
        session.refresh(new_parameter)
        create_audit_log(session, "parameter", new_parameter.id, "create", current_user, new_values=model_to_dict(new_parameter))
        return RedirectResponse(url="/parameters?success=Parameter saved successfully!", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/parameters?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/parameters/update/{param_id}")
def update_parameter(param_id: int, parameter_name: str = Form(...), parameter_short_name: str = Form(...),
                     is_header: str = Form(None), request: Request = None, session: Session = Depends(get_session)):
    if not require_permission(request, session, "parameters", "edit"):
        return RedirectResponse(url="/parameters?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        param = session.get(Parameter, param_id)
        if param:
            old_values = model_to_dict(param)
            param.parameter_name = parameter_name
            param.parameter_short_name = parameter_short_name.upper()
            param.is_header = True if is_header == "on" else False
            param.edited_by = current_user.id if current_user else None
            param.edited_at = datetime.now()
            session.add(param)
            session.commit()
            session.refresh(param)
            create_audit_log(session, "parameter", param.id, "update", current_user, old_values=old_values, new_values=model_to_dict(param))
            return RedirectResponse(url="/parameters?success=Parameter updated successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/parameters?error=Parameter not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/parameters?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/parameters/delete/{param_id}")
def delete_parameter(param_id: int, request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "parameters", "delete"):
        return RedirectResponse(url="/parameters?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        param = session.get(Parameter, param_id)
        if param:
            old_values = model_to_dict(param)
            create_audit_log(session, "parameter", param.id, "delete", current_user, old_values=old_values)
            session.delete(param)
            session.commit()
            return RedirectResponse(url="/parameters?success=Parameter deleted successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/parameters?error=Parameter not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/parameters?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

# ===========================
# REPORT NOTES ROUTES
# ===========================
@router.get("/report-notes", response_class=HTMLResponse)
def report_notes_page(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "report_notes"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    report_notes = session.exec(select(ReportNote).order_by(ReportNote.id.asc())).all()
    report_notes_dict = [model_to_dict(n) for n in report_notes]
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse("report_notes.html", {
        "request": request, "report_notes": report_notes,
        "report_notes_json": report_notes_dict, "message_success": success, "message_error": error
    })

@router.post("/report-notes/create")
def create_report_note(note_name: str = Form(...), note_content: str = Form(...),
                       request: Request = None, session: Session = Depends(get_session)):
    if not require_permission(request, session, "report_notes", "create"):
        return RedirectResponse(url="/report-notes?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        new_note = ReportNote(note_name=note_name, note_content=note_content, is_active=True,
                             created_by=current_user.id if current_user else None)
        session.add(new_note)
        session.commit()
        session.refresh(new_note)
        create_audit_log(session, "reportnote", new_note.id, "create", current_user, new_values=model_to_dict(new_note))
        return RedirectResponse(url="/report-notes?success=Report note saved successfully!", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/report-notes?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/report-notes/update/{note_id}")
def update_report_note(note_id: int, note_name: str = Form(...), note_content: str = Form(...),
                       request: Request = None, session: Session = Depends(get_session)):
    if not require_permission(request, session, "report_notes", "edit"):
        return RedirectResponse(url="/report-notes?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        note = session.get(ReportNote, note_id)
        if note:
            old_values = model_to_dict(note)
            note.note_name = note_name
            note.note_content = note_content
            note.edited_by = current_user.id if current_user else None
            note.edited_at = datetime.now()
            session.add(note)
            session.commit()
            session.refresh(note)
            create_audit_log(session, "reportnote", note.id, "update", current_user, old_values=old_values, new_values=model_to_dict(note))
            return RedirectResponse(url="/report-notes?success=Report note updated successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/report-notes?error=Report note not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/report-notes?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/report-notes/delete/{note_id}")
def delete_report_note(note_id: int, request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "report_notes", "delete"):
        return RedirectResponse(url="/report-notes?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        note = session.get(ReportNote, note_id)
        if note:
            old_values = model_to_dict(note)
            create_audit_log(session, "reportnote", note.id, "delete", current_user, old_values=old_values)
            session.delete(note)
            session.commit()
            return RedirectResponse(url="/report-notes?success=Report note deleted successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/report-notes?error=Report note not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/report-notes?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)
