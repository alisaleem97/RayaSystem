# main.py
from fastapi import FastAPI, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, List, Any
import json
import ast

from database import create_db_and_tables, get_session, engine
from models import User, Patient, TestCatalog, Order, Result, Parameter, Department, Device, SampleType, ReportNote, TestDefinition, TestDevice, TestParameter, AuditLog, Formula, FormulaItem, TestRange, TestResultType, Package, PackageTest, Partner, Province, Region,LabInfo

# Setup templates
templates = Jinja2Templates(directory="templates")

# Helper: Calculate age from DOB
def calculate_age(dob: datetime) -> int:
    today = datetime.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

# Add helper to templates
templates.env.globals["calculate_age"] = calculate_age

# Helper: Convert SQLModel object to dict
def model_to_dict(model):
    if model is None:
        return None
    data = {}
    for column in model.__table__.columns.keys():
        value = getattr(model, column)
        if isinstance(value, datetime):
            data[column] = value.isoformat()
        else:
            data[column] = value
    return data

# Helper: Get current logged-in user
def get_current_user(request: Request, session: Session) -> Optional[User]:
    user = session.exec(select(User).where(User.username == "admin")).first()
    return user

# Helper: Create audit log entry
def create_audit_log(session: Session, table_name: str, record_id: int, action: str, 
                     user: User, old_values: dict = None, new_values: dict = None):
    audit_entry = AuditLog(
        table_name=table_name,
        record_id=record_id,
        action=action,
        user_id=user.id if user else 0,
        username=user.username if user else "unknown",
        old_values=json.dumps(old_values) if old_values else None,
        new_values=json.dumps(new_values) if new_values else None,
        created_at=datetime.utcnow()
    )
    session.add(audit_entry)

# Run this once when app starts
@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    with Session(engine) as session:
        admin = session.exec(select(User).where(User.username == "admin")).first()
        if not admin:
            from passlib.context import CryptContext
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            new_admin = User(
                username="admin",
                full_name="System Admin",
                role="admin",
                hashed_password=pwd_context.hash("admin123"),
                is_active=True
            )
            session.add(new_admin)
            session.commit()
    yield

app = FastAPI(lifespan=lifespan)

# ===========================
# PAGE ROUTES (HTML)
# ===========================

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session)):
    patients = session.exec(select(Patient).order_by(Patient.created_at.desc())).all()
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse(
        "dashboard.html", 
        {"request": request, "patients": patients, "message_success": success, "message_error": error}
    )

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login_submit(username: str = Form(...), password: str = Form(...), session: Session = Depends(get_session)):
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    user = session.exec(select(User).where(User.username == username)).first()
    if user and pwd_context.verify(password, user.hashed_password) and user.is_active:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    else:
        return templates.TemplateResponse("login.html", {"request": request, "message_error": "Invalid username or password"})

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    error = request.query_params.get("error")
    return templates.TemplateResponse("register_patient.html", {"request": request, "message_error": error})

