"""
NexLab LIS — Clean Patients Tool
=================================
Deletes ALL patients and their related data from the database.

Affected tables (deleted in order):
  1. ResultDetail  (child of Result)
  2. Result        (child of Order)
  3. Payment       (child of PatientVisit)
  4. Attachment    (child of Patient)
  5. Order         (child of Patient / PatientVisit)
  6. PatientVisit  (child of Patient)
  7. Patient

NOT affected:
  - Users, Departments, Tests, Devices, Parameters, Packages, Partners
  - Provinces, Regions, LabInfo, PrintTemplates
  - Formulas, Supplies, Inventory, CalControl
  - AuditLog, ActivityLog, DeletedRecord (historical records preserved)
  - Chat, Messages, Expenses

Usage:
  python tools/clean_patients.py
"""

import sys
import os

# Ensure project root is in the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session, select, func
from app.database import engine
from app.models import (
    Patient, PatientVisit, Order, Result, ResultDetail,
    Payment, Attachment,
)


def count_records(session):
    """Count all patient-related records."""
    counts = {
        "Patient": session.exec(select(func.count(Patient.id))).one(),
        "PatientVisit": session.exec(select(func.count(PatientVisit.id))).one(),
        "Order": session.exec(select(func.count(Order.id))).one(),
        "Result": session.exec(select(func.count(Result.id))).one(),
        "ResultDetail": session.exec(select(func.count(ResultDetail.id))).one(),
        "Payment": session.exec(select(func.count(Payment.id))).one(),
        "Attachment": session.exec(select(func.count(Attachment.id))).one(),
    }
    return counts


def clean_patients():
    """Delete all patient data in the correct FK order."""

    with Session(engine) as session:
        # --- Show what will be deleted ---
        counts = count_records(session)
        total = sum(counts.values())

        if total == 0:
            print("\n  No patient data found. The system is already clean.")
            return

        print("\n  ============================================")
        print("    NexLab LIS - Clean Patients Tool")
        print("  ============================================")
        print()
        print("  The following records will be PERMANENTLY deleted:\n")
        for table, count in counts.items():
            print(f"    {table:<20} {count:>6} records")
        print(f"    {'':─<20} {'':─>6}─────────")
        print(f"    {'TOTAL':<20} {total:>6} records")
        print()

        # --- Safety confirmation ---
        print("  WARNING: This action is IRREVERSIBLE!")
        print("  Tip: Run 'python tools/backup_db.py' first to create a backup.\n")

        confirm = input("  Type 'DELETE ALL PATIENTS' to confirm: ").strip()
        if confirm != "DELETE ALL PATIENTS":
            print("\n  Cancelled. No data was deleted.")
            return

        # --- Delete in FK order (children first) ---
        print("\n  Deleting records...")

        # 1. ResultDetail (depends on Result)
        deleted = session.exec(select(ResultDetail)).all()
        for r in deleted:
            session.delete(r)
        print(f"    ResultDetail:  {len(deleted)} deleted")

        # 2. Result (depends on Order)
        deleted = session.exec(select(Result)).all()
        for r in deleted:
            session.delete(r)
        print(f"    Result:        {len(deleted)} deleted")

        # 3. Payment (depends on PatientVisit / Patient)
        deleted = session.exec(select(Payment)).all()
        for r in deleted:
            session.delete(r)
        print(f"    Payment:       {len(deleted)} deleted")

        # 4. Attachment (depends on Patient)
        deleted = session.exec(select(Attachment)).all()
        for r in deleted:
            session.delete(r)
        print(f"    Attachment:    {len(deleted)} deleted")

        # 5. Order (depends on Patient / PatientVisit)
        deleted = session.exec(select(Order)).all()
        for r in deleted:
            session.delete(r)
        print(f"    Order:         {len(deleted)} deleted")

        # 6. PatientVisit (depends on Patient)
        deleted = session.exec(select(PatientVisit)).all()
        for r in deleted:
            session.delete(r)
        print(f"    PatientVisit:  {len(deleted)} deleted")

        # 7. Patient
        deleted = session.exec(select(Patient)).all()
        for r in deleted:
            session.delete(r)
        print(f"    Patient:       {len(deleted)} deleted")

        # --- Commit ---
        session.commit()
        print("\n  All patient data has been deleted successfully.")

        # --- Verify ---
        remaining = count_records(session)
        total_remaining = sum(remaining.values())
        if total_remaining == 0:
            print("  Verification: OK - all patient tables are empty.")
        else:
            print(f"  WARNING: {total_remaining} records still remain. Check for orphaned data.")

        print()


if __name__ == "__main__":
    clean_patients()
