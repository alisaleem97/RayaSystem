# routes/expenses.py
from fastapi import APIRouter, Depends, Request, Form, status, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from datetime import datetime
import os
import secrets
from typing import Optional
from database import get_session
from models import ExpenseType, Expense
from routes.helpers import templates, get_current_user, create_audit_log, model_to_dict, require_permission

router = APIRouter()

EXPENSES_UPLOAD_DIR = "uploads/expenses"
os.makedirs(EXPENSES_UPLOAD_DIR, exist_ok=True)

# ===========================
# EXPENSE TYPES ROUTES
# ===========================
@router.get("/expenses-types", response_class=HTMLResponse)
def expenses_types_page(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "expenses_types"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    
    types = session.exec(select(ExpenseType).order_by(ExpenseType.id.asc())).all()
    types_dict = [model_to_dict(t) for t in types]
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    
    return templates.TemplateResponse("expenses_types.html", {
        "request": request, 
        "expense_types": types,
        "expense_types_json": types_dict, 
        "message_success": success, 
        "message_error": error
    })

@router.post("/expenses-types/create")
def create_expense_type(type_name: str = Form(...),
                        request: Request = None, session: Session = Depends(get_session)):
    if not require_permission(request, session, "expenses_types", "create"):
        return RedirectResponse(url="/expenses-types?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        new_type = ExpenseType(type_name=type_name,
                                created_by=current_user.id if current_user else None)
        session.add(new_type)
        session.commit()
        session.refresh(new_type)
        create_audit_log(session, "expensetype", new_type.id, "create", current_user, new_values=model_to_dict(new_type))
        return RedirectResponse(url="/expenses-types?success=Expense type saved successfully!", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/expenses-types?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/expenses-types/update/{type_id}")
def update_expense_type(type_id: int, type_name: str = Form(...),
                        request: Request = None, session: Session = Depends(get_session)):
    if not require_permission(request, session, "expenses_types", "edit"):
        return RedirectResponse(url="/expenses-types?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        etype = session.get(ExpenseType, type_id)
        if etype:
            old_values = model_to_dict(etype)
            etype.type_name = type_name
            etype.edited_by = current_user.id if current_user else None
            etype.edited_at = datetime.now()
            session.add(etype)
            session.commit()
            session.refresh(etype)
            create_audit_log(session, "expensetype", etype.id, "update", current_user, old_values=old_values, new_values=model_to_dict(etype))
            return RedirectResponse(url="/expenses-types?success=Expense type updated successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/expenses-types?error=Expense type not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/expenses-types?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/expenses-types/delete/{type_id}")
def delete_expense_type(type_id: int, request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "expenses_types", "delete"):
        return RedirectResponse(url="/expenses-types?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        etype = session.get(ExpenseType, type_id)
        if etype:
            old_values = model_to_dict(etype)
            create_audit_log(session, "expensetype", etype.id, "delete", current_user, old_values=old_values)
            session.delete(etype)
            session.commit()
            return RedirectResponse(url="/expenses-types?success=Expense type deleted successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/expenses-types?error=Expense type not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/expenses-types?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

# ===========================
# EXPENSES ENTRY ROUTES
# ===========================
@router.get("/expenses-entry", response_class=HTMLResponse)
def expenses_entry_page(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "expenses_entry"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    
    # Fetch all expenses joined with type
    expenses = session.exec(select(Expense).order_by(Expense.expense_date.desc())).all()
    # Fetch types for dropdown
    types = session.exec(select(ExpenseType).order_by(ExpenseType.type_name.asc())).all()
    
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    
    return templates.TemplateResponse("expenses_entry.html", {
        "request": request,
        "expenses": expenses,
        "expenses_json": [model_to_dict(e) for e in expenses],
        "expense_types": types,
        "message_success": success,
        "message_error": error
    })

@router.post("/expenses-entry/create")
async def create_expense(
    type_id: int = Form(...),
    expense_date: str = Form(...),
    amount: float = Form(...),
    note: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    request: Request = None,
    session: Session = Depends(get_session)
):
    if not require_permission(request, session, "expenses_entry", "create"):
        return RedirectResponse(url="/expenses-entry?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        
        # Handle file upload
        file_path = None
        file_name = None
        if file and file.filename:
            ext = os.path.splitext(file.filename)[1].lower()
            secure_filename = f"EXP_{secrets.token_hex(8)}{ext}"
            file_path = os.path.join(EXPENSES_UPLOAD_DIR, secure_filename).replace("\\", "/")
            file_name = file.filename
            
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
        
        # Parse date
        try:
            exp_dt = datetime.strptime(expense_date, "%Y-%m-%d")
        except ValueError:
            exp_dt = datetime.now()

        new_expense = Expense(
            type_id=type_id,
            expense_date=exp_dt,
            amount=amount,
            note=note,
            file_path=file_path,
            file_name=file_name,
            created_by=current_user.id if current_user else 0
        )
        session.add(new_expense)
        session.commit()
        session.refresh(new_expense)
        
        create_audit_log(session, "expense", new_expense.id, "create", current_user, new_values=model_to_dict(new_expense))
        return RedirectResponse(url="/expenses-entry?success=Expense saved successfully!", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/expenses-entry?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/expenses-entry/update/{expense_id}")
async def update_expense(
    expense_id: int,
    type_id: int = Form(...),
    expense_date: str = Form(...),
    amount: float = Form(...),
    note: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    request: Request = None,
    session: Session = Depends(get_session)
):
    if not require_permission(request, session, "expenses_entry", "edit"):
        return RedirectResponse(url="/expenses-entry?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        expense = session.get(Expense, expense_id)
        if not expense:
            return RedirectResponse(url="/expenses-entry?error=Expense not found", status_code=status.HTTP_303_SEE_OTHER)
        
        old_values = model_to_dict(expense)
        
        # Handle file upload if provided
        if file and file.filename:
            # Delete old file
            if expense.file_path and os.path.exists(expense.file_path):
                try:
                    os.remove(expense.file_path)
                except Exception:
                    pass
            
            ext = os.path.splitext(file.filename)[1].lower()
            secure_filename = f"EXP_{secrets.token_hex(8)}{ext}"
            file_path = os.path.join(EXPENSES_UPLOAD_DIR, secure_filename).replace("\\", "/")
            expense.file_path = file_path
            expense.file_name = file.filename
            
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
        
        # Update other fields
        try:
            exp_dt = datetime.strptime(expense_date, "%Y-%m-%d")
            expense.expense_date = exp_dt
        except Exception:
            pass
            
        expense.type_id = type_id
        expense.amount = amount
        expense.note = note
        expense.edited_by = current_user.id if current_user else None
        expense.edited_at = datetime.now()
        
        session.add(expense)
        session.commit()
        session.refresh(expense)
        
        create_audit_log(session, "expense", expense.id, "update", current_user, old_values=old_values, new_values=model_to_dict(expense))
        return RedirectResponse(url="/expenses-entry?success=Expense updated successfully!", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/expenses-entry?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/expenses-entry/delete/{expense_id}")
def delete_expense(expense_id: int, request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "expenses_entry", "delete"):
        return RedirectResponse(url="/expenses-entry?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        expense = session.get(Expense, expense_id)
        if expense:
            old_values = model_to_dict(expense)
            
            # Physically delete file if exists
            if expense.file_path and os.path.exists(expense.file_path):
                try:
                    os.remove(expense.file_path)
                except Exception:
                    pass
            
            create_audit_log(session, "expense", expense.id, "delete", current_user, old_values=old_values)
            session.delete(expense)
            session.commit()
            return RedirectResponse(url="/expenses-entry?success=Expense deleted successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/expenses-entry?error=Expense not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/expenses-entry?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)
