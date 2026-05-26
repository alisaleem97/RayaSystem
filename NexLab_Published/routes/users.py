# routes/users.py
# User Management: CRUD + Granular Page/Button Permissions

from fastapi import APIRouter, Depends, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlmodel import Session, select
from datetime import datetime
from typing import Optional
import json

from database import get_session
from models import User, UserPermission
from routes.helpers import templates, get_current_user, create_audit_log, model_to_dict, require_permission, pwd_context

router = APIRouter()

# ===========================
# PAGES REGISTRY — All pages and their actual buttons (audited from templates)
# ===========================
PAGES_REGISTRY = {
    # --- Main ---
    "dashboard": {"label": "Dashboard", "group": "Main", "buttons": []},
    # --- Patient Management ---
    "patient_registration": {"label": "Patient Registration", "group": "Patient Management", "buttons": [
        {"key": "save_registration", "label": "Save Registration"},
        {"key": "discount", "label": "Discount"},
        {"key": "print_barcode", "label": "Print Barcode"},
        {"key": "print_receipt", "label": "Print Receipt"},
    ]},
    "patients": {"label": "Patients", "group": "Patient Management", "buttons": [
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
        {"key": "print_barcode", "label": "Print Barcode"},
        {"key": "print_receipt", "label": "Print Receipt"},
        {"key": "result_entry", "label": "Result Entry"},
    ]},
    "patient_edit": {"label": "Patient Edit", "group": "Patient Management", "buttons": [
        {"key": "save", "label": "Save Changes"},
        {"key": "print_barcode", "label": "Print Barcode"},
        {"key": "print_receipt", "label": "Print Receipt"},
        {"key": "discount", "label": "Discount"},
    ]},
    "deleted_patients": {"label": "Deleted Patients", "group": "Patient Management", "buttons": [
        {"key": "restore", "label": "Restore"},
        {"key": "view", "label": "View"},
    ]},
    "deleted_tests": {"label": "Deleted Tests", "group": "Patient Management", "buttons": []},
    "patient_history": {"label": "Patient History", "group": "Patient Management", "buttons": []},
    "patient_status": {"label": "Patient Status", "group": "Patient Management", "buttons": []},
    # --- Results ---
    "result_entry": {"label": "Result Entry", "group": "Results", "buttons": [
        {"key": "save", "label": "Save Result"},
        {"key": "authorize", "label": "Authorize"},
        {"key": "duplicate", "label": "Duplicate"},
        {"key": "rerun", "label": "ReRun"},
        {"key": "no_sample", "label": "No Sample"},
    ]},
    "double_auth": {"label": "Double Authorisation", "group": "Results", "buttons": [
        {"key": "double_authorize", "label": "Double Authorize"},
        {"key": "rerun", "label": "ReRun"},
        {"key": "unauthorize", "label": "UnAUTH"},
    ]},
    "no_sample": {"label": "No Sample", "group": "Results", "buttons": [
        {"key": "mark_no_sample", "label": "Mark No Sample"},
        {"key": "receive_sample", "label": "Receive Sample"},
    ]},
    # --- Printing & Design ---
    "print_barcode": {"label": "Print Barcode", "group": "Printing & Design", "buttons": [
        {"key": "print", "label": "Print"},
    ]},
    "barcode_designer": {"label": "Barcode Designer", "group": "Printing & Design", "buttons": [
        {"key": "save", "label": "Save Design"},
    ]},
    "print_receipt": {"label": "Print Receipt", "group": "Printing & Design", "buttons": [
        {"key": "print", "label": "Print"},
    ]},
    "receipt_designer": {"label": "Receipt Designer", "group": "Printing & Design", "buttons": [
        {"key": "save", "label": "Save Design"},
    ]},
    "print_results": {"label": "Print Results", "group": "Printing & Design", "buttons": [
        {"key": "print", "label": "Print"},
        {"key": "view", "label": "View"},
    ]},
    "call_centre": {"label": "Call Centre", "group": "Printing & Design", "buttons": [
        {"key": "mark_called", "label": "Mark Called"},
        {"key": "send_whatsapp", "label": "Send WhatsApp"},
    ]},
    "result_designer": {"label": "Result Designer", "group": "Printing & Design", "buttons": [
        {"key": "save", "label": "Save Design"},
    ]},
    # --- Lab Setup ---
    "departments": {"label": "Departments", "group": "Lab Setup", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "sample_types": {"label": "Sample Types", "group": "Lab Setup", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "devices": {"label": "Devices", "group": "Lab Setup", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "parameters": {"label": "Parameters", "group": "Lab Setup", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "report_notes": {"label": "Report Notes", "group": "Lab Setup", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    # --- Tests & Packages ---
    "tests": {"label": "Tests", "group": "Tests & Packages", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "formulas": {"label": "Formulas", "group": "Tests & Packages", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "test_ranges": {"label": "Test Ranges", "group": "Tests & Packages", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "test_result_types": {"label": "Result Types", "group": "Tests & Packages", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "packages": {"label": "Packages", "group": "Tests & Packages", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    # --- Financials ---
    "expenses_types": {"label": "Expenses Types", "group": "Financials", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "expenses_entry": {"label": "Expenses Entry", "group": "Financials", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    # --- Reports ---
    "discount_report": {"label": "Discount Report", "group": "Reports", "buttons": [
        {"key": "view", "label": "View Report"},
    ]},
    "detailed_income": {"label": "Detailed Income", "group": "Reports", "buttons": [
        {"key": "view", "label": "View Report"},
    ]},
    "net_amounts": {"label": "Net Amounts", "group": "Reports", "buttons": [
        {"key": "view", "label": "View Report"},
    ]},
    "payment_records": {"label": "Payment Records", "group": "Reports", "buttons": [
        {"key": "view", "label": "View Report"},
    ]},
    "patients_number": {"label": "Patients Number", "group": "Reports", "buttons": [
        {"key": "view", "label": "View Report"},
    ]},
    "tests_number": {"label": "Tests Number", "group": "Reports", "buttons": [
        {"key": "view", "label": "View Report"},
    ]},
    "expenses_report": {"label": "Expenses Report", "group": "Reports", "buttons": [
        {"key": "view", "label": "View Report"},
        {"key": "edit", "label": "Edit Expense"},
        {"key": "delete", "label": "Delete Expense"},
    ]},
    # --- Geography & Partners ---
    "partners": {"label": "Partners", "group": "Geography & Partners", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "provinces": {"label": "Provinces", "group": "Geography & Partners", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "regions": {"label": "Regions", "group": "Geography & Partners", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    # --- Settings ---
    "lab_info": {"label": "Lab Info", "group": "Settings", "buttons": [
        {"key": "edit", "label": "Edit"},
        {"key": "save", "label": "Save"},
    ]},
    "user_management": {"label": "User Management", "group": "Settings", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "activity_logs": {"label": "Activity Logs", "group": "Settings", "buttons": [
        {"key": "view", "label": "View"},
    ]},
}


# ===========================
# USERS PAGE
# ===========================
@router.get("/users", response_class=HTMLResponse)
def users_page(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "user_management"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    current_user = get_current_user(request, session)
    users = session.exec(select(User).order_by(User.id.asc())).all()
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse("users.html", {
        "request": request,
        "users": users,
        "pages_registry": PAGES_REGISTRY,
        "message_success": success,
        "message_error": error,
        "current_user": current_user
    })

# ===========================
# CREATE USER
# ===========================
@router.post("/users/create")
def create_user(
    full_name: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("user"),
    date_of_birth: Optional[str] = Form(None),
    phone_number: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    permissions: Optional[str] = Form(None),
    request: Request = None,
    session: Session = Depends(get_session)
):
    if not require_permission(request, session, "user_management", "create"):
        return RedirectResponse(url="/users?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        
        # Check duplicate username
        existing = session.exec(select(User).where(User.username == username)).first()
        if existing:
            return RedirectResponse(url=f"/users?error=Username '{username}' already exists", status_code=status.HTTP_303_SEE_OTHER)
        
        # Parse DOB
        dob = None
        if date_of_birth and date_of_birth.strip():
            try:
                dob = datetime.strptime(date_of_birth.strip(), "%d-%m-%Y")
            except ValueError:
                try:
                    dob = datetime.strptime(date_of_birth.strip(), "%Y-%m-%d")
                except ValueError:
                    pass
        
        new_user = User(
            full_name=full_name,
            username=username,
            hashed_password=pwd_context.hash(password),
            role=role,
            is_active=True,
            date_of_birth=dob,
            phone_number=phone_number if phone_number else None,
            address=address if address else None,
        )
        session.add(new_user)
        session.commit()
        session.refresh(new_user)
        
        # Save permissions
        if permissions:
            _save_permissions(session, new_user.id, permissions)
        
        create_audit_log(session, "user", new_user.id, "create", current_user, new_values={"username": username, "full_name": full_name})
        session.commit()
        
        return RedirectResponse(url="/users?success=User created successfully!", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/users?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

# ===========================
# UPDATE USER
# ===========================
@router.post("/users/update/{user_id}")
def update_user(
    user_id: int,
    full_name: str = Form(...),
    username: str = Form(...),
    password: Optional[str] = Form(None),
    role: str = Form("user"),
    date_of_birth: Optional[str] = Form(None),
    phone_number: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    is_active: Optional[str] = Form(None),
    permissions: Optional[str] = Form(None),
    request: Request = None,
    session: Session = Depends(get_session)
):
    if not require_permission(request, session, "user_management", "edit"):
        return RedirectResponse(url="/users?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        
        user = session.get(User, user_id)
        if not user:
            return RedirectResponse(url="/users?error=User not found", status_code=status.HTTP_303_SEE_OTHER)
        
        # Prevent editing admin's role/username
        if user.username == "admin" and username != "admin":
            return RedirectResponse(url="/users?error=Cannot change admin username", status_code=status.HTTP_303_SEE_OTHER)
        
        # Check duplicate username (exclude current user)
        existing = session.exec(select(User).where(User.username == username, User.id != user_id)).first()
        if existing:
            return RedirectResponse(url=f"/users?error=Username '{username}' already exists", status_code=status.HTTP_303_SEE_OTHER)
        
        old_values = model_to_dict(user)
        
        # Parse DOB
        dob = None
        if date_of_birth and date_of_birth.strip():
            try:
                dob = datetime.strptime(date_of_birth.strip(), "%d-%m-%Y")
            except ValueError:
                try:
                    dob = datetime.strptime(date_of_birth.strip(), "%Y-%m-%d")
                except ValueError:
                    pass
        
        user.full_name = full_name
        user.username = username
        user.role = role
        user.date_of_birth = dob
        user.phone_number = phone_number if phone_number else None
        user.address = address if address else None
        user.is_active = is_active == "on" or is_active == "true"
        user.edited_by = current_user.id if current_user else None
        user.edited_at = datetime.now()
        
        # Update password only if provided
        if password and password.strip():
            user.hashed_password = pwd_context.hash(password.strip())
            user.session_token = None  # Force logout on password change
            
        # If user is deactivated, force logout
        if not user.is_active:
            user.session_token = None
        
        session.add(user)
        session.commit()
        
        # Save permissions (delete old, insert new)
        if permissions is not None:
            _save_permissions(session, user_id, permissions)
            session.commit()
        
        create_audit_log(session, "user", user.id, "update", current_user, old_values=old_values, new_values=model_to_dict(user))
        session.commit()
        
        return RedirectResponse(url="/users?success=User updated successfully!", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/users?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

# ===========================
# DELETE USER
# ===========================
@router.post("/users/delete/{user_id}")
def delete_user(user_id: int, request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "user_management", "delete"):
        return RedirectResponse(url="/users?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        user = session.get(User, user_id)
        
        if not user:
            return RedirectResponse(url="/users?error=User not found", status_code=status.HTTP_303_SEE_OTHER)
        
        # Prevent deleting admin
        if user.username == "admin":
            return RedirectResponse(url="/users?error=Cannot delete the admin account", status_code=status.HTTP_303_SEE_OTHER)
        
        old_values = model_to_dict(user)
        
        # Delete permissions first
        perms = session.exec(select(UserPermission).where(UserPermission.user_id == user_id)).all()
        for p in perms:
            session.delete(p)
        
        session.delete(user)
        session.commit()
        
        create_audit_log(session, "user", user_id, "delete", current_user, old_values=old_values)
        session.commit()
        
        return RedirectResponse(url="/users?success=User deleted successfully!", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/users?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

# ===========================
# API: Get user permissions
# ===========================
@router.get("/api/users/{user_id}/permissions")
def get_user_permissions(user_id: int, request: Request, session: Session = Depends(get_session)):
    # Since checking permissions could be sensitive, just ensure session exists
    if not require_permission(request, session, "user_management"):
        return JSONResponse({"success": False, "error": "Permission Denied"})

    user = session.get(User, user_id)
    if not user:
        return JSONResponse({"success": False, "error": "User not found"})
    
    perms = session.exec(select(UserPermission).where(UserPermission.user_id == user_id)).all()
    
    permissions = {}
    for p in perms:
        buttons = []
        if p.allowed_buttons:
            try:
                buttons = json.loads(p.allowed_buttons)
            except Exception:
                buttons = []
        permissions[p.page_key] = buttons
    
    return JSONResponse({
        "success": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active,
            "date_of_birth": user.date_of_birth.strftime("%d-%m-%Y") if user.date_of_birth else "",
            "phone_number": user.phone_number or "",
            "address": user.address or "",
        },
        "permissions": permissions,
        "pages_registry": PAGES_REGISTRY
    })

# ===========================
# API: Get pages registry
# ===========================
@router.get("/api/pages-registry")
def get_pages_registry():
    return JSONResponse({"success": True, "pages_registry": PAGES_REGISTRY})

# ===========================
# Helper: Save permissions
# ===========================
def _save_permissions(session: Session, user_id: int, permissions_json: str):
    """Delete old permissions and insert new ones from JSON."""
    # Delete existing
    old_perms = session.exec(select(UserPermission).where(UserPermission.user_id == user_id)).all()
    for p in old_perms:
        session.delete(p)
    session.flush()
    
    # Parse and insert new
    try:
        perms_data = json.loads(permissions_json)
        # perms_data = {"page_key": ["btn1", "btn2"], ...}
        if isinstance(perms_data, dict):
            for page_key, buttons in perms_data.items():
                if page_key in PAGES_REGISTRY:
                    perm = UserPermission(
                        user_id=user_id,
                        page_key=page_key,
                        allowed_buttons=json.dumps(buttons) if buttons else "[]"
                    )
                    session.add(perm)
    except (json.JSONDecodeError, TypeError):
        pass
