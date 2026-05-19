# app/models/messaging.py
# Chat, ChatMember, Message, MessageReceipt models.

from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field


class Chat(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    is_group: bool = Field(default=False)
    name: Optional[str] = None
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_at: Optional[datetime] = None


class ChatMember(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    chat_id: int = Field(foreign_key="chat.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    joined_at: datetime = Field(default_factory=datetime.now)
    is_admin: bool = Field(default=False)
    last_read_message_id: Optional[int] = None


class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    chat_id: int = Field(foreign_key="chat.id", index=True)
    sender_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    text: Optional[str] = None
    attachment_path: Optional[str] = None
    attachment_name: Optional[str] = None
    attachment_type: Optional[str] = None
    voice_note_path: Optional[str] = None
    voice_note_duration: Optional[int] = None
    reply_to_id: Optional[int] = Field(default=None, foreign_key="message.id")
    created_at: datetime = Field(default_factory=datetime.now)
    is_deleted: bool = Field(default=False)
    is_call: bool = Field(default=False)
    call_type: Optional[str] = None
    call_status: Optional[str] = None
    call_duration: Optional[int] = None


class MessageReceipt(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    message_id: int = Field(foreign_key="message.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    chat_id: int = Field(foreign_key="chat.id", index=True)
    status: str = Field(default="delivered")
    updated_at: datetime = Field(default_factory=datetime.now)