@app.post("/patients/create")
def create_patient_form(patient_id: str = Form(...), full_name: str = Form(...), date_of_birth: str = Form(...),
                        gender: str = Form(...), phone: str = Form(...), email: Optional[str] = Form(None),
                        address: Optional[str] = Form(None), request: Request = None, session: Session = Depends(get_session)):
    try:
        dob = datetime.strptime(date_of_birth, "%Y-%m-%d")
        current_user = get_current_user(request, session)
        new_patient = Patient(patient_id=patient_id, full_name=full_name, date_of_birth=dob, gender=gender,
                              phone=phone, email=email, address=address, created_by=current_user.id if current_user else None)
        session.add(new_patient)
        session.commit()
        session.refresh(new_patient)
        create_audit_log(session, "patient", new_patient.id, "create", current_user, new_values=model_to_dict(new_patient))
        return RedirectResponse(url="/?success=Patient registered successfully!", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/register?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/logout")
def logout():
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

# ===========================
# DEPARTMENTS ROUTES
# ===========================

@app.get("/departments", response_class=HTMLResponse)
def departments_page(request: Request, session: Session = Depends(get_session)):
    departments = session.exec(select(Department).order_by(Department.id.asc())).all()
    departments_dict = [model_to_dict(d) for d in departments]
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse("departments.html", {"request": request, "departments": departments,
        "departments_json": departments_dict, "message_success": success, "message_error": error})

@app.post("/departments/create")
def create_department(department_name: str = Form(...), department_note: Optional[str] = Form(None),
                      request: Request = None, session: Session = Depends(get_session)):
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

@app.post("/departments/update/{dept_id}")
def update_department(dept_id: int, department_name: str = Form(...), department_note: Optional[str] = Form(None),
                      request: Request = None, session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        dept = session.get(Department, dept_id)
        if dept:
            old_values = model_to_dict(dept)
            dept.department_name = department_name
            dept.department_note = department_note
            dept.edited_by = current_user.id if current_user else None
            dept.edited_at = datetime.utcnow()
            session.add(dept)
            session.commit()
            session.refresh(dept)
            create_audit_log(session, "department", dept.id, "update", current_user, old_values=old_values, new_values=model_to_dict(dept))
            return RedirectResponse(url="/departments?success=Department updated successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/departments?error=Department not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/departments?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/departments/delete/{dept_id}")
def delete_department(dept_id: int, request: Request, session: Session = Depends(get_session)):
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

@app.get("/sample-types", response_class=HTMLResponse)
def sample_types_page(request: Request, session: Session = Depends(get_session)):
    sample_types = session.exec(select(SampleType).order_by(SampleType.id.asc())).all()
    sample_types_dict = [model_to_dict(s) for s in sample_types]
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse("sample_types.html", {"request": request, "sample_types": sample_types,
        "sample_types_json": sample_types_dict, "message_success": success, "message_error": error})

@app.post("/sample-types/create")
def create_sample_type(sample_name: str = Form(...), sample_note: Optional[str] = Form(None),
                       request: Request = None, session: Session = Depends(get_session)):
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

@app.post("/sample-types/update/{sample_id}")
def update_sample_type(sample_id: int, sample_name: str = Form(...), sample_note: Optional[str] = Form(None),
                       request: Request = None, session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        sample = session.get(SampleType, sample_id)
        if sample:
            old_values = model_to_dict(sample)
            sample.sample_name = sample_name
            sample.sample_note = sample_note
            sample.edited_by = current_user.id if current_user else None
            sample.edited_at = datetime.utcnow()
            session.add(sample)
            session.commit()
            session.refresh(sample)
            create_audit_log(session, "sampletype", sample.id, "update", current_user, old_values=old_values, new_values=model_to_dict(sample))
            return RedirectResponse(url="/sample-types?success=Sample type updated successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/sample-types?error=Sample type not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/sample-types?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/sample-types/delete/{sample_id}")
def delete_sample_type(sample_id: int, request: Request, session: Session = Depends(get_session)):
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

@app.get("/devices", response_class=HTMLResponse)
def devices_page(request: Request, session: Session = Depends(get_session)):
    devices = session.exec(select(Device).order_by(Device.id.asc())).all()
    devices_dict = [model_to_dict(d) for d in devices]
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse("devices.html", {"request": request, "devices": devices,
        "devices_json": devices_dict, "message_success": success, "message_error": error})

@app.post("/devices/create")
def create_device(device_name: str = Form(...), serial_number: str = Form(...), install_date: str = Form(...),
                  installer_name: str = Form(...), installer_phone: str = Form(...), note: Optional[str] = Form(None),
                  request: Request = None, session: Session = Depends(get_session)):
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

@app.post("/devices/update/{device_id}")
def update_device(device_id: int, device_name: str = Form(...), serial_number: str = Form(...), install_date: str = Form(...),
                  installer_name: str = Form(...), installer_phone: str = Form(...), note: Optional[str] = Form(None),
                  request: Request = None, session: Session = Depends(get_session)):
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
            device.edited_at = datetime.utcnow()
            session.add(device)
            session.commit()
            session.refresh(device)
            create_audit_log(session, "device", device.id, "update", current_user, old_values=old_values, new_values=model_to_dict(device))
            return RedirectResponse(url="/devices?success=Device updated successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/devices?error=Device not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/devices?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/devices/delete/{device_id}")
def delete_device(device_id: int, request: Request, session: Session = Depends(get_session)):
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

@app.get("/parameters", response_class=HTMLResponse)
def parameters_page(request: Request, session: Session = Depends(get_session)):
    parameters = session.exec(select(Parameter).order_by(Parameter.id.asc())).all()
    parameters_dict = [model_to_dict(p) for p in parameters]
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse("parameters.html", {"request": request, "parameters": parameters,
        "parameters_json": parameters_dict, "message_success": success, "message_error": error})

@app.post("/parameters/create")
def create_parameter(parameter_name: str = Form(...), parameter_short_name: str = Form(...),
                     is_header: str = Form(None), request: Request = None, session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
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

@app.post("/parameters/update/{param_id}")
def update_parameter(param_id: int, parameter_name: str = Form(...), parameter_short_name: str = Form(...),
                     is_header: str = Form(None), request: Request = None, session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        param = session.get(Parameter, param_id)
        if param:
            old_values = model_to_dict(param)
            param.parameter_name = parameter_name
            param.parameter_short_name = parameter_short_name.upper()
            param.is_header = True if is_header == "on" else False
            param.edited_by = current_user.id if current_user else None
            param.edited_at = datetime.utcnow()
            session.add(param)
            session.commit()
            session.refresh(param)
            create_audit_log(session, "parameter", param.id, "update", current_user, old_values=old_values, new_values=model_to_dict(param))
            return RedirectResponse(url="/parameters?success=Parameter updated successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/parameters?error=Parameter not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/parameters?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/parameters/delete/{param_id}")
def delete_parameter(param_id: int, request: Request, session: Session = Depends(get_session)):
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

@app.get("/report-notes", response_class=HTMLResponse)
def report_notes_page(request: Request, session: Session = Depends(get_session)):
    report_notes = session.exec(select(ReportNote).order_by(ReportNote.id.asc())).all()
    report_notes_dict = [model_to_dict(n) for n in report_notes]
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse("report_notes.html", {
        "request": request,
        "report_notes": report_notes,
        "report_notes_json": report_notes_dict,
        "message_success": success,
        "message_error": error
    })

@app.post("/report-notes/create")
def create_report_note(
    note_name: str = Form(...),
    note_content: str = Form(...),
    request: Request = None,
    session: Session = Depends(get_session)
):
    try:
        current_user = get_current_user(request, session)
        new_note = ReportNote(
            note_name=note_name,
            note_content=note_content,
            is_active=True,
            created_by=current_user.id if current_user else None
        )
        session.add(new_note)
        session.commit()
        session.refresh(new_note)
        create_audit_log(session, "reportnote", new_note.id, "create", current_user, new_values=model_to_dict(new_note))
        return RedirectResponse(url="/report-notes?success=Report note saved successfully!", 
                              status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        error_msg = str(e).replace(" ", "%20")
        return RedirectResponse(url=f"/report-notes?error={error_msg}", 
                              status_code=status.HTTP_303_SEE_OTHER)

@app.post("/report-notes/update/{note_id}")
def update_report_note(
    note_id: int,
    note_name: str = Form(...),
    note_content: str = Form(...),
    request: Request = None,
    session: Session = Depends(get_session)
):
    try:
        current_user = get_current_user(request, session)
        note = session.get(ReportNote, note_id)
        if note:
            old_values = model_to_dict(note)
            note.note_name = note_name
            note.note_content = note_content
            note.edited_by = current_user.id if current_user else None
            note.edited_at = datetime.utcnow()
            session.add(note)
            session.commit()
            session.refresh(note)
            create_audit_log(session, "reportnote", note.id, "update", current_user, old_values=old_values, new_values=model_to_dict(note))
            return RedirectResponse(url="/report-notes?success=Report note updated successfully!", 
                                  status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/report-notes?error=Report note not found", 
                              status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        error_msg = str(e).replace(" ", "%20")
        return RedirectResponse(url=f"/report-notes?error={error_msg}", 
                              status_code=status.HTTP_303_SEE_OTHER)

@app.get("/report-notes/delete/{note_id}")
def delete_report_note(note_id: int, request: Request, session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        note = session.get(ReportNote, note_id)
        if note:
            old_values = model_to_dict(note)
            create_audit_log(session, "reportnote", note.id, "delete", current_user, old_values=old_values)
            session.delete(note)
            session.commit()
            return RedirectResponse(url="/report-notes?success=Report note deleted successfully!", 
                                  status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/report-notes?error=Report note not found", 
                              status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        error_msg = str(e).replace(" ", "%20")
        return RedirectResponse(url=f"/report-notes?error={error_msg}", 
                              status_code=status.HTTP_303_SEE_OTHER)

# ===========================
# TEST DEFINITION ROUTES
# ===========================

@app.get("/tests", response_class=HTMLResponse)
def tests_page(request: Request, session: Session = Depends(get_session)):
    tests = session.exec(select(TestDefinition).order_by(TestDefinition.id.asc())).all()
    
    # Prepare JSON data with related IDs for multi-select
    tests_json = []
    for test in tests:
        test_dict = model_to_dict(test)
        device_ids = [int(td.device_id) for td in test.test_devices]
        parameter_ids = [int(tp.parameter_id) for tp in test.test_parameters]
        test_dict['device_ids'] = device_ids
        test_dict['parameter_ids'] = parameter_ids
        tests_json.append(test_dict)
    
    # Get dropdown options (only active items for selection)
    departments = session.exec(select(Department).where(Department.is_active == True)).all()
    sample_types = session.exec(select(SampleType).where(SampleType.is_active == True)).all()
    report_notes = session.exec(select(ReportNote).where(ReportNote.is_active == True)).all()
    devices = session.exec(select(Device).where(Device.is_active == True)).all()
    parameters = session.exec(select(Parameter)).all()
    
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    
    return templates.TemplateResponse("tests.html", {
        "request": request,
        "tests": tests,
        "tests_json": tests_json,
        "departments": departments,
        "sample_types": sample_types,
        "report_notes": report_notes,
        "devices": devices,
        "parameters": parameters,
        "message_success": success,
        "message_error": error
    })

@app.post("/tests/create")
def create_test(
    test_name: str = Form(...),
    test_short_name: str = Form(...),
    department_id: int = Form(...),
    sample_type_id: int = Form(...),
    report_note_id: Optional[int] = Form(None),
    price: float = Form(...),
    test_note: Optional[str] = Form(None),
    test_condition: Optional[str] = Form(None),
    is_available: str = Form(None),
    device_ids: Optional[str] = Form(""),
    parameter_ids: Optional[str] = Form(""),
    request: Request = None,
    session: Session = Depends(get_session)
):
    try:
        current_user = get_current_user(request, session)
        is_available_bool = True if is_available == "on" else False
        
        new_test = TestDefinition(
            test_name=test_name,
            test_short_name=test_short_name.upper(),
            department_id=department_id,
            sample_type_id=sample_type_id,
            report_note_id=report_note_id if report_note_id and report_note_id != "" else None,
            price=price,
            test_note=test_note,
            test_condition=test_condition,
            is_available=is_available_bool,
            created_by=current_user.id if current_user else None
        )
        session.add(new_test)
        session.commit()
        session.refresh(new_test)
        
        # Handle device links - parse comma-separated string
        if device_ids and device_ids.strip():
            device_id_list = [int(d.strip()) for d in device_ids.split(',') if d.strip().isdigit()]
            for device_id in device_id_list:
                link = TestDevice(test_id=new_test.id, device_id=device_id)
                session.add(link)
        
        # Handle parameter links - parse comma-separated string
        if parameter_ids and parameter_ids.strip():
            parameter_id_list = [int(p.strip()) for p in parameter_ids.split(',') if p.strip().isdigit()]
            for parameter_id in parameter_id_list:
                link = TestParameter(test_id=new_test.id, parameter_id=parameter_id)
                session.add(link)
        
        session.commit()
        create_audit_log(session, "testdefinition", new_test.id, "create", current_user, new_values=model_to_dict(new_test))
        
        return RedirectResponse(url="/tests?success=Test saved successfully!", 
                              status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        error_msg = str(e).replace(" ", "%20")
        return RedirectResponse(url=f"/tests?error={error_msg}", 
                              status_code=status.HTTP_303_SEE_OTHER)

@app.post("/tests/update/{test_id}")
def update_test(
    test_id: int,
    test_name: str = Form(...),
    test_short_name: str = Form(...),
    department_id: int = Form(...),
    sample_type_id: int = Form(...),
    report_note_id: Optional[int] = Form(None),
    price: float = Form(...),
    test_note: Optional[str] = Form(None),
    test_condition: Optional[str] = Form(None),
    is_available: str = Form(None),
    device_ids: Optional[str] = Form(""),
    parameter_ids: Optional[str] = Form(""),
    request: Request = None,
    session: Session = Depends(get_session)
):
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
            
            # Delete existing device links
            existing_device_links = session.exec(select(TestDevice).where(TestDevice.test_id == test_id)).all()
            for link in existing_device_links:
                session.delete(link)
            
            # Add new device links
            if device_ids and device_ids.strip():
                device_id_list = [int(d.strip()) for d in device_ids.split(',') if d.strip().isdigit()]
                for device_id in device_id_list:
                    link = TestDevice(test_id=test.id, device_id=device_id)
                    session.add(link)
            
            # Delete existing parameter links
            existing_parameter_links = session.exec(select(TestParameter).where(TestParameter.test_id == test_id)).all()
            for link in existing_parameter_links:
                session.delete(link)
            
            # Add new parameter links
            if parameter_ids and parameter_ids.strip():
                parameter_id_list = [int(p.strip()) for p in parameter_ids.split(',') if p.strip().isdigit()]
                for parameter_id in parameter_id_list:
                    link = TestParameter(test_id=test.id, parameter_id=parameter_id)
                    session.add(link)
            
            session.add(test)
            session.commit()
            session.refresh(test)
            create_audit_log(session, "testdefinition", test.id, "update", current_user, old_values=old_values, new_values=model_to_dict(test))
            
            return RedirectResponse(url="/tests?success=Test updated successfully!", 
                                  status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/tests?error=Test not found", 
                              status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        error_msg = str(e).replace(" ", "%20")
        return RedirectResponse(url=f"/tests?error={error_msg}", 
                              status_code=status.HTTP_303_SEE_OTHER)

@app.get("/tests/delete/{test_id}")
def delete_test(test_id: int, request: Request, session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        test = session.get(TestDefinition, test_id)
        if test:
            old_values = model_to_dict(test)
            # Delete related TestDevice links
            existing_device_links = session.exec(select(TestDevice).where(TestDevice.test_id == test_id)).all()
            for link in existing_device_links:
                session.delete(link)
            # Delete related TestParameter links
            existing_parameter_links = session.exec(select(TestParameter).where(TestParameter.test_id == test_id)).all()
            for link in existing_parameter_links:
                session.delete(link)
            # Delete the test
            session.delete(test)
            session.commit()
            create_audit_log(session, "testdefinition", test.id, "delete", current_user, old_values=old_values)
            return RedirectResponse(url="/tests?success=Test deleted successfully!", 
                                  status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/tests?error=Test not found", 
                              status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        error_msg = str(e).replace(" ", "%20")
        return RedirectResponse(url=f"/tests?error={error_msg}", 
                              status_code=status.HTTP_303_SEE_OTHER)

# ===========================
# FORMULA ROUTES
# ===========================

@app.get("/api/get-formula-test/{formula_id}")
def get_formula_for_testing(formula_id: int, session: Session = Depends(get_session)):
    """Fetch formula data specifically for testing"""
    try:
        formula = session.get(Formula, formula_id)
        if not formula:
            return {"error": "Formula not found"}
        
        return {
            "formula_id": formula.id,
            "formula_name": formula.formula_name,
            "formula_expression": formula.formula_expression
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/formulas", response_class=HTMLResponse)
def formulas_page(request: Request, session: Session = Depends(get_session)):
    formulas = session.exec(select(Formula).order_by(Formula.id.asc())).all()
    
    formulas_json = []
    for formula in formulas:
        formula_dict = model_to_dict(formula)
        formulas_json.append(formula_dict)
    
    tests = session.exec(select(TestDefinition).where(TestDefinition.is_available == True)).all()
    parameters = session.exec(select(Parameter)).all()
    
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    
    return templates.TemplateResponse("formulas.html", {
        "request": request,
        "formulas": formulas,
        "formulas_json": formulas_json,
        "tests": tests,
        "parameters": parameters,
        "message_success": success,
        "message_error": error
    })

@app.post("/formulas/create")
def create_formula(
    formula_name: str = Form(...),
    main_test_id: int = Form(...),
    main_parameter_id: Optional[int] = Form(None),
    gender_type: str = Form(...),
    formula_expression: str = Form(""),
    formula_description: Optional[str] = Form(None),
    request: Request = None,
    session: Session = Depends(get_session)
):
    try:
        current_user = get_current_user(request, session)
        
        new_formula = Formula(
            formula_name=formula_name,
            main_test_id=main_test_id,
            main_parameter_id=main_parameter_id if main_parameter_id else None,
            gender_type=gender_type,
            formula_expression=formula_expression,
            formula_description=formula_description,
            is_active=True,
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

@app.post("/formulas/update/{formula_id}")
def update_formula(
    formula_id: int,
    formula_name: str = Form(...),
    main_test_id: int = Form(...),
    main_parameter_id: Optional[int] = Form(None),
    gender_type: str = Form(...),
    formula_expression: str = Form(""),
    formula_description: Optional[str] = Form(None),
    request: Request = None,
    session: Session = Depends(get_session)
):
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

@app.get("/formulas/delete/{formula_id}")
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

@app.get("/test-ranges", response_class=HTMLResponse)
def test_ranges_page(request: Request, session: Session = Depends(get_session)):
    ranges = session.exec(select(TestRange).order_by(TestRange.id.asc())).all()
    
    ranges_json = []
    for range_item in ranges:
        range_dict = model_to_dict(range_item)
        ranges_json.append(range_dict)
    
    tests = session.exec(select(TestDefinition).where(TestDefinition.is_available == True)).all()
    parameters = session.exec(select(Parameter)).all()
    devices = session.exec(select(Device).where(Device.is_active == True)).all()
    departments = session.exec(select(Department).where(Department.is_active == True)).all()  # ✅ Add this line
    
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    
    return templates.TemplateResponse("test_ranges.html", {
        "request": request,
        "ranges": ranges,
        "ranges_json": ranges_json,
        "tests": tests,
        "parameters": parameters,
        "devices": devices,
        "departments": departments,  # ✅ Add this line
        "message_success": success,
        "message_error": error
    })

@app.post("/test-ranges/create")
def create_test_range(
    test_id: int = Form(...),
    parameter_id: Optional[int] = Form(None),
    device_id: Optional[int] = Form(None),
    unit: str = Form(...),
    gender_type: str = Form(...),
    age_from: int = Form(...),
    age_to: int = Form(...),
    age_unit: str = Form(...),
    fasting_required: str = Form("false"),
    range_type: str = Form(...),
    # Numeric range values
    normal_from: Optional[float] = Form(None),
    normal_to: Optional[float] = Form(None),
    vlow_from: Optional[float] = Form(None),
    vlow_to: Optional[float] = Form(None),
    low_from: Optional[float] = Form(None),
    low_to: Optional[float] = Form(None),
    midlow_from: Optional[float] = Form(None),
    midlow_to: Optional[float] = Form(None),
    midhigh_from: Optional[float] = Form(None),
    midhigh_to: Optional[float] = Form(None),
    high_from: Optional[float] = Form(None),
    high_to: Optional[float] = Form(None),
    vhigh_from: Optional[float] = Form(None),
    vhigh_to: Optional[float] = Form(None),
    panic_less_than: Optional[float] = Form(None),
    panic_more_than: Optional[float] = Form(None),
    # Text range value
    text_range: Optional[str] = Form(None),
    request: Request = None,
    session: Session = Depends(get_session)
):
    try:
        current_user = get_current_user(request, session)
        fasting_bool = fasting_required.lower() == "true"
        
        new_range = TestRange(
            test_id=test_id,
            parameter_id=parameter_id if parameter_id else None,
            device_id=device_id if device_id else None,
            unit=unit,
            gender_type=gender_type,
            age_from=age_from,
            age_to=age_to,
            age_unit=age_unit,
            fasting_required=fasting_bool,
            range_type=range_type,
            # Numeric values
            normal_from=normal_from,
            normal_to=normal_to,
            vlow_from=vlow_from,
            vlow_to=vlow_to,
            low_from=low_from,
            low_to=low_to,
            midlow_from=midlow_from,
            midlow_to=midlow_to,
            midhigh_from=midhigh_from,
            midhigh_to=midhigh_to,
            high_from=high_from,
            high_to=high_to,
            vhigh_from=vhigh_from,
            vhigh_to=vhigh_to,
            panic_less_than=panic_less_than,
            panic_more_than=panic_more_than,
            # Text value
            text_range=text_range if range_type == "text" else None,
            is_active=True,
            created_by=current_user.id if current_user else None
        )
        session.add(new_range)
        session.commit()
        session.refresh(new_range)
        create_audit_log(session, "testrange", new_range.id, "create", current_user, new_values=model_to_dict(new_range))
        
        return RedirectResponse(url="/test-ranges?success=Test range saved successfully!", 
                              status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        error_msg = str(e).replace(" ", "%20")
        return RedirectResponse(url=f"/test-ranges?error={error_msg}", 
                              status_code=status.HTTP_303_SEE_OTHER)

@app.post("/test-ranges/update/{range_id}")
def update_test_range(
    range_id: int,
    test_id: int = Form(...),
    parameter_id: Optional[int] = Form(None),
    device_id: Optional[int] = Form(None),
    unit: str = Form(...),
    gender_type: str = Form(...),
    age_from: int = Form(...),
    age_to: int = Form(...),
    age_unit: str = Form(...),
    fasting_required: str = Form("false"),
    range_type: str = Form(...),
    # Numeric range values
    normal_from: Optional[float] = Form(None),
    normal_to: Optional[float] = Form(None),
    vlow_from: Optional[float] = Form(None),
    vlow_to: Optional[float] = Form(None),
    low_from: Optional[float] = Form(None),
    low_to: Optional[float] = Form(None),
    midlow_from: Optional[float] = Form(None),
    midlow_to: Optional[float] = Form(None),
    midhigh_from: Optional[float] = Form(None),
    midhigh_to: Optional[float] = Form(None),
    high_from: Optional[float] = Form(None),
    high_to: Optional[float] = Form(None),
    vhigh_from: Optional[float] = Form(None),
    vhigh_to: Optional[float] = Form(None),
    panic_less_than: Optional[float] = Form(None),
    panic_more_than: Optional[float] = Form(None),
    # Text range value
    text_range: Optional[str] = Form(None),
    request: Request = None,
    session: Session = Depends(get_session)
):
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
            # Numeric values
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
            # Text value
            range_item.text_range = text_range if range_type == "text" else None
            range_item.edited_by = current_user.id if current_user else None
            range_item.edited_at = datetime.utcnow()
            
            session.add(range_item)
            session.commit()
            session.refresh(range_item)
            create_audit_log(session, "testrange", range_item.id, "update", current_user, old_values=old_values, new_values=model_to_dict(range_item))
            
            return RedirectResponse(url="/test-ranges?success=Test range updated successfully!", 
                                  status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/test-ranges?error=Test range not found", 
                              status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        error_msg = str(e).replace(" ", "%20")
        return RedirectResponse(url=f"/test-ranges?error={error_msg}", 
                              status_code=status.HTTP_303_SEE_OTHER)

@app.get("/test-ranges/delete/{range_id}")
def delete_test_range(range_id: int, request: Request, session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        range_item = session.get(TestRange, range_id)
        
        if range_item:
            old_values = model_to_dict(range_item)
            session.delete(range_item)
            session.commit()
            create_audit_log(session, "testrange", range_item.id, "delete", current_user, old_values=old_values)
            
            return RedirectResponse(url="/test-ranges?success=Test range deleted successfully!", 
                                  status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/test-ranges?error=Test range not found", 
                              status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        error_msg = str(e).replace(" ", "%20")
        return RedirectResponse(url=f"/test-ranges?error={error_msg}", 
                              status_code=status.HTTP_303_SEE_OTHER)
    

# ===========================
# TEST RESULT TYPE ROUTES
# ===========================

@app.get("/test-result-types", response_class=HTMLResponse)
def test_result_types_page(request: Request, session: Session = Depends(get_session)):
    result_types = session.exec(select(TestResultType).order_by(TestResultType.id.asc())).all()
    
    result_types_json = []
    for rt in result_types:
        rt_dict = model_to_dict(rt)
        result_types_json.append(rt_dict)
    
    tests = session.exec(select(TestDefinition).where(TestDefinition.is_available == True)).all()
    parameters = session.exec(select(Parameter)).all()
    
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    
    return templates.TemplateResponse("test_result_types.html", {
        "request": request,
        "result_types": result_types,
        "result_types_json": result_types_json,
        "tests": tests,
        "parameters": parameters,
        "message_success": success,
        "message_error": error
    })

@app.post("/test-result-types/create")
def create_test_result_type(
    test_id: int = Form(...),
    parameter_id: Optional[int] = Form(None),
    result_type: str = Form(...),
    selection_options: Optional[str] = Form(None),
    request: Request = None,
    session: Session = Depends(get_session)
):
    try:
        current_user = get_current_user(request, session)
        
        new_result_type = TestResultType(
            test_id=test_id,
            parameter_id=parameter_id if parameter_id else None,
            result_type=result_type,
            selection_options=selection_options if result_type == "selection" else None,
            is_active=True,
            created_by=current_user.id if current_user else None
        )
        session.add(new_result_type)
        session.commit()
        session.refresh(new_result_type)
        create_audit_log(session, "testresulttype", new_result_type.id, "create", current_user, new_values=model_to_dict(new_result_type))
        
        return RedirectResponse(url="/test-result-types?success=Result type saved successfully!", 
                              status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        error_msg = str(e).replace(" ", "%20")
        return RedirectResponse(url=f"/test-result-types?error={error_msg}", 
                              status_code=status.HTTP_303_SEE_OTHER)

@app.post("/test-result-types/update/{result_type_id}")
def update_test_result_type(
    result_type_id: int,
    test_id: int = Form(...),
    parameter_id: Optional[int] = Form(None),
    result_type: str = Form(...),
    selection_options: Optional[str] = Form(None),
    request: Request = None,
    session: Session = Depends(get_session)
):
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
            
            return RedirectResponse(url="/test-result-types?success=Result type updated successfully!", 
                                  status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/test-result-types?error=Result type not found", 
                              status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        error_msg = str(e).replace(" ", "%20")
        return RedirectResponse(url=f"/test-result-types?error={error_msg}", 
                              status_code=status.HTTP_303_SEE_OTHER)

@app.get("/test-result-types/delete/{result_type_id}")
def delete_test_result_type(result_type_id: int, request: Request, session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        rt = session.get(TestResultType, result_type_id)
        
        if rt:
            old_values = model_to_dict(rt)
            session.delete(rt)
            session.commit()
            create_audit_log(session, "testresulttype", rt.id, "delete", current_user, old_values=old_values)
            
            return RedirectResponse(url="/test-result-types?success=Result type deleted successfully!", 
                                  status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/test-result-types?error=Result type not found", 
                              status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        error_msg = str(e).replace(" ", "%20")
        return RedirectResponse(url=f"/test-result-types?error={error_msg}", 
                              status_code=status.HTTP_303_SEE_OTHER)
    
# ===========================
# PACKAGE ROUTES
# ===========================

@app.get("/packages", response_class=HTMLResponse)
def packages_page(request: Request, session: Session = Depends(get_session)):
    packages = session.exec(select(Package).order_by(Package.id.asc())).all()
    
    packages_json = []
    for pkg in packages:
        pkg_dict = model_to_dict(pkg)
        # Get test IDs for this package
        test_ids = [pt.test_id for pt in pkg.package_tests]
        pkg_dict['test_ids'] = test_ids
        packages_json.append(pkg_dict)
    
    tests = session.exec(select(TestDefinition).where(TestDefinition.is_available == True)).all()
    
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    
    return templates.TemplateResponse("packages.html", {
        "request": request,
        "packages": packages,
        "packages_json": packages_json,
        "tests": tests,
        "message_success": success,
        "message_error": error
    })

@app.post("/packages/create")
def create_package(
    package_name: str = Form(...),
    package_short_name: str = Form(...),
    price: float = Form(...),
    package_note: Optional[str] = Form(None),
    test_ids: Optional[str] = Form(""),  # Comma-separated string from Tom Select
    request: Request = None,
    session: Session = Depends(get_session)
):
    try:
        current_user = get_current_user(request, session)
        
        new_package = Package(
            package_name=package_name,
            package_short_name=package_short_name.upper(),
            price=price,
            package_note=package_note,
            is_active=True,
            created_by=current_user.id if current_user else None
        )
        session.add(new_package)
        session.commit()
        session.refresh(new_package)
        
        # Add package-test links
        if test_ids and test_ids.strip():
            test_id_list = [int(t.strip()) for t in test_ids.split(',') if t.strip().isdigit()]
            for test_id in test_id_list:
                link = PackageTest(package_id=new_package.id, test_id=test_id)
                session.add(link)
        
        session.commit()
        create_audit_log(session, "package", new_package.id, "create", current_user, new_values=model_to_dict(new_package))
        
        return RedirectResponse(url="/packages?success=Package saved successfully!", 
                              status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        error_msg = str(e).replace(" ", "%20")
        return RedirectResponse(url=f"/packages?error={error_msg}", 
                              status_code=status.HTTP_303_SEE_OTHER)

@app.post("/packages/update/{package_id}")
def update_package(
    package_id: int,
    package_name: str = Form(...),
    package_short_name: str = Form(...),
    price: float = Form(...),
    package_note: Optional[str] = Form(None),
    test_ids: Optional[str] = Form(""),
    request: Request = None,
    session: Session = Depends(get_session)
):
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
            
            # Delete existing package-test links
            existing_links = session.exec(select(PackageTest).where(PackageTest.package_id == package_id)).all()
            for link in existing_links:
                session.delete(link)
            
            # Add new package-test links
            if test_ids and test_ids.strip():
                test_id_list = [int(t.strip()) for t in test_ids.split(',') if t.strip().isdigit()]
                for test_id in test_id_list:
                    link = PackageTest(package_id=pkg.id, test_id=test_id)
                    session.add(link)
            
            session.add(pkg)
            session.commit()
            session.refresh(pkg)
            create_audit_log(session, "package", pkg.id, "update", current_user, old_values=old_values, new_values=model_to_dict(pkg))
            
            return RedirectResponse(url="/packages?success=Package updated successfully!", 
                                  status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/packages?error=Package not found", 
                              status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        error_msg = str(e).replace(" ", "%20")
        return RedirectResponse(url=f"/packages?error={error_msg}", 
                              status_code=status.HTTP_303_SEE_OTHER)

@app.get("/packages/delete/{package_id}")
def delete_package(package_id: int, request: Request, session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        pkg = session.get(Package, package_id)
        
        if pkg:
            old_values = model_to_dict(pkg)
            
            # Delete related package-test links first
            existing_links = session.exec(select(PackageTest).where(PackageTest.package_id == package_id)).all()
            for link in existing_links:
                session.delete(link)
            
            session.delete(pkg)
            session.commit()
            create_audit_log(session, "package", pkg.id, "delete", current_user, old_values=old_values)
            
            return RedirectResponse(url="/packages?success=Package deleted successfully!", 
                                  status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/packages?error=Package not found", 
                              status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        error_msg = str(e).replace(" ", "%20")
        return RedirectResponse(url=f"/packages?error={error_msg}", 
                              status_code=status.HTTP_303_SEE_OTHER)
    
# ===========================
# PARTNER ROUTES
# ===========================

@app.get("/partners", response_class=HTMLResponse)
def partners_page(request: Request, session: Session = Depends(get_session)):
    partners = session.exec(select(Partner).order_by(Partner.id.asc())).all()
    
    partners_json = []
    for partner in partners:
        partner_dict = model_to_dict(partner)
        partners_json.append(partner_dict)
    
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    
    return templates.TemplateResponse("partners.html", {
        "request": request,
        "partners": partners,
        "partners_json": partners_json,
        "message_success": success,
        "message_error": error
    })

@app.post("/partners/create")
def create_partner(
    partner_name: str = Form(...),
    partner_note: Optional[str] = Form(None),
    partner_contact: Optional[str] = Form(None),
    partner_weight: Optional[float] = Form(None),
    request: Request = None,
    session: Session = Depends(get_session)
):
    try:
        current_user = get_current_user(request, session)
        
        new_partner = Partner(
            partner_name=partner_name,
            partner_note=partner_note,
            partner_contact=partner_contact,
            partner_weight=partner_weight if partner_weight else None,
            is_active=True,
            created_by=current_user.id if current_user else None
        )
        session.add(new_partner)
        session.commit()
        session.refresh(new_partner)
        create_audit_log(session, "partner", new_partner.id, "create", current_user, new_values=model_to_dict(new_partner))
        
        return RedirectResponse(url="/partners?success=Partner saved successfully!", 
                              status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        error_msg = str(e).replace(" ", "%20")
        return RedirectResponse(url=f"/partners?error={error_msg}", 
                              status_code=status.HTTP_303_SEE_OTHER)

@app.post("/partners/update/{partner_id}")
def update_partner(
    partner_id: int,
    partner_name: str = Form(...),
    partner_note: Optional[str] = Form(None),
    partner_contact: Optional[str] = Form(None),
    partner_weight: Optional[float] = Form(None),
    request: Request = None,
    session: Session = Depends(get_session)
):
    try:
        current_user = get_current_user(request, session)
        partner = session.get(Partner, partner_id)
        
        if partner:
            old_values = model_to_dict(partner)
            
            partner.partner_name = partner_name
            partner.partner_note = partner_note
            partner.partner_contact = partner_contact
            partner.partner_weight = partner_weight if partner_weight else None
            partner.edited_by = current_user.id if current_user else None
            partner.edited_at = datetime.utcnow()
            
            session.add(partner)
            session.commit()
            session.refresh(partner)
            create_audit_log(session, "partner", partner.id, "update", current_user, old_values=old_values, new_values=model_to_dict(partner))
            
            return RedirectResponse(url="/partners?success=Partner updated successfully!", 
                                  status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/partners?error=Partner not found", 
                              status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        error_msg = str(e).replace(" ", "%20")
        return RedirectResponse(url=f"/partners?error={error_msg}", 
                              status_code=status.HTTP_303_SEE_OTHER)

@app.get("/partners/delete/{partner_id}")
def delete_partner(partner_id: int, request: Request, session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        partner = session.get(Partner, partner_id)
        
        if partner:
            old_values = model_to_dict(partner)
            session.delete(partner)
            session.commit()
            create_audit_log(session, "partner", partner.id, "delete", current_user, old_values=old_values)
            
            return RedirectResponse(url="/partners?success=Partner deleted successfully!", 
                                  status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/partners?error=Partner not found", 
                              status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        error_msg = str(e).replace(" ", "%20")
        return RedirectResponse(url=f"/partners?error={error_msg}", 
                              status_code=status.HTTP_303_SEE_OTHER)
    
# ===========================
# PROVINCE ROUTES
# ===========================

@app.get("/provinces", response_class=HTMLResponse)
def provinces_page(request: Request, session: Session = Depends(get_session)):
    provinces = session.exec(select(Province).order_by(Province.id.asc())).all()
    
    provinces_json = []
    for province in provinces:
        province_dict = model_to_dict(province)
        provinces_json.append(province_dict)
    
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    
    return templates.TemplateResponse("provinces.html", {
        "request": request,
        "provinces": provinces,
        "provinces_json": provinces_json,
        "message_success": success,
        "message_error": error
    })

@app.post("/provinces/create")
def create_province(
    province_name: str = Form(...),
    request: Request = None,
    session: Session = Depends(get_session)
):
    try:
        current_user = get_current_user(request, session)
        
        new_province = Province(
            province_name=province_name,
            is_active=True,
            created_by=current_user.id if current_user else None
        )
        session.add(new_province)
        session.commit()
        session.refresh(new_province)
        create_audit_log(session, "province", new_province.id, "create", current_user, new_values=model_to_dict(new_province))
        
        return RedirectResponse(url="/provinces?success=Province saved successfully!", 
                              status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        error_msg = str(e).replace(" ", "%20")
        return RedirectResponse(url=f"/provinces?error={error_msg}", 
                              status_code=status.HTTP_303_SEE_OTHER)

@app.post("/provinces/update/{province_id}")
def update_province(
    province_id: int,
    province_name: str = Form(...),
    request: Request = None,
    session: Session = Depends(get_session)
):
    try:
        current_user = get_current_user(request, session)
        province = session.get(Province, province_id)
        
        if province:
            old_values = model_to_dict(province)
            
            province.province_name = province_name
            province.edited_by = current_user.id if current_user else None
            province.edited_at = datetime.utcnow()
            
            session.add(province)
            session.commit()
            session.refresh(province)
            create_audit_log(session, "province", province.id, "update", current_user, old_values=old_values, new_values=model_to_dict(province))
            
            return RedirectResponse(url="/provinces?success=Province updated successfully!", 
                                  status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/provinces?error=Province not found", 
                              status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        error_msg = str(e).replace(" ", "%20")
        return RedirectResponse(url=f"/provinces?error={error_msg}", 
                              status_code=status.HTTP_303_SEE_OTHER)

@app.get("/provinces/delete/{province_id}")
def delete_province(province_id: int, request: Request, session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        province = session.get(Province, province_id)
        
        if province:
            old_values = model_to_dict(province)
            session.delete(province)
            session.commit()
            create_audit_log(session, "province", province.id, "delete", current_user, old_values=old_values)
            
            return RedirectResponse(url="/provinces?success=Province deleted successfully!", 
                                  status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/provinces?error=Province not found", 
                              status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        error_msg = str(e).replace(" ", "%20")
        return RedirectResponse(url=f"/provinces?error={error_msg}", 
                              status_code=status.HTTP_303_SEE_OTHER)
    

# ===========================
# REGION ROUTES
# ===========================

@app.get("/regions", response_class=HTMLResponse)
def regions_page(request: Request, session: Session = Depends(get_session)):
    regions = session.exec(select(Region).order_by(Region.id.asc())).all()
    
    regions_json = []
    for region in regions:
        region_dict = model_to_dict(region)
        regions_json.append(region_dict)
    
    provinces = session.exec(select(Province).where(Province.is_active == True)).all()
    
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    
    return templates.TemplateResponse("regions.html", {
        "request": request,
        "regions": regions,
        "regions_json": regions_json,
        "provinces": provinces,
        "message_success": success,
        "message_error": error
    })

@app.post("/regions/create")
def create_region(
    region_name: str = Form(...),
    province_id: int = Form(...),
    request: Request = None,
    session: Session = Depends(get_session)
):
    try:
        current_user = get_current_user(request, session)
        
        new_region = Region(
            region_name=region_name,
            province_id=province_id,
            is_active=True,
            created_by=current_user.id if current_user else None
        )
        session.add(new_region)
        session.commit()
        session.refresh(new_region)
        create_audit_log(session, "region", new_region.id, "create", current_user, new_values=model_to_dict(new_region))
        
        return RedirectResponse(url="/regions?success=Region saved successfully!", 
                              status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        error_msg = str(e).replace(" ", "%20")
        return RedirectResponse(url=f"/regions?error={error_msg}", 
                              status_code=status.HTTP_303_SEE_OTHER)

@app.post("/regions/update/{region_id}")
def update_region(
    region_id: int,
    region_name: str = Form(...),
    province_id: int = Form(...),
    request: Request = None,
    session: Session = Depends(get_session)
):
    try:
        current_user = get_current_user(request, session)
        region = session.get(Region, region_id)
        
        if region:
            old_values = model_to_dict(region)
            
            region.region_name = region_name
            region.province_id = province_id
            region.edited_by = current_user.id if current_user else None
            region.edited_at = datetime.utcnow()
            
            session.add(region)
            session.commit()
            session.refresh(region)
            create_audit_log(session, "region", region.id, "update", current_user, old_values=old_values, new_values=model_to_dict(region))
            
            return RedirectResponse(url="/regions?success=Region updated successfully!", 
                                  status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/regions?error=Region not found", 
                              status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        error_msg = str(e).replace(" ", "%20")
        return RedirectResponse(url=f"/regions?error={error_msg}", 
                              status_code=status.HTTP_303_SEE_OTHER)

@app.get("/regions/delete/{region_id}")
def delete_region(region_id: int, request: Request, session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        region = session.get(Region, region_id)
        
        if region:
            old_values = model_to_dict(region)
            session.delete(region)
            session.commit()
            create_audit_log(session, "region", region.id, "delete", current_user, old_values=old_values)
            
            return RedirectResponse(url="/regions?success=Region deleted successfully!", 
                                  status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/regions?error=Region not found", 
                              status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        error_msg = str(e).replace(" ", "%20")
        return RedirectResponse(url=f"/regions?error={error_msg}", 
                              status_code=status.HTTP_303_SEE_OTHER)

# ===========================
# LAB INFO ROUTES
# ===========================

import os
import shutil
from fastapi import UploadFile, File

# Create uploads directory if it doesn't exist
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def save_uploaded_file(file: UploadFile, filename: str) -> str:
    """Save uploaded file and return the filename"""
    file_path = os.path.join(UPLOAD_DIR, filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return filename

@app.get("/lab-info", response_class=HTMLResponse)
def lab_info_page(request: Request, session: Session = Depends(get_session)):
    # Get the first (and should be only) lab info record
    lab_info = session.exec(select(LabInfo).limit(1)).first()
    
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    
    return templates.TemplateResponse("lab_info.html", {
        "request": request,
        "lab_info": lab_info,
        "edit_mode": False,
        "message_success": success,
        "message_error": error
    })

@app.get("/lab-info/edit", response_class=HTMLResponse)
def lab_info_edit_page(request: Request, session: Session = Depends(get_session)):
    # Get the first (and should be only) lab info record
    lab_info = session.exec(select(LabInfo).limit(1)).first()
    
    return templates.TemplateResponse("lab_info.html", {
        "request": request,
        "lab_info": lab_info,
        "edit_mode": True
    })

@app.post("/lab-info/update")
async def update_lab_info(
    request: Request,
    lab_name: str = Form(...),
    lab_title: Optional[str] = Form(None),
    first_doctor_name: Optional[str] = Form(None),
    second_doctor_name: Optional[str] = Form(None),
    lab_address: Optional[str] = Form(None),
    lab_phone_1: str = Form(...),
    lab_phone_2: Optional[str] = Form(None),
    whatsapp_api: Optional[str] = Form(None),
    whatsapp_token: Optional[str] = Form(None),
    telegram_api: Optional[str] = Form(None),
    telegram_token: Optional[str] = Form(None),
    lab_email: Optional[str] = Form(None),
    lab_website: Optional[str] = Form(None),
    lab_note_1: Optional[str] = Form(None),
    lab_note_2: Optional[str] = Form(None),
    lab_logo: Optional[UploadFile] = File(None),
    lab_qr_1: Optional[UploadFile] = File(None),
    lab_qr_2: Optional[UploadFile] = File(None),
    lab_stamp_1: Optional[UploadFile] = File(None),
    lab_stamp_2: Optional[UploadFile] = File(None),
    lab_signature_1: Optional[UploadFile] = File(None),
    lab_signature_2: Optional[UploadFile] = File(None),
    lab_image_1: Optional[UploadFile] = File(None),
    lab_image_2: Optional[UploadFile] = File(None),
    session: Session = Depends(get_session)
):
    try:
        current_user = get_current_user(request, session)
        
        # Get existing lab info or create new
        lab_info = session.exec(select(LabInfo).limit(1)).first()
        
        if not lab_info:
            lab_info = LabInfo()
            session.add(lab_info)
        
        # Update text fields
        lab_info.lab_name = lab_name
        lab_info.lab_title = lab_title
        lab_info.first_doctor_name = first_doctor_name
        lab_info.second_doctor_name = second_doctor_name
        lab_info.lab_address = lab_address
        lab_info.lab_phone_1 = lab_phone_1
        lab_info.lab_phone_2 = lab_phone_2
        lab_info.whatsapp_api = whatsapp_api
        lab_info.whatsapp_token = whatsapp_token
        lab_info.telegram_api = telegram_api
        lab_info.telegram_token = telegram_token
        lab_info.lab_email = lab_email
        lab_info.lab_website = lab_website
        lab_info.lab_note_1 = lab_note_1
        lab_info.lab_note_2 = lab_note_2
        lab_info.edited_by = current_user.id if current_user else None
        lab_info.edited_at = datetime.utcnow()
        
        # Handle file uploads
        import uuid
        
        files_to_upload = [
            ('lab_logo', lab_logo),
            ('lab_qr_1', lab_qr_1),
            ('lab_qr_2', lab_qr_2),
            ('lab_stamp_1', lab_stamp_1),
            ('lab_stamp_2', lab_stamp_2),
            ('lab_signature_1', lab_signature_1),
            ('lab_signature_2', lab_signature_2),
            ('lab_image_1', lab_image_1),
            ('lab_image_2', lab_image_2),
        ]
        
        for field_name, file in files_to_upload:
            if file and file.filename:
                # Generate unique filename
                ext = os.path.splitext(file.filename)[1]
                unique_filename = f"{field_name}_{uuid.uuid4().hex}{ext}"
                
                # Save file
                saved_filename = save_uploaded_file(file, unique_filename)
                
                # Update field
                setattr(lab_info, field_name, saved_filename)
        
        session.commit()
        session.refresh(lab_info)
        
        return RedirectResponse(url="/lab-info?success=Lab information updated successfully!", 
                              status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        error_msg = str(e).replace(" ", "%20")
        return RedirectResponse(url=f"/lab-info?error={error_msg}", 
                              status_code=status.HTTP_303_SEE_OTHER)

# ===========================
# PATIENT REGISTRATION ROUTES
# ===========================

@app.get("/patient-registration", response_class=HTMLResponse)
def patient_registration_page(request: Request, session: Session = Depends(get_session)):
    provinces = session.exec(select(Province).where(Province.is_active == True)).all()
    partners = session.exec(select(Partner).where(Partner.is_active == True)).all()
    tests = session.exec(select(TestDefinition).where(TestDefinition.is_available == True)).all()
    packages = session.exec(select(Package).where(Package.is_active == True)).all()
    
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    
    return templates.TemplateResponse("patient_registration.html", {
        "request": request,
        "provinces": provinces,
        "partners": partners,
        "tests": tests,
        "packages": packages,
        "message_success": success,
        "message_error": error
    })

@app.get("/api/regions")
def get_regions_by_province(province_id: int, session: Session = Depends(get_session)):
    regions = session.exec(select(Region).where(Region.province_id == province_id)).all()
    return [{"id": r.id, "region_name": r.region_name} for r in regions]

@app.get("/api/package-tests/{package_id}")
def get_package_tests(package_id: int, session: Session = Depends(get_session)):
    package_tests = session.exec(select(PackageTest).where(PackageTest.package_id == package_id)).all()
    return {"test_ids": [pt.test_id for pt in package_tests]}

@app.post("/patient-registration/create")
async def create_patient_registration(
    request: Request,
    patient_id: str = Form(...),
    full_name: str = Form(...),
    gender: str = Form(...),
    date_of_birth: str = Form(...),
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
    selected_items: str = Form(...),  # JSON string
    discount_percentage: Optional[float] = Form(None),
    discount_amount: Optional[float] = Form(None),
    discount_note: Optional[str] = Form(None),
    received_amount: Optional[float] = Form(None),
    session: Session = Depends(get_session)
):
    try:
        current_user = get_current_user(request, session)
        import json
        
        # Parse selected items
        items = json.loads(selected_items)
        
        # Create patient
        new_patient = Patient(
            patient_id=patient_id,
            full_name=full_name,
            gender=gender,
            date_of_birth=datetime.strptime(date_of_birth, "%Y-%m-%d"),
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
        
        # Generate Visit ID (PatientID + 3 digits)
        visit_count = session.exec(select(PatientVisit).where(PatientVisit.patient_id == new_patient.id)).count()
        visit_id = patient_id + str(visit_count).zfill(3)
        
        new_visit = PatientVisit(
            visit_id=visit_id,
            patient_id=new_patient.id,
            created_by=current_user.id if current_user else None
        )
        session.add(new_visit)
        session.commit()
        session.refresh(new_visit)
        
        # Create orders for selected items
        for item in items:
            if item['type'] == 'test':
                order = Order(
                    order_number=f"ORD-{visit_id}-{item['id']}",
                    patient_id=new_patient.id,
                    test_id=item['id'],
                    visit_id=new_visit.id,
                    ordered_by=current_user.id if current_user else None
                )
                session.add(order)
            elif item['type'] == 'package':
                # Get all tests in package
                package_tests = session.exec(select(PackageTest).where(PackageTest.package_id == item['id'])).all()
                for pt in package_tests:
                    order = Order(
                        order_number=f"ORD-{visit_id}-{pt.test_id}",
                        patient_id=new_patient.id,
                        test_id=pt.test_id,
                        visit_id=new_visit.id,
                        ordered_by=current_user.id if current_user else None
                    )
                    session.add(order)
        
        session.commit()
        
        return RedirectResponse(url="/patient-registration?success=Patient registered successfully!", 
                              status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        error_msg = str(e).replace(" ", "%20")
        return RedirectResponse(url=f"/patient-registration?error={error_msg}", 
                              status_code=status.HTTP_303_SEE_OTHER) 


# ===========================
# API ENDPOINTS
# ===========================

@app.get("/api/patients")
def list_patients_api(session: Session = Depends(get_session)):
    return session.exec(select(Patient)).all()

@app.get("/api/parameters")
def list_parameters_api(session: Session = Depends(get_session)):
    return session.exec(select(Parameter)).all()

@app.get("/api/departments")
def list_departments_api(session: Session = Depends(get_session)):
    return session.exec(select(Department)).all()

@app.get("/api/devices")
def list_devices_api(session: Session = Depends(get_session)):
    return session.exec(select(Device)).all()

@app.get("/api/sample-types")
def list_sample_types_api(session: Session = Depends(get_session)):
    return session.exec(select(SampleType)).all()

@app.get("/api/report-notes")
def list_report_notes_api(session: Session = Depends(get_session)):
    return session.exec(select(ReportNote)).all()

@app.get("/api/tests")
def list_tests_api(session: Session = Depends(get_session)):
    return session.exec(select(TestDefinition)).all()

@app.get("/api/formulas")
def list_formulas_api(session: Session = Depends(get_session)):
    return session.exec(select(Formula)).all()

@app.get("/api/audit-logs")
def list_audit_logs_api(session: Session = Depends(get_session)):
    return session.exec(select(AuditLog).order_by(AuditLog.created_at.desc())).all()

