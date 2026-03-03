# main.py
from fastapi import FastAPI, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
import json

from database import create_db_and_tables, get_session, engine
from models import User, Patient, TestCatalog, Order, Result, Parameter, Department, Device, SampleType, ReportNote, TestDefinition, TestDevice, TestParameter, AuditLog

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
# TEST DEFINITION ROUTES (COMPLETELY FIXED)
# ===========================

@app.get("/tests", response_class=HTMLResponse)
def tests_page(request: Request, session: Session = Depends(get_session)):
    # Get ALL tests - no filtering
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

@app.get("/api/audit-logs")
def list_audit_logs_api(session: Session = Depends(get_session)):
    return session.exec(select(AuditLog).order_by(AuditLog.created_at.desc())).all()