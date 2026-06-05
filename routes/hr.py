# routes/hr.py
# HR Module: Employee Management

from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlmodel import Session, select
from datetime import datetime
from typing import Optional
import os
import shutil
import uuid

from database import get_session
from app.models.hr import Employee, EmployeeAttachment
from routes.helpers import templates, get_current_user

router = APIRouter()

EMPLOYEES_UPLOAD_DIR = "uploads/employees"
os.makedirs(EMPLOYEES_UPLOAD_DIR, exist_ok=True)

EMPLOYEE_ATTACHMENTS_DIR = "uploads/employee_attachments"
os.makedirs(EMPLOYEE_ATTACHMENTS_DIR, exist_ok=True)

# ===========================
# HR PAGE
# ===========================
@router.get("/hr", response_class=HTMLResponse)
def hr_page(request: Request, session: Session = Depends(get_session)):
    current_user = get_current_user(request, session)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    employees = session.exec(select(Employee).where(Employee.is_active == True).order_by(Employee.created_at.desc())).all()

    import json
    employees_json = {}
    for emp in employees:
        emp_dict = emp.dict() if hasattr(emp, 'dict') else emp.model_dump()
        emp_dict['start_date'] = emp.start_date.isoformat() if emp.start_date else None
        emp_dict['created_at'] = emp.created_at.isoformat() if emp.created_at else None
        emp_dict['working_life_months'] = emp.working_life_months
        employees_json[emp.id] = emp_dict

    success = request.query_params.get("success")
    error = request.query_params.get("error")

    return templates.TemplateResponse("hr.html", {
        "request": request,
        "employees": employees,
        "employees_json": employees_json,
        "current_user": current_user,
        "message_success": success,
        "message_error": error
    })


