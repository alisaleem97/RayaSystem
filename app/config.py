# app/config.py
# Centralised configuration — single source of truth for all settings.

import os
import logging

# Load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    # Look for .env in project root (parent of app/)
    _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _env_path = os.path.join(_project_root, ".env")
    if os.path.exists(_env_path):
        load_dotenv(_env_path)
except ImportError:
    pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ===========================
# SECRET KEY
# ===========================
_env_secret = os.environ.get("NEXLAB_SECRET_KEY")
if _env_secret:
    SECRET_KEY = _env_secret
else:
    import uuid
    SECRET_KEY = uuid.uuid4().hex + uuid.uuid4().hex
    logging.getLogger("nexlab.security").warning(
        "NEXLAB_SECRET_KEY not set! Using auto-generated key. "
        "Sessions will NOT persist across restarts. "
        "Set NEXLAB_SECRET_KEY in .env for production use."
    )

# ===========================
# DATABASE
# ===========================
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./lab_database.db")

# If it is a relative sqlite URL, make it absolute relative to PROJECT_ROOT
if DATABASE_URL.startswith("sqlite:///"):
    db_path = DATABASE_URL[10:]
    if not (db_path.startswith("/") or db_path.startswith("\\") or (len(db_path) > 1 and db_path[1] == ":")):
        if db_path.startswith("./") or db_path.startswith(".\\"):
            db_path = db_path[2:]
        abs_db_path = os.path.abspath(os.path.join(PROJECT_ROOT, db_path))
        DATABASE_URL = f"sqlite:///{abs_db_path}"


# ===========================
# PATHS
# ===========================
TEMPLATE_DIR = os.path.join(PROJECT_ROOT, "templates")
STATIC_DIR = os.path.join(PROJECT_ROOT, "static")
UPLOAD_DIR = os.path.join(PROJECT_ROOT, "uploads")
TMP_DIR = os.path.join(PROJECT_ROOT, "tmp")
BACKUP_DIR = os.path.join(PROJECT_ROOT, "backups")

# ===========================
# SERVER
# ===========================
PORT = int(os.environ.get("PORT", 8000))

# ===========================
# PASSWORD HASHING
# ===========================
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
