# device_interfacing/device_watcher.py
# =====================================================
# NexLab Device Link — CBC Folder Watcher
# =====================================================
# Standalone service that watches a folder for CBC device
# result files and writes them directly to the database.
#
# Usage:
#   python device_interfacing/device_watcher.py
#
# File format expected:
#   PID = 110003
#   1=4.5
#   2=23.3
#
# Where PID is the patient_id and 1,2,... are parameter IDs.
# =====================================================

import os
import sys
import subprocess

# Resolve the project root (parent of device_interfacing/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# =====================================================
# AUTO-DETECT VENV: If running with system Python,
# re-launch with the project's venv Python automatically.
# =====================================================
VENV_PYTHON = os.path.join(PROJECT_ROOT, "venv", "Scripts", "python.exe")

if os.path.exists(VENV_PYTHON) and sys.executable.lower() != VENV_PYTHON.lower():
    # We're NOT running inside the venv — re-launch with venv Python
    print(f"Re-launching with venv Python: {VENV_PYTHON}")
    result = subprocess.call([VENV_PYTHON, os.path.abspath(__file__)])
    sys.exit(result)

# =====================================================
# From here on, we're guaranteed to be in the venv
# =====================================================
import time
import shutil
import logging
from datetime import datetime
from pathlib import Path

# CRITICAL: Change working directory to project root BEFORE importing database.
# database.py uses a relative SQLite path (sqlite:///./lab_database.db),
# so CWD must be the project root for the DB to be found.
os.chdir(PROJECT_ROOT)
sys.path.insert(0, PROJECT_ROOT)

from sqlmodel import Session, select
from database import engine
from models import (
    Patient, PatientVisit, Order, TestDefinition, TestParameter,
    Result, ResultDetail, AuditLog, ActivityLog
)

# =====================================================
# CONFIGURATION — Edit these to match your environment
# =====================================================
# Watch folder: where the CBC device drops .txt files
WATCH_FOLDER = r"C:\Users\aliss\Desktop\lab_system\device_interfacing\CBC"

# How often to check for new files (seconds) — used in polling mode
POLL_INTERVAL = 3

# System user ID for audit trail (admin = 1)
SYSTEM_USER_ID = 1
SYSTEM_USERNAME = "CBC_Device"

# Log file
LOG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "device_interfacing.log"
)

# =====================================================
# LOGGING SETUP
# =====================================================
logger = logging.getLogger("NexLabDeviceLink")
logger.setLevel(logging.INFO)

# File handler
file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
))
logger.addHandler(file_handler)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
))
logger.addHandler(console_handler)


# =====================================================
# FILE PARSER
# =====================================================
def parse_result_file(filepath: str) -> dict:
    """
    Parse a CBC result text file.
    
    Expected format:
        PID = 110003
        1=4.5
        2=23.3
    
    Returns:
        {
            "patient_id": "110003",
            "results": {1: "4.5", 2: "23.3"}
        }
    
    Raises ValueError if format is invalid.
    """
    patient_id = None
    results = {}

    with open(filepath, "r", encoding="utf-8-sig") as f:
        for line_num, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue

            # Parse PID line
            if line.upper().startswith("PID"):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    patient_id = parts[1].strip()
                else:
                    raise ValueError(f"Line {line_num}: Invalid PID format: '{line}'")
                continue

            # Parse parameter=value line
            if "=" in line:
                parts = line.split("=", 1)
                try:
                    param_id = int(parts[0].strip())
                    value = parts[1].strip()
                    results[param_id] = value
                except ValueError:
                    raise ValueError(f"Line {line_num}: Invalid parameter format: '{line}'")
            else:
                raise ValueError(f"Line {line_num}: Unrecognized line: '{line}'")

    if patient_id is None:
        raise ValueError("No PID line found in file")

    if not results:
        raise ValueError("No parameter results found in file")

    return {"patient_id": patient_id, "results": results}


