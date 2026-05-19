# routes/helpers.py
# ===================================================================
# BACKWARD-COMPATIBLE BRIDGE — re-exports from new SoC locations.
# All route files import from here; this file delegates to app/services/.
# ===================================================================

# Config
from app.config import SECRET_KEY, pwd_context

# Auth
from app.services.auth_service import get_current_user, login_required

# Permissions
from app.services.permission_service import require_permission

# Audit
from app.services.audit_service import (
    log_audit_action, create_audit_log,
    archive_deleted_record, log_activity_action
)

# Patient utilities
from app.services.patient_service import (
    calculate_age, age_to_days, model_to_dict,
    build_patient_visit_data
)

# Barcode
from app.services.barcode_service import generate_barcode_base64

# Templates
from app.routes.template_helpers import templates

# Upload directory
import os
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# File upload helper (used by several routes)
import shutil
import uuid

def save_uploaded_file(file, filename: str) -> str:
    """Save uploaded file and return the filename."""
    file_path = os.path.join(UPLOAD_DIR, filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return filename

# Timezone helper
from datetime import datetime
def local_now() -> datetime:
    """Return current local datetime."""
    return datetime.now()


# ===========================
# SHARED PATIENT LIST QUERY BUILDER (used by history.py)
# ===========================
from sqlmodel import select
from app.models import Patient, PatientVisit, Order, TestDefinition

def build_patient_list_query(request, defaults_today=True):
    """Build a filtered patient query from common request query params."""
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
        query = query.where(PatientVisit.visit_date >= datetime.strptime(f"{start_date} 00:00:00", "%Y-%m-%d %H:%M:%S"))
    if end_date:
        query = query.where(PatientVisit.visit_date <= datetime.strptime(f"{end_date} 23:59:59", "%Y-%m-%d %H:%M:%S"))

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


# Register calculate_age as a Jinja template global
templates.env.globals["calculate_age"] = calculate_age