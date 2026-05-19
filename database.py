# database.py
# ===================================================================
# BACKWARD-COMPATIBLE BRIDGE — re-exports from app/database.py.
# Existing code can continue to use: from database import get_session, engine
# ===================================================================

from app.database import engine, get_session, create_db_and_tables