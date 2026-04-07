from fastapi import APIRouter, Request, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, or_, and_
from typing import Optional, List
import os
import uuid
import datetime
from pathlib import Path

from database import get_session
from models import User, Chat, ChatMember, Message, MessageReceipt
from routes.helpers import templates

router = APIRouter(prefix="/messages", tags=["Messages"])

# Dependency to get current user ID
def get_current_user_id(request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id

@router.get("/", response_class=HTMLResponse)
async def messages_page(request: Request, session: Session = Depends(get_session)):
    user_id = get_current_user_id(request)
    current_user = session.get(User, user_id)
    if not current_user:
        raise HTTPException(status_code=401)
        
    return templates.TemplateResponse("messages.html", {"request": request, "current_user": current_user})

@router.get("/api/users")
async def get_all_users(request: Request, session: Session = Depends(get_session)):
    user_id = get_current_user_id(request)
    users = session.exec(select(User).where(User.is_active == True)).all()
    # Exclude admin if it's not relevant, or just return all except self
    # Return id, full_name, username, is_online, last_seen
    users_data = []
    for u in users:
        users_data.append({
            "id": u.id,
            "full_name": u.full_name,
            "username": u.username,
            "is_online": u.is_online,
            "last_seen": u.last_seen.isoformat() if u.last_seen else None
        })
    return {"users": users_data}

@router.get("/api/chats")
async def get_user_chats(request: Request, session: Session = Depends(get_session)):
    user_id = get_current_user_id(request)
    
    # Get all chats the user is a member of
    memberships = session.exec(select(ChatMember).where(ChatMember.user_id == user_id)).all()
    chat_ids = [m.chat_id for m in memberships]
    
    if not chat_ids:
        return {"chats": []}
        
    chats = session.exec(select(Chat).where(Chat.id.in_(chat_ids))).all()
    
    chats_data = []
    for chat in chats:
        # Get members of this chat
        members = session.exec(select(ChatMember).where(ChatMember.chat_id == chat.id)).all()
        # Get last message
        last_msg = session.exec(select(Message).where(Message.chat_id == chat.id).order_by(Message.created_at.desc())).first()
        
        # Determine chat title and avatar if it's 1-on-1
        chat_name = chat.name
        other_user = None
        if not chat.is_group:
            for m in members:
                if m.user_id != user_id:
                    u = session.get(User, m.user_id)
                    if u:
                        chat_name = u.full_name
                        other_user = u
                        break
                        
        last_msg_data = None
        unread_count = 0
        if last_msg:
            # Count unread messages strictly for this user
            # Unread could be calculated by checking MessageReceipt for this user where status != 'read'
            unread_count = len(session.exec(select(MessageReceipt).where(
                MessageReceipt.chat_id == chat.id,
                MessageReceipt.user_id == user_id,
                MessageReceipt.status != "read"
            )).all())
            
            last_msg_data = {
                "id": last_msg.id,
                "text": last_msg.text,
                "created_at": last_msg.created_at.isoformat(),
                "sender_id": last_msg.sender_id,
                "is_attachment": bool(last_msg.attachment_path),
                "is_voice": bool(last_msg.voice_note_path)
            }
            
        chats_data.append({
            "id": chat.id,
            "is_group": chat.is_group,
            "name": chat_name,
            "other_user_id": other_user.id if other_user else None,
            "other_user_online": other_user.is_online if other_user else False,
            "other_user_last_seen": other_user.last_seen.isoformat() if other_user and other_user.last_seen else None,
            "last_message": last_msg_data,
            "unread_count": unread_count,
            "members": [m.user_id for m in members]
        })
        
    # Sort by recent message
    chats_data.sort(key=lambda x: x["last_message"]["created_at"] if x["last_message"] else "", reverse=True)
    return {"chats": chats_data}

@router.get("/api/chats/{chat_id}/history")
async def get_chat_history(chat_id: int, request: Request, session: Session = Depends(get_session)):
    user_id = get_current_user_id(request)
    
    # Verify membership
    membership = session.exec(select(ChatMember).where(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id)).first()
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this chat")
        
    messages = session.exec(select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at.asc())).all()
    
    # Mark all unread messages as read
    unreads = session.exec(select(MessageReceipt).where(
        MessageReceipt.chat_id == chat_id,
        MessageReceipt.user_id == user_id,
        MessageReceipt.status != "read"
    )).all()
    for unread in unreads:
        unread.status = "read"
        unread.updated_at = datetime.datetime.now()
        session.add(unread)
    session.commit()
    
    msg_data = []
    for msg in messages:
        # Get receipt status for message sender (if valid)
        # Usually sender wants to know if others read it
        receipts = session.exec(select(MessageReceipt).where(MessageReceipt.message_id == msg.id)).all()
        status = "sent"
        if receipts:
            # If all are read, it's read. If some delivered, delivered.
            if all(r.status == "read" for r in receipts):
                status = "read"
            elif any(r.status == "delivered" for r in receipts):
                status = "delivered"
                
        msg_data.append({
            "id": msg.id,
            "sender_id": msg.sender_id,
            "text": msg.text,
            "attachment_path": msg.attachment_path,
            "attachment_name": msg.attachment_name,
            "attachment_type": msg.attachment_type,
            "voice_note_path": msg.voice_note_path,
            "voice_note_duration": msg.voice_note_duration,
            "is_call": msg.is_call,
            "call_status": msg.call_status,
            "call_duration": msg.call_duration,
            "created_at": msg.created_at.isoformat(),
            "status": status
        })
        
    return {"messages": msg_data}

