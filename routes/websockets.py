from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import Dict, List, Any
import json
import datetime
from sqlmodel import Session, select
from database import get_session
from models import User, Chat, ChatMember, Message, MessageReceipt

router = APIRouter(prefix="/ws", tags=["WebSockets"])

# Simple in-memory connection manager
class ConnectionManager:
    def __init__(self):
        # Maps user_id to a list of active websocket connections (user can have multiple tabs)
        self.active_connections: Dict[int, List[WebSocket]] = {}
        # Maps user_id to active call info {target_id, start_time, call_type}
        self.active_calls: Dict[int, Dict[str, Any]] = {}
        
    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        
    def disconnect(self, user_id: int, websocket: WebSocket):
        if user_id in self.active_connections:
            self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                
    async def send_personal_message(self, message: str, user_id: int):
        if user_id in self.active_connections:
            for connection in self.active_connections[user_id]:
                await connection.send_text(message)
                
    async def broadcast_to_users(self, message: str, user_ids: List[int]):
        for user_id in user_ids:
            if user_id in self.active_connections:
                for connection in self.active_connections[user_id]:
                    await connection.send_text(message)

manager = ConnectionManager()

# This is a public websocket endpoint, so client should pass some secure token 
# For simplicity, we assume client passes user_id in path and validates session cookie if needed.
# Since FastAPI websocket dependencies can be tricky, we handle auth via the first message or query param.

