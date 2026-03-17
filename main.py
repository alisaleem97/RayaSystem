# main.py
from fastapi import FastAPI, Depends, Request, Form, HTTPException, status, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, List, Any
import json
import base64
from io import BytesIO
import os
import shutil
import uuid
import tempfile
from database import create_db_and_tables, get_session, engine
from models import (
    User, Patient, TestCatalog, Order, Result, Parameter, Department, Device,
    SampleType, ReportNote, TestDefinition, TestDevice, TestParameter, AuditLog,
    Formula, FormulaItem, TestRange, TestResultType, Package, PackageTest,
    Partner, Province, Region, LabInfo, PatientVisit, PrintTemplate,
)

# Setup templates
templates = Jinja2Templates(directory="templates")

# Create uploads directory
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ===========================
# HELPER FUNCTIONS
# ===========================
def calculate_age(dob: datetime) -> int:
    """Calculate age from date of birth"""
    today = datetime.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

def model_to_dict(model):
    """Convert SQLModel object to dict"""
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

def get_current_user(request: Request, session: Session) -> Optional[User]:
    """Get current logged-in user"""
    user = session.exec(select(User).where(User.username == "admin")).first()
    return user

def create_audit_log(session: Session, table_name: str, record_id: int, action: str,
                     user: User, old_values: dict = None, new_values: dict = None):
    """Create audit log entry"""
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

def save_uploaded_file(file, filename: str) -> str:
    """Save uploaded file and return the filename"""
    file_path = os.path.join(UPLOAD_DIR, filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return filename

# ===========================
# BARCODE GENERATOR (LOCAL) - 100% OFFLINE
# ===========================
def generate_barcode_base64(patient_id: str) -> str:
    """Generate linear barcode (Code128) as base64 encoded image - 100% OFFLINE"""
    try:
        from barcode import Code128
        from barcode.writer import ImageWriter
        print(f"🔍 Starting barcode generation for: {patient_id}")
        
        # Create barcode
        code = Code128(patient_id, writer=ImageWriter())
        print(f"✅ Barcode object created")
        
        # Use tempfile to avoid path issues
        temp_dir = tempfile.gettempdir()
        temp_filename = os.path.join(temp_dir, f"temp_barcode_{patient_id}")
        
        # Save barcode to file
        filepath = code.save(temp_filename, options={
            'module_width': 0.4,
            'module_height': 15.0,
            'font_size': 10,
            'text_distance': 5.0,
            'quiet_zone': 6.5,
            'write_text': True,
        })
        print(f"✅ Barcode saved to: {filepath}")
        
        # Check if file exists (try with and without .png extension)
        png_path = filepath if filepath.endswith('.png') else filepath + '.png'
        if not os.path.exists(png_path):
            # Try to find the file
            for ext in ['.png', '']:
                test_path = filepath + ext
                if os.path.exists(test_path):
                    png_path = test_path
                    break
        
        if not os.path.exists(png_path):
            raise FileNotFoundError(f"Barcode file not created at: {png_path}")
        
        # Read the file and convert to base64
        file_size = os.path.getsize(png_path)
        print(f"✅ File size: {file_size} bytes")
        
        with open(png_path, 'rb') as f:
            barcode_base64 = base64.b64encode(f.read()).decode()
        print(f"✅ Base64 length: {len(barcode_base64)} characters")
        
        # Delete temporary file
        if os.path.exists(png_path):
            os.remove(png_path)
        print(f"✅ Temporary file deleted")
        print(f"✅ Barcode generated successfully for {patient_id}")
        
        return f"data:image/png;base64,{barcode_base64}"
    
    except ImportError as e:
        print(f"❌ IMPORT ERROR: python-barcode library not found!")
        print(f"❌ Error: {e}")
        print(f"💡 Run: pip install python-barcode pillow")
        # Fallback to external API
        return f"https://bwipjs-api.metafloor.com/?bcid=code128&text={patient_id}&scale=3&height=10&includetext"
    
    except Exception as e:
        print(f"❌ GENERATION ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        # Fallback to external API
        return f"https://bwipjs-api.metafloor.com/?bcid=code128&text={patient_id}&scale=3&height=10&includetext"

# ===========================
# APP LIFESPAN
# ===========================
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
# STATIC FILE SERVING (For uploaded images)
# ===========================
from fastapi.staticfiles import StaticFiles

# Mount the uploads directory to serve static files
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
# Add helper to templates
templates.env.globals["calculate_age"] = calculate_age

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
    return templates.TemplateResponse("departments.html", {
        "request": request, "departments": departments,
        "departments_json": departments_dict, "message_success": success, "message_error": error
    })

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
    return templates.TemplateResponse("sample_types.html", {
        "request": request, "sample_types": sample_types,
        "sample_types_json": sample_types_dict, "message_success": success, "message_error": error
    })

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
    return templates.TemplateResponse("devices.html", {
        "request": request, "devices": devices,
        "devices_json": devices_dict, "message_success": success, "message_error": error
    })

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
    return templates.TemplateResponse("parameters.html", {
        "request": request, "parameters": parameters,
        "parameters_json": parameters_dict, "message_success": success, "message_error": error
    })

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
        "request": request, "report_notes": report_notes,
        "report_notes_json": report_notes_dict, "message_success": success, "message_error": error
    })

