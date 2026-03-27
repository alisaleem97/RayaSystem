# routes/geography.py
# CRUD routes for: Partners, Provinces, Regions, Lab Info.

from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from datetime import datetime
from typing import Optional
import os
import uuid
from database import get_session
from models import Partner, Province, Region, LabInfo
from routes.helpers import templates, get_current_user, create_audit_log, model_to_dict, save_uploaded_file

router = APIRouter()

# ===========================
# PARTNER ROUTES
# ===========================
@router.get("/partners", response_class=HTMLResponse)
def partners_page(request: Request, session: Session = Depends(get_session)):
    partners = session.exec(select(Partner).order_by(Partner.id.asc())).all()
    partners_json = [model_to_dict(p) for p in partners]
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse("partners.html", {
        "request": request, "partners": partners, "partners_json": partners_json,
        "message_success": success, "message_error": error
    })

@router.post("/partners/create")
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

@router.post("/partners/update/{partner_id}")
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

@router.post("/partners/delete/{partner_id}")
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
@router.get("/provinces", response_class=HTMLResponse)
def provinces_page(request: Request, session: Session = Depends(get_session)):
    provinces = session.exec(select(Province).order_by(Province.id.asc())).all()
    provinces_json = [model_to_dict(p) for p in provinces]
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse("provinces.html", {
        "request": request, "provinces": provinces, "provinces_json": provinces_json,
        "message_success": success, "message_error": error
    })

@router.post("/provinces/create")
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

@router.post("/provinces/update/{province_id}")
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

@router.post("/provinces/delete/{province_id}")
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
@router.get("/regions", response_class=HTMLResponse)
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

@router.post("/regions/create")
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

@router.post("/regions/update/{region_id}")
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

@router.post("/regions/delete/{region_id}")
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
@router.get("/lab-info", response_class=HTMLResponse)
def lab_info_page(request: Request, session: Session = Depends(get_session)):
    lab_info = session.exec(select(LabInfo).limit(1)).first()
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    return templates.TemplateResponse("lab_info.html", {
        "request": request, "lab_info": lab_info, "edit_mode": False,
        "message_success": success, "message_error": error
    })

@router.get("/lab-info/edit", response_class=HTMLResponse)
def lab_info_edit_page(request: Request, session: Session = Depends(get_session)):
    lab_info = session.exec(select(LabInfo).limit(1)).first()
    return templates.TemplateResponse("lab_info.html", {
        "request": request, "lab_info": lab_info, "edit_mode": True
    })

@router.post("/lab-info/update")
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