@router.websocket("/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    # In a production app, validate user_id using the session cookie or token from headers.
    await manager.connect(user_id, websocket)
    
    # Update user status to online
    from database import engine
    with Session(engine) as session:
        user = session.get(User, user_id)
        if user:
            user.is_online = True
            session.add(user)
            session.commit()
            
            # Notify everyone that this user is online
            await manager.broadcast_to_users(
                json.dumps({"type": "status", "user_id": user_id, "is_online": True, "last_seen": None}),
                list(manager.active_connections.keys())
            )
            
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            
            # Handle different event types
            event_type = payload.get("type")
            
            with Session(engine) as session:
                
                if event_type == "message":
                    chat_id = payload.get("chat_id")
                    text = payload.get("text")
                    attachment = payload.get("attachment")
                    voice = payload.get("voice")
                    reply_to = payload.get("reply_to_id")
                    
                    # Create message
                    new_msg = Message(
                        chat_id=chat_id,
                        sender_id=user_id,
                        text=text,
                        reply_to_id=reply_to,
                        created_at=datetime.datetime.now()
                    )
                    
                    if attachment:
                        new_msg.attachment_path = attachment.get("path")
                        new_msg.attachment_name = attachment.get("name")
                        new_msg.attachment_type = attachment.get("type")
                        
                    if voice:
                        new_msg.voice_note_path = voice.get("path")
                        new_msg.voice_note_duration = voice.get("duration")
                        
                    session.add(new_msg)
                    session.commit()
                    session.refresh(new_msg)
                    
                    # Get members of this chat to broadcast
                    members = session.exec(select(ChatMember).where(ChatMember.chat_id == chat_id)).all()
                    member_ids = [m.user_id for m in members]
                    
                    # Create receipts
                    for m_id in member_ids:
                        if m_id != user_id:
                            status = "delivered" if m_id in manager.active_connections else "sent"
                            receipt = MessageReceipt(
                                message_id=new_msg.id,
                                user_id=m_id,
                                chat_id=chat_id,
                                status=status
                            )
                            session.add(receipt)
                    session.commit()
                    
                    # Broadcast
                    await manager.broadcast_to_users(
                        json.dumps({
                            "type": "new_message",
                            "chat_id": chat_id,
                            "message": {
                                "id": new_msg.id,
                                "sender_id": user_id,
                                "text": text,
                                "attachment_path": getattr(new_msg, 'attachment_path', None),
                                "attachment_name": getattr(new_msg, 'attachment_name', None),
                                "attachment_type": getattr(new_msg, 'attachment_type', None),
                                "voice_note_path": getattr(new_msg, 'voice_note_path', None),
                                "voice_note_duration": getattr(new_msg, 'voice_note_duration', None),
                                "created_at": new_msg.created_at.isoformat(),
                                "status": "delivered"
                            }
                        }),
                        member_ids
                    )
                    
                elif event_type == "read":
                    chat_id = payload.get("chat_id")
                    message_ids = payload.get("message_ids", [])
                    
                    if message_ids:
                        receipts = session.exec(select(MessageReceipt).where(
                            MessageReceipt.message_id.in_(message_ids),
                            MessageReceipt.user_id == user_id
                        )).all()
                        for r in receipts:
                            r.status = "read"
                            r.updated_at = datetime.datetime.now()
                            session.add(r)
                        session.commit()
                        
                        # Find who sent these to notify them
                        for msg_id in message_ids:
                            m = session.get(Message, msg_id)
                            if m and m.sender_id:
                                await manager.send_personal_message(
                                    json.dumps({
                                        "type": "receipt",
                                        "chat_id": chat_id,
                                        "message_id": msg_id,
                                        "status": "read"
                                    }),
                                    m.sender_id
                                )
                                
                elif event_type == "typing":
                    chat_id = payload.get("chat_id")
                    members = session.exec(select(ChatMember).where(ChatMember.chat_id == chat_id)).all()
                    member_ids = [m.user_id for m in members if m.user_id != user_id]
                    await manager.broadcast_to_users(
                        json.dumps({
                            "type": "typing",
                            "chat_id": chat_id,
                            "user_id": user_id
                        }),
                        member_ids
                    )
                    
                # WebRTC Signaling
                elif event_type in ["offer", "answer", "ice-candidate", "call-end"]:
                    target_id = payload.get("target_id")
                    if target_id:
                        payload["sender_id"] = user_id
                        
                        # Handle call persistence
                        if event_type == "offer":
                            manager.active_calls[user_id] = {
                                "target_id": target_id,
                                "type": payload.get("callType", "voice"),
                                "start_time": None,
                                "initiator_id": user_id
                            }
                            # Also track for target so they can hang up/decline
                            manager.active_calls[target_id] = {
                                "target_id": user_id,
                                "type": payload.get("callType", "voice"),
                                "start_time": None,
                                "initiator_id": user_id
                            }
                        elif event_type == "answer":
                            # Mark call as started for both
                            start_time = datetime.datetime.now()
                            if user_id in manager.active_calls:
                                manager.active_calls[user_id]["start_time"] = start_time
                            if target_id in manager.active_calls:
                                manager.active_calls[target_id]["start_time"] = start_time
                                
                        elif event_type == "call-end":
                            # Call finished, save log
                            call_info = manager.active_calls.get(user_id)
                            if not call_info: # Fallback
                                call_info = manager.active_calls.get(target_id)
                                
                            if call_info:
                                status = "answered" if call_info.get("start_time") else "missed"
                                duration = 0
                                if call_info.get("start_time"):
                                    duration = int((datetime.datetime.now() - call_info["start_time"]).total_seconds())
                                
                                initiator_id = call_info.get("initiator_id", user_id)
                                
                                # Find common chat robustly
                                chats_a = session.exec(select(ChatMember.chat_id).where(ChatMember.user_id == user_id)).all()
                                chats_b = session.exec(select(ChatMember.chat_id).where(ChatMember.user_id == target_id)).all()
                                common_ids = list(set(chats_a) & set(chats_b))
                                
                                chat = None
                                if common_ids:
                                    chat = session.exec(select(Chat).where(
                                        Chat.id.in_(common_ids), 
                                        Chat.is_group == False
                                    )).first()
                                
                                if chat:
                                    call_msg = Message(
                                        chat_id=chat.id,
                                        sender_id=initiator_id, # Caller is always the sender for logs
                                        text=f"{call_info.get('type','voice').capitalize()} Call",
                                        is_call=True,
                                        call_type=call_info.get("type", "voice"),
                                        call_status=status,
                                        call_duration=duration,
                                        created_at=datetime.datetime.now()
                                    )
                                    session.add(call_msg)
                                    session.commit()
                                    session.refresh(call_msg)
                                    
                                    # Broadcast call message
                                    members = session.exec(select(ChatMember).where(ChatMember.chat_id == chat.id)).all()
                                    member_ids = [m.user_id for m in members]
                                    await manager.broadcast_to_users(
                                        json.dumps({
                                            "type": "new_message",
                                            "chat_id": chat.id,
                                            "message": {
                                                "id": call_msg.id,
                                                "sender_id": call_msg.sender_id,
                                                "text": call_msg.text,
                                                "is_call": True,
                                                "call_status": status,
                                                "call_duration": duration,
                                                "created_at": call_msg.created_at.isoformat(),
                                                "status": "delivered"
                                            }
                                        }),
                                        member_ids
                                    )
                                
                                # Cleanup for BOTH
                                manager.active_calls.pop(user_id, None)
                                manager.active_calls.pop(target_id, None)
                                # Ensure other side's key is also removed if it exists
                                manager.active_calls.pop(call_info.get("target_id"), None)

                        await manager.send_personal_message(
                            json.dumps(payload),
                            target_id
                        )

    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
        # Update user status to offline
        from database import engine
        with Session(engine) as session:
            user = session.get(User, user_id)
            if user:
                user.is_online = False
                user.last_seen = datetime.datetime.now()
                session.add(user)
                session.commit()
                
                # Notify everyone
                # (Ignore awaits in sync block, but wait, the inner engine loop isn't strict sync outside if we use safe session handling)
                pass 
                
        # Send offline status update
        await manager.broadcast_to_users(
            json.dumps({"type": "status", "user_id": user_id, "is_online": False, "last_seen": datetime.datetime.now().isoformat()}),
            list(manager.active_connections.keys())
        )
