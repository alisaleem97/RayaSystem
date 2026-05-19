"""Schema audit: compare model definitions vs actual database columns."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from sqlmodel import SQLModel
# Import all models to register them
from app.models import *

DB_PATH = "lab_database.db"
conn = sqlite3.connect(DB_PATH)

# 1. Get DB schema
db_schema = {}
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
for t in tables:
    cols = set(r[1] for r in conn.execute(f"PRAGMA table_info(\"{t}\")").fetchall())
    db_schema[t.lower()] = cols

# 2. Get model schema
model_schema = {}
for table_name, table_obj in SQLModel.metadata.tables.items():
    model_schema[table_name.lower()] = set(col.name for col in table_obj.columns)

# 3. Compare
print("=" * 60)
print("  NexLab Schema Audit: Models vs Database")
print("=" * 60)

issues = []

# Tables in models but not in DB
for table in sorted(model_schema.keys()):
    if table not in db_schema:
        issues.append(f"MISSING TABLE: '{table}' exists in models but NOT in database")
        print(f"\n[MISSING TABLE] {table}")
        print(f"  Columns needed: {sorted(model_schema[table])}")

# Columns comparison
for table in sorted(model_schema.keys()):
    if table in db_schema:
        model_cols = model_schema[table]
        db_cols = db_schema[table]
        
        missing_in_db = model_cols - db_cols
        extra_in_db = db_cols - model_cols
        
        if missing_in_db or extra_in_db:
            print(f"\n[MISMATCH] {table}")
            for col in sorted(missing_in_db):
                issues.append(f"MISSING COLUMN: {table}.{col}")
                print(f"  MISSING in DB: {col}")
            for col in sorted(extra_in_db):
                print(f"  EXTRA in DB (not in model): {col}")

if not issues:
    print("\n  [OK] All models match the database schema perfectly!")
else:
    print(f"\n{'=' * 60}")
    print(f"  TOTAL ISSUES: {len(issues)}")
    print(f"{'=' * 60}")

conn.close()
