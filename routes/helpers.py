# routes/helpers.py
# Shared helpers, constants, and utilities used across all route modules.

from fastapi.templating import Jinja2Templates
from fastapi import Request
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
from models import User, AuditLog, DeletedRecord, ActivityLog

# ===========================
# CENTRALIZED CONFIG
# ===========================
SECRET_KEY = os.environ.get("NEXLAB_SECRET_KEY", "nexlab-secret-key-2026")

from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Setup templates with auto-injection of current_user + permissions
_base_templates = Jinja2Templates(directory="templates")

from models import UserPermission

class AutoUserTemplates:
    """Wrapper that auto-injects current_user, has_page(), has_button() into every template."""
    def __init__(self, base):
        self.base = base
        self.env = base.env
    
    def TemplateResponse(self, name, context, **kwargs):
        request = context.get("request")
        
        # --- Resolve current_user ---
        if "current_user" not in context and request:
            try:
                from itsdangerous import URLSafeSerializer
                s = URLSafeSerializer(SECRET_KEY)
                cookie = request.cookies.get("nexlab_session")
                if cookie:
                    data = s.loads(cookie)
                    user_id = data.get("user_id")
                    if user_id:
                        with Session(engine) as sess:
                            user = sess.get(User, user_id)
                            if user:
                                sess.expunge(user)
                                context["current_user"] = user
            except Exception:
                pass
            if "current_user" not in context:
                context["current_user"] = None
        
        # --- Load permissions dict for the user ---
        current_user = context.get("current_user")
        is_admin = current_user and (current_user.role == "admin" or current_user.username == "admin")
        
        user_perms = {}  # {page_key: [btn_key, ...]}
        if current_user and not is_admin:
            try:
                with Session(engine) as sess:
                    perms = sess.exec(
                        select(UserPermission).where(UserPermission.user_id == current_user.id)
                    ).all()
                    for p in perms:
                        buttons = []
                        if p.allowed_buttons:
                            try:
                                buttons = json.loads(p.allowed_buttons)
                            except Exception:
                                buttons = []
                        user_perms[p.page_key] = buttons
            except Exception:
                pass
        
        # --- Inject permission helpers ---
        def has_page(page_key):
            """Check if user has access to a page. Admin always True."""
            if is_admin:
                return True
            return page_key in user_perms
        
        def has_button(page_key, button_key):
            """Check if user has a specific button on a page. Admin always True."""
            if is_admin:
                return True
            if page_key not in user_perms:
                return False
            return button_key in user_perms[page_key]
        
        context["has_page"] = has_page
        context["has_button"] = has_button
        context["is_admin"] = is_admin
        context["user_perms"] = user_perms
        
        return self.base.TemplateResponse(name, context, **kwargs)

templates = AutoUserTemplates(_base_templates)

# Create uploads directory
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ===========================
# HELPER FUNCTIONS
# ===========================
def calculate_age(dob: datetime) -> int:
    """Calculate age from date of birth"""
    if dob is None:
        return 0
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
    """Get current logged-in user from session cookie"""
    try:
        from itsdangerous import URLSafeSerializer
        s = URLSafeSerializer(SECRET_KEY)
        cookie = request.cookies.get("nexlab_session")
        if not cookie:
            return None
        data = s.loads(cookie)
        user_id = data.get("user_id")
        if user_id:
            return session.get(User, user_id)
    except Exception:
        pass
    return None

def login_required(request: Request, session: Session) -> Optional[User]:
    """Check if user is logged in, return user or None"""
    return get_current_user(request, session)

def require_permission(request: Request, session: Session, page_key: str, button_key: str = None) -> bool:
    """Verifies if the current user has the specified page/button permission."""
    user = get_current_user(request, session)
    if not user:
        return False
        
    # Admins always have all permissions
    if user.role == 'admin' or user.username == 'admin':
        return True
        
    # Check page permission
    perms = session.exec(
        select(UserPermission).where(
            UserPermission.user_id == user.id,
            UserPermission.page_key == page_key
        )
    ).first()
    
    if not perms:
        return False
        
    # Check specific button permission if requested
    if button_key:
        if not perms.allowed_buttons:
            return False
        try:
            buttons = json.loads(perms.allowed_buttons)
            if button_key not in buttons:
                return False
        except Exception:
            return False
            
    return True

