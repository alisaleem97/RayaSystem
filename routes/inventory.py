# routes/inventory.py
from fastapi import APIRouter, Depends, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from datetime import datetime, timedelta
from typing import Optional
from database import get_session
from models import Inventory, TestDefinition, Supply
from sqlalchemy.orm import selectinload
from routes.helpers import templates, get_current_user, create_audit_log, model_to_dict, require_permission

router = APIRouter()

@router.get("/inventory", response_class=HTMLResponse)
def inventory_list(request: Request, search: Optional[str] = None, expires_soon: Optional[bool] = False, session: Session = Depends(get_session)):
    if not require_permission(request, session, "inventory"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    
    query = select(Inventory).options(
        selectinload(Inventory.test),
        selectinload(Inventory.supply)
    ).where(Inventory.is_active == True)
    
    # Base query for display
    items = session.exec(query.order_by(Inventory.expiration_date.asc())).all()
    
    # Filter in python or db
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    thirty_days_later = today + timedelta(days=30)
    
    filtered_items = []
    
    for item in items:
        # Determine name dynamically based on material_type
        if item.material_type == "Test":
            name = item.test.test_name if item.test else "Unknown Test"
        else:
            name = item.supply.name if item.supply else "Unknown Supply"
        
        # Apply Search Filter
        if search and search.lower() not in name.lower():
            continue
            
        # Apply Expiration Filter
        if expires_soon:
            if item.expiration_date > thirty_days_later:
                continue
        
        # Determine if it expires soon for row highlighting
        is_expiring_soon = item.expiration_date <= thirty_days_later
        
        filtered_items.append({
            "id": item.id,
            "material_type": item.material_type,
            "name": name,
            "quantity": item.quantity,
            "unit": item.unit,
            "expiration_date": item.expiration_date,
            "note": item.note,
            "is_expiring_soon": is_expiring_soon,
            "test_id": item.test_id,
            "supply_id": item.supply_id
        })
        
    # Get total sum of quantity at the bottom
    total_quantity = sum(float(item["quantity"]) for item in filtered_items)
    
    # Create JSON safe items
    json_safe_items = []
    for fi in filtered_items:
        new_fi = fi.copy()
        new_fi["expiration_date"] = new_fi["expiration_date"].isoformat()
        json_safe_items.append(new_fi)
        
    # Get tests and supplies for the form dropdowns
    tests = session.exec(select(TestDefinition).where(TestDefinition.is_available == True)).all()
    supplies = session.exec(select(Supply).where(Supply.is_active == True)).all()
    
    tests_dict = [{"id": t.id, "name": t.test_name} for t in tests]
    supplies_dict = [{"id": s.id, "name": s.name} for s in supplies]
        
    return templates.TemplateResponse("inventory.html", {
        "request": request, 
        "inventory_items": filtered_items,
        "inventory_json": json_safe_items, # To be used in javascript for editing
        "tests": tests,
        "supplies": supplies,
        "tests_json": tests_dict,
        "supplies_json": supplies_dict,
        "search": search or "",
        "expires_soon": expires_soon,
        "total_quantity": total_quantity,
        "message_success": request.query_params.get("success"), 
        "message_error": request.query_params.get("error")
    })

@router.post("/inventory/create")
def create_inventory(
    material_type: str = Form(...),
    test_id: Optional[int] = Form(None),
    supply_id: Optional[int] = Form(None),
    quantity: float = Form(...),
    unit: str = Form("Test"),
    expiration_date: str = Form(...), # DD-MM-YYYY
    note: Optional[str] = Form(None),
    request: Request = None, 
    session: Session = Depends(get_session)
):
    if not require_permission(request, session, "inventory", "create"):
        return RedirectResponse(url="/inventory?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    
    try:
        current_user = get_current_user(request, session)
        exp_date_obj = datetime.strptime(expiration_date, "%Y-%m-%d")
        
        new_item = Inventory(
            material_type=material_type,
            test_id=test_id if material_type == "Test" else None,
            supply_id=supply_id if material_type == "Supply" else None,
            quantity=quantity,
            unit=unit if material_type == "Supply" else "Test",
            expiration_date=exp_date_obj,
            note=note,
            created_by=current_user.id if current_user else None
        )
        session.add(new_item)
        session.commit()
        session.refresh(new_item)
        
        create_audit_log(session, "inventory", new_item.id, "create", current_user, new_values=model_to_dict(new_item))
        return RedirectResponse(url="/inventory?success=Inventory item added successfully!", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/inventory?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/inventory/update/{item_id}")
def update_inventory(
    item_id: int,
    material_type: str = Form(...),
    test_id: Optional[int] = Form(None),
    supply_id: Optional[int] = Form(None),
    quantity: float = Form(...),
    unit: str = Form("Test"),
    expiration_date: str = Form(...),
    note: Optional[str] = Form(None),
    request: Request = None, 
    session: Session = Depends(get_session)
):
    if not require_permission(request, session, "inventory", "edit"):
        return RedirectResponse(url="/inventory?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
        
    try:
        current_user = get_current_user(request, session)
        item = session.get(Inventory, item_id)
        if item:
            old_values = model_to_dict(item)
            
            item.material_type = material_type
            item.test_id = test_id if material_type == "Test" else None
            item.supply_id = supply_id if material_type == "Supply" else None
            item.quantity = quantity
            item.unit = unit if material_type == "Supply" else "Test"
            item.expiration_date = datetime.strptime(expiration_date, "%Y-%m-%d")
            item.note = note
            item.edited_by = current_user.id if current_user else None
            item.edited_at = datetime.now()
            
            session.add(item)
            session.commit()
            create_audit_log(session, "inventory", item.id, "update", current_user, old_values=old_values, new_values=model_to_dict(item))
            return RedirectResponse(url="/inventory?success=Inventory item updated successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/inventory?error=Item not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/inventory?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/inventory/delete/{item_id}")
def delete_inventory(item_id: int, request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "inventory", "delete"):
        return RedirectResponse(url="/inventory?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        item = session.get(Inventory, item_id)
        if item:
            old_values = model_to_dict(item)
            session.delete(item)
            session.commit()
            create_audit_log(session, "inventory", item.id, "delete", current_user, old_values=old_values)
            return RedirectResponse(url="/inventory?success=Inventory item deleted successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/inventory?error=Item not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/inventory?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)