# =====================================================
# DATABASE WRITER
# =====================================================
def write_results_to_db(patient_id: str, results: dict) -> dict:
    """
    Write parsed results to the NexLab database.
    
    Logic:
        1. Find the patient by patient_id
        2. Find their latest visit
        3. Find all orders for that visit
        4. Match parameter IDs to orders via TestParameter
        5. Upsert Result + ResultDetail rows
        6. Set order status to "resulted"
        7. Create audit log entries
    
    Args:
        patient_id: The patient's ID string (e.g., "110003")
        results: Dict of {parameter_id: value} (e.g., {1: "4.5", 2: "23.3"})
    
    Returns:
        Summary dict with counts of what was updated.
    """
    now = datetime.now()
    summary = {
        "patient_id": patient_id,
        "parameters_matched": 0,
        "orders_updated": 0,
        "parameters_skipped": [],
    }

    with Session(engine) as session:
        # Step 1: Find patient
        patient = session.exec(
            select(Patient).where(Patient.patient_id == patient_id)
        ).first()

        if not patient:
            raise ValueError(f"Patient not found: {patient_id}")

        # Step 2: Find latest visit
        visit = session.exec(
            select(PatientVisit)
            .where(PatientVisit.patient_id == patient.id)
            .order_by(PatientVisit.id.desc())
        ).first()

        if not visit:
            raise ValueError(f"No visit found for patient: {patient_id}")

        # Step 3: Find all orders for this visit (excluding no_sample)
        orders = session.exec(
            select(Order)
            .where(Order.visit_id == visit.id, Order.status != "no_sample")
        ).all()

        if not orders:
            raise ValueError(f"No orders found for patient {patient_id}, visit {visit.visit_id}")

        # Step 4: Build a map of parameter_id → order
        # This tells us which order each parameter belongs to
        param_to_order = {}
        for order in orders:
            # Skip already finalized orders
            if order.status == "double_authorized":
                continue

            test_params = session.exec(
                select(TestParameter).where(TestParameter.test_id == order.test_id)
            ).all()

            for tp in test_params:
                param_to_order[tp.parameter_id] = order

        # Step 5: Group results by order
        order_results = {}  # order_id -> list of (param_id, value)
        unmatched_params = []

        for param_id, value in results.items():
            if param_id in param_to_order:
                order = param_to_order[param_id]
                if order.id not in order_results:
                    order_results[order.id] = []
                order_results[order.id].append((param_id, value))
            else:
                unmatched_params.append(param_id)

        if unmatched_params:
            summary["parameters_skipped"] = unmatched_params
            logger.warning(
                f"  Parameters not matching any order: {unmatched_params}"
            )

        if not order_results:
            raise ValueError(
                f"None of the parameters ({list(results.keys())}) "
                f"match any order for patient {patient_id}"
            )

        # Step 6: Write results to database
        for order_id, param_values in order_results.items():
            order = session.get(Order, order_id)
            if not order:
                continue

            # Upsert parent Result
            result = session.exec(
                select(Result).where(Result.order_id == order_id)
            ).first()

            if not result:
                result = Result(
                    order_id=order_id,
                    result_value="",
                    rerun_result="",
                    flag="",
                    note="",
                    entered_by=SYSTEM_USER_ID,
                    entered_at=now,
                )
                session.add(result)
                session.flush()  # Need result.id for details

            # Upsert each ResultDetail
            for param_id, value in param_values:
                detail = session.exec(
                    select(ResultDetail).where(
                        ResultDetail.result_id == result.id,
                        ResultDetail.parameter_id == param_id,
                    )
                ).first()

                if not detail:
                    detail = ResultDetail(
                        result_id=result.id,
                        parameter_id=param_id,
                    )
                    session.add(detail)

                detail.result_value = value
                session.add(detail)
                summary["parameters_matched"] += 1

            # Update order status to "resulted" (not authorized — needs human review)
            if order.status in ("ordered", "resulted"):
                order.status = "resulted"
                session.add(order)
                summary["orders_updated"] += 1

        # Step 7: Audit log
        try:
            import json
            audit_entry = AuditLog(
                table_name="result",
                record_id=visit.id,
                action="DEVICE_IMPORT",
                user_id=SYSTEM_USER_ID,
                username=SYSTEM_USERNAME,
                old_values=None,
                new_values=json.dumps({
                    "source": "CBC_Device",
                    "patient_id": patient_id,
                    "parameters_updated": summary["parameters_matched"],
                    "orders_updated": summary["orders_updated"],
                }),
                created_at=now,
            )
            session.add(audit_entry)

            activity = ActivityLog(
                action_type="DEVICE_IMPORT",
                description=(
                    f"CBC device imported {summary['parameters_matched']} result(s) "
                    f"for patient {patient_id}"
                ),
                user_id=SYSTEM_USER_ID,
                username=SYSTEM_USERNAME,
                target_type="patient",
                target_id=patient.id,
            )
            session.add(activity)
        except Exception as e:
            logger.warning(f"  Audit log failed (non-critical): {e}")

        session.commit()

    return summary