def log_audit_action(session, table_name: str, record_id: int, action: str, current_user, old_values: dict = None, new_values: dict = None):
    """
    Universal Audit Logger — single source of truth for all audit logging.
    Safely resolves user identity and wraps in try/except to never crash the caller.
    """
    try:
        username = "System"
        user_id = None
        if current_user:
            user_id = current_user.id
            username = getattr(current_user, 'full_name', current_user.username)

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

# Backwards-compatible alias — older routes use this name
create_audit_log = log_audit_action

# ===========================
# DATA ARCHIVAL HELPER
# ===========================
def archive_deleted_record(session, source_table: str, record_id: int, record_data: dict, current_user, deleted_reason: str = None):
    """Saves a JSON snapshot of a record before soft or hard deletion."""
    try:
        user_id = current_user.id if hasattr(current_user, 'id') else 0
        archive = DeletedRecord(
            source_table=source_table,
            record_id=record_id,
            record_data=json.dumps(record_data),
            deleted_by=user_id,
            deleted_reason=deleted_reason
        )
        session.add(archive)
    except Exception as e:
        print(f"⚠️ Failed to archive deleted record: {str(e)}")

# ===========================
# ACTIVITY LOG HELPER
# ===========================
def log_activity_action(session, action_type: str, description: str, current_user, target_type: str = None, target_id: int = None):
    """Logs non-data operational events (logins, printing, etc.)."""
    try:
        user_id = current_user.id if hasattr(current_user, 'id') else None
        username = getattr(current_user, 'full_name', getattr(current_user, 'username', "System"))
        
        activity = ActivityLog(
            action_type=action_type.upper(),
            description=description,
            user_id=user_id,
            username=username,
            target_type=target_type,
            target_id=target_id
        )
        session.add(activity)
    except Exception as e:
        print(f"⚠️ Activity Log Failure: {str(e)}")

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

# ===========================
# SHARED PATIENT LIST QUERY BUILDER
# ===========================
from models import Patient, PatientVisit, Order, TestDefinition

def build_patient_list_query(request, defaults_today=True):
    """
    Build a filtered patient query from common request query params.
    Returns (query, filters_dict) where filters_dict has the parsed filter values.
    Used by: result_entry, double_auth, print_results, call_centre, patient_history.
    """
    today_str = datetime.today().strftime("%Y-%m-%d") if defaults_today else ""
    
    start_date = request.query_params.get("start_date", today_str)
    end_date = request.query_params.get("end_date", today_str)
    name = request.query_params.get("name", "")
    patient_id_q = request.query_params.get("patient_id", "")
    test_q = request.query_params.get("test", "")
    
    query = select(Patient).where(Patient.is_active == True)
    
    needs_visit_join = bool(start_date or end_date or test_q)
    if needs_visit_join:
        query = query.join(PatientVisit)
    
    if start_date:
        query = query.where(PatientVisit.visit_date >= f"{start_date} 00:00:00")
    if end_date:
        query = query.where(PatientVisit.visit_date <= f"{end_date} 23:59:59")
    
    if name:
        query = query.where(Patient.full_name.ilike(f"%{name}%"))
    if patient_id_q:
        query = query.where(Patient.patient_id.ilike(f"%{patient_id_q}%"))
    
    if test_q:
        if not needs_visit_join:
            query = query.join(PatientVisit)
        query = query.join(Order, Order.visit_id == PatientVisit.id).join(TestDefinition, Order.test_id == TestDefinition.id)
        query = query.where(
            (TestDefinition.test_name.ilike(f"%{test_q}%")) |
            (TestDefinition.test_short_name.ilike(f"%{test_q}%"))
        )
    
    query = query.distinct().order_by(Patient.created_at.desc())
    
    filters = {
        "start_date": start_date,
        "end_date": end_date,
        "name": name,
        "patient_id": patient_id_q,
        "test": test_q,
    }
    
    return query, filters

# Add helper to templates
templates.env.globals["calculate_age"] = calculate_age