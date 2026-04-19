# routes/supplies.py
from fastapi import APIRouter, Depends, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from datetime import datetime
from typing import Optional
from database import get_session
from models import Supply
from routes.helpers import templates, get_current_user, create_audit_log, model_to_dict, require_permission

router = APIRouter()

@router.get("/supplies", response_class=HTMLResponse)
def supplies_page(request: Request, session: Session = Depends(get_session), search: Optional[str] = None):
    if not require_permission(request, session, "supplies"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    
    query = select(Supply).where(Supply.is_active == True)
    if search:
        query = query.where(Supply.name.ilike(f"%{search}%"))
    
    supplies = session.exec(query.order_by(Supply.id.asc())).all()
    supplies_dict = [model_to_dict(s) for s in supplies]
    
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    
    return templates.TemplateResponse("supplies.html", {
        "request": request, 
        "supplies": supplies,
        "supplies_json": supplies_dict,
        "search": search or "",
        "message_success": success, 
        "message_error": error
    })

@router.post("/supplies/create")
def create_supply(name: str = Form(...), note: Optional[str] = Form(None),
                  request: Request = None, session: Session = Depends(get_session)):
    if not require_permission(request, session, "supplies", "create"):
        return RedirectResponse(url="/supplies?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        new_supply = Supply(
            name=name, 
            note=note, 
            is_active=True,
            created_by=current_user.id if current_user else None
        )
        session.add(new_supply)
        session.commit()
        session.refresh(new_supply)
        create_audit_log(session, "supply", new_supply.id, "create", current_user, new_values=model_to_dict(new_supply))
        return RedirectResponse(url="/supplies?success=Supply saved successfully!", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/supplies?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/supplies/update/{supply_id}")
def update_supply(supply_id: int, name: str = Form(...), note: Optional[str] = Form(None),
                  request: Request = None, session: Session = Depends(get_session)):
    if not require_permission(request, session, "supplies", "edit"):
        return RedirectResponse(url="/supplies?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        supply = session.get(Supply, supply_id)
        if supply:
            old_values = model_to_dict(supply)
            supply.name = name
            supply.note = note
            supply.edited_by = current_user.id if current_user else None
            supply.edited_at = datetime.now()
            session.add(supply)
            session.commit()
            session.refresh(supply)
            create_audit_log(session, "supply", supply.id, "update", current_user, old_values=old_values, new_values=model_to_dict(supply))
            return RedirectResponse(url="/supplies?success=Supply updated successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/supplies?error=Supply not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/supplies?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/supplies/delete/{supply_id}")
def delete_supply(supply_id: int, request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "supplies", "delete"):
        return RedirectResponse(url="/supplies?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    try:
        current_user = get_current_user(request, session)
        supply = session.get(Supply, supply_id)
        if supply:
            # Soft delete or hard delete? Standard in this app seems to be hard delete for minor configs
            # but let's stick to what departments.py does. 
            # departments.py uses session.delete(dept) which is a hard delete.
            old_values = model_to_dict(supply)
            create_audit_log(session, "supply", supply.id, "delete", current_user, old_values=old_values)
            session.delete(supply)
            session.commit()
            return RedirectResponse(url="/supplies?success=Supply deleted successfully!", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/supplies?error=Supply not found", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/supplies?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)