# =====================================================
# FILE PROCESSOR
# =====================================================
def process_file(filepath: str) -> bool:
    """
    Process a single result file: parse → write to DB → move to processed/failed.
    Returns True on success, False on failure.
    """
    filename = os.path.basename(filepath)
    logger.info(f"Found new file: {filename}")

    watch_dir = os.path.dirname(filepath)
    processed_dir = os.path.join(watch_dir, "processed")
    failed_dir = os.path.join(watch_dir, "failed")
    os.makedirs(processed_dir, exist_ok=True)
    os.makedirs(failed_dir, exist_ok=True)

    try:
        # Parse the file
        data = parse_result_file(filepath)
        logger.info(
            f"Processing results for Patient ID: {data['patient_id']} "
            f"({len(data['results'])} parameters)"
        )

        # Write to database
        summary = write_results_to_db(data["patient_id"], data["results"])
        logger.info(
            f"✅ Successfully updated results for Patient {data['patient_id']} — "
            f"{summary['parameters_matched']} params, "
            f"{summary['orders_updated']} orders updated"
        )

        # Move to processed folder (add timestamp to avoid name collisions)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_name = f"{timestamp}_{filename}"
        dest_path = os.path.join(processed_dir, dest_name)
        shutil.move(filepath, dest_path)
        logger.info(f"Moved {filename} → processed/{dest_name}")

        return True

    except ValueError as e:
        # Known error (bad format, missing patient, etc.)
        logger.error(f"❌ Failed to process {filename}: {e}")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_name = f"{timestamp}_{filename}"
        dest_path = os.path.join(failed_dir, dest_name)
        shutil.move(filepath, dest_path)
        logger.info(f"Moved {filename} → failed/{dest_name}")
        return False

    except Exception as e:
        # Unexpected error
        logger.error(f"❌ Unexpected error processing {filename}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_name = f"{timestamp}_{filename}"
        dest_path = os.path.join(failed_dir, dest_name)
        try:
            shutil.move(filepath, dest_path)
            logger.info(f"Moved {filename} → failed/{dest_name}")
        except Exception:
            pass
        return False


# =====================================================
# STARTUP — Process any existing files first
# =====================================================
def process_existing_files(watch_folder: str):
    """Process any .txt files already in the watch folder on startup."""
    existing = sorted(Path(watch_folder).glob("*.txt"))
    if existing:
        logger.info(f"Found {len(existing)} existing file(s) to process")
        for fp in existing:
            process_file(str(fp))


# =====================================================
# WATCHER — Two modes: watchdog (preferred) or polling
# =====================================================
def start_watchdog_watcher(watch_folder: str):
    """Use the watchdog library for efficient file system monitoring."""
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    class CBCFileHandler(FileSystemEventHandler):
        def on_created(self, event):
            if event.is_directory:
                return
            if event.src_path.lower().endswith(".txt"):
                # Small delay to ensure the file is fully written
                time.sleep(0.5)
                process_file(event.src_path)

    observer = Observer()
    observer.schedule(CBCFileHandler(), watch_folder, recursive=False)
    observer.start()
    logger.info("Watching with watchdog (real-time file detection)")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        logger.info("Service stopped by user")
    observer.join()


def start_polling_watcher(watch_folder: str):
    """Fallback: poll the folder every POLL_INTERVAL seconds."""
    logger.warning(
        "Watchdog library not found. Falling back to polling mode "
        f"(every {POLL_INTERVAL} seconds)."
    )
    logger.info("Tip: Run 'pip install watchdog' for better performance.")

    known_files = set()
    # Initialize with current files (already processed at startup)
    for fp in Path(watch_folder).glob("*.txt"):
        known_files.add(str(fp))

    try:
        while True:
            time.sleep(POLL_INTERVAL)
            current_files = set(str(fp) for fp in Path(watch_folder).glob("*.txt"))
            new_files = current_files - known_files

            for filepath in sorted(new_files):
                # Small delay to ensure the file is fully written
                time.sleep(0.3)
                process_file(filepath)

            known_files = current_files
    except KeyboardInterrupt:
        logger.info("Service stopped by user")


# =====================================================
# MAIN ENTRY POINT
# =====================================================
def main():
    print()
    print("=" * 55)
    print("   NexLab Device Link — CBC Folder Watcher")
    print("=" * 55)
    print()

    # Ensure watch folder exists
    os.makedirs(WATCH_FOLDER, exist_ok=True)

    logger.info("NexLab Device Link Service Started")
    logger.info(f"Watching folder: {WATCH_FOLDER}")

    # Process any files already waiting
    process_existing_files(WATCH_FOLDER)

    # Start watching for new files
    try:
        start_watchdog_watcher(WATCH_FOLDER)
    except ImportError:
        start_polling_watcher(WATCH_FOLDER)


if __name__ == "__main__":
    main()
