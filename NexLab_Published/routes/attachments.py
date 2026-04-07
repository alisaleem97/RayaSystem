from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select
import os
import secrets
from datetime import datetime

from database import get_session
from models import Patient, Attachment
from routes.helpers import get_current_user, require_permission

router = APIRouter()

ATTACHMENTS_DIR = "uploads/attachments"
os.makedirs(ATTACHMENTS_DIR, exist_ok=True)

@router.post("/patient/{patient_id}/attachment")
async def upload_attachment(
    patient_id: str,
    request: Request,
    file: UploadFile = File(...),
    description: str = Form(None),
    session: Session = Depends(get_session)
):
    current_user = get_current_user(request, session)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        
    try:
        patient = session.exec(select(Patient).where(Patient.patient_id == patient_id)).first()
        if not patient:
            return RedirectResponse(url="/patients", status_code=status.HTTP_303_SEE_OTHER)
            
        if not file.filename:
            return RedirectResponse(url=f"/patient/edit/{patient_id}?error=No file selected", status_code=status.HTTP_303_SEE_OTHER)
            
        # Secure file saving
        ext = os.path.splitext(file.filename)[1].lower()
        secure_filename = f"{patient.id}_{secrets.token_hex(8)}{ext}"
        file_path = os.path.join(ATTACHMENTS_DIR, secure_filename)
        
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
            
        file_type = "image" if ext in ['.jpg', '.jpeg', '.png', '.gif'] else ("pdf" if ext == ".pdf" else "document")
            
        attachment = Attachment(
            patient_id=patient.id,
            file_name=file.filename,
            file_path=file_path.replace("\\", "/"),
            file_type=file_type,
            description=description,
            uploaded_by=current_user.id
        )
        session.add(attachment)
        session.commit()
        
        return RedirectResponse(url=f"/patient/edit/{patient_id}?success=Attachment uploaded", status_code=status.HTTP_303_SEE_OTHER)
        
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/patient/edit/{patient_id}?error={str(e).replace(' ', '%20')}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/attachment/{attachment_id}/delete")
def delete_attachment(
    attachment_id: int,
    request: Request,
    session: Session = Depends(get_session)
):
    current_user = get_current_user(request, session)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        
    try:
        attachment = session.get(Attachment, attachment_id)
        if not attachment:
            return RedirectResponse(url="/patients", status_code=status.HTTP_303_SEE_OTHER)
            
        patient = session.get(Patient, attachment.patient_id)
        patient_route_id = patient.patient_id if patient else ""
            
        # Physically delete the file
        if os.path.exists(attachment.file_path):
            os.remove(attachment.file_path)
            
        session.delete(attachment)
        session.commit()
        
        return RedirectResponse(url=f"/patient/edit/{patient_route_id}?success=Attachment deleted", status_code=status.HTTP_303_SEE_OTHER)
        
    except Exception as e:
        session.rollback()
        return RedirectResponse(url="/patients?error=Failed to delete attachment", status_code=status.HTTP_303_SEE_OTHER)