@app.post("/report-notes/create")
def create_report_note(note_name: str = Form(...), note_content: str = Form(...),
                       request: Request = None, session: Session = Depends(get_session)):
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

@app.post("/report-notes/update/{note_id}")
def update_report_note(note_id: int, note_name: str = Form(...), note_content: str = Form(...),
                       request: Request = None, session: Session = Depends(get_session)):
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
            return RedirectResponse(url="/report-notes?success=Report note updated successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/report-notes?error=Report note not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/report-notes?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

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
            return RedirectResponse(url="/report-notes?success=Report note deleted successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/report-notes?error=Report note not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/report-notes?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

# ===========================
# TEST DEFINITION ROUTES
# ===========================
@app.get("/tests", response_class=HTMLResponse)
def tests_page(request: Request, session: Session = Depends(get_session)):
    tests = session.exec(select(TestDefinition).order_by(TestDefinition.id.asc())).all()
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

@app.post("/tests/create")
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

@app.post("/tests/update/{test_id}")
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

@app.get("/tests/delete/{test_id}")
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
@app.get("/formulas", response_class=HTMLResponse)
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

@app.post("/formulas/create")
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

@app.post("/formulas/update/{formula_id}")
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

@app.post("/test-ranges/create")
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

@app.post("/test-ranges/update/{range_id}")
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
            return RedirectResponse(url="/test-ranges?success=Test range deleted successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/test-ranges?error=Test range not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/test-ranges?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

# ===========================
# TEST RESULT TYPE ROUTES
# ===========================
@app.get("/test-result-types", response_class=HTMLResponse)
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

@app.post("/test-result-types/create")
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

@app.post("/test-result-types/update/{result_type_id}")
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
            return RedirectResponse(url="/test-result-types?success=Result type deleted successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/test-result-types?error=Result type not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/test-result-types?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

# ===========================
# PACKAGE ROUTES
# ===========================
@app.get("/packages", response_class=HTMLResponse)
def packages_page(request: Request, session: Session = Depends(get_session)):
    packages = session.exec(select(Package).order_by(Package.id.asc())).all()
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

@app.post("/packages/create")
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

@app.post("/packages/update/{package_id}")
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

@app.get("/packages/delete/{package_id}")
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

# ===========================
# PARTNER ROUTES
# ===========================
@app.get("/partners", response_class=HTMLResponse)
def partners_page(request: Request, session: Session = Depends(get_session)):
    partners = session.exec(select(Partner).order_by(Partner.id.asc())).all()
    partners_json = [model_to_dict(p) for p in partners]
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse("partners.html", {
        "request": request, "partners": partners, "partners_json": partners_json,
        "message_success": success, "message_error": error
    })

@app.post("/partners/create")
def create_partner(partner_name: str = Form(...), partner_note: Optional[str] = Form(None),
                   partner_contact: Optional[str] = Form(None), partner_weight: Optional[float] = Form(None),
                   request: Request = None, session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        new_partner = Partner(
            partner_name=partner_name, partner_note=partner_note,
            partner_contact=partner_contact, partner_weight=partner_weight if partner_weight else None,
            is_active=True, created_by=current_user.id if current_user else None
        )
        session.add(new_partner)
        session.commit()
        session.refresh(new_partner)
        create_audit_log(session, "partner", new_partner.id, "create", current_user, new_values=model_to_dict(new_partner))
        return RedirectResponse(url="/partners?success=Partner saved successfully!", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/partners?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/partners/update/{partner_id}")
def update_partner(partner_id: int, partner_name: str = Form(...), partner_note: Optional[str] = Form(None),
                   partner_contact: Optional[str] = Form(None), partner_weight: Optional[float] = Form(None),
                   request: Request = None, session: Session = Depends(get_session)):
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
            return RedirectResponse(url="/partners?success=Partner updated successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/partners?error=Partner not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/partners?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

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
            return RedirectResponse(url="/partners?success=Partner deleted successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/partners?error=Partner not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/partners?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

# ===========================
# PROVINCE ROUTES
# ===========================
@app.get("/provinces", response_class=HTMLResponse)
def provinces_page(request: Request, session: Session = Depends(get_session)):
    provinces = session.exec(select(Province).order_by(Province.id.asc())).all()
    provinces_json = [model_to_dict(p) for p in provinces]
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse("provinces.html", {
        "request": request, "provinces": provinces, "provinces_json": provinces_json,
        "message_success": success, "message_error": error
    })

@app.post("/provinces/create")
def create_province(province_name: str = Form(...), request: Request = None,
                    session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        new_province = Province(province_name=province_name, is_active=True,
                               created_by=current_user.id if current_user else None)
        session.add(new_province)
        session.commit()
        session.refresh(new_province)
        create_audit_log(session, "province", new_province.id, "create", current_user, new_values=model_to_dict(new_province))
        return RedirectResponse(url="/provinces?success=Province saved successfully!", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/provinces?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/provinces/update/{province_id}")
def update_province(province_id: int, province_name: str = Form(...), request: Request = None,
                    session: Session = Depends(get_session)):
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
            return RedirectResponse(url="/provinces?success=Province updated successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/provinces?error=Province not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/provinces?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

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
            return RedirectResponse(url="/provinces?success=Province deleted successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/provinces?error=Province not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/provinces?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

# ===========================
# REGION ROUTES
# ===========================
@app.get("/regions", response_class=HTMLResponse)
def regions_page(request: Request, session: Session = Depends(get_session)):
    regions = session.exec(select(Region).order_by(Region.id.asc())).all()
    regions_json = [model_to_dict(r) for r in regions]
    provinces = session.exec(select(Province).where(Province.is_active == True)).all()
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse("regions.html", {
        "request": request, "regions": regions, "regions_json": regions_json,
        "provinces": provinces, "message_success": success, "message_error": error
    })

@app.post("/regions/create")
def create_region(region_name: str = Form(...), province_id: int = Form(...),
                  request: Request = None, session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        new_region = Region(region_name=region_name, province_id=province_id, is_active=True,
                           created_by=current_user.id if current_user else None)
        session.add(new_region)
        session.commit()
        session.refresh(new_region)
        create_audit_log(session, "region", new_region.id, "create", current_user, new_values=model_to_dict(new_region))
        return RedirectResponse(url="/regions?success=Region saved successfully!", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/regions?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/regions/update/{region_id}")
def update_region(region_id: int, region_name: str = Form(...), province_id: int = Form(...),
                  request: Request = None, session: Session = Depends(get_session)):
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
            return RedirectResponse(url="/regions?success=Region updated successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/regions?error=Region not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/regions?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

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
            return RedirectResponse(url="/regions?success=Region deleted successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/regions?error=Region not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/regions?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

# ===========================
# LAB INFO ROUTES
# ===========================
@app.get("/lab-info", response_class=HTMLResponse)
def lab_info_page(request: Request, session: Session = Depends(get_session)):
    lab_info = session.exec(select(LabInfo).limit(1)).first()
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse("lab_info.html", {
        "request": request, "lab_info": lab_info, "edit_mode": False,
        "message_success": success, "message_error": error
    })

@app.get("/lab-info/edit", response_class=HTMLResponse)
def lab_info_edit_page(request: Request, session: Session = Depends(get_session)):
    lab_info = session.exec(select(LabInfo).limit(1)).first()
    return templates.TemplateResponse("lab_info.html", {
        "request": request, "lab_info": lab_info, "edit_mode": True
    })

@app.post("/lab-info/update")
async def update_lab_info(request: Request, lab_name: str = Form(...), lab_title: Optional[str] = Form(None),
                          first_doctor_name: Optional[str] = Form(None), second_doctor_name: Optional[str] = Form(None),
                          lab_address: Optional[str] = Form(None), lab_phone_1: str = Form(...),
                          lab_phone_2: Optional[str] = Form(None), whatsapp_api: Optional[str] = Form(None),
                          whatsapp_token: Optional[str] = Form(None), telegram_api: Optional[str] = Form(None),
                          telegram_token: Optional[str] = Form(None), lab_email: Optional[str] = Form(None),
                          lab_website: Optional[str] = Form(None), lab_note_1: Optional[str] = Form(None),
                          lab_note_2: Optional[str] = Form(None), lab_logo: Optional[UploadFile] = File(None),
                          lab_qr_1: Optional[UploadFile] = File(None), lab_qr_2: Optional[UploadFile] = File(None),
                          lab_stamp_1: Optional[UploadFile] = File(None), lab_stamp_2: Optional[UploadFile] = File(None),
                          lab_signature_1: Optional[UploadFile] = File(None), lab_signature_2: Optional[UploadFile] = File(None),
                          lab_image_1: Optional[UploadFile] = File(None), lab_image_2: Optional[UploadFile] = File(None),
                          session: Session = Depends(get_session)):
    try:
        current_user = get_current_user(request, session)
        lab_info = session.exec(select(LabInfo).limit(1)).first()
        if not lab_info:
            lab_info = LabInfo()
            session.add(lab_info)
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
        files_to_upload = [
            ('lab_logo', lab_logo), ('lab_qr_1', lab_qr_1), ('lab_qr_2', lab_qr_2),
            ('lab_stamp_1', lab_stamp_1), ('lab_stamp_2', lab_stamp_2),
            ('lab_signature_1', lab_signature_1), ('lab_signature_2', lab_signature_2),
            ('lab_image_1', lab_image_1), ('lab_image_2', lab_image_2),
        ]
        for field_name, file in files_to_upload:
            if file and file.filename:
                ext = os.path.splitext(file.filename)[1]
                unique_filename = f"{field_name}_{uuid.uuid4().hex}{ext}"
                saved_filename = save_uploaded_file(file, unique_filename)
                setattr(lab_info, field_name, saved_filename)
        session.commit()
        session.refresh(lab_info)
        return RedirectResponse(url="/lab-info?success=Lab information updated successfully!", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/lab-info?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

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
    last_patient_id = request.query_params.get("patient_id")
    return templates.TemplateResponse("patient_registration.html", {
        "request": request, "provinces": provinces, "partners": partners,
        "tests": tests, "packages": packages,
        "message_success": success, "message_error": error,
        "last_patient_id": last_patient_id
    })

@app.get("/api/regions")
def get_regions_by_province(province_id: int, session: Session = Depends(get_session)):
    regions = session.exec(select(Region).where(Region.province_id == province_id)).all()
    return [{"id": r.id, "region_name": r.region_name} for r in regions]

@app.get("/api/package-tests/{package_id}")
def get_package_tests(package_id: int, session: Session = Depends(get_session)):
    package_tests = session.exec(select(PackageTest).where(PackageTest.package_id == package_id)).all()
    return {"test_ids": [pt.test_id for pt in package_tests]}

@app.get("/api/generate-patient-id")
def generate_patient_id_api(session: Session = Depends(get_session)):
    try:
        labId = 1
        baseNumber = 100000
        last_patient = session.exec(select(Patient).order_by(Patient.id.desc()).limit(1)).first()
        if last_patient and last_patient.patient_id:
            try:
                last_number = int(last_patient.patient_id[1:])
                next_number = last_number + 1
            except:
                next_number = baseNumber
        else:
            next_number = baseNumber
        patient_id = str(labId) + str(next_number).zfill(6)
        return {"patient_id": patient_id}
    except Exception as e:
        return {"error": str(e)}

# ===========================
# ✅ UPDATED: PATIENT REGISTRATION CREATE (WITH PRICE SNAPSHOT)
# ===========================
@app.post("/patient-registration/create")
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
        
        # Calculate total price from items
        total_price = sum(float(item.get('price', 0)) for item in items)
        
        # Apply discount
        final_total = total_price
        discount_amt = float(discount_amount) if discount_amount else 0.0
        if discount_percentage:
            final_total = total_price * (1 - discount_percentage / 100)
            discount_amt = total_price - final_total
        elif discount_amount:
            final_total = total_price - float(discount_amount)
        
        # Calculate remaining amount
        received = float(received_amount) if received_amount else 0.0
        remaining = max(0, final_total - received)
        
        # Create patient
        new_patient = Patient(
            patient_id=patient_id,
            full_name=full_name,
            gender=gender,
            ate_of_birth=datetime.strptime(date_of_birth, "%Y-%m-%d") if date_of_birth else None,  # ✅ Handle None
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
        
        # Generate Visit ID
        visits = session.exec(select(PatientVisit).where(PatientVisit.patient_id == new_patient.id)).all()
        visit_count = len(visits)
        visit_id = patient_id + str(visit_count).zfill(3)
        
        # ✅ SAVE PAYMENT INFO TO PATIENTVISIT
        new_visit = PatientVisit(
            visit_id=visit_id,
            patient_id=new_patient.id,
            created_by=current_user.id if current_user else None,
            received_amount=received,
            discount_amount=discount_amt,
            remaining_amount=remaining
        )
        session.add(new_visit)
        session.commit()
        session.refresh(new_visit)
        
        # ✅ Calculate discount ratio for proportional distribution
        discount_ratio = discount_amt / total_price if total_price > 0 else 0
        
        # Process orders WITH PRICE SNAPSHOT
        for item in items:
            if item['type'] == 'test':
                # ✅ CAPTURE PRICE AT ORDER TIME (audit compliance)
                test = session.get(TestDefinition, item['id'])
                unit_price = test.price if test else 0.0
                
                # ✅ Calculate proportional discount for this order
                order_discount = unit_price * discount_ratio
                final_price = unit_price - order_discount
                
                order = Order(
                    order_number=f"ORD-{visit_id}-{item['id']}",
                    patient_id=new_patient.id,
                    test_id=item['id'],
                    visit_id=new_visit.id,
                    ordered_by=current_user.id if current_user else None,
                    unit_price=unit_price,        # ✅ SNAPSHOT
                    discount_amount=order_discount,  # ✅ SNAPSHOT
                    final_price=final_price
               # ✅ SNAPSHOT
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
                price_per_test = package_price / num_tests if num_tests > 0 else 0.
                for pt in package_tests:
                    test = session.get(TestDefinition, pt.test_id)
                    unit_price = price_per_test
                    
                    # ✅ Calculate proportional discount for this order
                    order_discount = unit_price * discount_ratio
                    final_price = unit_price - order_discount
                    
                    order = Order(
                        order_number=f"ORD-{visit_id}-{pt.test_id}",
                        patient_id=new_patient.id,
                        test_id=pt.test_id,
                        visit_id=new_visit.id,
                        ordered_by=current_user.id if current_user else None,
                        unit_price=unit_price,        # ✅ SNAPSHOT
                        discount_amount=order_discount,  # ✅ SNAPSHOT
                        final_price=final_price,
                        package_name=package_name       # ✅ SNAPSHOT
                    )
                    session.add(order)
        
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
# PRINT DESIGNER ROUTES
# ===========================
@app.get("/print-barcode-designer", response_class=HTMLResponse)
def print_barcode_designer(request: Request):
    return templates.TemplateResponse("print_barcode_designer.html", {"request": request})

@app.get("/print-receipt-designer", response_class=HTMLResponse)
def print_receipt_designer(request: Request):
    return templates.TemplateResponse("print_receipt_designer.html", {"request": request})

# ===========================
# PRINT TEMPLATE API ROUTES
# ===========================
@app.post("/api/print-template/save")
async def save_print_template(request: Request, session: Session = Depends(get_session)):
    try:
        data = await request.json()
        current_user = get_current_user(request, session)
        existing = session.exec(select(PrintTemplate).where(PrintTemplate.template_name == data['template_name'])).first()
        if existing:
            existing.paper_width = data['paper_width']
            existing.paper_height = data['paper_height']
            existing.margin = data['margin']
            existing.elements = data['elements']
            existing.edited_by = current_user.id if current_user else None
            existing.edited_at = datetime.utcnow()
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

@app.get("/api/print-template/load/{template_name}")
def load_print_template(template_name: str, session: Session = Depends(get_session)):
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

# ===========================
# ✅ NEW: PATIENT ORDERS API (FOR RECEIPT WITH PRICE SNAPSHOT)
# ===========================
@app.get("/api/patient-orders/{patient_id}")
def get_patient_orders_api(patient_id: str, session: Session = Depends(get_session)):
    """Get patient orders with price snapshot for receipt printing"""
    try:
        patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()
        if not patient:
            return {"success": False, "error": "Patient not found"}
        
        orders = session.exec(select(Order).where(Order.patient_id == patient.id)).all()
        
        orders_data = []
        for order in orders:
            test = session.get(TestDefinition, order.test_id)
            orders_data.append({
                "order_id": order.id,
                "order_number": order.order_number,
                "test_id": order.test_id,
                "test_name": test.test_name if test else 'Unknown',
                "package_name": order.package_name or None,  # ✅ ADD THIS LINE
                # ✅ PRICE SNAPSHOT (audit compliance)
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
# ✅ NEW: LAB INFO API (JSON FOR FRONTEND)
# ===========================
@app.get("/api/lab-info")
def get_lab_info_api(session: Session = Depends(get_session)):
    """Return lab branding data as JSON for frontend/printing"""
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
            "lab_name": "NexLab Medical Center",
            "lab_title": "Medical Laboratory",
            "lab_address": "",
            "lab_phone_1": "",
            "lab_phone_2": "",
            "lab_email": "",
            "lab_website": "",
            "lab_currency": "$",
            "first_doctor_name": "",
            "second_doctor_name": "",
            "lab_note_1": "",
            "lab_note_2": "",
            "lab_logo": "",
            "lab_qr_1": "",
            "lab_qr_2": "",
            "lab_stamp_1": "",
            "lab_stamp_2": "",
            "lab_signature_1": "",
            "lab_signature_2": "",
        }
    }

# ===========================
# PATIENT API ENDPOINTS (WITH ACCOUNTING DATA)
# ===========================
@app.get("/api/patient/{patient_id}")
def get_patient_api(patient_id: str, session: Session = Depends(get_session)):
    """Get patient data by patient_id with accounting info AND tests grouped by sample type"""
    try:
        patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()
        if not patient:
            return {"error": "Patient not found"}
        
        # Get patient's orders/tests
        orders = session.exec(select(Order).where(Order.patient_id == patient.id)).all()
        
        # ✅ Build test names array
        test_names = [order.test.test_name if order.test else 'Unknown' for order in orders]
        
        # ✅ Group tests by sample type (FOR BARCODE PRINTING)
        tests_by_sample_type = {}
        for order in orders:
            if order.test:
                sample_type_name = "Unknown"
                if order.test.sample_type_id:
                    sample_type = session.get(SampleType, order.test.sample_type_id)
                    if sample_type:
                        sample_type_name = sample_type.sample_name
                if sample_type_name not in tests_by_sample_type:
                    tests_by_sample_type[sample_type_name] = []
                tests_by_sample_type[sample_type_name].append(order.test.test_name)
        
        # Get visit info with PAYMENT DATA
        visits = session.exec(select(PatientVisit).where(PatientVisit.patient_id == patient.id)).all()
        visit_id = visits[0].visit_id if visits else patient.patient_id + '000'
        
        # ✅ GET ACTUAL PAYMENT DATA FROM PATIENTVISIT
        received_amount = visits[0].received_amount if visits else 0.0
        discount_amount = visits[0].discount_amount if visits else 0.0
        remaining_amount = visits[0].remaining_amount if visits else 0.0
        
        # Calculate total from orders (using snapshot prices)
        total_amount = sum([float(order.final_price) if order.final_price else 0 for order in orders])
        
        return {
            "patient_id": patient.patient_id,
            "full_name": patient.full_name,
            "gender": patient.gender,
            "age": patient.age,
            "age_unit": patient.age_unit,
            "phone_key": patient.phone_key,
            "phone_number": patient.phone_number,
            "tests": test_names,  # Simple array for receipt
            "tests_by_sample_type": tests_by_sample_type,  # ✅ Grouped by sample type (for barcode)
            "visit_id": visit_id,
            "visit_date": visits[0].visit_date.isoformat() if visits and visits[0].visit_date else None,
            # ✅ Accounting information (for receipt)
            "total_amount": round(total_amount, 2),
            "discount_amount": round(discount_amount, 2),
            "paid_amount": round(received_amount, 2),
            "remain_amount": round(remaining_amount, 2)
        }
    except Exception as e:
        print(f"❌ Error in get_patient_api: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

# ===========================
# BARCODE API FOR JAVASCRIPT
# ===========================
@app.get("/api/barcode/{patient_id}")
def get_barcode_api(patient_id: str, session: Session = Depends(get_session)):
    """Return barcode as base64 for JavaScript (works offline)"""
    barcode_data = generate_barcode_base64(patient_id)
    return {"barcode_data": barcode_data}

# ===========================
# PRINT ROUTES (WITH LOCAL BARCODE)
# ===========================
@app.get("/print-barcode/{patient_id}", response_class=HTMLResponse)
def print_barcode(patient_id: str, request: Request, session: Session = Depends(get_session)):
    patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()
    if not patient:
        return HTMLResponse(content="Patient not found", status_code=404)
    lab_info = session.exec(select(LabInfo).limit(1)).first()
    barcode_data = generate_barcode_base64(patient_id)
    return templates.TemplateResponse("print_barcode.html", {
        "request": request, "patient": patient, "lab_info": lab_info, "barcode_data": barcode_data
    })

@app.get("/print-receipt/{patient_id}", response_class=HTMLResponse)
def print_receipt(patient_id: str, request: Request, session: Session = Depends(get_session)):
    patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()
    if not patient:
        return HTMLResponse(content="Patient not found", status_code=404)
    visits = session.exec(select(PatientVisit).where(PatientVisit.patient_id == patient.id)).all()
    orders = session.exec(select(Order).where(Order.patient_id == patient.id)).all()
    lab_info = session.exec(select(LabInfo).limit(1)).first()
    barcode_data = generate_barcode_base64(patient_id)
    return templates.TemplateResponse("print_receipt.html", {
        "request": request, "patient": patient, "visits": visits, "orders": orders,
        "lab_info": lab_info, "barcode_data": barcode_data
    })
# ===========================
# ✅ NEW: CHECK DUPLICATE PATIENT BY PHONE
# ===========================
@app.get("/api/check-patient-phone")
def check_patient_phone(phone_key: str, phone_number: str, session: Session = Depends(get_session)):
    """Check if patient with same phone number already exists"""
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
# GENERAL API ENDPOINTS
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