# ===========================
# CREATE EMPLOYEE
# ===========================
@router.post("/api/hr/employees")
def create_employee(
    full_name: str = Form(...),
    age: Optional[int] = Form(None),
    phone: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    start_date: str = Form(...),
    working_days: Optional[str] = Form(None),
    working_hours_start: Optional[str] = Form(None),
    working_hours_end: Optional[str] = Form(None),
    salary: Optional[float] = Form(None),
    username: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    request: Request = None,
    session: Session = Depends(get_session)
):
    current_user = get_current_user(request, session)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    try:
        sd = datetime.strptime(start_date, "%Y-%m-%d")
        
        photo_path = None
        if photo and photo.filename:
            ext = photo.filename.split(".")[-1]
            unique_filename = f"{uuid.uuid4().hex}.{ext}"
            file_path = os.path.join(EMPLOYEES_UPLOAD_DIR, unique_filename)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(photo.file, buffer)
            photo_path = f"/{EMPLOYEES_UPLOAD_DIR}/{unique_filename}"

        emp = Employee(
            full_name=full_name,
            age=age,
            phone=phone,
            address=address,
            start_date=sd,
            working_days=working_days,
            working_hours_start=working_hours_start,
            working_hours_end=working_hours_end,
            salary=salary,
            username=username,
            photo_path=photo_path
        )
        session.add(emp)
        session.commit()
        return RedirectResponse(url="/hr?success=Employee created successfully", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/hr?error={str(e)}", status_code=status.HTTP_303_SEE_OTHER)


# ===========================
# UPDATE EMPLOYEE
# ===========================
@router.post("/api/hr/employees/{employee_id}/update")
def update_employee(
    employee_id: int,
    full_name: str = Form(...),
    age: Optional[int] = Form(None),
    phone: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    start_date: str = Form(...),
    working_days: Optional[str] = Form(None),
    working_hours_start: Optional[str] = Form(None),
    working_hours_end: Optional[str] = Form(None),
    salary: Optional[float] = Form(None),
    username: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    request: Request = None,
    session: Session = Depends(get_session)
):
    current_user = get_current_user(request, session)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    try:
        emp = session.get(Employee, employee_id)
        if not emp:
            return RedirectResponse(url="/hr?error=Employee not found", status_code=status.HTTP_303_SEE_OTHER)

        emp.full_name = full_name
        emp.age = age
        emp.phone = phone
        emp.address = address
        emp.start_date = datetime.strptime(start_date, "%Y-%m-%d")
        emp.working_days = working_days
        emp.working_hours_start = working_hours_start
        emp.working_hours_end = working_hours_end
        emp.salary = salary
        emp.username = username

        if photo and photo.filename:
            ext = photo.filename.split(".")[-1]
            unique_filename = f"{uuid.uuid4().hex}.{ext}"
            file_path = os.path.join(EMPLOYEES_UPLOAD_DIR, unique_filename)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(photo.file, buffer)
            emp.photo_path = f"/{EMPLOYEES_UPLOAD_DIR}/{unique_filename}"

        session.add(emp)
        session.commit()
        return RedirectResponse(url="/hr?success=Employee updated successfully", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/hr?error={str(e)}", status_code=status.HTTP_303_SEE_OTHER)


# ===========================
# DELETE EMPLOYEE
# ===========================
@router.post("/api/hr/employees/{employee_id}/delete")
def delete_employee(
    employee_id: int,
    request: Request,
    session: Session = Depends(get_session)
):
    current_user = get_current_user(request, session)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    try:
        emp = session.get(Employee, employee_id)
        if not emp:
            return RedirectResponse(url="/hr?error=Employee not found", status_code=status.HTTP_303_SEE_OTHER)

        emp.is_active = False
        session.add(emp)
        session.commit()
        return RedirectResponse(url="/hr?success=Employee deleted successfully", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/hr?error={str(e)}", status_code=status.HTTP_303_SEE_OTHER)


# ===========================
# GET ATTACHMENTS API
# ===========================
@router.get("/api/hr/employees/{employee_id}/attachments")
def get_employee_attachments(employee_id: int, session: Session = Depends(get_session)):
    attachments = session.exec(select(EmployeeAttachment).where(EmployeeAttachment.employee_id == employee_id)).all()
    return {"attachments": [{"id": a.id, "file_name": a.file_name, "file_path": a.file_path, "uploaded_at": a.uploaded_at.isoformat()} for a in attachments]}


# ===========================
# UPLOAD ATTACHMENT API
# ===========================
@router.post("/api/hr/employees/{employee_id}/attachments")
def upload_employee_attachment(
    employee_id: int,
    file: UploadFile = File(...),
    request: Request = None,
    session: Session = Depends(get_session)
):
    current_user = get_current_user(request, session)
    if not current_user:
        return JSONResponse(status_code=401, content={"success": False, "error": "Not authenticated"})

    try:
        emp = session.get(Employee, employee_id)
        if not emp:
            return JSONResponse(status_code=404, content={"success": False, "error": "Employee not found"})

        ext = file.filename.split(".")[-1] if "." in file.filename else ""
        unique_filename = f"{uuid.uuid4().hex}.{ext}"
        file_path = os.path.join(EMPLOYEE_ATTACHMENTS_DIR, unique_filename)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        attachment = EmployeeAttachment(
            employee_id=employee_id,
            file_name=file.filename,
            file_path=f"/{EMPLOYEE_ATTACHMENTS_DIR}/{unique_filename}"
        )
        session.add(attachment)
        session.commit()
        
        return JSONResponse({"success": True})
    except Exception as e:
        session.rollback()
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

# ===========================
# DELETE ATTACHMENT API
# ===========================
@router.delete("/api/hr/employees/attachments/{attachment_id}")
def delete_employee_attachment(
    attachment_id: int,
    request: Request,
    session: Session = Depends(get_session)
):
    current_user = get_current_user(request, session)
    if not current_user:
        return JSONResponse(status_code=401, content={"success": False, "error": "Not authenticated"})

    try:
        attachment = session.get(EmployeeAttachment, attachment_id)
        if not attachment:
            return JSONResponse(status_code=404, content={"success": False, "error": "Attachment not found"})

        session.delete(attachment)
        session.commit()
        return JSONResponse({"success": True})
    except Exception as e:
        session.rollback()
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})
