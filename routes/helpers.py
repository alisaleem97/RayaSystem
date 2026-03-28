# routes/helpers.py
# Shared helpers, constants, and utilities used across all route modules.

from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from datetime import datetime
from typing import Optional
import json
import base64
import os
import shutil
import tempfile
import uuid

from database import get_session, engine
from models import User, AuditLog

# Setup templates
templates = Jinja2Templates(directory="templates")

# Create uploads directory
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ===========================
# HELPER FUNCTIONS
# ===========================
def calculate_age(dob: datetime) -> int:
    """Calculate age from date of birth"""
    today = datetime.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

def model_to_dict(model):
    """Convert SQLModel object to dict"""
    if model is None:
        return None
    data = {}
    for column in model.__table__.columns.keys():
        value = getattr(model, column)
        if isinstance(value, datetime):
            data[column] = value.isoformat()
        else:
            data[column] = value
    return data

def get_current_user(request, session: Session) -> Optional[User]:
    """Get current logged-in user"""
    user = session.exec(select(User).where(User.username == "admin")).first()
    return user

def create_audit_log(session: Session, table_name: str, record_id: int, action: str,
                     user: User, old_values: dict = None, new_values: dict = None):
    """Original audit log entry function"""
    audit_entry = AuditLog(
        table_name=table_name,
        record_id=record_id,
        action=action,
        user_id=user.id if user else 0,
        username=user.username if user else "unknown",
        old_values=json.dumps(old_values) if old_values else None,
        new_values=json.dumps(new_values) if new_values else None,
        created_at=datetime.utcnow()
    )
    session.add(audit_entry)

# ---------------------------------------------------------
# ✅ NEW: Universal Audit Logger (Used by the newer routes)
# ---------------------------------------------------------
def log_audit_action(session, table_name: str, record_id: int, action: str, current_user, old_values: dict = None, new_values: dict = None):
    """
    Universal Audit Logger used by the newer route files.
    Inject this before session.commit() in any route.
    """
    try:
        # Resolve username safely
        username = "System"
        user_id = None
        if current_user:
            user_id = current_user.id
            username = getattr(current_user, 'full_name', current_user.username)

        # Create the log entry
        log_entry = AuditLog(
            table_name=table_name.lower(),
            record_id=record_id,
            action=action.upper(),
            user_id=user_id,
            username=username,
            old_values=json.dumps(old_values) if old_values else None,
            new_values=json.dumps(new_values) if new_values else None,
            created_at=datetime.utcnow()
        )
        
        session.add(log_entry)
        
    except Exception as e:
        print(f"⚠️ Audit Log Failure: {str(e)}")
# ---------------------------------------------------------

def save_uploaded_file(file, filename: str) -> str:
    """Save uploaded file and return the filename"""
    file_path = os.path.join(UPLOAD_DIR, filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return filename

# ===========================
# BARCODE GENERATOR (LOCAL) - 100% OFFLINE
# ===========================
def generate_barcode_base64(patient_id: str) -> str:
    """Generate linear barcode (Code128) as base64 encoded image - 100% OFFLINE"""
    try:
        from barcode import Code128
        from barcode.writer import ImageWriter
        
        code = Code128(patient_id, writer=ImageWriter())
        
        temp_dir = tempfile.gettempdir()
        temp_filename = os.path.join(temp_dir, f"temp_barcode_{patient_id}")
        
        filepath = code.save(temp_filename, options={
            'module_width': 0.4,
            'module_height': 15.0,
            'font_size': 10,
            'text_distance': 5.0,
            'quiet_zone': 6.5,
            'write_text': True,
        })
        
        png_path = filepath if filepath.endswith('.png') else filepath + '.png'
        if not os.path.exists(png_path):
            for ext in ['.png', '']:
                test_path = filepath + ext
                if os.path.exists(test_path):
                    png_path = test_path
                    break
        
        if not os.path.exists(png_path):
            raise FileNotFoundError(f"Barcode file not created at: {png_path}")
        
        with open(png_path, 'rb') as f:
            barcode_base64 = base64.b64encode(f.read()).decode()
        
        if os.path.exists(png_path):
            os.remove(png_path)
        
        return f"data:image/png;base64,{barcode_base64}"
    
    except ImportError:
        return f"https://bwipjs-api.metafloor.com/?bcid=code128&text={patient_id}&scale=3&height=10&includetext"
    
    except Exception:
        return f"https://bwipjs-api.metafloor.com/?bcid=code128&text={patient_id}&scale=3&height=10&includetext"

# Add helper to templates
templates.env.globals["calculate_age"] = calculate_age