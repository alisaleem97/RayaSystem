# routes/cal_control.py
from fastapi import APIRouter, Depends, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from datetime import datetime
from database import get_session
from models import CalControl, Inventory, TestDefinition, Device
from routes.helpers import templates, get_current_user, require_permission, create_audit_log, model_to_dict
from typing import Optional
from sqlalchemy.orm import selectinload

router = APIRouter()

@router.get("/cal-control", response_class=HTMLResponse)
def cal_control_page(request: Request, session: Session = Depends(get_session)):
    # Use inventory permission as primary for accessing this page
    if not (require_permission(request, session, "inventory") or require_permission(request, session, "tests")):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)

    tests = session.exec(select(TestDefinition).where(TestDefinition.is_available == True)).all()
    devices = session.exec(select(Device).where(Device.is_active == True)).all()
    
    date_from = request.query_params.get("date_from")
    date_to = request.query_params.get("date_to")
    search_test_id = request.query_params.get("search_test_id")
    search_device_id = request.query_params.get("search_device_id")
    search_process_type = request.query_params.get("search_process_type")
    is_search = request.query_params.get("search") == "true"
    
    history = []
    if is_search:
        history_query = select(CalControl).options(
            selectinload(CalControl.test),
            selectinload(CalControl.device)
        ).order_by(CalControl.created_at.desc())
        
        if date_from:
            try:
                df = datetime.strptime(date_from, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
                history_query = history_query.where(CalControl.created_at >= df)
            except:
                pass
        if date_to:
            try:
                dt = datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
                history_query = history_query.where(CalControl.created_at <= dt)
            except:
                pass
        if search_test_id:
            history_query = history_query.where(CalControl.test_id == int(search_test_id))
        if search_device_id:
            history_query = history_query.where(CalControl.device_id == int(search_device_id))
        if search_process_type:
            history_query = history_query.where(CalControl.process_type == search_process_type)

        history = session.exec(history_query).all()
        
    # Default to today if not provided
    default_date = datetime.now().strftime("%Y-%m-%d")
    
    return templates.TemplateResponse("cal_control.html", {
        "request": request,
        "tests": tests,
        "devices": devices,
        "history": history,
        "is_search": is_search,
        "date_from": date_from or default_date,
        "date_to": date_to or default_date,
        "search_test_id": search_test_id,
        "search_device_id": search_device_id,
        "search_process_type": search_process_type,
        "message_success": request.query_params.get("success"),
        "message_error": request.query_params.get("error")
    })

@router.post("/cal-control/create")
def create_cal_control(
    test_id: int = Form(...),
    device_id: int = Form(...),
    process_type: str = Form(...), # "Cal" or "Control"
    quantity: float = Form(...),
    note: Optional[str] = Form(None),
    request: Request = None,
    session: Session = Depends(get_session)
):
    if not (require_permission(request, session, "inventory", "edit") or require_permission(request, session, "tests")):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    
    if quantity <= 0:
        return RedirectResponse(url="/cal-control?error=Quantity must be greater than zero", status_code=status.HTTP_303_SEE_OTHER)
        
    try:
        current_user = get_current_user(request, session)
        
        # Determine total tests required
        remaining_qty = quantity
        
        # Fetch inventory for this test_id ordered by nearest expiration first
        inventory_items = session.exec(
            select(Inventory)
            .where(Inventory.test_id == test_id)
            .where(Inventory.material_type == "Test")
            .where(Inventory.is_active == True)
            .where(Inventory.quantity > 0)
            .order_by(Inventory.expiration_date.asc())
        ).all()
        
        # Check if enough inventory exists
        total_inv = sum(item.quantity for item in inventory_items)
        if total_inv < quantity:
            return RedirectResponse(url="/cal-control?error=Not enough tests in inventory. Total available: " + str(total_inv), status_code=status.HTTP_303_SEE_OTHER)
            
        # Deduct from inventory
        for item in inventory_items:
            if remaining_qty <= 0:
                break
                
            if item.quantity >= remaining_qty:
                old_val = model_to_dict(item)
                item.quantity -= remaining_qty
                item.edited_by = current_user.id if current_user else None
                item.edited_at = datetime.now()
                remaining_qty = 0
                create_audit_log(session, "inventory", item.id, "update_cal_control", current_user, old_values=old_val, new_values=model_to_dict(item))
            else:
                old_val = model_to_dict(item)
                remaining_qty -= item.quantity
                item.quantity = 0
                item.edited_by = current_user.id if current_user else None
                item.edited_at = datetime.now()
                create_audit_log(session, "inventory", item.id, "update_cal_control", current_user, old_values=old_val, new_values=model_to_dict(item))
                
            session.add(item)
            
        # Create CalControl entry
        new_cal = CalControl(
            test_id=test_id,
            device_id=device_id,
            process_type=process_type,
            quantity=quantity,
            note=note,
            created_by=current_user.id if current_user else None
        )
        session.add(new_cal)
        session.commit()
        session.refresh(new_cal)
        
        return RedirectResponse(url="/cal-control?success=Process recorded successfully and inventory deducted.", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/cal-control?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)