@router.post("/api/chats/create")
async def create_chat(data: dict, request: Request, session: Session = Depends(get_session)):
    user_id = get_current_user_id(request)
    is_group = data.get("is_group", False)
    members_ids = data.get("members", [])
    name = data.get("name")
    
    if user_id not in members_ids:
        members_ids.append(user_id)
        
    if not is_group and len(members_ids) == 2:
        # Check if 1-on-1 chat already exists
        target_id = [m for m in members_ids if m != user_id][0]
        # Find all 1-on-1 chats for this user
        my_chats = session.exec(select(ChatMember).where(ChatMember.user_id == user_id)).all()
        my_chat_ids = [m.chat_id for m in my_chats]
        
        # Check if target is in any of these, and chat is not a group
        shared_chats = session.exec(select(Chat).where(Chat.id.in_(my_chat_ids), Chat.is_group == False)).all()
        for sc in shared_chats:
            target_membership = session.exec(select(ChatMember).where(ChatMember.chat_id == sc.id, ChatMember.user_id == target_id)).first()
            if target_membership:
                return {"chat_id": sc.id} # return existing
                
    # Create new chat
    new_chat = Chat(is_group=is_group, name=name, created_by=user_id)
    session.add(new_chat)
    session.commit()
    session.refresh(new_chat)
    
    for m_id in members_ids:
        member = ChatMember(chat_id=new_chat.id, user_id=m_id, is_admin=(m_id == user_id))
        session.add(member)
    session.commit()
    
    return {"chat_id": new_chat.id}

@router.post("/api/upload")
async def upload_attachment(request: Request, file: UploadFile, type: str = Form(...), session: Session = Depends(get_session)):
    user_id = get_current_user_id(request)
    
    upload_dir = Path("uploads/chat_media")
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename
    ext = os.path.splitext(file.filename)[1]
    filename = f"{uuid.uuid4()}{ext}"
    if type == "voice" and not ext:
        filename += ".webm" # default for browser MediaRecorder
        
    filepath = upload_dir / filename
    
    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)
        
    return {
        "path": f"/uploads/chat_media/{filename}",
        "name": file.filename,
        "type": type # 'image', 'document', 'voice'
    }
